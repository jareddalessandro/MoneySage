from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.database import get_db
from app.models import AccessRole, Company, CompanyAccess, Household, HouseholdAccess, User
from app.schemas import CompanyAccessOut, HouseholdAccessOut, MeOut, UserOut
from app.tenancy import UserDep

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
    return MeOut(
        auth_mode=settings.auth_mode,
        user=UserOut.model_validate(user),
        households=[
            HouseholdAccessOut(
                id=h.id, name=h.name, timezone=h.timezone, role=role,
                owner_name=(o.name or o.email) if o else None,
            )
            for h, role, o in households
        ],
        companies=[CompanyAccessOut(id=cid, name=name, role=role) for cid, name, role in companies],
    )
