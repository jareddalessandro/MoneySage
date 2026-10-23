from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, CategoryKind

DEFAULT_CATEGORIES = {
    CategoryKind.income: [
        "Salary",
        "Bonus",
        "Interest & Dividends",
        "Side Income",
        "Gifts Received",
        "Refunds & Reimbursements",
        "Other Income",
    ],
    CategoryKind.expense: [
        "Housing",
        "Utilities",
        "Groceries",
        "Dining Out",
        "Transportation",
        "Insurance",
        "Healthcare",
        "Childcare & Education",
        "Debt Payments",
        "Subscriptions",
        "Shopping",
        "Entertainment",
        "Travel",
        "Gifts & Donations",
        "Home Maintenance",
        "Personal Care",
        "Savings & Investing",
        "Taxes",
        "Miscellaneous",
    ],
}


def seed_categories(db: Session) -> None:
    """Insert the default categories the first time the app starts."""
    if db.scalar(select(Category.id).limit(1)) is not None:
        return
    for kind, names in DEFAULT_CATEGORIES.items():
        db.add_all(Category(name=name, kind=kind) for name in names)
    db.commit()
