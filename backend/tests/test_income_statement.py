def add_txn(client, category_id, date, amount, unexpected=False, description="test"):
    response = client.post("/api/transactions", json={
        "date": date,
        "description": description,
        "amount": amount,
        "category_id": category_id,
        "is_unexpected": unexpected,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_income_statement_totals(client, category_id):
    salary, groceries, home = category_id("Salary"), category_id("Groceries"), category_id("Home Maintenance")
    client.post("/api/budget/items", json={
        "name": "Food", "category_id": groceries, "amount": 1000, "frequency": "monthly",
    })
    add_txn(client, salary, "2026-03-01", 4000)
    add_txn(client, salary, "2026-03-15", 4000)
    add_txn(client, groceries, "2026-03-07", 210.55)
    add_txn(client, home, "2026-03-20", 900, unexpected=True)
    add_txn(client, salary, "2026-04-01", 4000)  # different month, excluded

    s = client.get("/api/income-statement", params={"month": "2026-03"}).json()
    assert s["total_income"] == 8000
    assert s["total_expenses"] == 1110.55
    assert s["net"] == 6889.45
    assert s["unexpected_expenses"] == 900
    assert s["budgeted_expenses"] == 1000

    lines = {line["name"]: line for line in s["categories"]}
    assert lines["Groceries"] == {
        "category_id": groceries, "name": "Groceries", "kind": "expense", "color": "green",
        "actual": 210.55, "unexpected": 0, "budgeted": 1000,
    }
    assert lines["Home Maintenance"]["unexpected"] == 900


def test_transactions_listed_by_month(client, category_id):
    groceries = category_id("Groceries")
    add_txn(client, groceries, "2026-02-28", 10)
    add_txn(client, groceries, "2026-03-01", 20)
    add_txn(client, groceries, "2026-03-31", 30)

    march = client.get("/api/transactions", params={"month": "2026-03"}).json()
    assert [t["amount"] for t in march] == [30, 20]


def test_update_and_delete_transaction(client, category_id):
    txn = add_txn(client, category_id("Groceries"), "2026-03-05", 50)
    updated = client.put(f"/api/transactions/{txn['id']}", json={
        "date": "2026-03-05", "description": "Trader Joe's", "amount": 75,
        "category_id": category_id("Dining Out"), "is_unexpected": True,
    }).json()
    assert updated["amount"] == 75 and updated["category"]["name"] == "Dining Out"

    assert client.delete(f"/api/transactions/{txn['id']}").status_code == 204
    assert client.get("/api/transactions", params={"month": "2026-03"}).json() == []


def test_invalid_amount_rejected(client, category_id):
    response = client.post("/api/transactions", json={
        "date": "2026-03-05", "description": "x", "amount": -5, "category_id": category_id("Groceries"),
    })
    assert response.status_code == 422
