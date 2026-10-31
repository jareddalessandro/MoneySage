from datetime import date, timedelta

from sqlalchemy import delete

from app.database import SessionLocal
from app.models import PriceQuote
from app.months import current_month, format_month
from app.services.prices import refresh_all


def test_holding_valuation(client, fake_prices):
    fake_prices["AAPL"] = [100.0, 110.0]
    holding = client.post("/api/holdings", json={
        "ticker": " aapl ", "asset_type": "stock", "quantity": 5, "cost_per_unit": 80,
    }).json()
    assert holding["ticker"] == "AAPL"
    assert holding["price"] == 110
    assert holding["previous_close"] == 100
    assert holding["market_value"] == 550
    assert holding["day_change"] == 50
    assert holding["cost_per_unit"] == 80
    assert holding["cost_basis"] == 400  # total = 5 shares x $80
    assert holding["gain"] == 150


def test_crypto_ticker_normalized(client, fake_prices):
    fake_prices["ETH-USD"] = [3000.0]
    holding = client.post("/api/holdings", json={"ticker": "eth", "asset_type": "crypto", "quantity": 1.25}).json()
    assert holding["ticker"] == "ETH-USD"
    assert holding["market_value"] == 3750


def test_unknown_ticker_rejected(client, fake_prices):
    response = client.post("/api/holdings", json={"ticker": "NOPE", "asset_type": "stock", "quantity": 1})
    assert response.status_code == 400
    assert "NOPE" in response.json()["detail"]


def test_portfolio_summary_and_history(client, fake_prices):
    fake_prices["AAPL"] = [100.0, 110.0, 120.0]
    fake_prices["VOO"] = [500.0]  # only today's price
    client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 2, "cost_per_unit": 75})
    client.post("/api/holdings", json={"ticker": "VOO", "asset_type": "etf", "quantity": 1})

    summary = client.get("/api/portfolio/summary").json()
    assert summary["total_value"] == 740
    assert summary["day_change"] == 20
    assert summary["total_cost"] == 150
    assert summary["total_gain"] == 90

    # History starts once every ticker has a price, so it doesn't jump when VOO appears.
    history = client.get("/api/portfolio/history", params={"days": 30}).json()
    assert [p["value"] for p in history] == [740]



def test_history_opens_on_range_start(client, fake_prices):
    # Closes for the last 10 days ending today: 100, 101, ..., 109.
    fake_prices["AAPL"] = [100.0 + i for i in range(10)]
    client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 1})
    today = date.today()

    # A trading day on the start date: the line starts there.
    history = client.get("/api/portfolio/history", params={"days": 5}).json()
    assert history[0] == {"date": (today - timedelta(days=5)).isoformat(), "value": 104}
    assert [p["value"] for p in history][-1] == 109

    # No quote on the start date (weekend/holiday): it opens with the last close before it.
    with SessionLocal() as db:
        db.execute(delete(PriceQuote).where(PriceQuote.date.in_([today - timedelta(days=d) for d in (5, 6)])))
        db.commit()
    history = client.get("/api/portfolio/history", params={"days": 5}).json()
    assert history[0] == {"date": (today - timedelta(days=5)).isoformat(), "value": 102}
    assert history[1] == {"date": (today - timedelta(days=4)).isoformat(), "value": 105}

    # Short ranges (early January year to date) are allowed.
    assert client.get("/api/portfolio/history", params={"days": 1}).status_code == 200

def test_refresh_records_failures(client, fake_prices):
    fake_prices["AAPL"] = [100.0]
    client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 1})
    fake_prices["AAPL"] = [100.0, 105.0]
    with SessionLocal() as db:
        run = refresh_all(db)
    assert run.status == "success" and run.tickers_updated == 1

    del fake_prices["AAPL"]
    with SessionLocal() as db:
        run = refresh_all(db)
    assert run.status == "failed"
    assert "AAPL" in run.message
    assert client.get("/api/holdings").json()[0]["price"] == 105


def test_cash_in_an_account(client, fake_prices):
    fake_prices["VOO"] = [500.0, 510.0]
    ira = client.post("/api/accounts", json={
        "name": "Roth IRA", "kind": "asset", "subtype": "retirement", "sync_from_holdings": True,
    }).json()
    client.post("/api/holdings", json={"ticker": "VOO", "asset_type": "etf", "quantity": 2, "account_id": ira["id"]})

    # No ticker needed and nothing is fetched (fake_prices has no CASH, so a lookup would 400).
    cash = client.post("/api/holdings", json={
        "asset_type": "cash", "quantity": 1234.56, "cost_per_unit": 999, "account_id": ira["id"],
    })
    assert cash.status_code == 201
    cash = cash.json()
    assert cash["ticker"] == "CASH"
    assert cash["market_value"] == 1234.56
    assert cash["price"] is None and cash["day_change"] == 0
    assert cash["cost_per_unit"] is None and cash["cost_basis"] is None and cash["gain"] is None  # no gains on cash

    summary = client.get("/api/portfolio/summary").json()
    assert summary["total_value"] == 1020 + 1234.56
    assert summary["day_change"] == 20

    # The synced account's balance includes its cash.
    sheet = client.get("/api/balance-sheet", params={"month": format_month(current_month())}).json()
    row = next(r for r in sheet["rows"] if r["account"]["id"] == ira["id"])
    assert row["balance"] == 2254.56

    # Cash is a flat amount on every day of the history.
    assert [p["value"] for p in client.get("/api/portfolio/history", params={"days": 30}).json()] == [
        1000 + 1234.56, 1020 + 1234.56,
    ]

    # Refreshing prices skips cash (fetching "CASH" would fail and mark the run failed).
    with SessionLocal() as db:
        run = refresh_all(db)
    assert run.status == "success" and run.tickers_updated == 1

    updated = client.put(f"/api/holdings/{cash['id']}", json={
        "asset_type": "cash", "quantity": 500, "account_id": ira["id"],
    }).json()
    assert updated["market_value"] == 500


