from datetime import date, datetime
from decimal import Decimal

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models import AccountKind, AssetType, CategoryKind, Frequency


# Decimals stay exact internally but go out as JSON numbers for the frontend.
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Categories ----------

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_archived: bool | None = None


class CategoryOut(ORMModel):
    id: int
    name: str
    kind: CategoryKind
    is_archived: bool


# ---------- Budget ----------

class BudgetItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency
    notes: str | None = None


class BudgetItemOut(ORMModel):
    id: int
    name: str
    category: CategoryOut
    amount: Num
    frequency: Frequency
    monthly_amount: Num
    notes: str | None


class BudgetCategoryTotal(BaseModel):
    category_id: int
    name: str
    kind: CategoryKind
    monthly_amount: Num


class BudgetSummary(BaseModel):
    monthly_income: Num
    monthly_expenses: Num
    monthly_surplus: Num
    by_category: list[BudgetCategoryTotal]


# ---------- Accounts / Balance sheet ----------

class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: AccountKind
    subtype: str = Field(min_length=1, max_length=30)
    sync_from_holdings: bool = False
    notes: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: AccountKind | None = None
    subtype: str | None = Field(default=None, min_length=1, max_length=30)
    sync_from_holdings: bool | None = None
    is_archived: bool | None = None
    notes: str | None = None


class AccountOut(ORMModel):
    id: int
    name: str
    kind: AccountKind
    subtype: str
    sync_from_holdings: bool
    is_archived: bool
    notes: str | None


class BalanceRow(BaseModel):
    account: AccountOut
    balance: Num | None
    previous_balance: Num | None


class BalanceSheet(BaseModel):
    month: str
    rows: list[BalanceRow]
    total_assets: Num
    total_liabilities: Num
    net_worth: Num


class BalanceEntry(BaseModel):
    account_id: int
    balance: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)


class BalanceUpdate(BaseModel):
    balances: list[BalanceEntry]


class NetWorthPoint(BaseModel):
    month: str
    assets: Num
    liabilities: Num
    net_worth: Num


# ---------- Transactions / Income statement ----------

class TransactionIn(BaseModel):
    date: date
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    category_id: int
    is_unexpected: bool = False
    notes: str | None = None
    account_id: int | None = None


class TransactionOut(ORMModel):
    id: int
    date: date
    description: str
    amount: Num
    category: CategoryOut
    is_unexpected: bool
    notes: str | None
    account_id: int | None
    source: str


class StatementCategory(BaseModel):
    category_id: int
    name: str
    kind: CategoryKind
    actual: Num
    unexpected: Num
    budgeted: Num


class IncomeStatement(BaseModel):
    month: str
    total_income: Num
    total_expenses: Num
    net: Num
    unexpected_income: Num
    unexpected_expenses: Num
    budgeted_income: Num
    budgeted_expenses: Num
    categories: list[StatementCategory]


class IncomeTrendPoint(BaseModel):
    month: str
    income: Num
    expenses: Num
    net: Num
    unexpected_income: Num
    unexpected_expenses: Num


# ---------- Holdings / prices ----------

class HoldingIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    asset_type: AssetType
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    cost_basis: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    account_id: int | None = None
    notes: str | None = None


class HoldingOut(BaseModel):
    id: int
    ticker: str
    asset_type: AssetType
    quantity: Num
    cost_basis: Num | None
    account_id: int | None
    account_name: str | None
    notes: str | None
    price: Num | None
    price_date: date | None
    previous_close: Num | None
    market_value: Num | None
    day_change: Num | None
    gain: Num | None


class RefreshRunOut(ORMModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    tickers_updated: int
    message: str | None


class PortfolioSummary(BaseModel):
    total_value: Num
    total_cost: Num | None
    total_gain: Num | None
    day_change: Num
    last_refresh: RefreshRunOut | None


class PortfolioPoint(BaseModel):
    date: date
    value: Num


# ---------- Dashboard ----------

class Dashboard(BaseModel):
    month: str
    net_worth: Num | None
    net_worth_month: str | None
    net_worth_change: Num | None
    month_income: Num
    month_expenses: Num
    month_net: Num
    month_unexpected_expenses: Num
    budget_monthly_income: Num
    budget_monthly_expenses: Num
    portfolio_value: Num
    portfolio_day_change: Num
