from app.months import add_months, current_month, format_month


def make_account(client, name, kind, subtype, **extra):
    response = client.post("/api/accounts", json={"name": name, "kind": kind, "subtype": subtype, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_net_worth_and_copy_previous(client):
    checking = make_account(client, "Checking", "asset", "checking")
    savings = make_account(client, "Savings", "asset", "savings")
    card = make_account(client, "Visa", "liability", "credit_card")

    sheet = client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": checking, "balance": 5000},
        {"account_id": savings, "balance": 20000},
        {"account_id": card, "balance": 1200.50},
    ]}).json()
    assert sheet["total_assets"] == 25000
    assert sheet["total_liabilities"] == 1200.5
    assert sheet["net_worth"] == 23799.5

    # February: enter checking only, then copy the rest from January.
    client.put("/api/balance-sheet", params={"month": "2026-02"}, json={"balances": [
        {"account_id": checking, "balance": 6000},
    ]})
    feb = client.post("/api/balance-sheet/copy-previous", params={"month": "2026-02"}).json()
    balances = {r["account"]["name"]: (r["balance"], r["previous_balance"]) for r in feb["rows"]}
    assert balances == {"Checking": (6000, 5000), "Savings": (20000, 20000), "Visa": (1200.5, 1200.5)}

    trend = client.get("/api/balance-sheet/trend", params={"months": 240}).json()
    assert [(p["month"], p["net_worth"]) for p in trend] == [("2026-01", 23799.5), ("2026-02", 24799.5)]


def test_clearing_a_balance(client):
    checking = make_account(client, "Checking", "asset", "checking")
    client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": checking, "balance": 100},
    ]})
    sheet = client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": checking, "balance": None},
    ]}).json()
    assert sheet["rows"][0]["balance"] is None


def test_archived_account_hidden_without_balance(client):
    old = make_account(client, "Old Bank", "asset", "checking")
    client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": old, "balance": 50},
    ]})
    client.patch(f"/api/accounts/{old}", json={"is_archived": True})

    jan = client.get("/api/balance-sheet", params={"month": "2026-01"}).json()
    feb = client.get("/api/balance-sheet", params={"month": "2026-02"}).json()
    assert [r["account"]["name"] for r in jan["rows"]] == ["Old Bank"]
    assert feb["rows"] == []


def test_brokerage_synced_from_holdings(client, fake_prices):
    fake_prices["VTI"] = [250.0, 260.0]
    fake_prices["BTC-USD"] = [60000.0]
    brokerage = make_account(client, "Brokerage", "asset", "brokerage", sync_from_holdings=True)

    client.post("/api/holdings", json={"ticker": "VTI", "asset_type": "etf", "quantity": 10, "account_id": brokerage})
    client.post("/api/holdings", json={"ticker": "BTC", "asset_type": "crypto", "quantity": 0.5})  # unlinked

    month = format_month(current_month())
    sheet = client.get("/api/balance-sheet", params={"month": month}).json()
    assert sheet["rows"][0]["balance"] == 2600

    # Synced accounts can't be hand-edited for the current month...
    response = client.put("/api/balance-sheet", params={"month": month}, json={"balances": [
        {"account_id": brokerage, "balance": 1},
    ]})
    assert response.status_code == 400
    # ...but past months can be backfilled by hand.
    last_month = format_month(add_months(current_month(), -1))
    response = client.put("/api/balance-sheet", params={"month": last_month}, json={"balances": [
        {"account_id": brokerage, "balance": 2400},
    ]})
    assert response.status_code == 200
