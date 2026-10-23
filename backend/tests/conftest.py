import os
from datetime import date, timedelta
from decimal import Decimal

import psycopg
import pytest

# Point the app at a throwaway database before anything imports app.config.
MAIN_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://moneysage:moneysage@db:5432/moneysage")
TEST_URL = MAIN_URL.rsplit("/", 1)[0] + "/moneysage_test"
os.environ["DATABASE_URL"] = TEST_URL
os.environ["ENABLE_SCHEDULER"] = "false"


def _ensure_test_database() -> None:
    admin = MAIN_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'moneysage_test'").fetchone():
            conn.execute("CREATE DATABASE moneysage_test")


_ensure_test_database()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import prices  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def fake_prices(monkeypatch):
    """Ticker -> list of daily closes ending today. Unknown tickers return no data."""
    table: dict[str, list[float]] = {}

    def fetch(ticker: str, period: str):
        closes = table.get(ticker, [])
        today = date.today()
        return [
            (today - timedelta(days=len(closes) - 1 - i), Decimal(str(c))) for i, c in enumerate(closes)
        ]

    monkeypatch.setattr(prices, "fetch_history", fetch)
    return table


@pytest.fixture
def client():
    with TestClient(app) as c:  # runs lifespan, which seeds default categories
        yield c


@pytest.fixture
def category_id(client):
    categories = client.get("/api/categories").json()

    def lookup(name: str) -> int:
        return next(c["id"] for c in categories if c["name"] == name)

    return lookup
