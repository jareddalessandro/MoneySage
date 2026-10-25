from datetime import date
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import extract, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Company,
    CompanyEntry,
    CompanyEntryKind,
    CompanyMember,
    CompanyProduct,
    RevenueShare,
    RevenueShareBasis,
    RevenueShareMonth,
)
from app.months import format_month, parse_month
from app.schemas import (
    CompanyEntryIn,
    CompanyEntryOut,
    CompanyIn,
    CompanyListItem,
    CompanyMemberIn,
    CompanyMemberOut,
    CompanyMemberSummary,
    CompanyMonth,
    CompanyOut,
    CompanyProductIn,
    CompanyProductOut,
    CompanyProductSummary,
    CompanySummary,
    RevenueShareIn,
    RevenueShareMonthOut,
    RevenueShareMonthsUpdate,
    RevenueShareOut,
)
from app.services import revenue_shares
from app.services.company_statements import (
    build_statements,
    file_name,
    product_breakdown,
    render_pdf,
    render_xlsx,
)

router = APIRouter(prefix="/api/companies", tags=["companies"])

YEAR = Query(default=None, ge=1900, le=2200, description="Defaults to the current year")
ZERO = Decimal(0)


def get_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


def get_member(db: Session, company_id: int, member_id: int) -> CompanyMember:
    member = db.get(CompanyMember, member_id)
    if member is None or member.company_id != company_id:
        raise HTTPException(404, "Member not found")
    return member


def get_product(db: Session, company_id: int, product_id: int) -> CompanyProduct:
    product = db.get(CompanyProduct, product_id)
    if product is None or product.company_id != company_id:
        raise HTTPException(404, "Product not found")
    return product


def get_share(db: Session, company_id: int, share_id: int) -> RevenueShare:
    share = db.get(RevenueShare, share_id)
    if share is None or share.company_id != company_id:
        raise HTTPException(404, "Revenue share not found")
    return share


def get_entry(db: Session, company_id: int, entry_id: int) -> CompanyEntry:
    entry = db.get(CompanyEntry, entry_id)
    if entry is None or entry.company_id != company_id:
        raise HTTPException(404, "Entry not found")
    return entry


def _commit_unique(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, message)


def _year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year + 1, 1, 1)


def _totals_by_kind(db: Session, company_id: int, year: int) -> dict[CompanyEntryKind, Decimal]:
    start, end = _year_bounds(year)
    rows = db.execute(
        select(CompanyEntry.kind, func.sum(CompanyEntry.amount))
        .where(CompanyEntry.company_id == company_id, CompanyEntry.date >= start, CompanyEntry.date < end)
        .group_by(CompanyEntry.kind)
    ).all()
    return {kind: total for kind, total in rows}


MEMBER_KINDS = (CompanyEntryKind.contribution, CompanyEntryKind.distribution)


def _all_time_total(db: Session, company_id: int, kind: CompanyEntryKind) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(CompanyEntry.amount), 0)).where(
            CompanyEntry.company_id == company_id, CompanyEntry.kind == kind
        )
    )


# ---------- Companies ----------

@router.get("", response_model=list[CompanyListItem])
def list_companies(year: int | None = YEAR, db: Session = Depends(get_db)):
    year = year or date.today().year
    items = []
    start, end = _year_bounds(year)
    for company in db.scalars(select(Company).order_by(Company.name)).all():
        totals = _totals_by_kind(db, company.id, year)
        income = totals.get(CompanyEntryKind.income, ZERO)
        repaid = revenue_shares.repayments(db, company.id)
        repaid_ids = db.scalars(select(CompanyEntry.id).where(
            CompanyEntry.company_id == company.id, CompanyEntry.id.in_(list(repaid)),CompanyEntry.date >= start,
            CompanyEntry.date < end,
        )) if repaid else []
        expenses = totals.get(CompanyEntryKind.expense, ZERO) - sum((repaid[i] for i in repaid_ids), ZERO)
        items.append(CompanyListItem(
            id=company.id,
            name=company.name,
            description=company.description,
            members=company.members,
            year=year,
            income=income,
            expenses=expenses,
            net=income - expenses,
            contributions_total=_all_time_total(db, company.id, CompanyEntryKind.contribution),
            distributions_total=_all_time_total(db, company.id, CompanyEntryKind.distribution),
        ))
    return items


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, db: Session = Depends(get_db)):
    company = Company(**body.model_dump())
    db.add(company)
    _commit_unique(db, f"A company named '{body.name}' already exists")
    return company


