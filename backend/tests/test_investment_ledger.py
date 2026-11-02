"""Trades move the account's cash, and every trade lands in the investment ledger."""

from datetime import date, timedelta

from app.months import current_month, format_month


def brokerage(client, sync=True) -> int:
    return client.post("/api/accounts", json={
        "name": "Brokerage", "kind": "asset", "subtype": "brokerage", "sync_from_holdings": sync,
    }).json()["id"]


def holdings_by_ticker(client) -> dict[str, dict]:
    return {h["ticker"]: h for h in client.get("/api/holdings").json()}


def ledger(client) -> list[dict]:
    return client.get("/api/investment-transactions").json()


def trade(client, holding_id: int, **body):
    return client.post(f"/api/holdings/{holding_id}/trade", json=body)


def test_buys_come_out_of_cash_and_sales_go_into_it(client, fake_prices):
    fake_prices["VTI"] = [250.0]
    account = brokerage(client)
    client.post("/api/holdings", json={"asset_type": "cash", "quantity": 1000, "account_id": account})
    vti = client.post("/api/holdings", json={
        "ticker": "VTI", "asset_type": "etf", "quantity": 2, "cost_per_unit": 200, "account_id": account,
    }).json()

    # Buying 3 at $250.10 takes $750.30 from the account's cash.
    assert trade(client, vti["id"], side="buy", quantity=3, price=250.10, use_cash=True).status_code == 200
    held = holdings_by_ticker(client)
    assert held["CASH"]["quantity"] == 249.70 and held["VTI"]["quantity"] == 5

    # More than the cash on hand is refused, and nothing changes.
    short = trade(client, vti["id"], side="buy", quantity=1, price=250, use_cash=True)
    assert short.status_code == 400
    assert "$249.70 in cash" in short.json()["detail"] and "Pay from cash" in short.json()["detail"]
    assert holdings_by_ticker(client)["VTI"]["quantity"] == 5 and len(ledger(client)) == 3

    # Selling puts the proceeds into cash and records the gain against the average cost.
    sold = trade(client, vti["id"], side="sell", quantity=2, price=260, use_cash=True, date="2026-10-15")
    assert sold.status_code == 200
    held = holdings_by_ticker(client)
    assert held["CASH"]["quantity"] == 769.70
    sale = ledger(client)[-1]  # newest first, and this one is backdated
    assert sale["kind"] == "sell" and sale["date"] == "2026-10-15"
    assert sale["amount"] == 520 and sale["cash_change"] == 520
    assert sale["realized_gain"] == round((260 - held["VTI"]["cost_per_unit"]) * 2, 2)
    assert sale["account_name"] == "Brokerage" and sale["ticker"] == "VTI"

    # Without the switch, cash stays put.
    trade(client, vti["id"], side="sell", quantity=1, price=260)
    assert holdings_by_ticker(client)["CASH"]["quantity"] == 769.70
    assert ledger(client)[0]["cash_change"] is None

    kinds = [t["kind"] for t in ledger(client)]
    assert sorted(kinds) == ["add", "add", "buy", "sell", "sell"]


def test_cash_is_created_and_removed_as_needed(client, fake_prices):
    fake_prices["AAPL"] = [100.0]
    account = brokerage(client)
    aapl = client.post("/api/holdings", json={
        "ticker": "AAPL", "asset_type": "stock", "quantity": 10, "account_id": account,
    }).json()

    # A sale into an account with no cash holding starts one.
    trade(client, aapl["id"], side="sell", quantity=4, price=125.5, use_cash=True)
    assert holdings_by_ticker(client)["CASH"]["quantity"] == 502
    # No average cost, so no realized gain.
    assert ledger(client)[0]["realized_gain"] is None

    # Spending all of it removes the cash holding, like selling a whole position.
    trade(client, aapl["id"], side="buy", quantity=4, price=125.5, use_cash=True)
    assert "CASH" not in holdings_by_ticker(client)

    # A holding outside any account has no cash to use.
    loose = client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 1}).json()
    response = trade(client, loose["id"], side="buy", quantity=1, price=100, use_cash=True)
    assert response.status_code == 400 and "isn't in an account" in response.json()["detail"]


