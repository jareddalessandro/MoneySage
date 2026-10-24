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


PAYCHECK = {
    "name": "Paycheck",
    "amount": 3000,
    "gross_amount": 4600,
    "frequency": "biweekly",
    "deductions": [
        {"name": "401(k)", "type": "retirement", "pre_tax": True, "amount": 460},
        {"name": "Health insurance", "type": "insurance", "pre_tax": True, "amount": 140},
        {"name": "Federal tax", "type": "tax", "pre_tax": True, "amount": 650},
        {"name": "Social Security", "type": "tax", "amount": 250},
        {"name": "Roth IRA", "type": "retirement", "pre_tax": False, "amount": 50},
    ],
}


def test_paycheck_breakdown(client, category_id):
    salary = category_id("Salary")
    created = client.post("/api/budget/items", json={**PAYCHECK, "category_id": salary})
    assert created.status_code == 201
    item = created.json()
    assert item["monthly_amount"] == 6500  # take-home drives the budget
    assert item["monthly_gross_amount"] == 9966.67
    assert [d["name"] for d in item["deductions"]] == ["401(k)", "Health insurance", "Federal tax", "Social Security", "Roth IRA"]
    assert item["deductions"][2]["pre_tax"] is False  # taxes are never "pre-tax"

    # A second earner's 401(k) is combined with the first.
    client.post("/api/budget/items", json={
        "name": "Spouse paycheck", "category_id": salary, "amount": 2000, "gross_amount": 2600,
        "frequency": "monthly", "deductions": [{"name": "401(k)", "type": "retirement", "pre_tax": True, "amount": 200}],
    })
    client.post("/api/budget/items", json={
        "name": "Etsy", "category_id": category_id("Side Income"), "amount": 300, "frequency": "monthly",
    })

    summary = client.get("/api/budget/summary").json()
    assert summary["monthly_income"] == 8800  # 6500 + 2000 take-home + 300 side income
    p = summary["paycheck"]
    assert p["paychecks"] == 2
    assert p["annual_gross"] == 4600 * 26 + 2600 * 12  # exact, no monthly rounding
    assert p["annual_pre_tax"] == (460 + 140) * 26 + 200 * 12
    assert p["annual_taxes"] == (650 + 250) * 26
    assert p["annual_after_tax"] == p["annual_gross"] - p["annual_pre_tax"] - p["annual_taxes"]
    assert p["annual_post_tax"] == 50 * 26
    assert p["annual_take_home"] == 3000 * 26 + 2000 * 12
    # 4600 - 1550 - 3000 = 50 per paycheck not itemized; the spouse's 2600 - 200 - 2000 = 400.
    assert p["annual_unitemized"] == 50 * 26 + 400 * 12
    lines = {(l["stage"], l["name"]): l["annual_amount"] for l in p["lines"]}
    assert lines[("pre_tax", "401(k)")] == 460 * 26 + 200 * 12
    assert [l["stage"] for l in p["lines"]] == sorted((l["stage"] for l in p["lines"]), key=["pre_tax", "tax", "post_tax"].index)

    # Each paycheck on its own, so each earner's 401(k) can be seen separately.
    items = {i["name"]: i for i in summary["paycheck_items"]}
    assert p["name"] == "All paychecks" and p["budget_item_id"] is None and p["paychecks_per_year"] is None
    mine, spouse = items["Paycheck"], items["Spouse paycheck"]
    assert mine["paychecks_per_year"] == 26 and spouse["paychecks_per_year"] == 12
    assert mine["budget_item_id"] == item["id"]
    assert [(l["name"], l["annual_amount"]) for l in mine["lines"] if l["type"] == "retirement"] == [
        ("401(k)", 460 * 26), ("Roth IRA", 50 * 26),
    ]
    assert [(l["name"], l["annual_amount"]) for l in spouse["lines"]] == [("401(k)", 200 * 12)]
    assert spouse["annual_unitemized"] == 400 * 12


def test_paycheck_update_replaces_deductions(client, category_id):
    item = client.post("/api/budget/items", json={**PAYCHECK, "category_id": category_id("Salary")}).json()
    updated = client.put(f"/api/budget/items/{item['id']}", json={
        **PAYCHECK, "category_id": category_id("Salary"),
        "deductions": [{"name": "401(k)", "type": "retirement", "pre_tax": True, "amount": 500}],
    }).json()
    assert [(d["name"], d["amount"]) for d in updated["deductions"]] == [("401(k)", 500)]

    plain = client.put(f"/api/budget/items/{item['id']}", json={
        "name": "Paycheck", "category_id": category_id("Salary"), "amount": 3000, "frequency": "biweekly",
    }).json()
    assert plain["gross_amount"] is None and plain["deductions"] == []
    after = client.get("/api/budget/summary").json()
    assert after["paycheck"] is None and after["paycheck_items"] == []


@pytest.mark.parametrize(
    "change, message",
    [
        ({"amount": 5000}, "more than gross"),
        ({"gross_amount": None}, "Enter gross pay"),
        ({"category": "Housing"}, "only apply to income"),
    ],
)
def test_paycheck_validation(client, category_id, change, message):
    body = {**PAYCHECK, "category_id": category_id(change.pop("category", "Salary")), **change}
    response = client.post("/api/budget/items", json=body)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_category_colors(client, category_id):
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    assert cats["Housing"]["color"] == "blue"  # seeded defaults
    assert cats["Miscellaneous"]["color"] == "gray"

    # New categories get the least-used palette color for their kind; an explicit color wins.
    auto = client.post("/api/categories", json={"name": "Pets", "kind": "expense"}).json()
    used = [c["color"] for c in cats.values() if c["kind"] == "expense"]
    palette = ["blue", "orange", "teal", "violet", "gold", "pink", "green", "plum"]
    assert auto["color"] == min(palette, key=lambda c: (used.count(c), palette.index(c)))
    assert client.post("/api/categories", json={"name": "Kids", "kind": "expense", "color": "teal"}).json()["color"] == "teal"
    assert client.post("/api/categories", json={"name": "Bad", "kind": "expense", "color": "neon"}).status_code == 422

    recolored = client.patch(f"/api/categories/{category_id('Housing')}", json={"color": "plum"}).json()
    assert recolored["color"] == "plum"

    client.post("/api/budget/items", json={
        "name": "Mortgage", "category_id": category_id("Housing"), "amount": 2000, "frequency": "monthly",
    })
    summary = client.get("/api/budget/summary").json()
    assert summary["by_category"][0]["color"] == "plum"
