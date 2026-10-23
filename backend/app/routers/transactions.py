from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, CategoryKind, Transaction
from app.months import add_months, current_month, format_month, month_bounds, parse_month
from app.routers.balance_sheet import get_account
from app.routers.categories import get_category
from app.schemas import (
    IncomeStatement,
    IncomeTrendPoint,
    StatementCategory,
    TransactionIn,
    TransactionOut,
)
from app.services.budget import budget_by_category

router = APIRouter(prefix="/api", tags=["income statement"])

MONTH = Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")


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
    for key, value in body.model_dump().items():
        setattr(txn, key, value)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    db.delete(get_transaction(db, transaction_id))
    db.commit()


# ---------- Income statement ----------

@router.get("/income-statement", response_model=IncomeStatement)
def income_statement(month: str = MONTH, db: Session = Depends(get_db)):
    m = parse_month(month)
    start, end = month_bounds(m)
    rows = db.execute(
        select(
            Category.id,
            Category.name,
            Category.kind,
            Transaction.is_unexpected,
            func.sum(Transaction.amount),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(Transaction.date >= start, Transaction.date < end)
        .group_by(Category.id, Category.name, Category.kind, Transaction.is_unexpected)
    ).all()

    budget = budget_by_category(db)
    lines: dict[int, StatementCategory] = {
        cid: StatementCategory(
            category_id=cid, name=name, kind=kind, actual=0, unexpected=0, budgeted=budgeted
        )
        for cid, (name, kind, budgeted) in budget.items()
    }
    for cid, name, kind, unexpected, total in rows:
        line = lines.setdefault(
            cid,
            StatementCategory(category_id=cid, name=name, kind=kind, actual=0, unexpected=0, budgeted=0),
        )
        line.actual += total
        if unexpected:
            line.unexpected += total

    def total(kind: CategoryKind, field: str) -> Decimal:
        return sum((getattr(l, field) for l in lines.values() if l.kind == kind), Decimal(0))

    income = total(CategoryKind.income, "actual")
    expenses = total(CategoryKind.expense, "actual")
    return IncomeStatement(
        month=format_month(m),
        total_income=income,
        total_expenses=expenses,
        net=income - expenses,
        unexpected_income=total(CategoryKind.income, "unexpected"),
        unexpected_expenses=total(CategoryKind.expense, "unexpected"),
        budgeted_income=total(CategoryKind.income, "budgeted"),
        budgeted_expenses=total(CategoryKind.expense, "budgeted"),
        categories=sorted(lines.values(), key=lambda l: (l.kind.value, -l.actual, l.name)),
    )


def monthly_totals(db: Session, start: date, end: date) -> dict[date, dict[str, Decimal]]:
    month_col = func.date_trunc("month", Transaction.date).label("month")
    rows = db.execute(
        select(month_col, Category.kind, Transaction.is_unexpected, func.sum(Transaction.amount))
        .join(Category, Category.id == Transaction.category_id)
        .where(Transaction.date >= start, Transaction.date < end)
        .group_by(month_col, Category.kind, Transaction.is_unexpected)
    ).all()
    totals: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for month, kind, unexpected, amount in rows:
        bucket = totals[month.date()]
        key = "income" if kind == CategoryKind.income else "expenses"
        bucket[key] += amount
        if unexpected:
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
