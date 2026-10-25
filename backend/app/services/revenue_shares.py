"""Revenue-share agreements: what a payee earns each month, what's been paid, and what's still due.

- Income basis: the rate applies to the company's recorded income in the agreement's dates (one
  product's, if the agreement names one), less expenses in its `deduct_categories` (platform fees).
- Reported basis: the rate applies to revenue entered by hand for each month.

A month's base never goes below $0, and each month's share is rounded to the cent. Payments are
expense entries linked by `revenue_share_id`. Cash basis: an earned share is only an expense once paid.

Funding: money a payee paid the company for their share (a `funding` entry) is a liability for the sale
of future revenue, not income. Payments to that payee repay it first, in date order; only the part of a
payment beyond what's still owed is an expense. See `repayments`.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    CompanyEntry,
    CompanyEntryKind,
    CompanyProduct,
    RevenueShare,
    RevenueShareBasis,
    RevenueShareMonth,
)
from app.months import add_months
from app.services.documents import PdfKit, XlsxKit, money, pct

ZERO = Decimal(0)
CENT = Decimal("0.01")


@dataclass
class ShareMonth:
    month: date  # first of the month
    revenue: Decimal | None  # None: reported basis with nothing entered
    deductions: Decimal
    earned: Decimal
    paid: Decimal
    balance: Decimal = ZERO  # due at the end of the month

    @property
    def base(self) -> Decimal:
        return max((self.revenue or ZERO) - self.deductions, ZERO)


@dataclass
class Payment:
    date: date
    description: str
    amount: Decimal


@dataclass
class FundingRoll:
    """Funding from one payee over a period: the liability at its start, received, repaid, and at its end."""

    beginning: Decimal = ZERO
    received: Decimal = ZERO
    repaid: Decimal = ZERO

    @property
    def ending(self) -> Decimal:
        return self.beginning + self.received - self.repaid


@dataclass
class ShareTotals:
    earned_year: Decimal
    paid_year: Decimal
    earned_total: Decimal
    paid_total: Decimal
    balance_due: Decimal
    missing_months: list[date] = field(default_factory=list)
    funding: FundingRoll | None = None  # all time through today; None if no funding was received


def share_of(base: Decimal, rate_percent: Decimal) -> Decimal:
    return (base * rate_percent / 100).quantize(CENT, ROUND_HALF_UP)


def _month(d: date) -> date:
    return d.replace(day=1)


def payments(db: Session, share: RevenueShare, through: date) -> list[Payment]:
    return [
        Payment(e.date, e.description, e.amount)
        for e in db.scalars(
            select(CompanyEntry)
            .where(
                CompanyEntry.revenue_share_id == share.id,
                CompanyEntry.kind == CompanyEntryKind.expense,
                CompanyEntry.date <= through,
            )
            .order_by(CompanyEntry.date, CompanyEntry.id)
        )
    ]


def repayments(db: Session, company_id: int) -> dict[int, Decimal]:
    """How much of each revenue-share payment repays funding from that payee, by entry id.

    Per agreement, entries are taken in date order (funding before payments on the same day). Each payment
    repays as much of the funding still owed as it can; the rest of it is an expense. Funding that arrives
    after earlier funding was repaid starts a new balance, and earlier payments stay expenses.
    """
    entries = db.scalars(
        select(CompanyEntry).where(
            CompanyEntry.company_id == company_id,
            CompanyEntry.revenue_share_id.is_not(None),
            CompanyEntry.kind.in_((CompanyEntryKind.funding, CompanyEntryKind.expense)),
        )
    ).all()
    owed: dict[int, Decimal] = defaultdict(lambda: ZERO)
    repaid: dict[int, Decimal] = {}
    for e in sorted(entries, key=lambda e: (e.date, e.kind != CompanyEntryKind.funding, e.id)):
        if e.kind == CompanyEntryKind.funding:
            owed[e.revenue_share_id] += e.amount
        elif (part := min(e.amount, owed[e.revenue_share_id])) > 0:
            repaid[e.id] = part
            owed[e.revenue_share_id] -= part
    return repaid


def expensed(entry: CompanyEntry, repaid: dict[int, Decimal]) -> Decimal:
    """The part of an expense entry that's an expense: all of it, unless some of it repays funding."""
    return entry.amount - repaid.get(entry.id, ZERO)


