"""The public site facts, first-time setup, agreeing to the terms, and household settings."""

import pytest

from app import legal
from app.config import settings

SETUP = {"household_name": "The Does", "timezone": "America/Chicago", "accept_terms": True}


@pytest.fixture
def accounts_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "google")


def test_site_is_public(client, monkeypatch):
    monkeypatch.setattr(settings, "operator_name", "Jane Doe")
    monkeypatch.setattr(settings, "contact_email", "privacy@example.com")
    monkeypatch.setattr(settings, "app_version", "1.2.3")
    site = client.get("/api/site").json()
    assert site["operator_name"] == "Jane Doe" and site["contact_email"] == "privacy@example.com"
    assert site["governing_law"] is None and site["terms_version"] == legal.TERMS_VERSION
    assert site["version"] == "1.2.3"


def test_offline_installs_skip_setup(client):
    me = client.get("/api/me").json()
    assert me["needs_setup"] is False and me["needs_terms"] is False


def test_first_time_setup(client, people, accounts_on):
    pat = people.add("pat@example.com")
    people.act_as(pat)
    me = client.get("/api/me").json()
    assert me["needs_setup"] is True and me["needs_terms"] is True

    assert client.post("/api/onboarding", json={**SETUP, "accept_terms": False}).status_code == 422
    assert client.post("/api/onboarding", json={**SETUP, "timezone": "Mars/Olympus"}).status_code == 422
    assert client.post("/api/onboarding", json={**SETUP, "household_name": "   "}).status_code == 422
    assert client.post("/api/onboarding", json={"accept_terms": True}).status_code == 400

    assert client.post("/api/onboarding", json=SETUP).status_code == 204
    me = client.get("/api/me").json()
    assert me["needs_setup"] is False and me["needs_terms"] is False
    assert me["user"]["terms_version"] == legal.TERMS_VERSION
    assert (me["households"][0]["name"], me["households"][0]["timezone"]) == ("The Does", "America/Chicago")


def test_updated_terms_are_agreed_to_again(client, people, accounts_on, monkeypatch):
    pat = people.add("pat@example.com")
    people.act_as(pat)
    client.post("/api/onboarding", json=SETUP)
    monkeypatch.setattr(legal, "TERMS_VERSION", "2099-01-01")
    from app.routers import me as me_router
    monkeypatch.setattr(me_router, "TERMS_VERSION", "2099-01-01")
    me = client.get("/api/me").json()
    assert me["needs_setup"] is False and me["needs_terms"] is True
    # Only the agreement this time; the household stays as it was.
    assert client.post("/api/onboarding", json={"accept_terms": True}).status_code == 204
    me = client.get("/api/me").json()
    assert me["needs_terms"] is False and me["households"][0]["name"] == "The Does"


def test_household_settings(client, people, accounts_on):
    owner = people.local
    response = client.patch("/api/household", json={"name": "Home", "timezone": "Europe/London"})
    assert response.status_code == 200 and response.json()["timezone"] == "Europe/London"
    assert client.patch("/api/household", json={"timezone": "Nowhere/Land"}).status_code == 422

    editor = people.add("editor@example.com")
    people.share_household(owner["household_id"], editor, "editor")
    people.act_as(editor)
    shared = {"X-Household-Id": str(owner["household_id"])}
    assert client.patch("/api/household", json={"name": "Mine now"}, headers=shared).status_code == 403
