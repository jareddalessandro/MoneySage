from sqlalchemy.orm import Session

from app.models import Category, CategoryColor, CategoryKind

# Default categories and their colors. Eight hues can't cover 26 categories, so related ones
# share a color (e.g. Housing and Home Maintenance); colors can be changed on the Categories page.
# The migration that added colors (category colors) uses the same mapping.
CARD_PAYMENTS = "Credit Card Payments"  # flagged is_card_payments; see Category
DEFAULT_CATEGORIES: dict[CategoryKind, list[tuple[str, CategoryColor]]] = {
    CategoryKind.income: [
        ("Salary", CategoryColor.blue),
        ("Bonus", CategoryColor.green),
        ("Interest & Dividends", CategoryColor.teal),
        ("Side Income", CategoryColor.violet),
        ("Gifts Received", CategoryColor.pink),
        ("Refunds & Reimbursements", CategoryColor.gold),
        ("Other Income", CategoryColor.gray),
    ],
    CategoryKind.expense: [
        ("Housing", CategoryColor.blue),
        ("Utilities", CategoryColor.gold),
        ("Groceries", CategoryColor.green),
        ("Dining Out", CategoryColor.orange),
        ("Transportation", CategoryColor.teal),
        ("Insurance", CategoryColor.violet),
        ("Healthcare", CategoryColor.pink),
        ("Childcare & Education", CategoryColor.plum),
        ("Debt Payments", CategoryColor.violet),
        ("Credit Card Payments", CategoryColor.plum),
        ("Subscriptions", CategoryColor.plum),
        ("Shopping", CategoryColor.orange),
        ("Entertainment", CategoryColor.orange),
        ("Travel", CategoryColor.teal),
        ("Gifts & Donations", CategoryColor.pink),
        ("Home Maintenance", CategoryColor.blue),
        ("Personal Care", CategoryColor.pink),
        ("Savings & Investing", CategoryColor.green),
        ("Taxes", CategoryColor.gold),
        ("Miscellaneous", CategoryColor.gray),
    ],
}


def seed_categories(db: Session, household_id: int) -> None:
    """Insert the default categories into a new household."""
    for kind, entries in DEFAULT_CATEGORIES.items():
        db.add_all(
            Category(
                household_id=household_id, name=name, kind=kind, color=color, is_card_payments=name == CARD_PAYMENTS
            )
            for name, color in entries
        )
    db.flush()
