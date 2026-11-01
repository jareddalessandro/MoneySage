from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CreditCard
from app.schemas import CreditCardIn, CreditCardOut
from app.tenancy import HouseholdCtx, HouseholdDep

router = APIRouter(prefix="/api/credit-cards", tags=["credit cards"])


def get_card(ctx: HouseholdCtx, card_id: int) -> CreditCard:
    card = ctx.db.get(CreditCard, card_id)
    if card is None or card.household_id != ctx.household_id:
        raise HTTPException(404, "Credit card not found")
    return card


def _commit_unique(db: Session, name: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A card named '{name}' already exists")


@router.get("", response_model=list[CreditCardOut])
def list_cards(ctx: HouseholdDep):
    return ctx.db.scalars(
        select(CreditCard).where(CreditCard.household_id == ctx.household_id).order_by(CreditCard.name)
    ).all()


@router.post("", response_model=CreditCardOut, status_code=201)
def create_card(body: CreditCardIn, ctx: HouseholdDep):
    card = CreditCard(household_id=ctx.household_id, **body.model_dump())
    ctx.db.add(card)
    _commit_unique(ctx.db, body.name)
    return card


@router.put("/{card_id}", response_model=CreditCardOut)
def update_card(card_id: int, body: CreditCardIn, ctx: HouseholdDep):
    card = get_card(ctx, card_id)
    for key, value in body.model_dump().items():
        setattr(card, key, value)
    _commit_unique(ctx.db, body.name)
    return card


@router.delete("/{card_id}", status_code=204)
def delete_card(card_id: int, ctx: HouseholdDep):
    ctx.db.delete(get_card(ctx, card_id))
    ctx.db.commit()
