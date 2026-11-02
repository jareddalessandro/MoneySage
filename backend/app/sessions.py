"""Signed-in sessions (AUTH_MODE=google): an HttpOnly cookie holding a random token, looked up by its hash."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthSession, User

# How often a session's expiry is pushed forward (not on every request, to spare the database a write).
TOUCH_EVERY = timedelta(hours=1)


def cookie_name() -> str:
    # The __Host- prefix makes browsers refuse the cookie unless it's Secure, host-only and for the whole
    # site, so another subdomain can't set or overwrite it. It needs https, so plain-http installs go without.
    return "__Host-tallyvio_session" if settings.secure_cookies else "tallyvio_session"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def start(db: Session, user: User, user_agent: str | None) -> str:
    """A new session for `user`; returns the token for the cookie. The caller commits."""
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.expires_at < _now()))
    db.add(AuthSession(
        id=_hash(token),
        user_id=user.id,
        expires_at=_now() + timedelta(days=settings.session_days),
        user_agent=(user_agent or "")[:300] or None,
    ))
    return token


def user_for(db: Session, token: str | None) -> tuple[User | None, bool]:
    """The user a cookie's token belongs to, if the session is still good, and whether its expiry was just
    pushed forward (then the cookie should be sent again so the browser keeps it as long)."""
    if not token:
        return None, False
    session = db.get(AuthSession, _hash(token))
    now = _now()
    if session is None or session.expires_at <= now:
        return None, False
    user = db.get(User, session.user_id)
    touched = now - session.last_seen_at >= TOUCH_EVERY
    if touched:
        session.last_seen_at = now
        session.expires_at = now + timedelta(days=settings.session_days)
        if user is not None:
            user.last_seen_at = now
        db.commit()
    return user, touched


def end(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.id == _hash(token)))
        db.commit()


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        cookie_name(), token, max_age=settings.session_days * 86400, path="/",
        httponly=True, secure=settings.secure_cookies, samesite="lax",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(cookie_name(), path="/", httponly=True, secure=settings.secure_cookies, samesite="lax")
