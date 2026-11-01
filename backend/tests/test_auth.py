"""Google sign-in (AUTH_MODE=google), sessions, and the cross-site request check.

Google is faked: ID tokens are signed with a key made here, and the token endpoint returns them.
"""

import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import google_oauth
from app.config import settings
from app.database import system_session
from app.main import app
from app.models import AuthSession, HouseholdAccess, User

CLIENT_ID = "test-client.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_ROUTES = {"/api/health", "/api/auth/login", "/api/auth/callback", "/api/auth/logout"}


@pytest.fixture
def google(client, monkeypatch):
    """Google sign-in turned on, with a fake Google. Set `google.claims` to change the next ID token."""
    monkeypatch.setattr(settings, "auth_mode", "google")
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(settings, "public_url", "http://testserver")

    class FakeGoogle:
        def __init__(self):
            self.claims: dict = {}
            self.key = KEY
            self.nonce = ""
            self.token_requests: list[dict] = []

    fake = FakeGoogle()

    def post_token(data):
        fake.token_requests.append(data)
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "google-123", "iat": now,
            "exp": now + 3600, "email": "Pat@Example.com", "email_verified": True, "name": "Pat Doe",
            "picture": "https://lh3.googleusercontent.com/pat", "nonce": fake.nonce, **fake.claims,
        }
        return {"id_token": jwt.encode({k: v for k, v in claims.items() if v is not None}, fake.key, algorithm="RS256")}

    monkeypatch.setattr(google_oauth, "_post_token", post_token)
    monkeypatch.setattr(google_oauth, "_signing_key", lambda token: KEY.public_key())
    return fake


def sign_in(client, google, state: str | None = None, **params):
    """Go through the sign-in flow; returns the callback's response."""
    start = client.get("/api/auth/login", follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers["location"]).query)
    google.nonce = query["nonce"][0]
    return client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": state or query["state"][0], **params},
        follow_redirects=False,
    )


def test_everything_needs_a_session(client, google):
    checked = 0
    for route, methods in app.openapi()["paths"].items():
        if route in PUBLIC_ROUTES:
            continue
        path = re.sub(r"\{[^}]+\}", "1", route)
        for method in methods:
            response = client.request(method.upper(), path)
            assert response.status_code == 401, f"{method} {route} answered {response.status_code}"
            checked += 1
    assert checked > 60


def test_login_sends_the_browser_to_google(client, google):
    response = client.get("/api/auth/login", follow_redirects=False)
    url = urlparse(response.headers["location"])
    query = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["http://testserver/api/auth/callback"]
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["openid email profile"]
    cookie = response.cookies["moneysage_oauth"]
    assert cookie.startswith(query["state"][0] + ".")
    assert "HttpOnly" in response.headers["set-cookie"] and "samesite=lax" in response.headers["set-cookie"].lower()


def test_first_sign_in_creates_an_account_with_its_own_household(client, google):
    response = sign_in(client, google)
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert "moneysage_session" in client.cookies
    # The code went to Google with the PKCE verifier.
    assert google.token_requests[-1]["code_verifier"] and google.token_requests[-1]["code"] == "abc"

    me = client.get("/api/me").json()
    assert me["auth_mode"] == "google"
    assert me["user"]["email"] == "pat@example.com" and me["user"]["name"] == "Pat Doe"
    assert [h["role"] for h in me["households"]] == ["owner"]
    assert len(client.get("/api/categories").json()) == 27
    assert client.get("/api/credit-cards").json() == []  # not the local user's household

    # Signing in again is the same account and household, with Google's latest name.
    client.cookies.clear()
    google.claims = {"name": "Pat D."}
    sign_in(client, google)
    assert client.get("/api/me").json()["user"]["name"] == "Pat D."
    with system_session() as db:
        assert db.query(User).filter(User.is_local.is_(False)).count() == 1
        assert db.query(HouseholdAccess).count() == 2  # the local user's and Pat's


def test_a_known_address_is_linked_on_first_sign_in(client, google):
    with system_session() as db:
        known = User(email="pat@example.com")
        db.add(known)
        db.commit()
    sign_in(client, google)
    me = client.get("/api/me").json()
    assert me["user"]["id"] == known.id
    assert len(me["households"]) == 1