def funding_roll(
    db: Session, share: RevenueShare, start: date, end: date, repaid: dict[int, Decimal] | None = None
) -> FundingRoll | None:
    """The funding liability for one agreement between two dates (inclusive). None if no funding was
    received by `end`."""
    entries = db.scalars(
        select(CompanyEntry).where(
            CompanyEntry.revenue_share_id == share.id,
            CompanyEntry.kind.in_((CompanyEntryKind.funding, CompanyEntryKind.expense)),
            CompanyEntry.date <= end,
        )
    ).all()
    if not any(e.kind == CompanyEntryKind.funding for e in entries):
        return None
    if repaid is None:
        repaid = repayments(db, share.company_id)
    roll = FundingRoll()
    for e in entries:
        funding = e.kind == CompanyEntryKind.funding
        amount = e.amount if funding else repaid.get(e.id, ZERO)
        if e.date < start:
            roll.beginning += amount if funding else -amount
        elif funding:
            roll.received += amount
        else:
            roll.repaid += amount
    return roll


def monthly(db: Session, share: RevenueShare, through: date) -> list[ShareMonth]:
    """One row per month from the agreement's start month through `through`'s month.

    Income and fees count from the start date to the end date (if any), up to `through`. Payments count up
    to `through`; any dated before the start month land in the first month.
    """
    first, last = _month(share.start_date), _month(through)
    if last < first:
        return []
    window_end = min(share.end_date or through, through)
    end_month = _month(window_end)

    revenue: dict[date, Decimal] = defaultdict(lambda: ZERO)
    deductions: dict[date, Decimal] = defaultdict(lambda: ZERO)
    entered: set[date] = set()
    if share.basis == RevenueShareBasis.income:
        query = select(CompanyEntry).where(
            CompanyEntry.company_id == share.company_id,
            CompanyEntry.kind.in_((CompanyEntryKind.income, CompanyEntryKind.expense)),
            CompanyEntry.date >= share.start_date,
            CompanyEntry.date <= window_end,
        )
        if share.product_id is not None:
            query = query.where(CompanyEntry.product_id == share.product_id)
        fees = {c.lower() for c in share.deduct_categories}
        for e in db.scalars(query):
            if e.kind == CompanyEntryKind.income:
                revenue[_month(e.date)] += e.amount
            elif e.category and e.category.lower() in fees:
                deductions[_month(e.date)] += e.amount
    else:
        for row in db.scalars(
            select(RevenueShareMonth).where(
                RevenueShareMonth.revenue_share_id == share.id,
                RevenueShareMonth.month >= first,
                RevenueShareMonth.month <= end_month,
            )
        ):
            revenue[row.month] = row.revenue
            entered.add(row.month)

    paid: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for p in payments(db, share, through):
        paid[max(_month(p.date), first)] += p.amount

    rows, balance, month = [], ZERO, first
    while month <= last:
        active = month <= end_month and window_end >= share.start_date
        if share.basis == RevenueShareBasis.reported:
            month_revenue = revenue[month] if active and month in entered else None
        else:
            month_revenue = revenue[month] if active else ZERO
        row = ShareMonth(month, month_revenue, deductions[month], ZERO, paid[month])
        row.earned = share_of(row.base, share.rate_percent)
        balance += row.earned - row.paid
        row.balance = balance
        rows.append(row)
        month = add_months(month, 1)
    return rows


def totals(db: Session, share: RevenueShare, year: int, today: date | None = None) -> ShareTotals:
    today = today or date.today()
    rows = monthly(db, share, today)
    in_year = [r for r in rows if r.month.year == year]
    missing = []
    if share.basis == RevenueShareBasis.reported:
        end_month = _month(share.end_date) if share.end_date else None
        missing = [
            r.month for r in rows
            if r.revenue is None and r.month < _month(today) and (end_month is None or r.month <= end_month)
        ]
    return ShareTotals(
        earned_year=sum((r.earned for r in in_year), ZERO),
        paid_year=sum((r.paid for r in in_year), ZERO),
        earned_total=sum((r.earned for r in rows), ZERO),
        paid_total=sum((r.paid for r in rows), ZERO),
        balance_due=rows[-1].balance if rows else ZERO,
        missing_months=missing,
        funding=funding_roll(db, share, date.min, today),
    )


