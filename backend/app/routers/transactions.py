from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BudgetItem, Category, CategoryKind, MonthSetting, Transaction
from app.months import add_months, current_month, format_month, month_bounds, parse_month
from app.routers.balance_sheet import get_account
from app.routers.categories import get_category
from app.schemas import (
    IncomeStatement,
    IncomeTrendPoint,
    MonthNotesIn,
    StatementCategory,
    TotalsFromIn,
    TransactionIn,
    TransactionOut,
)
from app.services.budget import budget_by_category
from app.services.statement_import import card_category, remember

router = APIRouter(prefix="/api", tags=["income statement"])

MONTH = Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
STATEMENT = "statement"  # Transaction.source for rows imported from a bank statement


def get_transaction(db: Session, transaction_id: int) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(404, "Transaction not found")
    return txn


def _validate_refs(db: Session, body: TransactionIn) -> None:
    get_category(db, body.category_id)
    if body.account_id is not None:
        get_account(db, body.account_id)


# ---------- Transactions ----------

@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(month: str = MONTH, db: Session = Depends(get_db)):
    start, end = month_bounds(parse_month(month))
    return db.scalars(
        select(Transaction)
        .where(Transaction.date >= start, Transaction.date < end)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    ).unique().all()


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, db: Session = Depends(get_db)):
    _validate_refs(db, body)
    txn = Transaction(**body.model_dump())
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.put("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: int, body: TransactionIn, db: Session = Depends(get_db)):
    txn = get_transaction(db, transaction_id)
    _validate_refs(db, body)
    recategorized = txn.source == STATEMENT and body.category_id != txn.category_id
    for key, value in body.model_dump().items():
        setattr(txn, key, value)
    if recategorized:
        # Learn the correction so the next statement suggests it.
        kind = get_category(db, body.category_id).kind
        remember(db, txn.description, "in" if kind == CategoryKind.income else "out", body.category_id, False)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    db.delete(get_transaction(db, transaction_id))
    db.commit()


# ---------- Income statement ----------

def month_sources(db: Session, start: date, end: date) -> dict[date, tuple[str, bool]]:
    """month -> (totals_from, has_statement) for months with statement rows or a saved choice.

    A month with imported statement rows totals them by default, and manual entries then only explain
    the differences from the budget. The choice can be flipped per month. Without statement rows the
    manual entries are the totals, whatever was saved."""
    month_col = func.date_trunc("month", Transaction.date)
    with_statement = {
        m.date()
        for m in db.scalars(
            select(month_col)
            .where(Transaction.source == STATEMENT, Transaction.date >= start, Transaction.date < end)
            .group_by(month_col)
        )
    }
    saved = {
        s.month: s.totals_from
        for s in db.scalars(select(MonthSetting).where(MonthSetting.month >= start, MonthSetting.month < end))
    }
    return {
        m: ((saved.get(m) or STATEMENT) if m in with_statement else "manual", m in with_statement)
        for m in with_statement | set(saved)
    }


@router.put("/income-statement/totals-from", status_code=204)
def set_totals_from(body: TotalsFromIn, db: Session = Depends(get_db)):
    m = parse_month(body.month)
    setting = db.get(MonthSetting, m)
    if setting is None:
        db.add(MonthSetting(month=m, totals_from=body.totals_from))
    else:
        setting.totals_from = body.totals_from
    db.commit()


@router.put("/income-statement/notes", status_code=204)
def set_notes(body: MonthNotesIn, db: Session = Depends(get_db)):
    m = parse_month(body.month)
    notes = (body.notes or "").strip() or None
    setting = db.get(MonthSetting, m)
    if setting is None:
        if notes is not None:
            db.add(MonthSetting(month=m, notes=notes))
    elif notes is None and setting.totals_from is None:
        db.delete(setting)  # nothing left to keep for this month
    else:
        setting.notes = notes
    db.commit()


@router.get("/income-statement", response_model=IncomeStatement)
def income_statement(month: str = MONTH, db: Session = Depends(get_db)):
    m = parse_month(month)
    start, end = month_bounds(m)
    totals_from, has_statement = month_sources(db, start, end).get(m, ("manual", False))
    setting = db.get(MonthSetting, m)
    use_statement = totals_from == STATEMENT
    from_statement = Transaction.source == STATEMENT
    rows = db.execute(
        select(
            Category.id,
            Category.name,
            Category.kind,
            Category.color,
            from_statement,
            Transaction.is_unexpected,
            func.sum(Transaction.amount),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(Transaction.date >= start, Transaction.date < end)
        .group_by(Category.id, Category.name, Category.kind, Category.color, from_statement, Transaction.is_unexpected)
    ).all()

    # A statement sees card-paid budget items only inside card payments, so compare them as a group.
    card = card_category(db) if use_statement else None
    budget = budget_by_category(db, card)
    lines: dict[int, StatementCategory] = {
        cid: StatementCategory(
            category_id=cid, name=name, kind=kind, color=color, actual=0, unexpected=0, budgeted=budgeted
        )
        for cid, (name, kind, color, budgeted) in budget.items()
    }
    if card is not None and card.id in lines:
        lines[card.id].card_items = list(
            db.scalars(select(BudgetItem.name).where(BudgetItem.paid_by_card).order_by(BudgetItem.name))
        )

    unexpected = {CategoryKind.income: Decimal(0), CategoryKind.expense: Decimal(0)}
    for cid, name, kind, color, is_statement, is_unexpected, total in rows:
        counted = is_statement == use_statement
        # Manual unexpected items are listed even when they don't count: in a statement month they
        # explain the differences from the budget.
        if is_unexpected and (counted or not is_statement):
            unexpected[kind] += total
        if not counted:
            continue
        line = lines.setdefault(
            cid,
            StatementCategory(
                category_id=cid, name=name, kind=kind, color=color, actual=0, unexpected=0, budgeted=0
            ),
        )
        line.actual += total
        if is_unexpected:
            line.unexpected += total

    def total(kind: CategoryKind, field: str) -> Decimal:
        return sum((getattr(l, field) for l in lines.values() if l.kind == kind), Decimal(0))

    income = total(CategoryKind.income, "actual")
    expenses = total(CategoryKind.expense, "actual")
    return IncomeStatement(
        month=format_month(m),
        totals_from=totals_from,
        has_statement=has_statement,
        notes=setting.notes if setting else None,
        total_income=income,
        total_expenses=expenses,
        net=income - expenses,
        unexpected_income=unexpected[CategoryKind.income],
        unexpected_expenses=unexpected[CategoryKind.expense],
        budgeted_income=total(CategoryKind.income, "budgeted"),
        budgeted_expenses=total(CategoryKind.expense, "budgeted"),
        categories=sorted(lines.values(), key=lambda l: (l.kind.value, -l.actual, l.name)),
    )


def monthly_totals(db: Session, start: date, end: date) -> dict[date, dict[str, Decimal]]:
    """Counted income and expenses per month, following each month's totals source."""
    month_col = func.date_trunc("month", Transaction.date).label("month")
    from_statement = (Transaction.source == STATEMENT).label("from_statement")
    rows = db.execute(
        select(month_col, from_statement, Category.kind, Transaction.is_unexpected, func.sum(Transaction.amount))
        .join(Category, Category.id == Transaction.category_id)
        .where(Transaction.date >= start, Transaction.date < end)
        .group_by(month_col, from_statement, Category.kind, Transaction.is_unexpected)
    ).all()
    sources = month_sources(db, start, end)
    totals: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for month, is_statement, kind, unexpected, amount in rows:
        use_statement = sources.get(month.date(), ("manual", False))[0] == STATEMENT
        counted = is_statement == use_statement
        bucket = totals[month.date()]
        key = "income" if kind == CategoryKind.income else "expenses"
        if counted:
            bucket[key] += amount
        if unexpected and (counted or not is_statement):
            bucket[f"unexpected_{key}"] += amount
    return totals


@router.get("/income-statement/trend", response_model=list[IncomeTrendPoint])
def income_trend(months: int = Query(12, ge=1, le=120), db: Session = Depends(get_db)):
    end = add_months(current_month(), 1)
    start = add_months(end, -months)
    totals = monthly_totals(db, start, end)
    points = []
    for i in range(months):
        m = add_months(start, i)
        t = totals.get(m, {})
        income, expenses = t.get("income", Decimal(0)), t.get("expenses", Decimal(0))
        points.append(
            IncomeTrendPoint(
                month=format_month(m),
                income=income,
                expenses=expenses,
                net=income - expenses,
                unexpected_income=t.get("unexpected_income", Decimal(0)),
                unexpected_expenses=t.get("unexpected_expenses", Decimal(0)),
            )
        )
    return points
