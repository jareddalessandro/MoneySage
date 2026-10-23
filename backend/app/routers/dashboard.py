from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BalanceSnapshot
from app.months import add_months, current_month, format_month
from app.routers.balance_sheet import get_balance_sheet
from app.routers.budget import summary as budget_summary
from app.routers.stocks import portfolio_summary
from app.routers.transactions import monthly_totals
from app.schemas import Dashboard

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db)):
    month = current_month()

    net_worth = net_worth_change = None
    latest = db.scalar(select(func.max(BalanceSnapshot.month)))
    if latest is not None:
        sheet = get_balance_sheet(format_month(latest), db)
        net_worth = sheet.net_worth
        prior_month = add_months(latest, -1)
        if db.scalar(select(BalanceSnapshot.id).where(BalanceSnapshot.month == prior_month).limit(1)):
            net_worth_change = net_worth - get_balance_sheet(format_month(prior_month), db).net_worth

    totals = monthly_totals(db, month, add_months(month, 1)).get(month, {})
    income = totals.get("income", Decimal(0))
    expenses = totals.get("expenses", Decimal(0))
    budget = budget_summary(db)
    portfolio = portfolio_summary(db)

    return Dashboard(
        month=format_month(month),
        net_worth=net_worth,
        net_worth_month=format_month(latest) if latest else None,
        net_worth_change=net_worth_change,
        month_income=income,
        month_expenses=expenses,
        month_net=income - expenses,
        month_unexpected_expenses=totals.get("unexpected_expenses", Decimal(0)),
        budget_monthly_income=budget.monthly_income,
        budget_monthly_expenses=budget.monthly_expenses,
        portfolio_value=portfolio.total_value,
        portfolio_day_change=portfolio.day_change,
    )
