from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.legal import TERMS_VERSION
from app.database import get_db
from app.models import AccessRole, Company, CompanyAccess, Household, HouseholdAccess, User
from app.schemas import (
    CompanyAccessOut,
    HouseholdAccessOut,
    HouseholdOut,
    HouseholdUpdate,
    MeOut,
    OnboardingIn,
    SiteOut,
    UserOut,
)
from app.tenancy import HouseholdDep, UserDep, require_owner

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/me", response_model=MeOut)
def me(user: UserDep, db: Session = Depends(get_db)):
    """Who's signed in, and the households and companies they can open."""
    owner_access = aliased(HouseholdAccess)
    owner = aliased(User)
    households = db.execute(
        select(Household, HouseholdAccess.role, owner)
        .join(HouseholdAccess, HouseholdAccess.household_id == Household.id)
        .outerjoin(owner_access, (owner_access.household_id == Household.id) & (owner_access.role == AccessRole.owner))
        .outerjoin(owner, owner.id == owner_access.user_id)
        .where(HouseholdAccess.user_id == user.id)
        .order_by(HouseholdAccess.role != AccessRole.owner, HouseholdAccess.id)
    ).all()
    companies = db.execute(
        select(Company.id, Company.name, CompanyAccess.role)
        .join(CompanyAccess, CompanyAccess.company_id == Company.id)
        .where(CompanyAccess.user_id == user.id)
        .order_by(Company.name, Company.id)
    ).all()
    accounts = settings.auth_mode == "google"
    return MeOut(
        auth_mode=settings.auth_mode,
        user=UserOut.model_validate(user),
        needs_setup=accounts and user.onboarded_at is None,
        needs_terms=accounts and user.terms_version != TERMS_VERSION,
        households=[
            HouseholdAccessOut(
                id=h.id, name=h.name, timezone=h.timezone, role=role,
                owner_name=(o.name or o.email) if o else None,
            )
            for h, role, o in households
        ],
        companies=[CompanyAccessOut(id=cid, name=name, role=role) for cid, name, role in companies],
    )


@router.get("/site", response_model=SiteOut)
def site():
    """Public: who runs this install, for the landing page and the legal pages."""
    return SiteOut(
        auth_mode=settings.auth_mode,
        operator_name=settings.operator_name or None,
        contact_email=settings.contact_email or None,
        governing_law=settings.governing_law or None,
        terms_version=TERMS_VERSION,
    )


@router.post("/onboarding", status_code=204)
def onboarding(body: OnboardingIn, user: UserDep, db: Session = Depends(get_db)):
    """First-time setup: name and timezone for your own household, and agreeing to the terms. Later, after
    the terms change, it's just agreeing again."""
    if user.onboarded_at is None:
        if body.household_name is None or body.timezone is None:
            raise HTTPException(400, "Name your household and pick its timezone")
        household = db.scalar(
            select(Household)
            .join(HouseholdAccess, HouseholdAccess.household_id == Household.id)
            .where(HouseholdAccess.user_id == user.id, HouseholdAccess.role == AccessRole.owner)
            .order_by(HouseholdAccess.id)
        )
        if household is not None:
            household.name = body.household_name
            household.timezone = body.timezone
        user.onboarded_at = datetime.now(UTC)
    user.terms_version = TERMS_VERSION
    user.terms_accepted_at = datetime.now(UTC)
    db.commit()


@router.patch("/household", response_model=HouseholdOut)
def update_household(body: HouseholdUpdate, ctx: HouseholdDep):
    """Rename the current household or change its timezone (owner only)."""
    require_owner(ctx.role, "change this household's settings")
    if body.name is not None:
        ctx.household.name = body.name.strip() or ctx.household.name
    if body.timezone is not None:
        ctx.household.timezone = body.timezone
    ctx.db.commit()
    return ctx.household