def test_fractional_cost_per_unit(client, fake_prices):
    # Crypto: a fraction of a coin at a per-coin price; the total rounds to the cent.
    fake_prices["BTC-USD"] = [60000.0]
    btc = client.post("/api/holdings", json={
        "ticker": "BTC", "asset_type": "crypto", "quantity": 0.0123, "cost_per_unit": 45123.456789,
    }).json()
    assert btc["cost_per_unit"] == 45123.456789
    assert btc["cost_basis"] == 555.02  # 0.0123 x 45,123.456789 = 555.0185...
    assert btc["market_value"] == 738
    assert btc["gain"] == round(738 - 555.02, 2)


def test_buying_more_merges_into_the_holding(client, fake_prices):
    fake_prices["SOFI"] = [15.0]
    ira = client.post("/api/accounts", json={
        "name": "Roth IRA", "kind": "asset", "subtype": "retirement", "sync_from_holdings": True,
    }).json()
    first = client.post("/api/holdings", json={
        "ticker": "SOFI", "asset_type": "stock", "quantity": 200, "cost_per_unit": 15.30, "account_id": ira["id"],
    }).json()

    # Adding the same ticker to the same account buys more: one holding, share-weighted average cost.
    merged = client.post("/api/holdings", json={
        "ticker": "sofi", "asset_type": "stock", "quantity": 100, "cost_per_unit": 12, "account_id": ira["id"],
        "notes": "dip buy",
    })
    assert merged.status_code == 201
    merged = merged.json()
    assert merged["id"] == first["id"]
    assert merged["quantity"] == 300
    assert merged["cost_per_unit"] == 14.2  # (200 x 15.30 + 100 x 12) / 300
    assert merged["cost_basis"] == 4260  # 3,060 + 1,200: nothing lost to rounding
    assert merged["notes"] == "dip buy"
    assert len(client.get("/api/holdings").json()) == 1

    # The same ticker in another account (or none) stays its own holding.
    other = client.post("/api/holdings", json={"ticker": "SOFI", "asset_type": "stock", "quantity": 5}).json()
    assert other["id"] != first["id"]

    # A buy without a price would throw the average off.
    response = client.post(f"/api/holdings/{first['id']}/trade", json={"side": "buy", "quantity": 10})
    assert response.status_code == 400

    bought = client.post(f"/api/holdings/{first['id']}/trade", json={"side": "buy", "quantity": 100, "price": 18}).json()
    assert bought["quantity"] == 400 and bought["cost_per_unit"] == 15.15  # (4,260 + 1,800) / 400

    # Selling keeps the average cost; the synced account follows.
    sold = client.post(f"/api/holdings/{first['id']}/trade", json={"side": "sell", "quantity": 150}).json()
    assert sold["quantity"] == 250 and sold["cost_per_unit"] == 15.15
    sheet = client.get("/api/balance-sheet", params={"month": format_month(current_month())}).json()
    assert next(r for r in sheet["rows"] if r["account"]["id"] == ira["id"])["balance"] == 250 * 15

    response = client.post(f"/api/holdings/{first['id']}/trade", json={"side": "sell", "quantity": 251})
    assert response.status_code == 400 and "250" in response.json()["detail"]

    # Selling everything removes the holding.
    gone = client.post(f"/api/holdings/{first['id']}/trade", json={"side": "sell", "quantity": 250})
    assert gone.status_code == 200 and gone.json() is None
    assert [h["id"] for h in client.get("/api/holdings").json()] == [other["id"]]


def test_buying_more_without_a_known_cost(client, fake_prices):
    fake_prices["VOO"] = [500.0]
    first = client.post("/api/holdings", json={"ticker": "VOO", "asset_type": "etf", "quantity": 2}).json()
    # The old shares' cost is unknown, so the average stays unknown rather than claiming the new price.
    merged = client.post("/api/holdings", json={
        "ticker": "VOO", "asset_type": "etf", "quantity": 1, "cost_per_unit": 480,
    }).json()
    assert merged["id"] == first["id"] and merged["quantity"] == 3 and merged["cost_per_unit"] is None


def test_cash_deposits_and_withdrawals(client, fake_prices):
    cash = client.post("/api/holdings", json={"asset_type": "cash", "quantity": 1000}).json()
    again = client.post("/api/holdings", json={"asset_type": "cash", "quantity": 250.5}).json()
    assert again["id"] == cash["id"] and again["quantity"] == 1250.5

    after = client.post(f"/api/holdings/{cash['id']}/trade", json={"side": "sell", "quantity": 50.5}).json()
    assert after["quantity"] == 1200 and after["cost_per_unit"] is None


def test_editing_into_a_duplicate_is_refused(client, fake_prices):
    fake_prices["AAPL"] = [100.0]
    fake_prices["MSFT"] = [300.0]
    client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 1})
    msft = client.post("/api/holdings", json={"ticker": "MSFT", "asset_type": "stock", "quantity": 1}).json()
    response = client.put(f"/api/holdings/{msft['id']}", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 1})
    assert response.status_code == 409
    assert {h["ticker"] for h in client.get("/api/holdings").json()} == {"AAPL", "MSFT"}
