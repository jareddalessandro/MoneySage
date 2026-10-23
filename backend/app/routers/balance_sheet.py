from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, AccountKind, BalanceSnapshot
from app.months import add_months, current_month, format_month, parse_month
from app.schemas import (
    AccountIn,
    AccountOut,
    AccountUpdate,
    BalanceRow,
    BalanceSheet,
    BalanceUpdate,
    NetWorthPoint,
)
from app.services.portfolio import sync_account_snapshots

router = APIRouter(prefix="/api", tags=["balance sheet"])

MONTH = Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")


def get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    return account


def _commit_unique(db: Session, name: str | None) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"An account named '{name}' already exists")


# ---------- Accounts ----------

@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(include_archived: bool = False, db: Session = Depends(get_db)):
    query = select(Account).order_by(Account.kind, Account.name)
    if not include_archived:
        query = query.where(Account.is_archived.is_(False))
    return db.scalars(query).all()


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, db: Session = Depends(get_db)):
    account = Account(**body.model_dump())
    db.add(account)
    _commit_unique(db, body.name)
    if account.sync_from_holdings:
        sync_account_snapshots(db)
        db.commit()
    return account


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db)):
    account = get_account(db, account_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    _commit_unique(db, body.name)
    if account.sync_from_holdings:
        sync_account_snapshots(db)
        db.commit()
    return account


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Deletes the account and all its monthly balances. Prefer archiving to keep history."""
    db.delete(get_account(db, account_id))
    db.commit()


# ---------- Monthly balances ----------

def _balances_for(db: Session, month) -> dict[int, Decimal]:
    rows = db.execute(
        select(BalanceSnapshot.account_id, BalanceSnapshot.balance).where(BalanceSnapshot.month == month)
    ).all()
    return dict(rows)


@router.get("/balance-sheet", response_model=BalanceSheet)
def get_balance_sheet(month: str = MONTH, db: Session = Depends(get_db)):
    m = parse_month(month)
    if m == current_month():
        sync_account_snapshots(db)
        db.commit()
    balances = _balances_for(db, m)
    previous = _balances_for(db, add_months(m, -1))

    accounts = db.scalars(select(Account).order_by(Account.kind, Account.name)).all()
    rows = [
        BalanceRow(account=a, balance=balances.get(a.id), previous_balance=previous.get(a.id))
        for a in accounts
        # Archived accounts still show for months where they have a balance.
        if not a.is_archived or a.id in balances
    ]
    assets = sum((r.balance or 0 for r in rows if r.account.kind == AccountKind.asset), Decimal(0))
    liabilities = sum(
        (r.balance or 0 for r in rows if r.account.kind == AccountKind.liability), Decimal(0)
    )
    return BalanceSheet(
        month=format_month(m),
        rows=rows,
        total_assets=assets,
        total_liabilities=liabilities,
        net_worth=assets - liabilities,
    )


@router.put("/balance-sheet", response_model=BalanceSheet)
def save_balances(body: BalanceUpdate, month: str = MONTH, db: Session = Depends(get_db)):
    m = parse_month(month)
    for entry in body.balances:
        account = get_account(db, entry.account_id)
        if account.sync_from_holdings and m == current_month():
            raise HTTPException(
                400, f"'{account.name}' is synced from Stocks holdings and can't be edited this month"
            )
        if entry.balance is None:
            db.execute(
                delete(BalanceSnapshot).where(
                    BalanceSnapshot.account_id == entry.account_id, BalanceSnapshot.month == m
                )
            )
        else:
            stmt = insert(BalanceSnapshot).values(
                account_id=entry.account_id, month=m, balance=entry.balance
            )
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["account_id", "month"], set_={"balance": stmt.excluded.balance}
                )
            )
    db.commit()
    return get_balance_sheet(month, db)


@router.post("/balance-sheet/copy-previous", response_model=BalanceSheet)
def copy_previous(month: str = MONTH, db: Session = Depends(get_db)):
    """Fill in any missing balances this month with last month's values."""
    m = parse_month(month)
    current = _balances_for(db, m)
    previous = _balances_for(db, add_months(m, -1))
    accounts = {a.id: a for a in db.scalars(select(Account)).all()}
    for account_id, balance in previous.items():
        account = accounts[account_id]
        if account_id in current or account.is_archived or account.sync_from_holdings:
            continue
        db.add(BalanceSnapshot(account_id=account_id, month=m, balance=balance))
    db.commit()
    return get_balance_sheet(month, db)


@router.get("/balance-sheet/trend", response_model=list[NetWorthPoint])
def net_worth_trend(months: int = Query(24, ge=1, le=240), db: Session = Depends(get_db)):
    start = add_months(current_month(), -(months - 1))
    rows = db.execute(
        select(BalanceSnapshot.month, Account.kind, BalanceSnapshot.balance)
        .join(Account, Account.id == BalanceSnapshot.account_id)
        .where(BalanceSnapshot.month >= start)
    ).all()
    totals: dict = defaultdict(lambda: {AccountKind.asset: Decimal(0), AccountKind.liability: Decimal(0)})
    for month, kind, balance in rows:
        totals[month][kind] += balance
    return [
        NetWorthPoint(
            month=format_month(m),
            assets=t[AccountKind.asset],
            liabilities=t[AccountKind.liability],
            net_worth=t[AccountKind.asset] - t[AccountKind.liability],
        )
        for m, t in sorted(totals.items())
    ]
