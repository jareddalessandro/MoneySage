"""Google sign-in (OpenID Connect, authorization code flow with PKCE).

The browser is sent to Google with a random state, nonce and PKCE challenge, which are also kept in a
short-lived HttpOnly cookie. Google sends it back to /api/auth/callback with a code; the backend checks the
state against the cookie, swaps the code for tokens directly with Google, and verifies the ID token's
signature (Google's published keys), audience, issuer, expiry and nonce before trusting who it names.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

_jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)


class SignInError(Exception):
    """Sign-in failed. `code` goes back to the frontend as ?auth_error=."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


@dataclass
class LoginAttempt:
    state: str
    verifier: str
    nonce: str

    @classmethod
    def new(cls) -> "LoginAttempt":
        return cls(secrets.token_urlsafe(32), secrets.token_urlsafe(48), secrets.token_urlsafe(32))

    def dump(self) -> str:
        return f"{self.state}.{self.verifier}.{self.nonce}"

    @classmethod
    def load(cls, value: str | None) -> "LoginAttempt | None":
        parts = (value or "").split(".")
        return cls(*parts) if len(parts) == 3 and all(parts) else None


@dataclass
class GoogleIdentity:
    sub: str
    email: str
    name: str | None
    picture: str | None


def configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    return f"{settings.public_url.rstrip('/')}/api/auth/callback"


def authorize_url(attempt: LoginAttempt) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).rstrip(b"=").decode()
    return AUTHORIZE_URL + "?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": attempt.state,
        "nonce": attempt.nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })


def _post_token(data: dict) -> dict:
    response = httpx.post(TOKEN_URL, data=data, timeout=15)
    if response.status_code != 200:
        raise SignInError("failed", f"Google refused the sign-in code ({response.status_code})")
    return response.json()


def _signing_key(id_token: str):
    return _jwks.get_signing_key_from_jwt(id_token).key


def verify_id_token(id_token: str, nonce: str) -> GoogleIdentity:
    try:
        claims = jwt.decode(
            id_token,
            _signing_key(id_token),
            algorithms=["RS256"],
            audience=settings.google_client_id,
            leeway=60,
            options={"require": ["iss", "sub", "aud", "exp", "iat"]},
        )
    except (jwt.PyJWTError, httpx.HTTPError) as exc:
        raise SignInError("failed", f"Google's ID token didn't verify: {exc}") from exc
    if claims["iss"] not in ISSUERS:
        raise SignInError("failed", "The ID token wasn't issued by Google")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SignInError("failed", "The ID token is for a different sign-in")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise SignInError("unverified", "Google hasn't verified this account's email address")
    return GoogleIdentity(
        sub=str(claims["sub"]),
        email=claims["email"].strip().lower(),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


def finish(code: str, attempt: LoginAttempt) -> GoogleIdentity:
    """Swap the code from Google's redirect for the verified identity of whoever signed in."""
    try:
        tokens = _post_token({
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
            "code_verifier": attempt.verifier,
        })
    except httpx.HTTPError as exc:
        raise SignInError("failed", f"Couldn't reach Google: {exc}") from exc
    if not tokens.get("id_token"):
        raise SignInError("failed", "Google didn't return an ID token")
    return verify_id_token(tokens["id_token"], attempt.nonce)
