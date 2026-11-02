"""Export a household and companies to a file, and import it into another account."""

import json

from tests.test_statements import accounts, august, commit_body, upload  # noqa: F401  (accounts is a fixture)

MONTH = {"month": "2026-08"}


def strip_ids(value):
    """Responses without database ids, which differ after an import."""
    if isinstance(value, dict):
        return {k: strip_ids(v) for k, v in value.items() if k != "id" and not k.endswith("_id")}
    if isinstance(value, list):
        return [strip_ids(v) for v in value]
    return value


def build_everything(client, category_id) -> int:
    """A household with one of everything, and a company. Returns the company id."""
    p = upload(client, august()).json()
    assert client.post("/api/statements", json=commit_body(p)).status_code == 201
    client.post("/api/categories", json={"name": "Pets", "kind": "expense", "color": "teal"})
    client.patch(f"/api/categories/{category_id('Travel')}", json={"is_archived": True})
    client.post("/api/budget/items", json={
        "name": "Paycheck", "category_id": category_id("Salary"), "amount": 3000, "gross_amount": 4200,
        "frequency": "biweekly", "deductions": [
            {"name": "401(k)", "type": "retirement", "pre_tax": True, "amount": 300},
            {"name": "Federal", "type": "tax", "amount": 600},
        ],
    })
    client.post("/api/budget/items", json={
        "name": "Streaming", "category_id": category_id("Subscriptions"), "amount": 20, "frequency": "monthly",
        "paid_by_card": True,
    })
    client.post("/api/transactions", json={
        "date": "2026-08-12", "description": "Vet", "amount": 140, "category_id": category_id("Healthcare"),
        "is_unexpected": True,
    })
    brokerage = client.post("/api/accounts", json={
        "name": "Brokerage", "kind": "asset", "subtype": "brokerage", "sync_from_holdings": True,
    }).json()["id"]
    cash = client.post("/api/holdings", json={"asset_type": "cash", "quantity": 2500, "account_id": brokerage})
    client.post(f"/api/holdings/{cash.json()['id']}/trade", json={"side": "sell", "quantity": 100, "date": "2026-08-03"})
    client.put("/api/income-statement/notes", json={"month": "2026-08", "notes": "Back to school"})
    client.put("/api/income-statement/totals-from", json={"month": "2026-08", "totals_from": "manual"})
    client.post("/api/credit-cards", json={
        "name": "Sapphire", "payment_url": "chase.com", "annual_fee": 95, "annual_fee_month": 3,
        "benefits": ["3x dining"],
    })

    cid = client.post("/api/companies", json={"name": "Apps LLC", "description": "Mobile apps"}).json()["id"]
    sam = client.post(f"/api/companies/{cid}/members", json={"name": "Sam", "equity_percent": 60}).json()["id"]
    app_a = client.post(f"/api/companies/{cid}/products", json={"name": "App A"}).json()["id"]
    share = client.post(f"/api/companies/{cid}/revenue-shares", json={
        "payee": "Investor", "basis": "reported", "product_id": app_a, "rate_percent": 10,
        "start_date": "2026-01-01",
    }).json()["id"]
    client.put(f"/api/companies/{cid}/revenue-shares/{share}/months", json={"months": [{"month": "2026-02", "revenue": 5000}]})
    for body in [
        {"kind": "income", "date": "2026-02-10", "amount": 5000, "category": "Sales", "product_id": app_a},
        {"kind": "contribution", "date": "2026-01-05", "amount": 1000, "member_id": sam},
        {"kind": "funding", "date": "2026-01-20", "amount": 300, "revenue_share_id": share},
        {"kind": "expense", "date": "2026-03-01", "amount": 500, "revenue_share_id": share, "category": "Revenue share"},
    ]:
        assert client.post(f"/api/companies/{cid}/entries", json={"description": "x", **body}).status_code == 201
    return cid


def snapshot(client, cid: int) -> dict:
    return strip_ids({
        "income_statement": client.get("/api/income-statement", params=MONTH).json(),
        "transactions": client.get("/api/transactions", params=MONTH).json(),
        "statements": client.get("/api/statements", params=MONTH).json(),
        "balance_sheet": client.get("/api/balance-sheet", params=MONTH).json(),
        "budget": client.get("/api/budget/items").json(),
        "budget_summary": client.get("/api/budget/summary").json(),
        "categories": client.get("/api/categories", params={"include_archived": True}).json(),
        "holdings": client.get("/api/holdings").json(),
        "investment_transactions": client.get("/api/investment-transactions").json(),
        "cards": client.get("/api/credit-cards").json(),
        "company": client.get(f"/api/companies/{cid}").json(),
        "company_summary": client.get(f"/api/companies/{cid}/summary", params={"year": 2026}).json(),
        "entries": client.get(f"/api/companies/{cid}/entries", params={"year": 2026}).json(),
        "shares": client.get(f"/api/companies/{cid}/revenue-shares", params={"year": 2026}).json(),
    })


