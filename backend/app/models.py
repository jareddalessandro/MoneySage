import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

MONEY = Numeric(14, 2)


def _enum(cls: type[enum.Enum]) -> Enum:
    # Stored as VARCHAR + CHECK constraint so adding values later is a simple migration.
    return Enum(cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


class CategoryKind(str, enum.Enum):
    income = "income"
    expense = "expense"


class CategoryColor(str, enum.Enum):
    """Palette keys, in the validated order (the frontend maps each to a hex). Gray is the neutral."""

    blue = "blue"
    orange = "orange"
    teal = "teal"
    violet = "violet"
    gold = "gold"
    pink = "pink"
    green = "green"
    plum = "plum"
    gray = "gray"


class Frequency(str, enum.Enum):
    weekly = "weekly"
    biweekly = "biweekly"
    semimonthly = "semimonthly"
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class AccountKind(str, enum.Enum):
    asset = "asset"
    liability = "liability"


class DeductionType(str, enum.Enum):
    retirement = "retirement"
    insurance = "insurance"
    hsa = "hsa"  # HSA / FSA
    tax = "tax"
    other = "other"


class AssetType(str, enum.Enum):
    stock = "stock"
    etf = "etf"
    crypto = "crypto"
    # Uninvested cash in an account (e.g. a brokerage or IRA). Quantity is the dollar amount;
    # it's worth exactly that, so it has no price history and is never fetched.
    cash = "cash"


CASH_TICKER = "CASH"


class CompanyEntryKind(str, enum.Enum):
    income = "income"
    expense = "expense"
    # Money a member put into the company. Not income: it's capital, tracked per member.
    contribution = "contribution"
    # Money paid out of the company to a member (a draw or profit distribution). Not an expense.
    distribution = "distribution"
    # Money a revenue-share payee paid the company for their share (a sale of future revenue). Not income:
    # it's a liability, repaid by the payments made to that payee. Always linked to the agreement.
    funding = "funding"


class RevenueShareBasis(str, enum.Enum):
    # A percentage of the company's recorded income (optionally one product's), less any fee categories.
    income = "income"
    # A percentage of revenue entered by hand each month, e.g. sales from customers someone referred.
    reported = "reported"


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[CategoryKind] = mapped_column(_enum(CategoryKind))
    color: Mapped[CategoryColor] = mapped_column(
        _enum(CategoryColor), default=CategoryColor.gray, server_default=CategoryColor.gray.value
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # The one expense category that imported credit card payments go to. In a month whose totals come
    # from a statement, budget items marked paid_by_card are compared against it as a group.
    is_card_payments: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BudgetItem(Base):
    __tablename__ = "budget_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    # For a paycheck, amount is take-home pay (what hits the bank account), so budget totals and
    # actual deposits on the income statement line up. gross_amount is pay before deductions.
    amount: Mapped[Decimal] = mapped_column(MONEY)
    gross_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    frequency: Mapped[Frequency] = mapped_column(_enum(Frequency))
    # Expenses only: paid with a credit card, so a bank statement shows it inside a card payment.
    paid_by_card: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(lazy="joined")
    deductions: Mapped[list["PaycheckDeduction"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PaycheckDeduction.position"
    )


class PaycheckDeduction(Base):
    """One line on a pay stub between gross and take-home pay, per paycheck."""

    __tablename__ = "paycheck_deductions"

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_item_id: Mapped[int] = mapped_column(ForeignKey("budget_items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[DeductionType] = mapped_column(_enum(DeductionType))
    # Taken out before taxes (traditional 401k, most health insurance). Always false for taxes.
    pre_tax: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    amount: Mapped[Decimal] = mapped_column(MONEY)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[AccountKind] = mapped_column(_enum(AccountKind))
    subtype: Mapped[str] = mapped_column(String(30))
    # When true, this account's monthly balance is computed from the holdings linked to it.
    sync_from_holdings: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text)
    # Which account in an imported bank statement this is (e.g. "sofi-2845"), remembered from the last import.
    statement_key: Mapped[str | None] = mapped_column(String(40), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    month: Mapped[date] = mapped_column(Date, index=True)  # always the 1st of the month
    # Liabilities are stored as positive amounts owed.
    balance: Mapped[Decimal] = mapped_column(MONEY)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    # Always positive; income vs expense comes from the category.
    amount: Mapped[Decimal] = mapped_column(MONEY)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    is_unexpected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    # "manual" or "statement" (imported from a bank statement PDF).
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    import_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    statement_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("statement_imports.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(lazy="joined")


class StatementImport(Base):
    """One uploaded bank statement. Deleting it removes the transactions it created."""

    __tablename__ = "statement_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank: Mapped[str] = mapped_column(String(40))
    file_name: Mapped[str] = mapped_column(String(255))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    # Per statement account: [{key, name, beginning, ending, account_id}] (balances as strings).
    accounts: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    # Keys of the lines skipped (e.g. transfers), so importing the statement again finds them too.
    skipped_keys: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRule(Base):
    """What to do with a statement line, learned from the choices made when importing."""

    __tablename__ = "import_rules"
    __table_args__ = (UniqueConstraint("pattern", "direction"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Normalized description (see statement_import.normalize).
    pattern: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(3))  # "in" (deposit) or "out" (withdrawal)
    skip: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MonthSetting(Base):
    """Per-month choices on the Income Statement."""

    __tablename__ = "month_settings"

    month: Mapped[date] = mapped_column(Date, primary_key=True)  # the 1st of the month
    # "statement": imported rows are the totals and manual entries only explain them.
    # "manual": manual entries are the totals and imported rows are ignored.
    # Null when only notes were saved: the month then uses the default (statement when it has one).
    totals_from: Mapped[str | None] = mapped_column(String(20))
    # Free-form notes the household keeps about the month.
    notes: Mapped[str | None] = mapped_column(Text)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    asset_type: Mapped[AssetType] = mapped_column(_enum(AssetType))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    # Average price paid per share (or per coin). Total cost basis is derived from it.
    cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def cost_basis(self) -> Decimal | None:
        """Total cost: quantity x cost per unit, to the cent."""
        if self.cost_per_unit is None:
            return None
        return (self.quantity * self.cost_per_unit).quantize(Decimal("0.01"))


class PriceQuote(Base):
    __tablename__ = "price_quotes"
    __table_args__ = (UniqueConstraint("ticker", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6))


class PriceRefreshRun(Base):
    __tablename__ = "price_refresh_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running/success/partial/failed
    tickers_updated: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)


class CreditCard(Base):
    """Reference info for a credit card: where to pay it, what it offers, what it costs.

    Deliberately holds no card numbers or logins. Balances owed live on the Balance Sheet.
    """

    __tablename__ = "credit_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    issuer: Mapped[str | None] = mapped_column(String(100))
    payment_url: Mapped[str | None] = mapped_column(String(500))
    annual_fee: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    # Month the annual fee posts (1-12), if it has one.
    annual_fee_month: Mapped[int | None] = mapped_column(Integer)
    # Short benefit lines in display order, e.g. "3% back on dining".
    benefits: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    """A business the household has a stake in, tracked separately from household finances."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list["CompanyMember"]] = relationship(
        cascade="all, delete-orphan", order_by="CompanyMember.name", lazy="selectin"
    )
    products: Mapped[list["CompanyProduct"]] = relationship(
        cascade="all, delete-orphan", order_by="CompanyProduct.name", lazy="selectin"
    )


class CompanyMember(Base):
    """An owner of a company and their equity stake."""

    __tablename__ = "company_members"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # 0-100, e.g. 33.3333. A company's members never total more than 100.
    equity_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal(0), server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyProduct(Base):
    """Something a company sells (e.g. one app), so income and expenses can be broken out per product."""

    __tablename__ = "company_products"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevenueShare(Base):
    """An agreement to pay a non-member a percentage of revenue (an investor's share, a sales commission).

    What's earned is calculated per month; payments are expense entries linked by `revenue_share_id`.
    """

    __tablename__ = "revenue_shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    payee: Mapped[str] = mapped_column(String(100))
    basis: Mapped[RevenueShareBasis] = mapped_column(_enum(RevenueShareBasis))
    # Income basis: whose income counts (null = all of the company's). Either basis: the product
    # payments are tagged with.
    product_id: Mapped[int | None] = mapped_column(ForeignKey("company_products.id", ondelete="RESTRICT"))
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    # Income basis: expense categories subtracted from income before the rate applies (platform fees).
    deduct_categories: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    # Category given to payment entries; also counted as cost of revenue.
    category: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevenueShareMonth(Base):
    """Revenue entered for one month of a `reported`-basis revenue share."""

    __tablename__ = "revenue_share_months"
    __table_args__ = (UniqueConstraint("revenue_share_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    revenue_share_id: Mapped[int] = mapped_column(ForeignKey("revenue_shares.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)  # first of the month
    revenue: Mapped[Decimal] = mapped_column(MONEY)


class CompanyEntry(Base):
    """One income, expense, member contribution, distribution, or revenue-share funding. Amounts are positive;
    `kind` decides the meaning."""

    __tablename__ = "company_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CompanyEntryKind] = mapped_column(_enum(CompanyEntryKind))
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    # Free-text grouping for income and expenses (e.g. "Software"); null for member entries.
    category: Mapped[str | None] = mapped_column(String(80))
    # Who put money in or got paid; set only for contributions and distributions. A member with
    # entries can't be deleted.
    member_id: Mapped[int | None] = mapped_column(ForeignKey("company_members.id", ondelete="RESTRICT"))
    # Income and expenses can belong to a product. A product with entries can't be deleted.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_products.id", ondelete="RESTRICT"), index=True
    )
    # Set on an expense that pays a revenue share, and on funding received from its payee. An agreement
    # with either can't be deleted.
    revenue_share_id: Mapped[int | None] = mapped_column(
        ForeignKey("revenue_shares.id", ondelete="RESTRICT"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
