from app.database import SessionLocal
from app.services.prices import refresh_all


def test_holding_valuation(client, fake_prices):
    fake_prices["AAPL"] = [100.0, 110.0]
    holding = client.post("/api/holdings", json={
        "ticker": " aapl ", "asset_type": "stock", "quantity": 5, "cost_basis": 400,
    }).json()
    assert holding["ticker"] == "AAPL"
    assert holding["price"] == 110
    assert holding["previous_close"] == 100
    assert holding["market_value"] == 550
    assert holding["day_change"] == 50
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
    client.post("/api/holdings", json={"ticker": "AAPL", "asset_type": "stock", "quantity": 2, "cost_basis": 150})
    client.post("/api/holdings", json={"ticker": "VOO", "asset_type": "etf", "quantity": 1})

    summary = client.get("/api/portfolio/summary").json()
    assert summary["total_value"] == 740
    assert summary["day_change"] == 20
    assert summary["total_cost"] == 150
    assert summary["total_gain"] == 90

    # History starts once every ticker has a price, so it doesn't jump when VOO appears.
    history = client.get("/api/portfolio/history", params={"days": 30}).json()
    assert [p["value"] for p in history] == [740]


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
