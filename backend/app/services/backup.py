"""Export a household and companies to one JSON file, and import such a file elsewhere.

This is how data moves from an offline install into a hosted one (and how people take a copy of their
data). Rows are written with the API's own input schemas, so an imported file passes the same validation
as data typed into the app. Ids in the file are only labels within the file; references between rows
(a transaction's category, an entry's member) use them and are remapped to new ids on import.

Importing a household fills the current one, which must be empty (only its default, unused categories,
which are replaced). Each company in the file becomes a new company owned by the importer. It all happens
in one transaction, so a file is imported completely or not at all.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    CASH_TICKER,
    AccessRole,
    AssetType,
    Account,
    BalanceSnapshot,
    BudgetItem,
    Category,
    CategoryColor,
    CategoryKind,
    Company,
    CompanyAccess,
    CompanyEntry,
    CompanyMember,
    CompanyProduct,
    CreditCard,
    DeductionType,
    Holding,
    Household,
    ImportRule,
    MonthSetting,
    PaycheckDeduction,
    RevenueShare,
    RevenueShareMonth,
    StatementImport,
    Transaction,
    User,
)
from app.schemas import (
    AccountIn,
    BudgetItemIn,
    CompanyEntryIn,
    CompanyIn,
    CompanyMemberIn,
    CompanyProductIn,
    CreditCardIn,
    HoldingIn,
    RevenueShareIn,
    TransactionIn,
)

FORMAT = "moneysage-export"
VERSION = 1
Money = Field(max_digits=14, decimal_places=2)


# ---------- The file ----------

class XCategory(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind
    color: CategoryColor = CategoryColor.gray
    is_archived: bool = False
    is_card_payments: bool = False


class XBalance(BaseModel):
    month: date
    balance: Decimal = Money
    updated_at: datetime | None = None


class XAccount(AccountIn):
    id: int
    is_archived: bool = False
    statement_key: str | None = Field(default=None, max_length=40)
    balances: list[XBalance] = []


class XStatementAccount(BaseModel):
    key: str = Field(max_length=40)
    name: str = Field(max_length=255)
    beginning: str | None = None
    ending: str | None = None
    account_id: int | None = None


class XStatementImport(BaseModel):
    id: int
    bank: str = Field(max_length=40)
    file_name: str = Field(max_length=255)
    period_start: date
    period_end: date
    accounts: list[XStatementAccount] = []
    skipped_keys: list[str] = []
    created_at: datetime | None = None  # when it was imported


class XTransaction(TransactionIn):
    source: Literal["manual", "statement"] = "manual"
    import_hash: str | None = Field(default=None, max_length=64)
    statement_import_id: int | None = None


class XImportRule(BaseModel):
    pattern: str = Field(min_length=1, max_length=255)
    direction: Literal["in", "out"]
    skip: bool = False
    category_id: int | None = None


class XMonthSetting(BaseModel):
    month: date
    totals_from: Literal["statement", "manual"] | None = None
    notes: str | None = None


class XHousehold(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(max_length=64)
    categories: list[XCategory] = []
    accounts: list[XAccount] = []
    budget_items: list[BudgetItemIn] = []
    statement_imports: list[XStatementImport] = []
    transactions: list[XTransaction] = []
    import_rules: list[XImportRule] = []
    month_settings: list[XMonthSetting] = []
    holdings: list[HoldingIn] = []
    credit_cards: list[CreditCardIn] = []

    @field_validator("timezone")
    @classmethod
    def _zone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown timezone '{v}'")
        return v


class XMember(CompanyMemberIn):
    id: int


class XProduct(CompanyProductIn):
    id: int


class XRevenueShareMonth(BaseModel):
    month: date
    revenue: Decimal = Money


class XRevenueShare(RevenueShareIn):
    id: int
    months: list[XRevenueShareMonth] = []


class XCompany(CompanyIn):
    members: list[XMember] = []
    products: list[XProduct] = []
    revenue_shares: list[XRevenueShare] = []
    entries: list[CompanyEntryIn] = []


class ExportFile(BaseModel):
    format: Literal["moneysage-export"] = FORMAT
    version: Literal[1] = VERSION
    exported_at: datetime
    household: XHousehold | None = None
    companies: list[XCompany] = []


class ImportResult(BaseModel):
    household: bool
    companies: list[str]
    transactions: int
    entries: int
    holdings: int


# ---------- Export ----------

def export_household(db: Session, household: Household) -> XHousehold:
    hid = household.id

    def rows(model, *order):
        return db.scalars(select(model).where(model.household_id == hid).order_by(*order, model.id)).unique().all()

    snapshots: dict[int, list[XBalance]] = {}
    for s in db.scalars(
        select(BalanceSnapshot)
        .join(Account, Account.id == BalanceSnapshot.account_id)
        .where(Account.household_id == hid)
        .order_by(BalanceSnapshot.month)
    ):
        snapshots.setdefault(s.account_id, []).append(XBalance(month=s.month, balance=s.balance, updated_at=s.updated_at))

    return XHousehold(
        name=household.name,
        timezone=household.timezone,
        categories=[XCategory.model_validate(c, from_attributes=True) for c in rows(Category)],
        accounts=[
            XAccount(
                id=a.id, name=a.name, kind=a.kind, subtype=a.subtype, sync_from_holdings=a.sync_from_holdings,
                notes=a.notes, is_archived=a.is_archived, statement_key=a.statement_key,
                balances=snapshots.get(a.id, []),
            )
            for a in rows(Account)
        ],
        budget_items=[
            BudgetItemIn(
                name=i.name, category_id=i.category_id, amount=i.amount, frequency=i.frequency, notes=i.notes,
                paid_by_card=i.paid_by_card, gross_amount=i.gross_amount,
                deductions=[
                    {"name": d.name, "type": d.type, "pre_tax": d.pre_tax, "amount": d.amount} for d in i.deductions
                ],
            )
            for i in rows(BudgetItem)
        ],
        statement_imports=[XStatementImport.model_validate(s, from_attributes=True) for s in rows(StatementImport)],
        transactions=[
            XTransaction(
                date=t.date, description=t.description, amount=t.amount, category_id=t.category_id,
                is_unexpected=t.is_unexpected, notes=t.notes, account_id=t.account_id, source=t.source,
                import_hash=t.import_hash, statement_import_id=t.statement_import_id,
            )
            for t in rows(Transaction)
        ],
        import_rules=[XImportRule.model_validate(r, from_attributes=True) for r in rows(ImportRule)],
        month_settings=[
            XMonthSetting.model_validate(m, from_attributes=True)
            for m in db.scalars(select(MonthSetting).where(MonthSetting.household_id == hid).order_by(MonthSetting.month))
        ],
        holdings=[HoldingIn.model_validate(h, from_attributes=True) for h in rows(Holding)],
        credit_cards=[CreditCardIn.model_validate(c, from_attributes=True) for c in rows(CreditCard)],
    )


def export_company(db: Session, company: Company) -> XCompany:
    cid = company.id
    months: dict[int, list[XRevenueShareMonth]] = {}
    for m in db.scalars(
        select(RevenueShareMonth)
        .join(RevenueShare, RevenueShare.id == RevenueShareMonth.revenue_share_id)
        .where(RevenueShare.company_id == cid)
        .order_by(RevenueShareMonth.month)
    ):
        months.setdefault(m.revenue_share_id, []).append(XRevenueShareMonth(month=m.month, revenue=m.revenue))
    shares = db.scalars(select(RevenueShare).where(RevenueShare.company_id == cid).order_by(RevenueShare.id))
    entries = db.scalars(select(CompanyEntry).where(CompanyEntry.company_id == cid).order_by(CompanyEntry.id))
    return XCompany(
        name=company.name,
        description=company.description,
        members=[XMember.model_validate(m, from_attributes=True) for m in company.members],
        products=[XProduct.model_validate(p, from_attributes=True) for p in company.products],
        revenue_shares=[
            XRevenueShare.model_validate(s, from_attributes=True).model_copy(update={"months": months.get(s.id, [])})
            for s in shares
        ],
        entries=[CompanyEntryIn.model_validate(e, from_attributes=True) for e in entries],
    )


def build_export(db: Session, household: Household | None, companies: list[Company]) -> ExportFile:
    return ExportFile(
        exported_at=datetime.now(timezone.utc),
        household=export_household(db, household) if household else None,
        companies=[export_company(db, c) for c in companies],
    )


# ---------- Import ----------

def _ref(mapping: dict[int, int], old: int | None, what: str) -> int | None:
    if old is None:
        return None
    if old not in mapping:
        raise HTTPException(400, f"The file is damaged: it refers to a {what} it doesn't contain (id {old})")
    return mapping[old]


def household_is_empty(db: Session, household_id: int) -> bool:
    scoped = [Account, BudgetItem, Transaction, StatementImport, ImportRule, MonthSetting, Holding, CreditCard]
    return not any(
        db.scalar(select(exists().where(model.household_id == household_id))) for model in scoped
    )


def import_household(db: Session, household: Household, data: XHousehold) -> None:
    hid = household.id
    if not household_is_empty(db, hid):
        raise HTTPException(
            409, "This household already has data. A household can only be imported into an empty one."
        )
    # Replace the default categories (nothing uses them yet) with the file's.
    for category in db.scalars(select(Category).where(Category.household_id == hid)):
        db.delete(category)
    db.flush()
    household.name = data.name
    household.timezone = data.timezone

    categories: dict[int, int] = {}
    for c in data.categories:
        row = Category(household_id=hid, **c.model_dump(exclude={"id"}))
        db.add(row)
        db.flush()
        categories[c.id] = row.id

    accounts: dict[int, int] = {}
    for a in data.accounts:
        row = Account(household_id=hid, **a.model_dump(exclude={"id", "balances"}))
        db.add(row)
        db.flush()
        accounts[a.id] = row.id
        for b in a.balances:
            snapshot = BalanceSnapshot(account_id=row.id, month=b.month.replace(day=1), balance=b.balance)
            if b.updated_at is not None:
                snapshot.updated_at = b.updated_at  # keeps month-end finalizing as it was
            db.add(snapshot)

    for i in data.budget_items:
        item = BudgetItem(
            household_id=hid, category_id=_ref(categories, i.category_id, "category"),
            **i.model_dump(exclude={"category_id", "deductions"}),
        )
        item.deductions = [
            PaycheckDeduction(
                name=d.name, type=d.type, pre_tax=d.pre_tax and d.type != DeductionType.tax, amount=d.amount, position=n
            )
            for n, d in enumerate(i.deductions)
        ]
        db.add(item)

    imports: dict[int, int] = {}
    for s in data.statement_imports:
        row = StatementImport(
            household_id=hid,
            bank=s.bank,
            file_name=s.file_name,
            period_start=s.period_start,
            period_end=s.period_end,
            accounts=[
                a.model_dump() | {"account_id": _ref(accounts, a.account_id, "account")} for a in s.accounts
            ],
            skipped_keys=s.skipped_keys,
        )
        if s.created_at is not None:
            row.created_at = s.created_at
        db.add(row)
        db.flush()
        imports[s.id] = row.id

    for t in data.transactions:
        db.add(
            Transaction(
                household_id=hid,
                category_id=_ref(categories, t.category_id, "category"),
                account_id=_ref(accounts, t.account_id, "account"),
                statement_import_id=_ref(imports, t.statement_import_id, "statement import"),
                **t.model_dump(exclude={"category_id", "account_id", "statement_import_id"}),
            )
        )

    for r in data.import_rules:
        db.add(
            ImportRule(
                household_id=hid, category_id=_ref(categories, r.category_id, "category"),
                **r.model_dump(exclude={"category_id"}),
            )
        )
    for m in data.month_settings:
        db.add(MonthSetting(household_id=hid, month=m.month.replace(day=1), totals_from=m.totals_from, notes=m.notes))
    for h in data.holdings:
        holding = Holding(
            household_id=hid, account_id=_ref(accounts, h.account_id, "account"), **h.model_dump(exclude={"account_id"})
        )
        if holding.asset_type == AssetType.cash:
            holding.ticker, holding.cost_per_unit = CASH_TICKER, None
        else:
            holding.ticker = holding.ticker.strip().upper()
        db.add(holding)
    for c in data.credit_cards:
        db.add(CreditCard(household_id=hid, **c.model_dump()))
    db.flush()


def import_company(db: Session, user: User, data: XCompany) -> Company:
    taken = db.scalar(
        select(exists().where(
            CompanyAccess.company_id == Company.id,
            CompanyAccess.user_id == user.id,
            func.lower(Company.name) == data.name.lower(),
        ))
    )
    if taken:
        raise HTTPException(409, f"You already have a company named '{data.name}'. Rename it first, then import.")
    company = Company(name=data.name, description=data.description, created_by_id=user.id)
    db.add(company)
    db.flush()
    db.add(CompanyAccess(company_id=company.id, user_id=user.id, role=AccessRole.owner))
    db.flush()
    cid = company.id

    members: dict[int, int] = {}
    for m in data.members:
        row = CompanyMember(company_id=cid, **m.model_dump(exclude={"id"}))
        db.add(row)
        db.flush()
        members[m.id] = row.id
    products: dict[int, int] = {}
    for p in data.products:
        row = CompanyProduct(company_id=cid, **p.model_dump(exclude={"id"}))
        db.add(row)
        db.flush()
        products[p.id] = row.id
    shares: dict[int, int] = {}
    for s in data.revenue_shares:
        row = RevenueShare(
            company_id=cid, product_id=_ref(products, s.product_id, "product"),
            **s.model_dump(exclude={"id", "product_id", "months"}),
        )
        db.add(row)
        db.flush()
        shares[s.id] = row.id
        for m in s.months:
            db.add(RevenueShareMonth(revenue_share_id=row.id, month=m.month.replace(day=1), revenue=m.revenue))
    for e in data.entries:
        db.add(
            CompanyEntry(
                company_id=cid,
                member_id=_ref(members, e.member_id, "member"),
                product_id=_ref(products, e.product_id, "product"),
                revenue_share_id=_ref(shares, e.revenue_share_id, "revenue share"),
                **e.model_dump(exclude={"member_id", "product_id", "revenue_share_id"}),
            )
        )
    db.flush()
    return company


def import_file(db: Session, user: User, household: Household | None, data: ExportFile) -> ImportResult:
    """Import everything in the file, or nothing. `household` is where its household goes (None when the
    importer can't write to one, which is only allowed if the file has no household)."""
    if data.household is not None and household is None:
        raise HTTPException(403, "Only a household's owner can import into it")
    try:
        if data.household is not None:
            import_household(db, household, data.household)
        names = [import_company(db, user, c).name for c in data.companies]
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "The file is damaged: it has duplicate rows (two of the same name, month or line)")
    except HTTPException:
        db.rollback()
        raise
    h = data.household
    return ImportResult(
        household=h is not None,
        companies=names,
        transactions=len(h.transactions) if h else 0,
        entries=sum(len(c.entries) for c in data.companies),
        holdings=len(h.holdings) if h else 0,
    )
