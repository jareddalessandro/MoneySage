from fastapi import APIRouter, HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BudgetItem, Category, CategoryColor, CategoryKind, Transaction
from app.schemas import CategoryIn, CategoryOut, CategoryUpdate
from app.tenancy import HouseholdCtx, HouseholdDep

router = APIRouter(prefix="/api/categories", tags=["categories"])


def get_category(ctx: HouseholdCtx, category_id: int) -> Category:
    category = ctx.db.get(Category, category_id)
    if category is None or category.household_id != ctx.household_id:
        raise HTTPException(404, "Category not found")
    return category


def next_color(db: Session, household_id: int, kind: CategoryKind) -> CategoryColor:
    """The palette color used least by active categories of this kind (palette order breaks ties)."""
    counts = dict(
        db.execute(
            select(Category.color, func.count())
            .where(Category.household_id == household_id, Category.kind == kind, Category.is_archived.is_(False))
            .group_by(Category.color)
        ).all()
    )
    palette = [c for c in CategoryColor if c != CategoryColor.gray]
    return min(palette, key=lambda c: (counts.get(c, 0), palette.index(c)))


@router.get("", response_model=list[CategoryOut])
def list_categories(ctx: HouseholdDep, include_archived: bool = False):
    query = select(Category).where(Category.household_id == ctx.household_id).order_by(Category.kind, Category.name)
    if not include_archived:
        query = query.where(Category.is_archived.is_(False))
    return ctx.db.scalars(query).all()


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, ctx: HouseholdDep):
    db = ctx.db
    category = Category(
        household_id=ctx.household_id,
        name=body.name.strip(),
        kind=body.kind,
        color=body.color or next_color(db, ctx.household_id, body.kind),
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A {body.kind.value} category named '{body.name}' already exists")
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryUpdate, ctx: HouseholdDep):
    db = ctx.db
    category = get_category(ctx, category_id)
    if body.name is not None:
        category.name = body.name.strip()
    if body.color is not None:
        category.color = body.color
    if body.is_archived is not None:
        category.is_archived = body.is_archived
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A category named '{body.name}' already exists")
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, ctx: HouseholdDep):
    db = ctx.db
    category = get_category(ctx, category_id)
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
