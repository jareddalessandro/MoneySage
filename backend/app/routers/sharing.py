"""Sharing: the owner of a household or company invites people by email as editors or viewers.

An invite waits for whoever signs in with that (Google-verified) email, who accepts or declines it. Only
the owner invites, changes roles or removes people; anyone with access can see who else has it, and anyone
but the owner can leave. Households and companies are shared separately.
"""

from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AccessRole, CompanyAccess, HouseholdAccess, Invite, User
from app.schemas import AcceptedOut, AccessListOut, InviteIn, InviteOut, MyInviteOut, PersonOut, RoleIn
from app.tenancy import (
    DEFAULT_HOUSEHOLD_NAME,
    CompanyCtx,
    CompanyDep,
    HouseholdCtx,
    HouseholdDep,
    UserDep,
    require_owner,
)

router = APIRouter(prefix="/api", tags=["sharing"])

# People with access plus pending invites, per household or company.
MAX_PEOPLE = 50


@dataclass
class Target:
    """A household or company being shared, and the requester's role in it."""

    db: Session
    user: User
    role: AccessRole
    kind: Literal["household", "company"]
    id: int
    name: str

    @property
    def access(self):
        return HouseholdAccess if self.kind == "household" else CompanyAccess

    @property
    def fk(self):
        return self.access.household_id if self.kind == "household" else self.access.company_id

    @property
    def invite_fk(self):
        return Invite.household_id if self.kind == "household" else Invite.company_id

    @property
    def what(self) -> str:
        return f"this {self.kind}"


def _household(ctx: HouseholdCtx) -> Target:
    name = ctx.household.name
    if name == DEFAULT_HOUSEHOLD_NAME:
        owner = ctx.db.scalar(
            select(User)
            .join(HouseholdAccess, HouseholdAccess.user_id == User.id)
            .where(HouseholdAccess.household_id == ctx.household_id, HouseholdAccess.role == AccessRole.owner)
        )
        if owner is not None:
            name = f"{owner.name or owner.email}'s household"
    return Target(ctx.db, ctx.user, ctx.role, "household", ctx.household_id, name)


def _company(ctx: CompanyCtx) -> Target:
    return Target(ctx.db, ctx.user, ctx.role, "company", ctx.company_id, ctx.company.name)


def _require_accounts() -> None:
    if settings.auth_mode != "google":
        raise HTTPException(400, "Sharing needs sign-in (AUTH_MODE=google)")


def _list(t: Target) -> AccessListOut:
    rows = t.db.execute(
        select(User, t.access.role)
        .join(t.access, t.access.user_id == User.id)
        .where(t.fk == t.id)
        .order_by(t.access.role != AccessRole.owner, t.access.id)
    ).all()
    people = [
        PersonOut(user_id=u.id, name=u.name, email=u.email, picture_url=u.picture_url, role=role, is_you=u.id == t.user.id)
        for u, role in rows
    ]
    invites = []
    if t.role == AccessRole.owner:
        invites = [
            InviteOut.model_validate(i)
            for i in t.db.scalars(select(Invite).where(t.invite_fk == t.id).order_by(Invite.id))
        ]
    return AccessListOut(people=people, invites=invites, can_manage=t.role == AccessRole.owner)


def _invite(t: Target, body: InviteIn) -> Invite:
    _require_accounts()
    require_owner(t.role, f"share {t.what}")
    db = t.db
    if body.email == t.user.email:
        raise HTTPException(400, "That's you")
    has_access = db.scalar(
        select(t.access.id).join(User, User.id == t.access.user_id).where(t.fk == t.id, User.email == body.email)
    )
    if has_access:
        raise HTTPException(409, f"{body.email} already has access")
    if db.scalar(select(Invite.id).where(t.invite_fk == t.id, Invite.email == body.email)):
        raise HTTPException(409, f"{body.email} is already invited")
    count = len(db.scalars(select(t.access.id).where(t.fk == t.id)).all()) + len(
        db.scalars(select(Invite.id).where(t.invite_fk == t.id)).all()
    )
    if count >= MAX_PEOPLE:
        raise HTTPException(400, f"{t.what.capitalize()} can be shared with at most {MAX_PEOPLE} people")
    invite = Invite(
        email=body.email, role=AccessRole(body.role), target_name=t.name[:200], invited_by_id=t.user.id,
        **{f"{t.kind}_id": t.id},
    )
    db.add(invite)
    db.commit()
    return invite


def _revoke(t: Target, invite_id: int) -> None:
    require_owner(t.role, f"manage who can open {t.what}")
    t.db.execute(delete(Invite).where(Invite.id == invite_id, t.invite_fk == t.id))
    t.db.commit()


def _access_row(t: Target, user_id: int):
    row = t.db.scalar(select(t.access).where(t.fk == t.id, t.access.user_id == user_id))
    if row is None:
        raise HTTPException(404, "They don't have access")
    if row.role == AccessRole.owner:
        raise HTTPException(400, "The owner's access can't be changed")
    return row


def _set_role(t: Target, user_id: int, body: RoleIn) -> AccessListOut:
    require_owner(t.role, f"manage who can open {t.what}")
    _access_row(t, user_id).role = AccessRole(body.role)
    t.db.commit()
    return _list(t)


