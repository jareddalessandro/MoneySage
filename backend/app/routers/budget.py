from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BudgetItem, CategoryKind
from app.routers.categories import get_category
from app.schemas import BudgetCategoryTotal, BudgetItemIn, BudgetItemOut, BudgetSummary
from app.services.budget import budget_by_category, monthly_amount

router = APIRouter(prefix="/api/budget", tags=["budget"])


def to_out(item: BudgetItem) -> BudgetItemOut:
    return BudgetItemOut(
        id=item.id,
        name=item.name,
        category=item.category,
        amount=item.amount,
        frequency=item.frequency,
        monthly_amount=monthly_amount(item.amount, item.frequency),
        notes=item.notes,
    )


def get_item(db: Session, item_id: int) -> BudgetItem:
    item = db.get(BudgetItem, item_id)
    if item is None:
        raise HTTPException(404, "Budget item not found")
    return item


@router.get("/items", response_model=list[BudgetItemOut])
def list_items(db: Session = Depends(get_db)):
    items = db.scalars(select(BudgetItem).order_by(BudgetItem.name)).unique().all()
    return [to_out(i) for i in items]


@router.post("/items", response_model=BudgetItemOut, status_code=201)
def create_item(body: BudgetItemIn, db: Session = Depends(get_db)):
    get_category(db, body.category_id)
    item = BudgetItem(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.put("/items/{item_id}", response_model=BudgetItemOut)
def update_item(item_id: int, body: BudgetItemIn, db: Session = Depends(get_db)):
    item = get_item(db, item_id)
    get_category(db, body.category_id)
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db.delete(get_item(db, item_id))
    db.commit()


@router.get("/summary", response_model=BudgetSummary)
def summary(db: Session = Depends(get_db)):
    by_category = budget_by_category(db)
    income = sum((t for _, k, t in by_category.values() if k == CategoryKind.income), Decimal(0))
    expenses = sum((t for _, k, t in by_category.values() if k == CategoryKind.expense), Decimal(0))
    return BudgetSummary(
        monthly_income=income,
        monthly_expenses=expenses,
        monthly_surplus=income - expenses,
        by_category=sorted(
            (
                BudgetCategoryTotal(category_id=cid, name=name, kind=kind, monthly_amount=total)
                for cid, (name, kind, total) in by_category.items()
            ),
            key=lambda c: -c.monthly_amount,
        ),
    )