def import_file(client, content: bytes, name="export.json"):
    return client.post("/api/import", files={"file": (name, content, "application/json")})


def test_export_and_import_round_trip(client, people, accounts, category_id):  # noqa: F811
    cid = build_everything(client, category_id)
    before = snapshot(client, cid)
    exported = client.get("/api/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].startswith('attachment; filename="tallyvio-export-')
    data = exported.json()
    assert data["format"] == "tallyvio-export" and data["version"] == 1
    assert len(data["companies"]) == 1

    newcomer = people.add("new@example.com")
    people.act_as(newcomer)
    result = import_file(client, exported.content)
    assert result.status_code == 200, result.text
    assert result.json() == {
        "household": True, "companies": ["Apps LLC"], "transactions": 11, "entries": 4, "holdings": 1,
    }
    new_cid = client.get("/api/companies").json()[0]["id"]
    assert snapshot(client, new_cid) == before

    # Imported statement lines are still recognized, so the same statement isn't imported twice.
    assert all(r["duplicate"] for r in upload(client, august()).json()["rows"])

    # A household only imports into an empty one, and a failed import adds nothing (not even the company).
    again = import_file(client, exported.content)
    assert again.status_code == 409 and "already has data" in again.json()["detail"]
    assert len(client.get("/api/companies").json()) == 1

    # The original is untouched.
    people.act_as(None)
    assert snapshot(client, cid) == before


def test_company_export_into_an_account_with_data(client, people, category_id):
    cid = client.post("/api/companies", json={"name": "Acme"}).json()["id"]
    client.post(f"/api/companies/{cid}/entries", json={"kind": "income", "date": "2026-02-01", "description": "Sale", "amount": 90})
    exported = client.get(f"/api/companies/{cid}/export")
    assert exported.json()["household"] is None

    partner = people.add("partner@example.com")
    people.act_as(partner)
    client.post("/api/credit-cards", json={"name": "Their card"})  # their household isn't empty
    assert import_file(client, exported.content).json()["companies"] == ["Acme"]
    assert import_file(client, exported.content).status_code == 409  # they already have an Acme
    imported = client.get("/api/companies").json()[0]["id"]
    assert client.get(f"/api/companies/{imported}/summary", params={"year": 2026}).json()["income"] == 90


def test_only_the_owner_imports_a_household(client, people):
    exported = client.get("/api/export/household").content
    editor = people.add("editor@example.com")
    shared = {"X-Household-Id": str(people.local["household_id"])}
    people.share_household(people.local["household_id"], editor, "editor")
    people.act_as(editor)
    response = client.post("/api/import", headers=shared, files={"file": ("x.json", exported, "application/json")})
    assert response.status_code == 403


def test_rejects_bad_files(client, people):
    exported = client.get("/api/export").json()
    people.act_as(people.add("new@example.com"))

    assert import_file(client, b"not json").json()["detail"] == "That isn't a Tallyvio export file"
    assert import_file(client, json.dumps({"format": "other", "version": 1}).encode()).status_code == 400

    # Files from before the rename still import.
    legacy = json.loads(json.dumps(exported))
    legacy["format"] = "moneysage-export"
    legacy["household"] = None
    assert import_file(client, json.dumps(legacy).encode()).status_code == 200

    broken = json.loads(json.dumps(exported))
    broken["household"]["transactions"] = [{
        "date": "2026-01-01", "description": "x", "amount": "5", "category_id": 99999,
    }]
    response = import_file(client, json.dumps(broken).encode())
    assert response.status_code == 400 and "damaged" in response.json()["detail"]
    assert client.get("/api/credit-cards").json() == []  # nothing was kept

    unsafe = json.loads(json.dumps(exported))
    unsafe["household"]["credit_cards"] = [{"name": "Evil", "payment_url": "javascript:alert(1)"}]
    response = import_file(client, json.dumps(unsafe).encode())
    assert response.status_code == 400 and "credit_cards" in response.json()["detail"]
