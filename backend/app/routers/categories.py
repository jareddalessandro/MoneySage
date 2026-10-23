from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BudgetItem, Category, Transaction
from app.schemas import CategoryIn, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


def get_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(include_archived: bool = False, db: Session = Depends(get_db)):
    query = select(Category).order_by(Category.kind, Category.name)
    if not include_archived:
        query = query.where(Category.is_archived.is_(False))
    return db.scalars(query).all()


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    category = Category(name=body.name.strip(), kind=body.kind)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A {body.kind.value} category named '{body.name}' already exists")
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryUpdate, db: Session = Depends(get_db)):
    category = get_category(db, category_id)
    if body.name is not None:
        category.name = body.name.strip()
    if body.is_archived is not None:
        category.is_archived = body.is_archived
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A category named '{body.name}' already exists")
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = get_category(db, category_id)
    in_use = db.scalar(
        select(
            exists().where(Transaction.category_id == category_id)
            | exists().where(BudgetItem.category_id == category_id)
        )
    )
    if in_use:
        raise HTTPException(409, "Category is in use by transactions or budget items; archive it instead")
    db.delete(category)
    db.commit()
