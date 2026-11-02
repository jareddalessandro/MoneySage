"""The Admin page: how many people use this install and when they last did. Account details only; nothing
from inside anyone's households or companies. Only ADMIN_EMAILS can open it; to anyone else it's a 404.

Every table read here (users, sessions, access rows, invites) has no row-level security, so the counts
cover everyone. Company and household rows themselves are never read.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.legal import TERMS_VERSION
from app.models import AccessRole, AuthSession, CompanyAccess, HouseholdAccess, Invite, User
from app.schemas import AdminOverviewOut, AdminStatsOut, AdminUserOut
from app.tenancy import UserDep, is_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: UserDep) -> User:
    if not is_admin(user):
        raise HTTPException(404, "Not found")
    return user


AdminDep = Annotated[User, Depends(require_admin)]


def _count_by_user(db: Session, column) -> dict[int, int]:
    return dict(db.execute(select(column, func.count()).group_by(column)).all())


@router.get("/overview", response_model=AdminOverviewOut)
def overview(_: AdminDep, db: Session = Depends(get_db)):
    """Sign-ups, activity, and one row per account."""
    now = datetime.now(UTC)
    # The offline install's local user can't sign in; whatever it holds isn't anyone's account.
    users = db.scalars(select(User).where(User.is_local.is_(False)).order_by(User.created_at.desc(), User.id.desc())).all()
    ids = {u.id for u in users}
    sessions = dict(db.execute(
        select(AuthSession.user_id, func.count()).where(AuthSession.expires_at > now).group_by(AuthSession.user_id)
    ).all())
    households = _count_by_user(db, HouseholdAccess.user_id)
    companies = _count_by_user(db, CompanyAccess.user_id)
    owned_households = db.scalar(
        select(func.count(func.distinct(HouseholdAccess.household_id)))
        .where(HouseholdAccess.role == AccessRole.owner, HouseholdAccess.user_id.in_(ids))
    )
    owned_companies = db.scalar(
        select(func.count(func.distinct(CompanyAccess.company_id)))
        .where(CompanyAccess.role == AccessRole.owner, CompanyAccess.user_id.in_(ids))
    )

    def since(days: int, when: datetime | None) -> bool:
        return when is not None and when >= now - timedelta(days=days)

    return AdminOverviewOut(
        stats=AdminStatsOut(
            users=len(users),
            new_7d=sum(since(7, u.created_at) for u in users),
            new_30d=sum(since(30, u.created_at) for u in users),
            active_7d=sum(since(7, u.last_seen_at) for u in users),
            active_30d=sum(since(30, u.last_seen_at) for u in users),
            onboarded=sum(u.onboarded_at is not None for u in users),
            households=owned_households or 0,
            companies=owned_companies or 0,
            pending_invites=db.scalar(select(func.count()).select_from(Invite)) or 0,
        ),
        users=[
            AdminUserOut(
                id=u.id, email=u.email, name=u.name, picture_url=u.picture_url,
                created_at=u.created_at, last_login_at=u.last_login_at, last_seen_at=u.last_seen_at,
                onboarded=u.onboarded_at is not None, terms_current=u.terms_version == TERMS_VERSION,
                active_sessions=sessions.get(u.id, 0), households=households.get(u.id, 0),
                companies=companies.get(u.id, 0), is_admin=is_admin(u),
            )
            for u in users
        ],
    )