def _remove(t: Target, user_id: int) -> None:
    require_owner(t.role, f"manage who can open {t.what}")
    t.db.delete(_access_row(t, user_id))
    t.db.commit()


# ---------- The current household ----------

@router.get("/household/access", response_model=AccessListOut)
def household_access(ctx: HouseholdDep):
    return _list(_household(ctx))


@router.post("/household/access/invites", response_model=InviteOut, status_code=201)
def invite_to_household(body: InviteIn, ctx: HouseholdDep):
    return _invite(_household(ctx), body)


@router.delete("/household/access/invites/{invite_id}", status_code=204)
def revoke_household_invite(invite_id: int, ctx: HouseholdDep):
    _revoke(_household(ctx), invite_id)


@router.patch("/household/access/{user_id}", response_model=AccessListOut)
def set_household_role(user_id: int, body: RoleIn, ctx: HouseholdDep):
    return _set_role(_household(ctx), user_id, body)


@router.delete("/household/access/{user_id}", status_code=204)
def remove_from_household(user_id: int, ctx: HouseholdDep):
    _remove(_household(ctx), user_id)


# ---------- A company ----------

@router.get("/companies/{company_id}/access", response_model=AccessListOut)
def company_access(company_id: int, ctx: CompanyDep):
    return _list(_company(ctx))


@router.post("/companies/{company_id}/access/invites", response_model=InviteOut, status_code=201)
def invite_to_company(company_id: int, body: InviteIn, ctx: CompanyDep):
    return _invite(_company(ctx), body)


@router.delete("/companies/{company_id}/access/invites/{invite_id}", status_code=204)
def revoke_company_invite(company_id: int, invite_id: int, ctx: CompanyDep):
    _revoke(_company(ctx), invite_id)


@router.patch("/companies/{company_id}/access/{user_id}", response_model=AccessListOut)
def set_company_role(company_id: int, user_id: int, body: RoleIn, ctx: CompanyDep):
    return _set_role(_company(ctx), user_id, body)


@router.delete("/companies/{company_id}/access/{user_id}", status_code=204)
def remove_from_company(company_id: int, user_id: int, ctx: CompanyDep):
    _remove(_company(ctx), user_id)


# ---------- The signed-in user's side ----------
# These take only the user (not HouseholdDep/CompanyDep), so viewers can leave and invitees can answer.

def _leave(db: Session, user: User, access, fk, target_id: int, what: str) -> None:
    row = db.scalar(select(access).where(fk == target_id, access.user_id == user.id))
    if row is None:
        raise HTTPException(404, f"{what.capitalize()} not found")
    if row.role == AccessRole.owner:
        raise HTTPException(400, f"You own this {what}, so you can't leave it")
    db.delete(row)
    db.commit()


@router.delete("/me/households/{household_id}", status_code=204)
def leave_household(household_id: int, user: UserDep, db: Session = Depends(get_db)):
    _leave(db, user, HouseholdAccess, HouseholdAccess.household_id, household_id, "household")


@router.delete("/me/companies/{company_id}", status_code=204)
def leave_company(company_id: int, user: UserDep, db: Session = Depends(get_db)):
    _leave(db, user, CompanyAccess, CompanyAccess.company_id, company_id, "company")


@router.get("/invites", response_model=list[MyInviteOut])
def my_invites(user: UserDep, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Invite, User)
        .outerjoin(User, User.id == Invite.invited_by_id)
        .where(Invite.email == user.email)
        .order_by(Invite.id)
    ).all()
    return [
        MyInviteOut(
            id=i.id,
            kind="household" if i.household_id is not None else "company",
            name=i.target_name,
            role=i.role,
            invited_by=(by.name or by.email) if by else None,
            created_at=i.created_at,
        )
        for i, by in rows
    ]


def _my_invite(db: Session, user: User, invite_id: int) -> Invite:
    invite = db.scalar(select(Invite).where(Invite.id == invite_id, Invite.email == user.email))
    if invite is None:
        raise HTTPException(404, "Invite not found")
    return invite


@router.post("/invites/{invite_id}/accept", response_model=AcceptedOut)
def accept_invite(invite_id: int, user: UserDep, db: Session = Depends(get_db)):
    invite = _my_invite(db, user, invite_id)
    if invite.household_id is not None:
        kind, target_id, access, fk = "household", invite.household_id, HouseholdAccess, HouseholdAccess.household_id
    else:
        kind, target_id, access, fk = "company", invite.company_id, CompanyAccess, CompanyAccess.company_id
    if db.scalar(select(access.id).where(fk == target_id, access.user_id == user.id)) is None:
        db.add(access(user_id=user.id, role=invite.role, **{f"{kind}_id": target_id}))
    db.delete(invite)
    db.commit()
    return AcceptedOut(kind=kind, id=target_id)


@router.post("/invites/{invite_id}/decline", status_code=204)
def decline_invite(invite_id: int, user: UserDep, db: Session = Depends(get_db)):
    db.delete(_my_invite(db, user, invite_id))
    db.commit()
