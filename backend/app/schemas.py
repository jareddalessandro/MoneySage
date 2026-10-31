import re
from datetime import date, datetime
from decimal import Decimal

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.models import (
    AccountKind,
    AssetType,
    CategoryColor,
    CategoryKind,
    CompanyEntryKind,
    RevenueShareBasis,
    DeductionType,
    Frequency,
)


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
    is_card_payments: bool


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
    paid_by_card: bool = False  # expenses only
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
    paid_by_card: bool
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
    statement_import_id: int | None


TotalsFrom = Literal["statement", "manual"]


class StatementCategory(BaseModel):
    category_id: int
    name: str
    kind: CategoryKind
    color: CategoryColor
    actual: Num
    unexpected: Num
    budgeted: Num
    # On the card payments line in a statement month: the paid-by-card budget items it's compared with.
    card_items: list[str] = []


class IncomeStatement(BaseModel):
    month: str
    # Which transactions make up the totals; the other source only explains them.
    totals_from: TotalsFrom
    has_statement: bool
    notes: str | None
    total_income: Num
    total_expenses: Num
    net: Num
    unexpected_income: Num
    unexpected_expenses: Num
    budgeted_income: Num
    budgeted_expenses: Num
    categories: list[StatementCategory]


class MonthNotesIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    notes: str | None = Field(default=None, max_length=20000)


class TotalsFromIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    totals_from: TotalsFrom


# ---------- Statement import ----------

class PreviewAccount(BaseModel):
    key: str  # e.g. "sofi-2845"
    name: str  # e.g. "SoFi Checking 2845"
    kind: str  # "checking" or "savings"
    last4: str
    beginning: Num | None
    ending: Num | None
    row_total: Num
    # Ending - (beginning + rows). Anything but 0 means some lines weren't read.
    difference: Num | None
    account_id: int | None  # suggested Balance Sheet account


class PreviewRow(BaseModel):
    key: str  # becomes the transaction's import_hash
    date: date
    account_key: str
    section: str
    bank_type: str
    description: str
    amount: Num  # signed: deposits positive
    category_id: int | None
    skip: bool
    reason: str
    duplicate: bool  # already imported


class StatementPreview(BaseModel):
    bank: str
    period_start: date
    period_end: date
    month: str
    accounts: list[PreviewAccount]
    rows: list[PreviewRow]


class ImportAccountIn(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    beginning: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    ending: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    account_id: int | None = None


class ImportRowIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    date: date
    account_key: str
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(max_digits=14, decimal_places=2)  # signed
    category_id: int | None = None
    skip: bool = False

    @field_validator("amount")
    @classmethod
    def not_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Amount can't be 0")
        return v


class StatementImportIn(BaseModel):
    bank: str = Field(min_length=1, max_length=40)
    file_name: str = Field(min_length=1, max_length=255)
    period_start: date
    period_end: date
    accounts: list[ImportAccountIn]
    rows: list[ImportRowIn]
    update_balances: bool = True


class StatementImportOut(BaseModel):
    id: int
    bank: str
    file_name: str
    period_start: date
    period_end: date
    accounts: list[dict]
    transaction_count: int
    created_at: datetime


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


class TradeIn(BaseModel):
    """Buy more of a holding or sell some of it (for cash: deposit or withdraw dollars)."""

    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    price: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=6)  # per share, buys only


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


# ---------- Credit cards ----------

class CreditCardIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    issuer: str | None = Field(default=None, max_length=100)
    payment_url: str | None = Field(default=None, max_length=500)
    annual_fee: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=2)
    annual_fee_month: int | None = Field(default=None, ge=1, le=12)
    benefits: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name is required")
        return v.strip()

    @field_validator("issuer", "notes")
    @classmethod
    def _optional_text(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @field_validator("payment_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        # People paste "chase.com"; make it a link that opens. Only web links are allowed, so a
        # scheme like javascript: is rejected rather than turned into a clickable link.
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", v):
            v = f"https://{v}"
        if not v.lower().startswith(("http://", "https://")) or " " in v:
            raise ValueError("Payment site must be a web address, like chase.com")
        return v

    @field_validator("benefits")
    @classmethod
    def _benefits(cls, v: list[str]) -> list[str]:
        lines = [line.strip() for line in v]
        if any(len(line) > 300 for line in lines):
            raise ValueError("Each benefit must be 300 characters or fewer")
        return [line for line in lines if line]


class CreditCardOut(ORMModel):
    id: int
    name: str
    issuer: str | None
    payment_url: str | None
    annual_fee: Num
    annual_fee_month: int | None
    benefits: list[str]
    notes: str | None


# ---------- Companies ----------

def _required_text(v: str) -> str:
    if not v.strip():
        raise ValueError("Can't be blank")
    return v.strip()


def _blank_to_none(v: str | None) -> str | None:
    return (v or "").strip() or None


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None

    _name = field_validator("name")(_required_text)
    _description = field_validator("description")(_blank_to_none)


class CompanyMemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    equity_percent: Decimal = Field(default=Decimal(0), ge=0, le=100, max_digits=7, decimal_places=4)

    _name = field_validator("name")(_required_text)


class CompanyMemberOut(ORMModel):
    id: int
    name: str
    equity_percent: Num


class CompanyProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None

    _name = field_validator("name")(_required_text)
    _description = field_validator("description")(_blank_to_none)


class CompanyProductOut(ORMModel):
    id: int
    name: str
    description: str | None


class CompanyOut(ORMModel):
    id: int
    name: str
    description: str | None
    members: list[CompanyMemberOut]
    products: list[CompanyProductOut]


class CompanyEntryIn(BaseModel):
    kind: CompanyEntryKind
    date: date
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    category: str | None = Field(default=None, max_length=80)
    member_id: int | None = None
    product_id: int | None = None
    revenue_share_id: int | None = None
    notes: str | None = None

    _description = field_validator("description")(_required_text)
    _optional = field_validator("category", "notes")(_blank_to_none)


class CompanyEntryOut(ORMModel):
    id: int
    kind: CompanyEntryKind
    date: date
    description: str
    amount: Num
    category: str | None
    member_id: int | None
    product_id: int | None
    revenue_share_id: int | None
    notes: str | None
    # On a revenue-share payment: the part that repays funding from the payee (so isn't an expense).
    funding_repaid: Num | None = None


class CompanyMonth(BaseModel):
    month: str
    income: Num
    expenses: Num


class CompanyMemberSummary(BaseModel):
    member_id: int
    name: str
    equity_percent: Num
    contributed_year: Num
    contributed_total: Num
    distributed_year: Num
    distributed_total: Num
    # The year's net profit times their equity. A paper share, not money paid out.
    profit_share: Num


class CompanyProductSummary(BaseModel):
    product_id: int | None
    name: str
    income: Num
    cost_of_revenue: Num
    # Everything else (operating expenses).
    other_expenses: Num
    net: Num


class CompanySummary(BaseModel):
    company_id: int
    year: int
    income: Num
    expenses: Num
    net: Num
    contributions_year: Num
    contributions_total: Num
    distributions_year: Num
    distributions_total: Num
    equity_assigned: Num
    # Revenue-share payments and the fee categories those agreements subtract. Part of `expenses`.
    cost_of_revenue: Num
    # Revenue-share funding received in the year (a liability, not income), and the part of the year's
    # revenue-share payments that repaid funding (left out of `expenses`).
    funding_received: Num
    funding_repaid: Num
    months: list[CompanyMonth]
    members: list[CompanyMemberSummary]
    # One row per product, then "no product" when the company has products and anything is untagged.
    products: list[CompanyProductSummary]
    # Years that have entries, newest first, for the year picker.
    years: list[int]
    # Categories already used, for suggestions in the entry form.
    income_categories: list[str]
    expense_categories: list[str]


class CompanyListItem(BaseModel):
    id: int
    name: str
    description: str | None
    members: list[CompanyMemberOut]
    year: int
    income: Num
    expenses: Num
    net: Num
    contributions_total: Num
    distributions_total: Num


class RevenueShareIn(BaseModel):
    payee: str = Field(min_length=1, max_length=100)
    basis: RevenueShareBasis = RevenueShareBasis.income
    product_id: int | None = None
    rate_percent: Decimal = Field(gt=0, le=100, max_digits=7, decimal_places=4)
    deduct_categories: list[str] = Field(default_factory=list, max_length=20)
    start_date: date
    end_date: date | None = None
    category: str = Field(default="Revenue share", min_length=1, max_length=80)
    notes: str | None = None

    _payee = field_validator("payee", "category")(_required_text)
    _notes = field_validator("notes")(_blank_to_none)

    @field_validator("deduct_categories")
    @classmethod
    def _clean_categories(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for name in (c.strip() for c in v):
            if name and name.lower() not in seen:
                if len(name) > 80:
                    raise ValueError("Category names can be at most 80 characters")
                seen.add(name.lower())
                out.append(name)
        return out

    @model_validator(mode="after")
    def _check_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("The end date can't be before the start date")
        return self


class RevenueShareOut(ORMModel):
    id: int
    payee: str
    basis: RevenueShareBasis
    product_id: int | None
    rate_percent: Num
    deduct_categories: list[str]
    start_date: date
    end_date: date | None
    category: str
    notes: str | None
    # e.g. "10% of App A revenue after App Store fees, starting January 1, 2026".
    terms: str = ""
    # Figures for the requested year, and all time through today.
    earned_year: Num = Decimal(0)
    paid_year: Num = Decimal(0)
    earned_total: Num = Decimal(0)
    paid_total: Num = Decimal(0)
    # Earned minus paid, all time. Below 0 means it's been overpaid (or paid in advance).
    balance_due: Num = Decimal(0)
    # Reported basis: finished months since the start with no revenue entered, oldest first.
    missing_months: list[str] = []
    # Funding received from the payee, how much payments have repaid, and what's still owed, all time.
    funding_received: Num = Decimal(0)
    funding_repaid: Num = Decimal(0)
    funding_outstanding: Num = Decimal(0)


class RevenueShareMonthOut(BaseModel):
    month: str
    # Income basis: the counted income. Reported basis: what was entered, or null if nothing yet.
    revenue: Num | None
    deductions: Num
    base: Num
    earned: Num
    paid: Num
    # Balance due at the end of the month.
    balance: Num


class RevenueShareMonthIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    # Null clears the month.
    revenue: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)


class RevenueShareMonthsUpdate(BaseModel):
    months: list[RevenueShareMonthIn] = Field(max_length=120)
