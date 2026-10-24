from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CreditCard
from app.schemas import CreditCardIn, CreditCardOut

router = APIRouter(prefix="/api/credit-cards", tags=["credit cards"])


def get_card(db: Session, card_id: int) -> CreditCard:
    card = db.get(CreditCard, card_id)
    if card is None:
        raise HTTPException(404, "Credit card not found")
    return card


def _commit_unique(db: Session, name: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A card named '{name}' already exists")


@router.get("", response_model=list[CreditCardOut])
def list_cards(db: Session = Depends(get_db)):
    return db.scalars(select(CreditCard).order_by(CreditCard.name)).all()


@router.post("", response_model=CreditCardOut, status_code=201)
def create_card(body: CreditCardIn, db: Session = Depends(get_db)):
    card = CreditCard(**body.model_dump())
    db.add(card)
    _commit_unique(db, body.name)
    return card


@router.put("/{card_id}", response_model=CreditCardOut)
def update_card(card_id: int, body: CreditCardIn, db: Session = Depends(get_db)):
    card = get_card(db, card_id)
    for key, value in body.model_dump().items():
        setattr(card, key, value)
    _commit_unique(db, body.name)
    return card


@router.delete("/{card_id}", status_code=204)
def delete_card(card_id: int, db: Session = Depends(get_db)):
    db.delete(get_card(db, card_id))
    db.commit()
