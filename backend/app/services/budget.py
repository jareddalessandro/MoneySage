from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BudgetItem, Category, CategoryColor, CategoryKind, DeductionType, Frequency, PaycheckDeduction
from app.schemas import PaycheckBreakdown, PaycheckLine, Stage

CENT = Decimal("0.01")

# How many times each frequency occurs per year.
OCCURRENCES_PER_YEAR = {
    Frequency.weekly: 52,
    Frequency.biweekly: 26,
    Frequency.semimonthly: 24,
    Frequency.monthly: 12,
    Frequency.quarterly: 4,
    Frequency.annual: 1,
}


def monthly_amount(amount: Decimal, frequency: Frequency) -> Decimal:
    return (amount * OCCURRENCES_PER_YEAR[frequency] / 12).quantize(CENT, ROUND_HALF_UP)


def budget_by_category(
    db: Session, card_category: Category | None = None
) -> dict[int, tuple[str, CategoryKind, CategoryColor, Decimal]]:
    """category_id -> (name, kind, color, monthly budgeted amount).

    With `card_category`, items paid by card count toward it instead of their own category, which is
    how a bank statement sees them (inside one card payment)."""
    totals: dict[int, Decimal] = defaultdict(Decimal)
    info: dict[int, tuple[str, CategoryKind, CategoryColor]] = {}
    for item in db.scalars(select(BudgetItem)).unique():
        category = card_category if card_category is not None and item.paid_by_card else item.category
        totals[category.id] += monthly_amount(item.amount, item.frequency)
        info[category.id] = (category.name, category.kind, category.color)
    return {cid: (*info[cid], total) for cid, total in totals.items()}


def deduction_stage(d: PaycheckDeduction) -> Stage:
    if d.type == DeductionType.tax:
        return "tax"
    return "pre_tax" if d.pre_tax else "post_tax"


def annual_amount(amount: Decimal, frequency: Frequency) -> Decimal:
    return amount * OCCURRENCES_PER_YEAR[frequency]


def is_paycheck(item: BudgetItem) -> bool:
    return item.gross_amount is not None and item.category.kind == CategoryKind.income


def paycheck_breakdown(
    paychecks: list[BudgetItem], name: str = "All paychecks", item_id: int | None = None
) -> PaycheckBreakdown:
    """Yearly gross-to-take-home totals across the given paychecks."""
    gross = take_home = Decimal(0)
    stages: dict[Stage, Decimal] = defaultdict(Decimal)
    # Same-named lines across paychecks (e.g. two earners' 401(k)) are combined.
    lines: dict[tuple[Stage, DeductionType, str], Decimal] = defaultdict(Decimal)
    for item in paychecks:
        gross += annual_amount(item.gross_amount, item.frequency)
        take_home += annual_amount(item.amount, item.frequency)
        for d in item.deductions:
            annual = annual_amount(d.amount, item.frequency)
            stage = deduction_stage(d)
            stages[stage] += annual
            lines[(stage, d.type, d.name.strip())] += annual

    order = {"pre_tax": 0, "tax": 1, "post_tax": 2}
    return PaycheckBreakdown(
        budget_item_id=item_id,
        name=name,
        paychecks=len(paychecks),
        paychecks_per_year=OCCURRENCES_PER_YEAR[paychecks[0].frequency] if item_id is not None else None,
        annual_gross=gross,
        annual_pre_tax=stages["pre_tax"],
        annual_taxes=stages["tax"],
        annual_after_tax=gross - stages["pre_tax"] - stages["tax"],
        annual_post_tax=stages["post_tax"],
        annual_unitemized=gross - sum(stages.values(), Decimal(0)) - take_home,
        annual_take_home=take_home,
        lines=[
            PaycheckLine(name=name, type=type_, stage=stage, annual_amount=amount)
            for (stage, type_, name), amount in sorted(lines.items(), key=lambda kv: (order[kv[0][0]], -kv[1]))
        ],
    )
