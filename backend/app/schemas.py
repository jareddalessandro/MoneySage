from datetime import date, datetime
from decimal import Decimal

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models import AccountKind, AssetType, CategoryColor, CategoryKind, DeductionType, Frequency


# Decimals stay exact internally but go out as JSON numbers for the frontend.
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Categories ----------

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind
    color: CategoryColor | None = None  # picked automatically when omitted


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: CategoryColor | None = None
    is_archived: bool | None = None


class CategoryOut(ORMModel):
    id: int
    name: str
    kind: CategoryKind
    color: CategoryColor
    is_archived: bool


# ---------- Budget ----------

class DeductionIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: DeductionType
    pre_tax: bool = False
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class DeductionOut(ORMModel):
    name: str
    type: DeductionType
    pre_tax: bool
    amount: Num


class BudgetItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    frequency: Frequency
    notes: str | None = None
    # Paycheck breakdown (income only): pay before deductions, and the deductions themselves.
    gross_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    deductions: list[DeductionIn] = []


class BudgetItemOut(ORMModel):
    id: int
    name: str
    category: CategoryOut
    amount: Num
    frequency: Frequency
    monthly_amount: Num
    notes: str | None
    gross_amount: Num | None
    monthly_gross_amount: Num | None
    deductions: list[DeductionOut]


class BudgetCategoryTotal(BaseModel):
    category_id: int
    name: str
    kind: CategoryKind
    color: CategoryColor
    monthly_amount: Num


Stage = Literal["pre_tax", "tax", "post_tax"]


class PaycheckLine(BaseModel):
    name: str
    type: DeductionType
    stage: Stage
    annual_amount: Num


class PaycheckBreakdown(BaseModel):
    """Yearly totals for one paycheck or all of them combined (exact: per-paycheck amount x
    paychecks per year).

    gross - pre-tax - taxes = after-tax; after-tax - post-tax - unitemized = take-home.
    The frontend divides by 12 for monthly figures, or by paychecks_per_year for one paycheck.
    """

    budget_item_id: int | None  # None for the combined view
    name: str
    paychecks: int  # how many budget items are included
    paychecks_per_year: int | None  # None for the combined view
    annual_gross: Num
    annual_pre_tax: Num
    annual_taxes: Num
    annual_after_tax: Num
    annual_post_tax: Num
    # Gross minus itemized deductions minus take-home: withholding that wasn't itemized
    # (negative if the deductions add up to more than gross minus take-home).
    annual_unitemized: Num
    annual_take_home: Num
    lines: list[PaycheckLine]


class BudgetSummary(BaseModel):
    monthly_income: Num
    monthly_expenses: Num
    monthly_surplus: Num
    by_category: list[BudgetCategoryTotal]
    paycheck: PaycheckBreakdown | None  # every paycheck combined
    paycheck_items: list[PaycheckBreakdown]  # one per paycheck


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
    # Null for a month with nothing recorded (a gap between recorded months).
    assets: Num | None
    liabilities: Num | None
    net_worth: Num | None


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
    color: CategoryColor
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
    ticker: str = Field(default="", max_length=20)  # ignored for cash
    asset_type: AssetType
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    cost_per_unit: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=6)  # per share/coin
    account_id: int | None = None
    notes: str | None = None


class HoldingOut(BaseModel):
    id: int
    ticker: str
    asset_type: AssetType
    quantity: Num
    cost_per_unit: Num | None  # what was paid per share/coin
    cost_basis: Num | None  # total: quantity x cost_per_unit
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
