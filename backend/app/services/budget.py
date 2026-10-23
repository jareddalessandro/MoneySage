from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BudgetItem, CategoryKind, Frequency

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


def budget_by_category(db: Session) -> dict[int, tuple[str, CategoryKind, Decimal]]:
    """category_id -> (name, kind, monthly budgeted amount)."""
    totals: dict[int, Decimal] = defaultdict(Decimal)
    info: dict[int, tuple[str, CategoryKind]] = {}
    for item in db.scalars(select(BudgetItem)).unique():
        totals[item.category_id] += monthly_amount(item.amount, item.frequency)
        info[item.category_id] = (item.category.name, item.category.kind)
    return {cid: (*info[cid], total) for cid, total in totals.items()}
