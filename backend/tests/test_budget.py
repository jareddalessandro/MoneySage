from decimal import Decimal

import pytest

from app.models import Frequency
from app.services.budget import monthly_amount


@pytest.mark.parametrize(
    "amount, frequency, expected",
    [
        ("100", Frequency.weekly, "433.33"),
        ("3000", Frequency.biweekly, "6500.00"),
        ("2000", Frequency.semimonthly, "4000.00"),
        ("1500", Frequency.monthly, "1500.00"),
        ("600", Frequency.quarterly, "200.00"),
        ("1200", Frequency.annual, "100.00"),
    ],
)
def test_monthly_amount(amount, frequency, expected):
    assert monthly_amount(Decimal(amount), frequency) == Decimal(expected)


def test_budget_summary(client, category_id):
    client.post("/api/budget/items", json={
        "name": "Paycheck", "category_id": category_id("Salary"), "amount": 3000, "frequency": "biweekly",
    })
    client.post("/api/budget/items", json={
        "name": "Mortgage", "category_id": category_id("Housing"), "amount": 2100, "frequency": "monthly",
    })
    client.post("/api/budget/items", json={
        "name": "Car insurance", "category_id": category_id("Insurance"), "amount": 1200, "frequency": "annual",
    })

    summary = client.get("/api/budget/summary").json()
    assert summary["monthly_income"] == 6500
    assert summary["monthly_expenses"] == 2200
    assert summary["monthly_surplus"] == 4300


def test_category_in_use_cannot_be_deleted(client, category_id):
    groceries = category_id("Groceries")
    client.post("/api/budget/items", json={
        "name": "Food", "category_id": groceries, "amount": 200, "frequency": "weekly",
    })
    assert client.delete(f"/api/categories/{groceries}").status_code == 409

    archived = client.patch(f"/api/categories/{groceries}", json={"is_archived": True}).json()
    assert archived["is_archived"] is True
    assert groceries not in [c["id"] for c in client.get("/api/categories").json()]


def test_duplicate_category_rejected(client):
    assert client.post("/api/categories", json={"name": "Groceries", "kind": "expense"}).status_code == 409
    assert client.post("/api/categories", json={"name": "Groceries", "kind": "income"}).status_code == 201