def cost_categories(db: Session, company_id: int) -> set[str]:
    """Lowercased expense categories that count as cost of revenue: every agreement's payment category and
    the fee categories agreements subtract."""
    names: set[str] = set()
    for share in db.scalars(select(RevenueShare).where(RevenueShare.company_id == company_id)):
        names.add(share.category.lower())
        names.update(c.lower() for c in share.deduct_categories)
    return names


FUNDING_NOTE = (
    "Funding received from a revenue-share payee is a liability for the sale of future revenue, not income. "
    "Payments to that payee repay it first; only payments beyond it are expenses."
)


def is_cost_of_revenue(entry: CompanyEntry, cost_cats: set[str]) -> bool:
    return entry.kind == CompanyEntryKind.expense and (
        entry.revenue_share_id is not None or (entry.category or "").lower() in cost_cats
    )


def long_date(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def describe(share: RevenueShare, product_name: str | None) -> str:
    """'10% of App A revenue after App Store fees, starting January 1, 2026'."""
    rate = f"{share.rate_percent.normalize():f}%"
    if share.basis == RevenueShareBasis.income:
        text = f"{rate} of {product_name + ' revenue' if product_name else 'company revenue'}"
        if share.deduct_categories:
            text += f" after {_join(share.deduct_categories)}"
    else:
        text = f"{rate} of eligible revenue, reported monthly"
    text += f", starting {long_date(share.start_date)}"
    if share.end_date:
        text += f" through {long_date(share.end_date)}"
    return text


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ---------- Payee statement ----------

@dataclass
class PayeeStatement:
    company_name: str
    payee: str
    terms: str
    basis: RevenueShareBasis
    revenue_label: str
    rate_percent: Decimal
    deduct_categories: list[str]
    month: date
    through: date  # month end, or today for the current month
    generated: date
    opening: Decimal  # balance due at the start of the month
    current: ShareMonth
    year_to_date: list[ShareMonth]
    month_payments: list[Payment]
    funding: FundingRoll | None = None  # this month; None if the payee hasn't funded anything

    @property
    def period_label(self) -> str:
        label = f"{self.month:%B} {self.month.year}"
        return label if self.generated > self.through else f"{label}, through {long_date(self.through)}"


def build_payee_statement(
    db: Session, company: Company, share: RevenueShare, month: date, today: date | None = None
) -> PayeeStatement:
    """Raises ValueError if the month is in the future or before the agreement starts."""
    today = today or date.today()
    if month > _month(today):
        raise ValueError("That month hasn't started yet")
    if month < _month(share.start_date):
        raise ValueError(f"The agreement starts {long_date(share.start_date)}")
    through = min(add_months(month, 1) - timedelta(days=1), today)
    rows = monthly(db, share, through)
    product = db.get(CompanyProduct, share.product_id) if share.product_id else None
    if share.basis == RevenueShareBasis.income:
        revenue_label = f"{product.name} revenue" if product else "Company revenue"
    else:
        revenue_label = "Eligible revenue"
    return PayeeStatement(
        company_name=company.name,
        payee=share.payee,
        terms=describe(share, product.name if product else None),
        basis=share.basis,
        revenue_label=revenue_label,
        rate_percent=share.rate_percent,
        deduct_categories=list(share.deduct_categories),
        month=month,
        through=through,
        generated=today,
        opening=rows[-2].balance if len(rows) > 1 else ZERO,
        current=rows[-1],
        year_to_date=[r for r in rows if r.month.year == month.year],
        # Payments before the start month are counted in the first month, so they're listed there too.
        month_payments=[p for p in payments(db, share, through) if len(rows) == 1 or _month(p.date) == month],
        funding=funding_roll(db, share, month, through),
    )


def payee_file_name(st: PayeeStatement, extension: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9 ._,&()'-]+", "", f"{st.company_name} {st.payee}").strip() or "Revenue share"
    return f"{safe} revenue share {st.month:%Y-%m}.{extension}"


def render_payee_pdf(st: PayeeStatement) -> bytes:
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, TableStyle

    k = PdfKit()
    width = k.width
    cur = st.current
    rate = pct(st.rate_percent)
    fees = _join(st.deduct_categories) if st.deduct_categories else None
    story = [
        k.p("Revenue share statement", k.title),
        k.p(f"{st.company_name} · prepared for {st.payee}", k.subtitle),
        k.p(st.period_label, k.subtitle),
        Spacer(1, 4),
        k.p(f"Terms: {st.terms}.", k.small),
        k.p(f"Prepared {long_date(st.generated)} from {st.company_name}'s records.", k.small),
    ]

    rows = [["", "Amount"], [st.revenue_label, money(cur.revenue) if cur.revenue is not None else "Not entered yet"]]
    totals = []
    if fees:
        rows.append([f"Less {fees}", money(-cur.deductions)])
        rows.append(["Revenue share base", money(cur.base)])
        totals.append(len(rows) - 1)
    rows.append([f"Your share at {rate}", money(cur.earned)])
    story += [Paragraph("This month", k.heading),
              k.table(rows, [width * 0.7, width * 0.3], totals=totals, grand=[len(rows) - 1])]

    end_label = "Balance due at month end" if st.generated > st.through else f"Balance due as of {long_date(st.through)}"
    paid = sum((p.amount for p in st.month_payments), ZERO)
    rows = [
        ["", "Amount"],
        ["Balance due at start of month", money(st.opening)],
        ["Earned this month", money(cur.earned)],
        ["Payments this month", money(-paid)],
        [end_label, money(cur.balance)],
    ]
    story += [Paragraph("Account", k.heading), k.table(rows, [width * 0.7, width * 0.3], grand=[4])]

    if (f := st.funding) is not None:
        rows = [
            ["", "Amount"],
            ["Funding outstanding at start of month", money(f.beginning)],
            ["Funding received this month", money(f.received)],
            ["Repaid by payments this month", money(-f.repaid)],
            ["Funding outstanding at month end" if st.generated > st.through
             else f"Funding outstanding as of {long_date(st.through)}", money(f.ending)],
        ]
        story += [KeepTogether([
            Paragraph("Funding", k.heading),
            k.table(rows, [width * 0.7, width * 0.3], grand=[4]),
            Spacer(1, 4),
            k.p("Funding you provided is repaid by your revenue share payments until it's paid back in full.", k.small),
        ])]

    if st.month_payments:
        rows = [["Date", "Description", "Amount"]] + [
            [f"{p.date:%b} {p.date.day}, {p.date.year}", k.p(p.description), money(p.amount)]
            for p in st.month_payments
        ]
        t = k.table(rows, [width * 0.2, width * 0.55, width * 0.25])
        t.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "LEFT")]))
        story += [KeepTogether([Paragraph("Payments this month", k.heading), t])]

    head = ["Month", "Revenue"] + (["Fees", "Base"] if fees else []) + ["Earned", "Paid"]
    rows = [head]
    for r in st.year_to_date:
        rows.append(
            [f"{r.month:%B}", money(r.revenue) if r.revenue is not None else "—"]
            + ([money(-r.deductions), money(r.base)] if fees else [])
            + [money(r.earned), money(r.paid)]
        )
    ytd = st.year_to_date
    rows.append(
        ["Total", money(sum((r.revenue or ZERO for r in ytd), ZERO))]
        + ([money(-sum((r.deductions for r in ytd), ZERO)), money(sum((r.base for r in ytd), ZERO))] if fees else [])
        + [money(sum((r.earned for r in ytd), ZERO)), money(sum((r.paid for r in ytd), ZERO))]
    )
    first = width * 0.2
    story += [KeepTogether([
        Paragraph(f"{st.month.year} year to date", k.heading),
        k.table(rows, [first] + [(width - first) / (len(head) - 1)] * (len(head) - 1), grand=[len(rows) - 1]),
        Spacer(1, 4),
        k.p(f"Each month's share is {rate} of that month's base, rounded to the cent."
            + (" Eligible revenue is reported monthly by the company." if st.basis == RevenueShareBasis.reported
               else ""), k.small),
    ])]

    return k.build(story, f"{st.company_name} · {st.payee} · {st.period_label}",
                   f"{st.company_name} revenue share statement {st.month:%Y-%m}")


