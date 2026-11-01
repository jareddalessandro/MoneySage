import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import google_oauth, sessions
from app.config import settings
from app.database import get_db, set_session_user
from app.google_oauth import GoogleIdentity, LoginAttempt, SignInError
from app.models import AccessRole, HouseholdAccess, User
from app.tenancy import create_household

router = APIRouter(prefix="/api/auth", tags=["account"])
log = logging.getLogger(__name__)

# Holds the login attempt between leaving for Google and coming back. Lax, because the callback is a
# top-level navigation from Google, which Lax cookies are sent with.
ATTEMPT_COOKIE = "moneysage_oauth"
ATTEMPT_MINUTES = 10


def _require_google() -> None:
    if settings.auth_mode != "google":
        raise HTTPException(404, "Sign-in is turned off (AUTH_MODE=none)")
    if not google_oauth.configured():
        raise HTTPException(503, "Google sign-in isn't set up: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are missing")


def _back_to_app(error: str | None = None) -> RedirectResponse:
    response = RedirectResponse("/" if error is None else f"/?auth_error={error}", status_code=303)
    response.delete_cookie(ATTEMPT_COOKIE, path="/api/auth", httponly=True, secure=settings.secure_cookies, samesite="lax")
    return response


def sign_in(db: Session, identity: GoogleIdentity) -> User:
    """The user for a verified Google identity, created on first sign-in."""
    allowed = settings.allowed_email_list
    if allowed and identity.email not in allowed:
        raise SignInError("not_allowed", f"{identity.email} isn't in ALLOWED_EMAILS")
    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user is None:
        # Someone already known by email who hasn't signed in with Google yet.
        user = db.scalar(
            select(User).where(User.email == identity.email, User.google_sub.is_(None), User.is_local.is_(False))
        )
    if user is None:
        user = User(email=identity.email)
        db.add(user)
    user.google_sub = identity.sub
    user.name = identity.name
    user.picture_url = identity.picture
    user.last_login_at = datetime.now(UTC)
    # Google lets people change their address; take the new one unless another account already has it.
    if user.email != identity.email and db.scalar(select(User.id).where(User.email == identity.email)) is None:
        user.email = identity.email
    db.flush()
    # Everyone has a household of their own, even if they were first added to someone else's.
    owns_one = db.scalar(
        select(HouseholdAccess.id).where(HouseholdAccess.user_id == user.id, HouseholdAccess.role == AccessRole.owner)
    )
    if owns_one is None:
        set_session_user(db, user.id)  # the household's default categories are written as them
        create_household(db, user)
    return user


@router.get("/login")
def login():
    """Start Google sign-in: sends the browser to Google, which comes back to /api/auth/callback."""
    _require_google()
    attempt = LoginAttempt.new()
    response = RedirectResponse(google_oauth.authorize_url(attempt), status_code=303)
    response.set_cookie(
        ATTEMPT_COOKIE, attempt.dump(), max_age=ATTEMPT_MINUTES * 60, path="/api/auth",
        httponly=True, secure=settings.secure_cookies, samesite="lax",
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    _require_google()
    if error:
        return _back_to_app("cancelled" if error == "access_denied" else "failed")
    attempt = LoginAttempt.load(request.cookies.get(ATTEMPT_COOKIE))
    if attempt is None or not state or not secrets.compare_digest(state, attempt.state) or not code:
        return _back_to_app("expired")
    try:
        user = sign_in(db, google_oauth.finish(code, attempt))
    except SignInError as exc:
        db.rollback()
        log.warning("Sign-in failed: %s", exc)
        return _back_to_app(exc.code)
    token = sessions.start(db, user, request.headers.get("user-agent"))
    db.commit()
    response = _back_to_app()
    sessions.set_cookie(response, token)
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    sessions.end(db, request.cookies.get(sessions.cookie_name()))
    response = Response(status_code=204)
    sessions.clear_cookie(response)
    return response
