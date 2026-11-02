"""The Admin page: account details for ADMIN_EMAILS only, and nothing from inside households or companies."""

from datetime import UTC, datetime, timedelta

import pytest

from app.config import settings
from app.database import system_session
from app.models import AuthSession, Invite, User
from tests.test_auth import google, sign_in  # noqa: F401 (the fixture is used by name)

USER_FIELDS = {
    "id", "email", "name", "picture_url", "created_at", "last_login_at", "last_seen_at", "onboarded",
    "terms_current", "active_sessions", "households", "companies", "is_admin",
}


@pytest.fixture
def accounts_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "google")
    monkeypatch.setattr(settings, "admin_emails", "Admin@Example.com")


def test_only_admins_can_open_it(client, people, accounts_on):
    admin, pat = people.add("admin@example.com"), people.add("pat@example.com")
    people.act_as(pat)
    assert client.get("/api/me").json()["is_admin"] is False
    assert client.get("/api/admin/overview").status_code == 404
    people.act_as(admin)
    assert client.get("/api/me").json()["is_admin"] is True
    assert client.get("/api/admin/overview").status_code == 200


def test_not_on_an_offline_install(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "local@tallyvio.invalid")
    assert client.get("/api/me").json()["is_admin"] is False
    assert client.get("/api/admin/overview").status_code == 404


def test_overview(client, people, accounts_on, category_id):
    admin, pat = people.add("admin@example.com"), people.add("pat@example.com")
    sam = people.add("sam@example.com", with_household=False)
    people.share_household(pat["household_id"], sam, "viewer")
    now = datetime.now(UTC)
    with system_session() as db:
        db.get(User, pat["id"]).last_seen_at = now - timedelta(days=10)
        db.get(User, pat["id"]).onboarded_at = now
        db.get(User, sam["id"]).created_at = now - timedelta(days=60)
        db.add(AuthSession(id="a" * 64, user_id=pat["id"], expires_at=now + timedelta(days=1)))
        db.add(AuthSession(id="b" * 64, user_id=pat["id"], expires_at=now - timedelta(days=1)))
        db.add(Invite(email="new@example.com", household_id=pat["household_id"], role="editor", target_name="Household"))
        db.commit()
    people.act_as(pat)
    client.post("/api/budget/items", json={
        "name": "Secret paycheck", "category_id": category_id("Salary"), "amount": 4321.98, "frequency": "monthly",
    })
    client.post("/api/companies", json={"name": "Pat's Secret LLC"})

    people.act_as(admin)
    response = client.get("/api/admin/overview")
    body = response.json()
    assert body["stats"] == {
        "users": 3, "new_7d": 2, "new_30d": 2, "active_7d": 0, "active_30d": 1, "onboarded": 1,
        "households": 2, "companies": 1, "pending_invites": 1,
    }
    # Newest first; the offline install's local user isn't an account.
    assert [u["email"] for u in body["users"]] == ["pat@example.com", "admin@example.com", "sam@example.com"]
    rows = {u["email"]: u for u in body["users"]}
    assert all(set(u) == USER_FIELDS for u in body["users"])
    assert rows["pat@example.com"]["active_sessions"] == 1
    assert rows["pat@example.com"]["households"] == 1 and rows["pat@example.com"]["companies"] == 1
    assert rows["sam@example.com"]["households"] == 1 and rows["sam@example.com"]["onboarded"] is False
    assert rows["admin@example.com"]["is_admin"] is True and rows["pat@example.com"]["is_admin"] is False
    # Nothing from inside anyone's household or company.
    assert "Secret" not in response.text and "4321" not in response.text


def test_last_seen_follows_sign_in_and_use(client, google, monkeypatch):  # noqa: F811
    sign_in(client, google)
    with system_session() as db:
        user = db.query(User).filter(User.email == "pat@example.com").one()
        assert user.last_seen_at is not None and user.last_seen_at == user.last_login_at
        earlier = datetime.now(UTC) - timedelta(hours=2)
        user.last_seen_at = earlier
        db.query(AuthSession).update({"last_seen_at": earlier})
        db.commit()
    client.get("/api/me")
    with system_session() as db:
        user = db.query(User).filter(User.email == "pat@example.com").one()
        assert user.last_seen_at > earlier + timedelta(hours=1)
        assert user.last_login_at < user.last_seen_at