def render_payee_xlsx(st: PayeeStatement) -> bytes:
    k = XlsxKit(f"{st.company_name} · revenue share statement for {st.payee}", st.period_label,
                f"Terms: {st.terms}. Prepared {long_date(st.generated)}.")
    put = k.put
    cur = st.current
    fees = _join(st.deduct_categories) if st.deduct_categories else None

    ws = k.sheet("Statement", "This month", [44, 18])
    put(ws, 6, ["", "Amount"], font=k.header_font)
    put(ws, 7, [st.revenue_label, cur.revenue], money_cols=(2,))
    r = 8
    if fees:
        put(ws, 8, [f"Less {fees}", -cur.deductions], money_cols=(2,))
        put(ws, 9, ["Revenue share base", "=MAX(B7+B8,0)"], font=k.bold, border=k.top_rule, money_cols=(2,))
        r = 10
    put(ws, r, [f"Your share at {pct(st.rate_percent)}", cur.earned], font=k.bold, border=k.grand_rule,
        money_cols=(2,))
    r += 2
    put(ws, r, ["Account", None], font=k.bold, fill=k.section_fill)
    put(ws, r + 1, ["Balance due at start of month", st.opening], money_cols=(2,), indent=True)
    put(ws, r + 2, ["Earned this month", f"=B{r - 2}"], money_cols=(2,), indent=True)
    put(ws, r + 3, ["Payments this month", -sum((p.amount for p in st.month_payments), ZERO)], money_cols=(2,),
        indent=True)
    put(ws, r + 4, ["Balance due", f"=SUM(B{r + 1}:B{r + 3})"], font=k.bold, border=k.grand_rule, money_cols=(2,))
    r += 6
    if st.month_payments:
        put(ws, r, ["Payments this month", None], font=k.bold, fill=k.section_fill)
        for i, p in enumerate(st.month_payments, start=r + 1):
            put(ws, i, [f"{p.date:%b} {p.date.day}, {p.date.year} · {p.description}", p.amount], money_cols=(2,),
                indent=True)
        r += len(st.month_payments) + 2
    if (f := st.funding) is not None:
        put(ws, r, ["Funding", None], font=k.bold, fill=k.section_fill)
        put(ws, r + 1, ["Funding outstanding at start of month", f.beginning], money_cols=(2,), indent=True)
        put(ws, r + 2, ["Funding received this month", f.received], money_cols=(2,), indent=True)
        put(ws, r + 3, ["Repaid by payments this month", -f.repaid], money_cols=(2,), indent=True)
        put(ws, r + 4, ["Funding outstanding", f"=SUM(B{r + 1}:B{r + 3})"], font=k.bold, border=k.grand_rule,
            money_cols=(2,))
        k.note(ws, r + 6, "Funding you provided is repaid by your revenue share payments until it's paid back in full.")

    ws = k.sheet("Year to date", f"{st.month.year} year to date", [16, 16, 16, 16, 16, 16])
    head = ["Month", "Revenue"] + (["Fees", "Base"] if fees else []) + ["Earned", "Paid"]
    put(ws, 6, head, font=k.header_font)
    cols = range(2, len(head) + 1)
    for i, m in enumerate(st.year_to_date, start=7):
        put(ws, i, [f"{m.month:%B}", m.revenue] + ([-m.deductions, m.base] if fees else []) + [m.earned, m.paid],
            money_cols=cols)
    last = 6 + len(st.year_to_date)
    letters = "ABCDEF"
    put(ws, last + 1, ["Total"] + [f"=SUM({letters[c - 1]}7:{letters[c - 1]}{last})" for c in cols],
        font=k.bold, border=k.grand_rule, money_cols=cols)
    k.note(ws, last + 3, f"Each month's share is {pct(st.rate_percent)} of that month's base, rounded to the cent.")
    return k.save()