@pytest.mark.parametrize("claims, error", [
    ({"aud": "someone-else"}, "failed"),
    ({"iss": "https://evil.example.com"}, "failed"),
    ({"exp": int(time.time()) - 600}, "failed"),
    ({"nonce": "replayed"}, "failed"),
    ({"email_verified": False}, "unverified"),
    ({"email": None}, "unverified"),
])
def test_bad_id_tokens_are_refused(client, google, claims, error):
    google.claims = claims
    response = sign_in(client, google)
    assert response.headers["location"] == f"/?auth_error={error}"
    assert "moneysage_session" not in client.cookies
    with system_session() as db:
        assert db.query(User).filter(User.is_local.is_(False)).count() == 0


def test_a_token_signed_by_someone_else_is_refused(client, google):
    google.key = OTHER_KEY
    assert sign_in(client, google).headers["location"] == "/?auth_error=failed"


def test_state_must_match_the_browser_that_started(client, google):
    assert sign_in(client, google, state="forged").headers["location"] == "/?auth_error=expired"
    client.cookies.clear()
    response = client.get("/api/auth/callback", params={"code": "abc", "state": "x"}, follow_redirects=False)
    assert response.headers["location"] == "/?auth_error=expired"
    assert google.token_requests == []


def test_cancelled_at_google(client, google):
    response = client.get("/api/auth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert response.headers["location"] == "/?auth_error=cancelled"


def test_allowed_emails(client, google, monkeypatch):
    monkeypatch.setattr(settings, "allowed_emails", "someone@example.com, PAT@example.com")
    assert sign_in(client, google).headers["location"] == "/"
    client.cookies.clear()
    google.claims = {"sub": "google-999", "email": "stranger@example.com"}
    assert sign_in(client, google).headers["location"] == "/?auth_error=not_allowed"


def test_sign_out_and_expiry(client, google):
    sign_in(client, google)
    token = client.cookies["moneysage_session"]
    with system_session() as db:
        stored = db.query(AuthSession).one()
        assert stored.id != token  # only a hash is stored

    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("moneysage_session", token)
    assert client.get("/api/me").status_code == 401

    sign_in(client, google)
    with system_session() as db:
        db.query(AuthSession).update({"expires_at": datetime.now(UTC) - timedelta(minutes=1)})
        db.commit()
    assert client.get("/api/me").status_code == 401


def test_an_idle_session_is_extended(client, google):
    sign_in(client, google)
    with system_session() as db:
        db.query(AuthSession).update({"last_seen_at": datetime.now(UTC) - timedelta(hours=2)})
        db.commit()
    response = client.get("/api/me")
    assert "moneysage_session=" in response.headers["set-cookie"]
    with system_session() as db:
        assert db.query(AuthSession).one().expires_at > datetime.now(UTC) + timedelta(days=29)


def test_secure_cookie_on_https(client, google, monkeypatch):
    monkeypatch.setattr(settings, "public_url", "https://testserver")
    client.base_url = "https://testserver"  # browsers only send Secure cookies over https
    response = sign_in(client, google)
    assert response.headers["location"] == "/"
    cookie = next(c for c in response.headers.get_list("set-cookie") if "moneysage_session" in c)
    assert cookie.startswith("__Host-moneysage_session=") and "Secure" in cookie and "Path=/" in cookie
    assert client.get("/api/me").status_code == 200


def test_sign_in_needs_google_mode_and_credentials(client, monkeypatch):
    assert client.get("/api/auth/login", follow_redirects=False).status_code == 404
    monkeypatch.setattr(settings, "auth_mode", "google")
    monkeypatch.setattr(settings, "google_client_id", None)
    assert client.get("/api/auth/login", follow_redirects=False).status_code == 503


def test_changes_need_the_app_header(client):
    without = client.post("/api/credit-cards", json={"name": "Card"}, headers={"X-Requested-With": ""})
    assert without.status_code == 403
    assert client.post("/api/credit-cards", json={"name": "Card"}).status_code == 201
    assert client.get("/api/credit-cards", headers={"X-Requested-With": ""}).status_code == 200

