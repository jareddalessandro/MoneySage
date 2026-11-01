from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.app_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ---------- Row-level security context ----------
#
# Postgres policies (app.rls) read two transaction-local settings: app.user_id (whose households and
# companies are visible) and app.bypass_rls (background jobs that work across everyone). They're set at
# the start of every transaction from Session.info, so they survive commits. A session with neither set
# sees nothing, so forgetting to set them fails closed. They only take effect when the app connects as
# the restricted role (settings.app_db_password); the database owner isn't subject to the policies.

_SET_CONTEXT = text(
    "SELECT set_config('app.user_id', :user_id, true), set_config('app.bypass_rls', :bypass, true)"
)


def _apply_context(session: Session, connection) -> None:
    user_id = session.info.get("user_id")
    connection.execute(
        _SET_CONTEXT,
        {"user_id": "" if user_id is None else str(user_id), "bypass": "on" if session.info.get("system") else "off"},
    )


@event.listens_for(SessionLocal, "after_begin")
def _on_begin(session: Session, transaction, connection) -> None:
    _apply_context(session, connection)


def set_session_user(db: Session, user_id: int) -> None:
    """Make this session act for a user, including the transaction already open."""
    db.info["user_id"] = user_id
    if db.in_transaction():
        _apply_context(db, db.connection())


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def system_session() -> Iterator[Session]:
    """A session for background work across all households and companies (scheduler, startup)."""
    db = SessionLocal(info={"system": True})
    try:
        yield db
    finally:
        db.close()
