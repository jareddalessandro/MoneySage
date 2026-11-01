import os
from datetime import date, timedelta
from decimal import Decimal

import psycopg
import pytest

# Point the app at a throwaway database before anything imports app.config. The app connects as a
# restricted role, as in production, so row-level security is exercised by every test. TEST_WITHOUT_RLS=1
# connects as the owner instead, which checks that the app's own household and company filters hold up alone.
MAIN_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://moneysage:moneysage@db:5432/moneysage")
TEST_URL = MAIN_URL.rsplit("/", 1)[0] + "/moneysage_test"
RLS = os.environ.get("TEST_WITHOUT_RLS") != "1"
os.environ["DATABASE_URL"] = TEST_URL
os.environ["APP_DB_USER"] = "moneysage_test_app"
os.environ["APP_DB_PASSWORD"] = "moneysage-test-app" if RLS else ""
os.environ["AUTH_MODE"] = "none"
os.environ["ENABLE_SCHEDULER"] = "false"


def _ensure_test_database() -> None:
    admin = MAIN_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'moneysage_test'").fetchone():
            conn.execute("CREATE DATABASE moneysage_test")


_ensure_test_database()

from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models, rls  # noqa: E402
from app.database import Base, get_db, set_session_user, system_session  # noqa: E402
from app.db_role import ensure_app_role  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AccessRole, CompanyAccess, HouseholdAccess, User  # noqa: E402
from app.services import prices  # noqa: E402
from app.tenancy import create_household, get_current_user  # noqa: E402

# The database owner, for creating the schema and resetting it between tests.
owner_engine = create_engine(TEST_URL)


@pytest.fixture(scope="session", autouse=True)
def schema():
    with owner_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        Base.metadata.create_all(conn)
        for statement in rls.statements():
            conn.execute(text(statement))
        if RLS:
            ensure_app_role(conn, os.environ["APP_DB_USER"], os.environ["APP_DB_PASSWORD"])
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    with owner_engine.begin() as conn:
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
    with TestClient(app) as c:  # runs lifespan, which creates the local user and their household
        yield c


@pytest.fixture
def category_id(client):
    categories = client.get("/api/categories").json()

    def lookup(name: str) -> int:
        return next(c["id"] for c in categories if c["name"] == name)

    return lookup


class People:
    """Other people using the app. Requests come from the local user until `act_as` switches."""

    def __init__(self):
        self.current: int | None = None

        def current_user(db: Session = Depends(get_db)) -> User:
            if self.current is None:
                user = db.query(User).filter(User.is_local.is_(True)).one()
            else:
                user = db.get(User, self.current)
            set_session_user(db, user.id)
            return user

        app.dependency_overrides[get_current_user] = current_user

    def add(self, email: str, with_household: bool = True) -> dict:
        """A new user (and their own household): {"id", "household_id"}."""
        with system_session() as db:
            user = User(email=email, name=email.split("@")[0])
            db.add(user)
            db.flush()
            household_id = create_household(db, user).id if with_household else None
            db.commit()
            return {"id": user.id, "household_id": household_id}

    @property
    def local(self) -> dict:
        with system_session() as db:
            user = db.query(User).filter(User.is_local.is_(True)).one()
            access = db.query(HouseholdAccess).filter(HouseholdAccess.user_id == user.id).first()
            return {"id": user.id, "household_id": access.household_id}

    def act_as(self, person: dict | None) -> None:
        self.current = None if person is None else person["id"]

    def share_household(self, household_id: int, person: dict, role: str) -> None:
        with system_session() as db:
            db.add(HouseholdAccess(household_id=household_id, user_id=person["id"], role=AccessRole(role)))
            db.commit()

    def share_company(self, company_id: int, person: dict, role: str) -> None:
        with system_session() as db:
            db.add(CompanyAccess(company_id=company_id, user_id=person["id"], role=AccessRole(role)))
            db.commit()


@pytest.fixture
def people(client):
    people = People()
    yield people
    app.dependency_overrides.pop(get_current_user, None)
