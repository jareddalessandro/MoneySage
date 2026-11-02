"""The Tiingo price provider, against a fake Tiingo (no network)."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.config import settings
from app.services import prices


class FakeResponse:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def tiingo(monkeypatch):
    """Tiingo turned on; `calls` records each request, `answers` maps URL suffix to (status, body)."""
    monkeypatch.setattr(settings, "price_provider", "tiingo")
    monkeypatch.setattr(settings, "tiingo_api_key", "test-key")
    calls, answers = [], {}

    def get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        for suffix, answer in answers.items():
            if url.endswith(suffix):
                return FakeResponse(*answer)
        return FakeResponse(404, {"detail": "Not found"})

    monkeypatch.setattr(prices.httpx, "get", get)
    return calls, answers


def test_stock_closes(tiingo):
    calls, answers = tiingo
    answers["/tiingo/daily/brk-b/prices"] = (200, [
        {"date": "2026-10-30T00:00:00.000Z", "close": 470.12, "adjClose": 470.12},
        {"date": "2026-10-29T00:00:00.000Z", "close": 468.5},
    ])
    assert prices.fetch_history("BRK-B", "7d") == [
        (date(2026, 10, 29), Decimal("468.5")),
        (date(2026, 10, 30), Decimal("470.12")),
    ]
    assert calls[0]["headers"]["Authorization"] == "Token test-key"
    assert "startDate" in calls[0]["params"]


def test_crypto_closes(tiingo):
    calls, answers = tiingo
    answers["/tiingo/crypto/prices"] = (200, [
        {"ticker": "btcusd", "priceData": [{"date": "2026-10-31T00:00:00+00:00", "close": 70123.456789}]},
    ])
    assert prices.fetch_history("BTC-USD", "1y") == [(date(2026, 10, 31), Decimal("70123.456789"))]
    assert calls[0]["params"]["tickers"] == "btcusd" and calls[0]["params"]["resampleFreq"] == "1day"


def test_unknown_ticker_has_no_data(tiingo):
    assert prices.fetch_history("NOPE", "1y") == []


def test_errors(tiingo, monkeypatch):
    _, answers = tiingo
    answers["/tiingo/daily/aapl/prices"] = (429, {"detail": "Too many requests"})
    with pytest.raises(prices.PriceFetchError, match="429"):
        prices.fetch_history("AAPL", "7d")

    def down(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(prices.httpx, "get", down)
    with pytest.raises(prices.PriceFetchError, match="no route"):
        prices.fetch_history("AAPL", "7d")

    monkeypatch.setattr(settings, "tiingo_api_key", None)
    with pytest.raises(prices.PriceFetchError, match="TIINGO_API_KEY"):
        prices.fetch_history("AAPL", "7d")


def test_period_start():
    today = date(2026, 11, 2)
    assert prices._period_start("7d", today) == date(2026, 10, 26)
    assert prices._period_start("1y", today) == date(2025, 11, 1)
    with pytest.raises(ValueError):
        prices._period_start("forever", today)
