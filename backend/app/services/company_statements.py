"""Year-end financial statements for a company, as data and rendered to PDF or Excel.

Cash basis, built only from the company's recorded entries:
- Income statement: income, cost of revenue (revenue-share payments and the fee categories agreements
  subtract) and gross profit when there is any, operating expenses by category, and net profit.
- Statement of members' capital: each member's beginning balance, contributions, share of profit,
  distributions, and ending balance. Profit is allocated by *current* ownership percentages (ownership
  history isn't kept), including for the prior years that make up the beginning balance.
- Cash summary: cash in and out from recorded entries. Not a bank reconciliation.
- Results by product, when the company has products.
- Revenue shares: what each payee earned and was paid in the period, and what was due at its end.
- Revenue-share funding, when any was received: the liability's beginning balance, funding received,
  repaid by payments, and ending balance per payee. The repaid part of payments isn't an expense.
- Transaction detail: every entry in the period.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CompanyEntry, CompanyEntryKind, CompanyProduct, RevenueShare
from app.services import revenue_shares
from app.services.documents import PdfKit, XlsxKit, money as _money, pct as _pct
from app.services.revenue_shares import (
    FUNDING_NOTE,
    cost_categories,
    expensed,
    is_cost_of_revenue,
    long_date as _long_date,
    repayments,
)

ZERO = Decimal(0)
CENT = Decimal("0.01")
UNCATEGORIZED = "Uncategorized"
KIND_LABELS = {
    CompanyEntryKind.income: "Income",
    CompanyEntryKind.expense: "Expense",
    CompanyEntryKind.contribution: "Contribution",
    CompanyEntryKind.distribution: "Distribution",
    CompanyEntryKind.funding: "Funding",
}
# Cash direction of each kind: money into the company is positive.
CASH_SIGN = {
    CompanyEntryKind.income: 1,
    CompanyEntryKind.contribution: 1,
    CompanyEntryKind.funding: 1,
    CompanyEntryKind.expense: -1,
    CompanyEntryKind.distribution: -1,
}


@dataclass
class Line:
    label: str
    amount: Decimal


@dataclass
class CapitalAccount:
    name: str
    equity_percent: Decimal
    beginning: Decimal
    contributions: Decimal
    profit_share: Decimal
    distributions: Decimal

    @property
    def ending(self) -> Decimal:
        return self.beginning + self.contributions + self.profit_share - self.distributions


@dataclass
class LedgerRow:
    date: date
    kind: str
    description: str
    detail: str
    amount: Decimal  # signed by cash direction
    product: str = ""


@dataclass
class ProductResult:
    product_id: int | None
    name: str
    income: Decimal = ZERO
    cost_of_revenue: Decimal = ZERO
    other_expenses: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.income - self.cost_of_revenue - self.other_expenses


@dataclass
class ShareResult:
    payee: str
    terms: str
    earned: Decimal
    paid: Decimal
    balance: Decimal  # due at the end of the period


@dataclass
class FundingResult:
    payee: str
    beginning: Decimal
    received: Decimal
    repaid: Decimal

    @property
    def ending(self) -> Decimal:
        return self.beginning + self.received - self.repaid


NO_PRODUCT = "No product"


def product_breakdown(
    entries: list[CompanyEntry],
    products: list[CompanyProduct],
    cost_cats: set[str],
    repaid: dict[int, Decimal] | None = None,
) -> list[ProductResult]:
    """Income and expenses per product, plus a "No product" row for untagged ones if there are any.
    `repaid` (from `repayments`) leaves out the part of payments that repays funding.

    Empty when the company has no products.
    """
    if not products:
        return []
    repaid = repaid or {}
    results = {p.id: ProductResult(p.id, p.name) for p in products}
    untagged = ProductResult(None, NO_PRODUCT)
    for e in entries:
        if e.kind not in (CompanyEntryKind.income, CompanyEntryKind.expense):
            continue
        r = results.get(e.product_id, untagged)
        if e.kind == CompanyEntryKind.income:
            r.income += e.amount
        elif is_cost_of_revenue(e, cost_cats):
            r.cost_of_revenue += expensed(e, repaid)
        else:
            r.other_expenses += expensed(e, repaid)
    rows = list(results.values())
    if untagged.income or untagged.cost_of_revenue or untagged.other_expenses:
        rows.append(untagged)
    return rows


@dataclass
class Statements:
    company_name: str
    year: int
    period_end: date
    is_full_year: bool
    generated: date
    income: list[Line]
    cost_of_revenue: list[Line]
    expenses: list[Line]  # operating expenses: everything that isn't cost of revenue
    capital: list[CapitalAccount]
    equity_assigned: Decimal
    # Profit not allocated to anyone because ownership totals under 100%.
    unallocated_profit: Decimal
    cash_beginning: Decimal
    contributions: Decimal
    distributions: Decimal
    ledger: list[LedgerRow] = field(default_factory=list)
    products: list[ProductResult] = field(default_factory=list)
    shares: list[ShareResult] = field(default_factory=list)
    funding: list[FundingResult] = field(default_factory=list)  # one per payee who has funded anything

    @property
    def funding_received(self) -> Decimal:
        return sum((f.received for f in self.funding), ZERO)

    @property
    def funding_repaid(self) -> Decimal:
        return sum((f.repaid for f in self.funding), ZERO)

    @property
    def total_income(self) -> Decimal:
        return sum((l.amount for l in self.income), ZERO)

    @property
    def total_cost_of_revenue(self) -> Decimal:
        return sum((l.amount for l in self.cost_of_revenue), ZERO)

    @property
    def gross_profit(self) -> Decimal:
        return self.total_income - self.total_cost_of_revenue

    @property
    def total_operating_expenses(self) -> Decimal:
        return sum((l.amount for l in self.expenses), ZERO)

    @property
    def total_expenses(self) -> Decimal:
        """Cost of revenue plus operating expenses."""
        return self.total_cost_of_revenue + self.total_operating_expenses

    @property
    def net(self) -> Decimal:
        return self.total_income - self.total_expenses

    @property
    def net_cash_change(self) -> Decimal:
        return (self.total_income + self.contributions + self.funding_received
                - self.total_expenses - self.funding_repaid - self.distributions)

    @property
    def cash_ending(self) -> Decimal:
        return self.cash_beginning + self.net_cash_change

    @property
    def period_label(self) -> str:
        if self.is_full_year:
            return f"For the year ended December 31, {self.year}"
        return f"Year to date, January 1 through {_long_date(self.period_end)}"


def _share(net: Decimal, percent: Decimal) -> Decimal:
    return (net * percent / 100).quantize(CENT)


def build_statements(db: Session, company: Company, year: int, today: date | None = None) -> Statements:
    today = today or date.today()
    start, year_end = date(year, 1, 1), date(year, 12, 31)
    is_full_year = today > year_end
    period_end = year_end if is_full_year else today

    entries = db.scalars(
        select(CompanyEntry)
        .where(CompanyEntry.company_id == company.id, CompanyEntry.date <= year_end)
        .order_by(CompanyEntry.date, CompanyEntry.id)
    ).all()
    prior = [e for e in entries if e.date < start]
    current = [e for e in entries if e.date >= start]
    members = {m.id: m for m in company.members}
    products = {p.id: p.name for p in company.products}
    cost_cats = cost_categories(db, company.id)
    repaid = repayments(db, company.id)

    def counted(e: CompanyEntry) -> Decimal:
        """What an income or expense entry counts for in profit: payments leave out what repays funding."""
        return expensed(e, repaid) if e.kind == CompanyEntryKind.expense else e.amount

    def by_category(kind: CompanyEntryKind, cost: bool | None = None) -> list[Line]:
        totals: dict[str, Decimal] = {}
        for e in current:
            if e.kind == kind and (cost is None or is_cost_of_revenue(e, cost_cats) == cost) and counted(e):
                label = e.category or UNCATEGORIZED
                totals[label] = totals.get(label, ZERO) + counted(e)
        # Largest first, with Uncategorized last.
        return [
            Line(label, amount)
            for label, amount in sorted(totals.items(), key=lambda kv: (kv[0] == UNCATEGORIZED, -kv[1], kv[0].lower()))
        ]

    def member_total(rows, kind: CompanyEntryKind, member_id: int) -> Decimal:
        return sum((e.amount for e in rows if e.kind == kind and e.member_id == member_id), ZERO)

    def kind_total(rows, kind: CompanyEntryKind) -> Decimal:
        return sum((e.amount for e in rows if e.kind == kind), ZERO)

    def net_of(rows) -> Decimal:
        return kind_total(rows, CompanyEntryKind.income) - sum(
            (counted(e) for e in rows if e.kind == CompanyEntryKind.expense), ZERO)

    prior_net = net_of(prior)
    net = net_of(current)

    capital = []
    for m in company.members:
        beginning = (
            member_total(prior, CompanyEntryKind.contribution, m.id)
            - member_total(prior, CompanyEntryKind.distribution, m.id)
            + _share(prior_net, m.equity_percent)
        )
        capital.append(CapitalAccount(
            name=m.name,
            equity_percent=m.equity_percent,
            beginning=beginning,
            contributions=member_total(current, CompanyEntryKind.contribution, m.id),
            profit_share=_share(net, m.equity_percent),
            distributions=member_total(current, CompanyEntryKind.distribution, m.id),
        ))
    assigned = sum((m.equity_percent for m in company.members), ZERO)

    all_shares = db.scalars(
        select(RevenueShare).where(RevenueShare.company_id == company.id).order_by(RevenueShare.payee, RevenueShare.id)
    ).all()
    payees = {s.id: s.payee for s in all_shares}

    def detail(e: CompanyEntry) -> str:
        if e.member_id is not None:
            member = members.get(e.member_id)
            return member.name if member else ""
        if e.kind == CompanyEntryKind.funding:
            return f"From {payees.get(e.revenue_share_id, 'revenue-share payee')}"
        if e.id in repaid:
            part = "repays funding" if repaid[e.id] == e.amount else f"{_money(repaid[e.id])} repays funding"
            return f"{e.category or UNCATEGORIZED} ({part})"
        return e.category or ""

    shares, funding = [], []
    for share in all_shares:
        roll = revenue_shares.funding_roll(db, share, start, period_end, repaid)
        if roll is not None and (roll.beginning or roll.received or roll.repaid):
            funding.append(FundingResult(share.payee, roll.beginning, roll.received, roll.repaid))
        rows = revenue_shares.monthly(db, share, period_end)
        if not rows:
            continue  # starts after this period
        in_year = [r for r in rows if r.month.year == year]
        shares.append(ShareResult(
            payee=share.payee,
            terms=revenue_shares.describe(share, products.get(share.product_id)),
            earned=sum((r.earned for r in in_year), ZERO),
            paid=sum((r.paid for r in in_year), ZERO),
            balance=rows[-1].balance,
        ))

    return Statements(
        company_name=company.name,
        year=year,
        period_end=period_end,
        is_full_year=is_full_year,
        generated=today,
        income=by_category(CompanyEntryKind.income),
        cost_of_revenue=by_category(CompanyEntryKind.expense, cost=True),
        expenses=by_category(CompanyEntryKind.expense, cost=False),
        capital=capital,
        equity_assigned=assigned,
        unallocated_profit=net - sum((c.profit_share for c in capital), ZERO),
        cash_beginning=sum((CASH_SIGN[e.kind] * e.amount for e in prior), ZERO),
        contributions=kind_total(current, CompanyEntryKind.contribution),
        distributions=kind_total(current, CompanyEntryKind.distribution),
        ledger=[
            LedgerRow(e.date, KIND_LABELS[e.kind], e.description, detail(e), CASH_SIGN[e.kind] * e.amount,
                      products.get(e.product_id, ""))
            for e in current
        ],
        products=product_breakdown(current, company.products, cost_cats, repaid),
        shares=shares,
        funding=funding,
    )


def file_name(st: Statements, extension: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9 ._,&()'-]+", "", st.company_name).strip() or "Company"
    period = st.year if st.is_full_year else f"{st.year} YTD"
    return f"{safe} {period} financial statements.{extension}"


# ---------- PDF ----------

def render_pdf(st: Statements) -> bytes:
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, TableStyle

    k = PdfKit()
    width = k.width
    story = [
        k.p(st.company_name, k.title),
        k.p("Financial statements", k.subtitle),
        k.p(st.period_label, k.subtitle),
        Spacer(1, 4),
        k.p(f"Prepared {_long_date(st.generated)} from the company's records in MoneySage. Cash basis; unaudited.",
            k.small),
    ]

    # Income statement
    rows = [["", "Amount"]]
    sections, totals, lines_at = [], [], []

    def section(label: str, lines: list[Line], empty: str, total_label: str, total: Decimal):
        rows.append([label, ""])
        sections.append(len(rows) - 1)
        for l in lines or [Line(empty, ZERO)]:
            rows.append([k.p(l.label), _money(l.amount)])
            lines_at.append(len(rows) - 1)
        rows.append([total_label, _money(total)])
        totals.append(len(rows) - 1)

    section("Income", st.income, "No income recorded", "Total income", st.total_income)
    if st.cost_of_revenue:
        section("Cost of revenue", st.cost_of_revenue, "", "Total cost of revenue", st.total_cost_of_revenue)
        rows.append(["Gross profit", _money(st.gross_profit)])
        totals.append(len(rows) - 1)
        section("Operating expenses", st.expenses, "No operating expenses recorded", "Total operating expenses",
                st.total_operating_expenses)
    else:
        section("Expenses", st.expenses, "No expenses recorded", "Total expenses", st.total_expenses)
    rows.append(["Net profit" if st.net >= 0 else "Net loss", _money(st.net)])
    story += [
        Paragraph("Income statement", k.heading),
        k.table(rows, [width * 0.7, width * 0.3], totals=totals, sections=sections, grand=[len(rows) - 1],
                indent=lines_at),
    ]
    notes = []
    if st.cost_of_revenue:
        notes.append("Cost of revenue is revenue-share payments and the platform fees those agreements are "
                     "calculated after.")
    if st.funding:
        notes.append(FUNDING_NOTE)
    story += [Spacer(1, 4)] + [k.p(n, k.small) for n in notes] if notes else []

    # Results by product
    if st.products:
        rows = [["Product", "Income", "Cost of revenue", "Other expenses", "Net"]] + [
            [k.p(r.name), _money(r.income), _money(r.cost_of_revenue), _money(r.other_expenses), _money(r.net)]
            for r in st.products
        ]
        rows.append([
            "Total",
            _money(sum((r.income for r in st.products), ZERO)),
            _money(sum((r.cost_of_revenue for r in st.products), ZERO)),
            _money(sum((r.other_expenses for r in st.products), ZERO)),
            _money(sum((r.net for r in st.products), ZERO)),
        ])
        story.append(KeepTogether([
            Paragraph("Results by product", k.heading),
            k.table(rows, [width * 0.32] + [width * 0.17] * 4, grand=[len(rows) - 1]),
        ]))

    # Members' capital
    story.append(Paragraph("Statement of members' capital", k.heading))
    if st.capital:
        head = ["Member", "Ownership", "Beginning", "Contributions", "Share of profit", "Distributions", "Ending"]
        rows = [head] + [
            [k.p(c.name), _pct(c.equity_percent), _money(c.beginning), _money(c.contributions),
             _money(c.profit_share), _money(c.distributions), _money(c.ending)]
            for c in st.capital
        ]
        rows.append([
            "Total", _pct(st.equity_assigned),
            _money(sum((c.beginning for c in st.capital), ZERO)),
            _money(sum((c.contributions for c in st.capital), ZERO)),
            _money(sum((c.profit_share for c in st.capital), ZERO)),
            _money(sum((c.distributions for c in st.capital), ZERO)),
            _money(sum((c.ending for c in st.capital), ZERO)),
        ])
        col = width / 7.6
        story.append(k.table(rows, [col * 1.6] + [col] * 6, grand=[len(rows) - 1]))
        notes = [
            "Share of profit is net profit times each member's ownership. Ownership history isn't kept, so the "
            "current percentages are used for every year, including the prior years in the beginning balance."
        ]
        if st.unallocated_profit:
            notes.append(
                f"Ownership totals {_pct(st.equity_assigned)}, so {_money(st.unallocated_profit)} of this period's "
                "profit isn't allocated to a member.")
        story += [Spacer(1, 4)] + [k.p(n, k.small) for n in notes]
    else:
        story.append(k.p("No members recorded."))

    # Revenue shares
    if st.shares:
        rows = [["Payee", "Terms", "Earned", "Paid", "Due Dec 31" if st.is_full_year else "Due now"]] + [
            [k.p(r.payee), k.p(r.terms), _money(r.earned), _money(r.paid), _money(r.balance)]
            for r in st.shares
        ]
        t = k.table(rows, [width * 0.17, width * 0.41, width * 0.14, width * 0.14, width * 0.14])
        t.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "LEFT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(KeepTogether([
            Paragraph("Revenue shares", k.heading),
            t,
            Spacer(1, 4),
            k.p("Earned and paid are for this period. The balance due is everything earned minus everything paid "
                "as of the period's end. Cash basis: a share is an expense when it's paid, so a balance due isn't "
                "in the income statement.", k.small),
        ]))

    # Revenue-share funding (a liability)
    if st.funding:
        end_label = "Owed Dec 31" if st.is_full_year else "Owed now"
        rows = [["Payee", "Beginning", "Received", "Repaid", end_label]] + [
            [k.p(f.payee), _money(f.beginning), _money(f.received), _money(f.repaid), _money(f.ending)]
            for f in st.funding
        ]
        if len(st.funding) > 1:
            rows.append(["Total"] + [_money(sum((getattr(f, a) for f in st.funding), ZERO))
                                     for a in ("beginning", "received", "repaid", "ending")])
        story.append(KeepTogether([
            Paragraph("Revenue-share funding", k.heading),
            k.table(rows, [width * 0.32] + [width * 0.17] * 4, grand=[len(rows) - 1] if len(st.funding) > 1 else []),
            Spacer(1, 4),
            k.p(FUNDING_NOTE + " Repaid is the part of this period's payments that went toward it.", k.small),
        ]))

    # Cash summary
    received = [["Income", st.total_income], ["Member contributions", st.contributions]]
    paid = [["Expenses", -st.total_expenses], ["Distributions to members", -st.distributions]]
    if st.funding:
        received.append(["Revenue-share funding", st.funding_received])
        paid.insert(1, ["Revenue-share funding repaid", -st.funding_repaid])
    rows = [["", "Amount"], ["Cash at beginning of period", _money(st.cash_beginning)], ["Cash received", ""]]
    sections, indent = [2], []
    for label, amount in received:
        rows.append([label, _money(amount)])
        indent.append(len(rows) - 1)
    rows.append(["Cash paid", ""])
    sections.append(len(rows) - 1)
    for label, amount in paid:
        rows.append([label, _money(amount)])
        indent.append(len(rows) - 1)
    rows += [["Net change in cash", _money(st.net_cash_change)], ["Cash at end of period", _money(st.cash_ending)]]
    story.append(KeepTogether([
        Paragraph("Cash summary", k.heading),
        k.table(rows, [width * 0.7, width * 0.3], sections=sections, totals=[len(rows) - 2], grand=[len(rows) - 1],
                indent=indent),
        Spacer(1, 4),
        k.p("From recorded entries only: compare with the bank balance to confirm nothing is missing.", k.small),
    ]))

    # Transaction detail
    story += [PageBreak(), Paragraph("Transaction detail", k.heading)]
    if st.ledger:
        rows = [["Date", "Type", "Description", "Category / member", "Amount"]] + [
            [f"{r.date:%b} {r.date.day}, {r.date.year}", r.kind, k.p(r.description),
             k.p(" · ".join(x for x in (r.detail, r.product) if x)), k.p(_money(r.amount), k.cell_right)]
            for r in st.ledger
        ]
        t = k.table(rows, [width * 0.15, width * 0.14, width * 0.35, width * 0.21, width * 0.15])
        t.setStyle(TableStyle([("ALIGN", (1, 0), (3, -1), "LEFT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        note = "Amounts are cash in (positive) or out (in parentheses)."
        if st.products:
            note += " The product, if any, follows the category."
        story += [t, Spacer(1, 4), k.p(note, k.small)]
    else:
        story.append(k.p("No entries in this period."))

    return k.build(story, f"{st.company_name} · {st.period_label}",
                   f"{st.company_name} financial statements {st.year}")


# ---------- Excel ----------

def render_xlsx(st: Statements) -> bytes:
    k = XlsxKit(st.company_name, st.period_label,
                f"Prepared {_long_date(st.generated)} from MoneySage records. Cash basis; unaudited.")
    put = k.put

    # Income statement: totals are formulas over their section's lines.
    ws = k.sheet("Income statement", "Income statement", [40, 18])
    put(ws, 6, ["", "Amount"], font=k.header_font)
    r = 7

    def section(label: str, lines: list[Line], total_label: str) -> str:
        nonlocal r
        put(ws, r, [label, None], font=k.bold, fill=k.section_fill)
        r += 1
        first = r
        for l in lines:
            put(ws, r, [l.label, l.amount], money_cols=(2,), indent=True)
            r += 1
        put(ws, r, [total_label, f"=SUM(B{first}:B{r - 1})" if lines else 0], font=k.bold, border=k.top_rule,
            money_cols=(2,))
        cell = f"B{r}"
        r += 2
        return cell

    income = section("Income", st.income, "Total income")
    if st.cost_of_revenue:
        cost = section("Cost of revenue", st.cost_of_revenue, "Total cost of revenue")
        put(ws, r - 1, ["Gross profit", f"={income}-{cost}"], font=k.bold, border=k.top_rule, money_cols=(2,))
        r += 1
        operating = section("Operating expenses", st.expenses, "Total operating expenses")
        net = f"={income}-{cost}-{operating}"
    else:
        expenses = section("Expenses", st.expenses, "Total expenses")
        net = f"={income}-{expenses}"
    put(ws, r, ["Net profit" if st.net >= 0 else "Net loss", net], font=k.bold, border=k.grand_rule,
        money_cols=(2,))
    if st.cost_of_revenue:
        r += 2
        k.note(ws, r, "Cost of revenue is revenue-share payments and the platform fees those agreements are "
                      "calculated after.")
    if st.funding:
        k.note(ws, r + (1 if st.cost_of_revenue else 2), FUNDING_NOTE)

    if st.products:
        ws = k.sheet("By product", "Results by product", [32, 16, 16, 16, 16])
        put(ws, 6, ["Product", "Income", "Cost of revenue", "Other expenses", "Net"], font=k.header_font)
        for i, p in enumerate(st.products, start=7):
            put(ws, i, [p.name, p.income, p.cost_of_revenue, p.other_expenses, f"=B{i}-C{i}-D{i}"],
                money_cols=(2, 3, 4, 5))
        last = 6 + len(st.products)
        put(ws, last + 1, ["Total"] + [f"=SUM({c}7:{c}{last})" for c in "BCDE"], font=k.bold, border=k.grand_rule,
            money_cols=(2, 3, 4, 5))

    # Members' capital
    ws = k.sheet("Members' capital", "Statement of members' capital", [28, 12, 16, 16, 16, 16, 16])
    head = ["Member", "Ownership", "Beginning", "Contributions", "Share of profit", "Distributions", "Ending"]
    put(ws, 6, head, font=k.header_font)
    r = 7
    money_cols = (3, 4, 5, 6, 7)
    for c in st.capital:
        put(ws, r, [c.name, c.equity_percent / 100, c.beginning, c.contributions, c.profit_share, c.distributions,
                    c.ending], money_cols=money_cols, pct_cols=(2,))
        r += 1
    if st.capital:
        first, last = 7, r - 1
        totals = ["Total"] + [f"=SUM({col}{first}:{col}{last})" for col in "BCDEFG"]
        put(ws, r, totals, font=k.bold, border=k.grand_rule, money_cols=money_cols, pct_cols=(2,))
        r += 2
        ws.cell(row=r, column=1, value="Share of profit is net profit times each member's current ownership "
                                       "(also used for prior years in the beginning balance).")
        if st.unallocated_profit:
            ws.cell(row=r + 1, column=1, value=f"{_money(st.unallocated_profit)} of profit isn't allocated: "
                                               f"ownership totals {_pct(st.equity_assigned)}.")
    else:
        ws.cell(row=7, column=1, value="No members recorded.")

    if st.shares:
        ws = k.sheet("Revenue shares", "Revenue shares", [24, 60, 16, 16, 16])
        put(ws, 6, ["Payee", "Terms", "Earned", "Paid", "Due Dec 31" if st.is_full_year else "Due now"],
            font=k.header_font)
        for i, sh in enumerate(st.shares, start=7):
            put(ws, i, [sh.payee, sh.terms, sh.earned, sh.paid, sh.balance], money_cols=(3, 4, 5))
        k.note(ws, 8 + len(st.shares), "Earned and paid are for this period. Due is everything earned minus "
                                       "everything paid as of the period's end; it isn't an expense until paid.")

    if st.funding:
        ws = k.sheet("Funding", "Revenue-share funding", [28, 16, 16, 16, 16])
        put(ws, 6, ["Payee", "Beginning", "Received", "Repaid", "Owed Dec 31" if st.is_full_year else "Owed now"],
            font=k.header_font)
        for i, f in enumerate(st.funding, start=7):
            put(ws, i, [f.payee, f.beginning, f.received, f.repaid, f"=B{i}+C{i}-D{i}"], money_cols=(2, 3, 4, 5))
        last = 6 + len(st.funding)
        put(ws, last + 1, ["Total"] + [f"=SUM({c}7:{c}{last})" for c in "BCDE"], font=k.bold, border=k.grand_rule,
            money_cols=(2, 3, 4, 5))
        k.note(ws, last + 3, FUNDING_NOTE)

    # Cash summary
    ws = k.sheet("Cash summary", "Cash summary", [40, 18])
    put(ws, 6, ["", "Amount"], font=k.header_font)
    put(ws, 7, ["Cash at beginning of period", st.cash_beginning], money_cols=(2,))
    received = [["Income", st.total_income], ["Member contributions", st.contributions]]
    paid = [["Expenses", -st.total_expenses], ["Distributions to members", -st.distributions]]
    if st.funding:
        received.append(["Revenue-share funding", st.funding_received])
        paid.insert(1, ["Revenue-share funding repaid", -st.funding_repaid])
    r = 8
    ranges = []
    for heading, lines in (("Cash received", received), ("Cash paid", paid)):
        put(ws, r, [heading, None], font=k.bold, fill=k.section_fill)
        for i, line in enumerate(lines, start=r + 1):
            put(ws, i, line, money_cols=(2,), indent=True)
        ranges.append(f"B{r + 1}:B{r + len(lines)}")
        r += len(lines) + 1
    put(ws, r, ["Net change in cash", f"=SUM({','.join(ranges)})"], font=k.bold, border=k.top_rule, money_cols=(2,))
    put(ws, r + 1, ["Cash at end of period", f"=B7+B{r}"], font=k.bold, border=k.grand_rule, money_cols=(2,))
    ws.cell(row=r + 3, column=1, value="From recorded entries only: compare with the bank balance.")

    # Transactions
    ws = k.sheet("Transactions", "Transaction detail", [14, 14, 40, 24, 20, 16])
    put(ws, 6, ["Date", "Type", "Description", "Category / member", "Product", "Amount"], font=k.header_font)
    for i, row in enumerate(st.ledger, start=7):
        put(ws, i, [row.date, row.kind, row.description, row.detail or None, row.product or None, row.amount],
            money_cols=(6,))
        ws.cell(row=i, column=1).number_format = "mmm d, yyyy"
    ws.freeze_panes = "A7"
    if st.ledger:
        ws.auto_filter.ref = f"A6:F{6 + len(st.ledger)}"

    return k.save()
