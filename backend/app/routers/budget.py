from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BudgetItem, CategoryKind, DeductionType, PaycheckDeduction
from app.routers.categories import get_category
from app.schemas import BudgetCategoryTotal, BudgetItemIn, BudgetItemOut, BudgetSummary
from app.services.budget import budget_by_category, is_paycheck, monthly_amount, paycheck_breakdown

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
        gross_amount=item.gross_amount,
        monthly_gross_amount=None if item.gross_amount is None else monthly_amount(item.gross_amount, item.frequency),
        deductions=item.deductions,
    )


def apply(db: Session, item: BudgetItem, body: BudgetItemIn) -> None:
    category = get_category(db, body.category_id)
    if body.gross_amount is not None or body.deductions:
        if category.kind != CategoryKind.income:
            raise HTTPException(400, "Gross pay and deductions only apply to income")
        if body.gross_amount is None:
            raise HTTPException(400, "Enter gross pay to itemize deductions")
        if body.amount > body.gross_amount:
            raise HTTPException(400, "Take-home pay can't be more than gross pay")
    for key, value in body.model_dump(exclude={"deductions"}).items():
        setattr(item, key, value)
    item.deductions = [
        PaycheckDeduction(
            name=d.name.strip(),
            type=d.type,
            pre_tax=d.pre_tax and d.type != DeductionType.tax,
            amount=d.amount,
            position=i,
        )
        for i, d in enumerate(body.deductions)
    ]


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
    item = BudgetItem()
    apply(db, item, body)
    db.add(item)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.put("/items/{item_id}", response_model=BudgetItemOut)
def update_item(item_id: int, body: BudgetItemIn, db: Session = Depends(get_db)):
    item = get_item(db, item_id)
    apply(db, item, body)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db.delete(get_item(db, item_id))
    db.commit()


@router.get("/summary", response_model=BudgetSummary)
def summary(db: Session = Depends(get_db)):
    items = db.scalars(select(BudgetItem).order_by(BudgetItem.name)).unique().all()
    paychecks = [i for i in items if is_paycheck(i)]
    by_category = budget_by_category(db)
    income = sum((t for _, k, _, t in by_category.values() if k == CategoryKind.income), Decimal(0))
    expenses = sum((t for _, k, _, t in by_category.values() if k == CategoryKind.expense), Decimal(0))
    return BudgetSummary(
        monthly_income=income,
        monthly_expenses=expenses,
        monthly_surplus=income - expenses,
        by_category=sorted(
            (
                BudgetCategoryTotal(category_id=cid, name=name, kind=kind, color=color, monthly_amount=total)
                for cid, (name, kind, color, total) in by_category.items()
            ),
            key=lambda c: -c.monthly_amount,
        ),
        paycheck=paycheck_breakdown(paychecks) if paychecks else None,
        paycheck_items=[paycheck_breakdown([p], p.name, p.id) for p in paychecks],
    )