@router.get("/{company_id}", response_model=CompanyOut)
def read_company(company_id: int, db: Session = Depends(get_db)):
    return get_company(db, company_id)


@router.put("/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyIn, db: Session = Depends(get_db)):
    company = get_company(db, company_id)
    for key, value in body.model_dump().items():
        setattr(company, key, value)
    _commit_unique(db, f"A company named '{body.name}' already exists")
    return company


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = get_company(db, company_id)
    # Entries go first, then revenue shares: they reference members, products and shares, which would
    # otherwise block the company's cascade.
    for entry in db.scalars(select(CompanyEntry).where(CompanyEntry.company_id == company_id)):
        db.delete(entry)
    db.flush()
    for share in db.scalars(select(RevenueShare).where(RevenueShare.company_id == company_id)):
        db.delete(share)
    db.flush()
    db.delete(company)
    db.commit()


# ---------- Members ----------

def _check_equity(db: Session, company: Company, body: CompanyMemberIn, member_id: int | None) -> None:
    others = sum((m.equity_percent for m in company.members if m.id != member_id), ZERO)
    total = others + body.equity_percent
    if total > 100:
        available = 100 - others
        raise HTTPException(
            400, f"Ownership would total {total.normalize():f}%. {body.name} can have at most {available.normalize():f}%."
        )


@router.post("/{company_id}/members", response_model=CompanyMemberOut, status_code=201)
def create_member(company_id: int, body: CompanyMemberIn, db: Session = Depends(get_db)):
    company = get_company(db, company_id)
    _check_equity(db, company, body, None)
    member = CompanyMember(company_id=company_id, **body.model_dump())
    db.add(member)
    _commit_unique(db, f"{body.name} is already a member")
    return member


@router.put("/{company_id}/members/{member_id}", response_model=CompanyMemberOut)
def update_member(company_id: int, member_id: int, body: CompanyMemberIn, db: Session = Depends(get_db)):
    company = get_company(db, company_id)
    member = get_member(db, company_id, member_id)
    _check_equity(db, company, body, member_id)
    for key, value in body.model_dump().items():
        setattr(member, key, value)
    _commit_unique(db, f"{body.name} is already a member")
    return member


@router.delete("/{company_id}/members/{member_id}", status_code=204)
def delete_member(company_id: int, member_id: int, db: Session = Depends(get_db)):
    member = get_member(db, company_id, member_id)
    if db.scalar(select(func.count()).where(CompanyEntry.member_id == member_id)):
        raise HTTPException(
            409, f"{member.name} has contributions or distributions. Delete or reassign them first."
        )
    db.delete(member)
    db.commit()


# ---------- Products ----------

@router.post("/{company_id}/products", response_model=CompanyProductOut, status_code=201)
def create_product(company_id: int, body: CompanyProductIn, db: Session = Depends(get_db)):
    get_company(db, company_id)
    product = CompanyProduct(company_id=company_id, **body.model_dump())
    db.add(product)
    _commit_unique(db, f"There's already a product named '{body.name}'")
    return product


@router.put("/{company_id}/products/{product_id}", response_model=CompanyProductOut)
def update_product(company_id: int, product_id: int, body: CompanyProductIn, db: Session = Depends(get_db)):
    product = get_product(db, company_id, product_id)
    for key, value in body.model_dump().items():
        setattr(product, key, value)
    _commit_unique(db, f"There's already a product named '{body.name}'")
    return product


@router.delete("/{company_id}/products/{product_id}", status_code=204)
def delete_product(company_id: int, product_id: int, db: Session = Depends(get_db)):
    product = get_product(db, company_id, product_id)
    entries = db.scalar(select(func.count()).where(CompanyEntry.product_id == product_id))
    shares = db.scalar(select(func.count()).where(RevenueShare.product_id == product_id))
    if entries or shares:
        used = " and ".join(
            text for text in (
                f"{entries} {'entry' if entries == 1 else 'entries'}" if entries else "",
                f"{shares} revenue {'share' if shares == 1 else 'shares'}" if shares else "",
            ) if text
        )
        raise HTTPException(409, f"{product.name} is used by {used}. Move them to another product first.")
    db.delete(product)
    db.commit()


# ---------- Entries ----------

def _apply(db: Session, company_id: int, entry: CompanyEntry, body: CompanyEntryIn) -> None:
    data = body.model_dump()
    if body.kind in MEMBER_KINDS:
        if body.member_id is None:
            raise HTTPException(400, f"Pick the member for this {body.kind.value}")
        get_member(db, company_id, body.member_id)
        data["category"] = None
        data["product_id"] = None
    elif body.kind == CompanyEntryKind.funding:
        # Funding belongs to an agreement, not a category or product.
        if body.revenue_share_id is None:
            raise HTTPException(400, "Pick the revenue share this funding is for")
        data.update(member_id=None, category=None, product_id=None)
    else:
        # Only contributions and distributions belong to a member.
        data["member_id"] = None
        if body.product_id is not None:
            get_product(db, company_id, body.product_id)
    if body.kind in (CompanyEntryKind.expense, CompanyEntryKind.funding) and body.revenue_share_id is not None:
        get_share(db, company_id, body.revenue_share_id)
    else:
        # Only a payment (an expense) or funding links to a revenue share.
        data["revenue_share_id"] = None
    for key, value in data.items():
        setattr(entry, key, value)


@router.get("/{company_id}/entries", response_model=list[CompanyEntryOut])
def list_entries(company_id: int, year: int | None = YEAR, db: Session = Depends(get_db)):
    get_company(db, company_id)
    start, end = _year_bounds(year or date.today().year)
    entries = db.scalars(
        select(CompanyEntry)
        .where(CompanyEntry.company_id == company_id, CompanyEntry.date >= start, CompanyEntry.date < end)
        .order_by(CompanyEntry.date.desc(), CompanyEntry.id.desc())
    ).all()
    repaid = revenue_shares.repayments(db, company_id)
    return [
        CompanyEntryOut.model_validate(e).model_copy(update={"funding_repaid": repaid.get(e.id)}) for e in entries
    ]


@router.post("/{company_id}/entries", response_model=CompanyEntryOut, status_code=201)
def create_entry(company_id: int, body: CompanyEntryIn, db: Session = Depends(get_db)):
    get_company(db, company_id)
    entry = CompanyEntry(company_id=company_id)
    _apply(db, company_id, entry, body)
    db.add(entry)
    db.commit()
    return entry


@router.put("/{company_id}/entries/{entry_id}", response_model=CompanyEntryOut)
def update_entry(company_id: int, entry_id: int, body: CompanyEntryIn, db: Session = Depends(get_db)):
    entry = get_entry(db, company_id, entry_id)
    _apply(db, company_id, entry, body)
    db.commit()
    return entry


@router.delete("/{company_id}/entries/{entry_id}", status_code=204)
def delete_entry(company_id: int, entry_id: int, db: Session = Depends(get_db)):
    db.delete(get_entry(db, company_id, entry_id))
    db.commit()


# ---------- Summary ----------

@router.get("/{company_id}/summary", response_model=CompanySummary)
def company_summary(company_id: int, year: int | None = YEAR, db: Session = Depends(get_db)):
    company = get_company(db, company_id)
    year = year or date.today().year
    start, end = _year_bounds(year)
    in_year = (CompanyEntry.company_id == company_id, CompanyEntry.date >= start, CompanyEntry.date < end)

    totals = _totals_by_kind(db, company_id, year)
    year_entries = db.scalars(
        select(CompanyEntry).where(*in_year, CompanyEntry.kind.in_((CompanyEntryKind.income, CompanyEntryKind.expense)))
    ).all()
    # The part of revenue-share payments that repays funding isn't an expense.
    repaid = revenue_shares.repayments(db, company_id)
    repaid_year = {e.id: repaid[e.id] for e in year_entries if e.id in repaid}
    funding_repaid = sum(repaid_year.values(), ZERO)

    income = totals.get(CompanyEntryKind.income, ZERO)
    expenses = totals.get(CompanyEntryKind.expense, ZERO) - funding_repaid
    net = income - expenses

    cost_cats = revenue_shares.cost_categories(db, company_id)
    cost_of_revenue = sum(
        (revenue_shares.expensed(e, repaid) for e in year_entries if revenue_shares.is_cost_of_revenue(e, cost_cats)),
        ZERO,
    )

    monthly = {m: {CompanyEntryKind.income: ZERO, CompanyEntryKind.expense: ZERO} for m in range(1, 13)}
    for e in year_entries:
        monthly[e.date.month][e.kind] += revenue_shares.expensed(e, repaid) if e.kind == CompanyEntryKind.expense \
            else e.amount

    def by_member(kind: CompanyEntryKind, *where) -> dict[int, Decimal]:
        return dict(db.execute(
            select(CompanyEntry.member_id, func.sum(CompanyEntry.amount))
            .where(CompanyEntry.company_id == company_id, CompanyEntry.kind == kind, *where)
            .group_by(CompanyEntry.member_id)
        ).all())

    this_year = (CompanyEntry.date >= start, CompanyEntry.date < end)
    contributed_year = by_member(CompanyEntryKind.contribution, *this_year)
    contributed_total = by_member(CompanyEntryKind.contribution)
    distributed_year = by_member(CompanyEntryKind.distribution, *this_year)
    distributed_total = by_member(CompanyEntryKind.distribution)

    year_col = extract("year", CompanyEntry.date)
    years = db.scalars(
        select(year_col).where(CompanyEntry.company_id == company_id).group_by(year_col).order_by(year_col.desc())
    ).all()

    def categories(kind: CompanyEntryKind) -> list[str]:
        return list(db.scalars(
            select(CompanyEntry.category)
            .where(CompanyEntry.company_id == company_id, CompanyEntry.kind == kind, CompanyEntry.category.is_not(None))
            .group_by(CompanyEntry.category)
            .order_by(func.lower(CompanyEntry.category))
        ))

    return CompanySummary(
        company_id=company_id,
        year=year,
        income=income,
        expenses=expenses,
        net=net,
        contributions_year=totals.get(CompanyEntryKind.contribution, ZERO),
        contributions_total=sum(contributed_total.values(), ZERO),
        distributions_year=totals.get(CompanyEntryKind.distribution, ZERO),
        distributions_total=sum(distributed_total.values(), ZERO),
        equity_assigned=sum((m.equity_percent for m in company.members), ZERO),
        cost_of_revenue=cost_of_revenue,
        funding_received=totals.get(CompanyEntryKind.funding, ZERO),
        funding_repaid=funding_repaid,
        months=[
            CompanyMonth(
                month=format_month(date(year, m, 1)),
                income=v[CompanyEntryKind.income],
                expenses=v[CompanyEntryKind.expense],
            )
            for m, v in monthly.items()
        ],
        members=[
            CompanyMemberSummary(
                member_id=m.id,
                name=m.name,
                equity_percent=m.equity_percent,
                contributed_year=contributed_year.get(m.id, ZERO),
                contributed_total=contributed_total.get(m.id, ZERO),
                distributed_year=distributed_year.get(m.id, ZERO),
                distributed_total=distributed_total.get(m.id, ZERO),
                profit_share=(net * m.equity_percent / 100).quantize(Decimal("0.01")),
            )
            for m in company.members
        ],
        products=[
            CompanyProductSummary(
                product_id=r.product_id,
                name=r.name,
                income=r.income,
                cost_of_revenue=r.cost_of_revenue,
                other_expenses=r.other_expenses,
                net=r.net,
            )
            for r in product_breakdown(year_entries, company.products, cost_cats, repaid)
        ],
        years=[int(y) for y in years],
        income_categories=categories(CompanyEntryKind.income),
        expense_categories=categories(CompanyEntryKind.expense),
    )


# ---------- Revenue shares ----------

def _share_out(db: Session, share: RevenueShare, year: int) -> RevenueShareOut:
    t = revenue_shares.totals(db, share, year)
    product = db.get(CompanyProduct, share.product_id) if share.product_id else None
    funding = t.funding or revenue_shares.FundingRoll()
    return RevenueShareOut.model_validate(share).model_copy(update=dict(
        funding_received=funding.beginning + funding.received,
        funding_repaid=funding.repaid,
        funding_outstanding=funding.ending,
        terms=revenue_shares.describe(share, product.name if product else None),
        earned_year=t.earned_year,
        paid_year=t.paid_year,
        earned_total=t.earned_total,
        paid_total=t.paid_total,
        balance_due=t.balance_due,
        missing_months=[format_month(m) for m in t.missing_months],
    ))


def _apply_share(db: Session, company_id: int, share: RevenueShare, body: RevenueShareIn) -> None:
    data = body.model_dump()
    if body.product_id is not None:
        get_product(db, company_id, body.product_id)
    if body.basis == RevenueShareBasis.reported:
        data["deduct_categories"] = []  # fees only apply to recorded income
    for key, value in data.items():
        setattr(share, key, value)


@router.get("/{company_id}/revenue-shares", response_model=list[RevenueShareOut])
def list_revenue_shares(company_id: int, year: int | None = YEAR, db: Session = Depends(get_db)):
    get_company(db, company_id)
    year = year or date.today().year
    shares = db.scalars(
        select(RevenueShare).where(RevenueShare.company_id == company_id).order_by(RevenueShare.payee, RevenueShare.id)
    )
    return [_share_out(db, s, year) for s in shares]


@router.post("/{company_id}/revenue-shares", response_model=RevenueShareOut, status_code=201)
def create_revenue_share(company_id: int, body: RevenueShareIn, db: Session = Depends(get_db)):
    get_company(db, company_id)
    share = RevenueShare(company_id=company_id)
    _apply_share(db, company_id, share, body)
    db.add(share)
    db.commit()
    return _share_out(db, share, date.today().year)


@router.put("/{company_id}/revenue-shares/{share_id}", response_model=RevenueShareOut)
def update_revenue_share(company_id: int, share_id: int, body: RevenueShareIn, db: Session = Depends(get_db)):
    share = get_share(db, company_id, share_id)
    _apply_share(db, company_id, share, body)
    db.commit()
    return _share_out(db, share, date.today().year)


@router.delete("/{company_id}/revenue-shares/{share_id}", status_code=204)
def delete_revenue_share(company_id: int, share_id: int, db: Session = Depends(get_db)):
    share = get_share(db, company_id, share_id)
    if db.scalar(select(func.count()).where(CompanyEntry.revenue_share_id == share_id)):
        raise HTTPException(409, f"Payments to or funding from {share.payee} are recorded. Delete those entries first.")
    db.delete(share)
    db.commit()


@router.get("/{company_id}/revenue-shares/{share_id}/months", response_model=list[RevenueShareMonthOut])
def revenue_share_months(company_id: int, share_id: int, year: int | None = YEAR, db: Session = Depends(get_db)):
    """Each month of the year since the agreement started, through the current month."""
    share = get_share(db, company_id, share_id)
    year = year or date.today().year
    today = date.today()
    rows = revenue_shares.monthly(db, share, min(date(year, 12, 31), today))
    return [
        RevenueShareMonthOut(
            month=format_month(r.month), revenue=r.revenue, deductions=r.deductions, base=r.base,
            earned=r.earned, paid=r.paid, balance=r.balance,
        )
        for r in rows if r.month.year == year
    ]


@router.put("/{company_id}/revenue-shares/{share_id}/months", status_code=204)
def set_revenue_share_months(
    company_id: int, share_id: int, body: RevenueShareMonthsUpdate, db: Session = Depends(get_db)
):
    """Reported basis only: set (or, with a null revenue, clear) the revenue for each listed month."""
    share = get_share(db, company_id, share_id)
    if share.basis != RevenueShareBasis.reported:
        raise HTTPException(400, f"{share.payee}'s share is calculated from recorded income")
    existing = {
        r.month: r for r in db.scalars(select(RevenueShareMonth).where(RevenueShareMonth.revenue_share_id == share_id))
    }
    for item in body.months:
        month = parse_month(item.month)
        row = existing.get(month)
        if item.revenue is None:
            if row is not None:
                db.delete(row)
                del existing[month]
        elif row is None:
            existing[month] = RevenueShareMonth(revenue_share_id=share_id, month=month, revenue=item.revenue)
            db.add(existing[month])
        else:
            row.revenue = item.revenue
    db.commit()


MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _download(content: bytes, name: str, format: str) -> Response:
    return Response(
        content,
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"},
    )


@router.get("/{company_id}/revenue-shares/{share_id}/statement")
def export_payee_statement(
    company_id: int,
    share_id: int,
    month: str = Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    format: Literal["pdf", "xlsx"] = "pdf",
    db: Session = Depends(get_db),
):
    """A monthly statement to send the payee: the month's revenue and share, payments, the balance due,
    and the year to date by month."""
    company = get_company(db, company_id)
    share = get_share(db, company_id, share_id)
    try:
        st = revenue_shares.build_payee_statement(db, company, share, parse_month(month))
    except ValueError as e:
        raise HTTPException(400, str(e))
    render = revenue_shares.render_payee_pdf if format == "pdf" else revenue_shares.render_payee_xlsx
    return _download(render(st), revenue_shares.payee_file_name(st, format), format)


# ---------- Year-end statements ----------


@router.get("/{company_id}/statements")
def export_statements(
    company_id: int,
    year: int | None = YEAR,
    format: Literal["pdf", "xlsx"] = "pdf",
    db: Session = Depends(get_db),
):
    """Income statement, members' capital, cash summary and transaction detail for one year, as a download.

    For the current year it covers January 1 through today and is labeled year to date.
    """
    company = get_company(db, company_id)
    st = build_statements(db, company, year or date.today().year)
    content = render_pdf(st) if format == "pdf" else render_xlsx(st)
    return _download(content, file_name(st, format), format)