def test_trades_need_a_price_and_a_past_date(client, fake_prices):
    fake_prices["AAPL"] = [100.0]
    aapl = client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 10}).json()
    assert trade(client, aapl["id"], side="sell", quantity=1).status_code == 400
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    response = trade(client, aapl["id"], side="sell", quantity=1, price=100, date=tomorrow)
    assert response.status_code == 400 and "future" in response.json()["detail"]
    assert holdings_by_ticker(client)["AAPL"]["quantity"] == 10

    # Cash needs no price: a withdrawal is just dollars.
    cash = client.post("/api/holdings", json={"asset_type": "cash", "quantity": 100}).json()
    trade(client, cash["id"], side="sell", quantity=40)
    entry = ledger(client)[0]
    assert entry["kind"] == "withdraw" and entry["amount"] == 40 and entry["price"] is None


def test_adding_a_holding_can_pay_from_cash(client, fake_prices):
    fake_prices["MSFT"] = [400.0]
    account = brokerage(client)
    client.post("/api/holdings", json={"asset_type": "cash", "quantity": 1000, "account_id": account})
    body = {"ticker": "MSFT", "asset_type": "stock", "quantity": 2, "cost_per_unit": 400, "account_id": account}

    # By default an added holding is something already owned: cash stays, and it's logged as added.
    client.post("/api/holdings", json=body)
    assert holdings_by_ticker(client)["CASH"]["quantity"] == 1000
    assert ledger(client)[0]["kind"] == "add"

    paid = client.post("/api/holdings", json={**body, "pay_from_cash": True})
    assert paid.status_code == 201 and paid.json()["quantity"] == 4
    assert holdings_by_ticker(client)["CASH"]["quantity"] == 200
    assert ledger(client)[0] | {"id": 0, "date": None} == {
        "id": 0, "date": None, "kind": "buy", "asset_type": "stock", "ticker": "MSFT", "account_id": account,
        "account_name": "Brokerage", "quantity": 2, "price": 400, "amount": 800, "realized_gain": None,
        "cash_change": -800,
    }

    # Paying from cash needs the price, and enough cash.
    assert client.post("/api/holdings", json={**body, "cost_per_unit": None, "pay_from_cash": True}).status_code == 400
    assert client.post("/api/holdings", json={**body, "pay_from_cash": True}).status_code == 400
    assert holdings_by_ticker(client)["MSFT"]["quantity"] == 4


def test_synced_balance_follows_cash_moves(client, fake_prices):
    fake_prices["VTI"] = [250.0]
    account = brokerage(client)
    client.post("/api/holdings", json={"asset_type": "cash", "quantity": 1000, "account_id": account})
    vti = client.post("/api/holdings", json={
        "ticker": "VTI", "asset_type": "etf", "quantity": 1, "cost_per_unit": 200, "account_id": account,
    }).json()
    trade(client, vti["id"], side="buy", quantity=2, price=250, use_cash=True)
    sheet = client.get("/api/balance-sheet", params={"month": format_month(current_month())}).json()
    # $500 moved from cash into shares worth $500: the account is still worth 1,000 + 250.
    assert next(r for r in sheet["rows"] if r["account"]["id"] == account)["balance"] == 1250


def test_deleting_a_ledger_entry_keeps_the_holdings(client, people, fake_prices):
    fake_prices["AAPL"] = [100.0]
    aapl = client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 10}).json()
    trade(client, aapl["id"], side="sell", quantity=3, price=100)
    entry = ledger(client)[0]

    # Someone else can't see or delete it; a viewer of this household can see it but not delete it.
    other = people.add("other@example.com")
    people.act_as(other)
    assert ledger(client) == []
    assert client.delete(f"/api/investment-transactions/{entry['id']}").status_code == 404
    viewer = people.add("viewer@example.com")
    people.share_household(people.local["household_id"], viewer, "viewer")
    people.act_as(viewer)
    client.headers["X-Household-Id"] = str(people.local["household_id"])
    assert len(ledger(client)) == 2
    assert client.delete(f"/api/investment-transactions/{entry['id']}").status_code == 403
    del client.headers["X-Household-Id"]

    people.act_as(None)
    assert client.delete(f"/api/investment-transactions/{entry['id']}").status_code == 204
    assert [t["kind"] for t in ledger(client)] == ["add"]
    assert holdings_by_ticker(client)["AAPL"]["quantity"] == 7
