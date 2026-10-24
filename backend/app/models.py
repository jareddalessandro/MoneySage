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
    # Import-friendly fields for future bank statement parsing.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    import_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(lazy="joined")


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
