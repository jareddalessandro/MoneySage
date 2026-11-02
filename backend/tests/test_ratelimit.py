"""Per-visitor request limits."""

import pytest

from app import ratelimit
from app.config import settings
from app.ratelimit import Limiter


def test_limits_per_client_and_window():
    limiter = Limiter()
    for i in range(20):
        assert limiter.check("1.1.1.1", "GET", "/api/auth/login", now=100 + i) is None
    retry = limiter.check("1.1.1.1", "GET", "/api/auth/login", now=119.5)
    assert retry is not None and 1 <= retry <= 60
    # Someone else isn't affected, and the first client gets in again once the window passes.
    assert limiter.check("2.2.2.2", "GET", "/api/auth/login", now=119.5) is None
    assert limiter.check("1.1.1.1", "GET", "/api/auth/login", now=161) is None


def test_which_rules_apply():
    names = lambda m, p: [r.name for r in ratelimit.RULES if r.matches(m, p)]  # noqa: E731
    assert names("POST", "/api/companies/3/access/invites") == ["invites", "writes", "all"]
    assert names("POST", "/api/household/access/invites") == ["invites", "writes", "all"]
    assert names("POST", "/api/companies/3/entries") == ["writes", "all"]
    assert names("POST", "/api/statements/preview") == ["uploads", "writes", "all"]
    assert names("GET", "/api/budget/items") == ["all"]


def test_turned_away_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(ratelimit, "limiter", Limiter())
    for _ in range(20):
        assert client.get("/api/auth/login", follow_redirects=False).status_code != 429
    response = client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1
    assert client.get("/api/me").status_code == 200  # other routes still work


def test_forgets_idle_clients():
    limiter = Limiter()
    limiter.check("1.1.1.1", "GET", "/api/me", now=0)
    limiter.check("2.2.2.2", "GET", "/api/me", now=4000)
    limiter.last_sweep = 0
    limiter.check("2.2.2.2", "GET", "/api/me", now=4000)
    assert all(client == "2.2.2.2" for _, client in limiter.hits)
