"""Who's asking, and which household or company they're working in.

Every household route takes a `HouseholdDep` and filters its queries by `ctx.household_id`; every company
route under /api/companies/{company_id} takes a `CompanyDep`. Both resolve only containers the user has
access to (anything else is a 404, so ids of other people's data aren't confirmed), and both refuse writes
(any method but GET/HEAD/OPTIONS) from viewers with a 403. Postgres row-level security (app.rls) backs this
up when the restricted database role is in use.
"""

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import sessions
from app.config import settings
from app.database import get_db, set_session_user
from app.models import AccessRole, Company, CompanyAccess, Household, HouseholdAccess, User
from app.months import today_in
from app.seed import seed_categories

READ_METHODS = {"GET", "HEAD", "OPTIONS"}
LOCAL_EMAIL = "local@tallyvio.invalid"
DEFAULT_HOUSEHOLD_NAME = "Household"


# ---------- The current user ----------

def get_current_user(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    if settings.auth_mode == "none":
        user = db.scalar(select(User).where(User.is_local.is_(True)))
        if user is None:
            raise HTTPException(503, "The local user hasn't been set up yet; restart the backend")
    else:
        token = request.cookies.get(sessions.cookie_name())
        user, touched = sessions.user_for(db, token)
        if user is None:
            raise HTTPException(401, "Sign in to continue")
        if touched:
            sessions.set_cookie(response, token)
    set_session_user(db, user.id)
    return user


UserDep = Annotated[User, Depends(get_current_user)]


def is_admin(user: User) -> bool:
    """Can open the Admin page: a signed-in account listed in ADMIN_EMAILS (never the offline local user)."""
    return settings.auth_mode == "google" and not user.is_local and user.email in settings.admin_email_list


def create_household(db: Session, owner: User, name: str = DEFAULT_HOUSEHOLD_NAME) -> Household:
    """A new household owned by `owner`, with the default categories."""
    household = Household(name=name, timezone=settings.default_timezone)
    db.add(household)
    db.flush()
    db.add(HouseholdAccess(household_id=household.id, user_id=owner.id, role=AccessRole.owner))
    db.flush()
    seed_categories(db, household.id)
    return household


def ensure_local_user(db: Session) -> User:
    """The automatic user of an offline install, and a household for them if they have none."""
    user = db.scalar(select(User).where(User.is_local.is_(True)))
    if user is None:
        user = User(email=LOCAL_EMAIL, name="You", is_local=True)
        db.add(user)
        db.flush()
    if db.scalar(select(HouseholdAccess.id).where(HouseholdAccess.user_id == user.id).limit(1)) is None:
        create_household(db, user)
    db.commit()
    return user


# ---------- Households ----------

@dataclass
class HouseholdCtx:
    db: Session
    user: User
    household: Household
    role: AccessRole

    @property
    def household_id(self) -> int:
        return self.household.id

    @property
    def can_write(self) -> bool:
        return self.role != AccessRole.viewer

    def today(self) -> date:
        return today_in(self.household.timezone)

    def current_month(self) -> date:
        return self.today().replace(day=1)


def household_ctx(
    request: Request,
    user: UserDep,
    db: Session = Depends(get_db),
    x_household_id: int | None = Header(default=None, description="Defaults to the household you own"),
) -> HouseholdCtx:
    query = (
        select(Household, HouseholdAccess.role)
        .join(HouseholdAccess, HouseholdAccess.household_id == Household.id)
        .where(HouseholdAccess.user_id == user.id)
    )
    if x_household_id is not None:
        row = db.execute(query.where(Household.id == x_household_id)).first()
        if row is None:
            raise HTTPException(404, "Household not found")
    else:
        # Their own household first, then the earliest one shared with them.
        row = db.execute(
            query.order_by(HouseholdAccess.role != AccessRole.owner, HouseholdAccess.id).limit(1)
        ).first()
        if row is None:
            raise HTTPException(404, "You don't have a household yet")
    household, role = row
    if request.method not in READ_METHODS and role == AccessRole.viewer:
        raise HTTPException(403, "You have view-only access to this household")
    return HouseholdCtx(db, user, household, role)


HouseholdDep = Annotated[HouseholdCtx, Depends(household_ctx)]


# ---------- Companies ----------

@dataclass
class CompanyCtx:
    db: Session
    user: User
    company: Company
    role: AccessRole

    @property
    def company_id(self) -> int:
        return self.company.id


def company_ctx(company_id: int, request: Request, user: UserDep, db: Session = Depends(get_db)) -> CompanyCtx:
    row = db.execute(
        select(Company, CompanyAccess.role)
        .join(CompanyAccess, CompanyAccess.company_id == Company.id)
        .where(Company.id == company_id, CompanyAccess.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(404, "Company not found")
    company, role = row
    if request.method not in READ_METHODS and role == AccessRole.viewer:
        raise HTTPException(403, "You have view-only access to this company")
    return CompanyCtx(db, user, company, role)


CompanyDep = Annotated[CompanyCtx, Depends(company_ctx)]


def require_owner(role: AccessRole, what: str) -> None:
    if role != AccessRole.owner:
        raise HTTPException(403, f"Only the owner can {what}")
