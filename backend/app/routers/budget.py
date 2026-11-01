from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.models import BudgetItem, CategoryKind, DeductionType, PaycheckDeduction
from app.routers.categories import get_category
from app.schemas import BudgetCategoryTotal, BudgetItemIn, BudgetItemOut, BudgetSummary
from app.services.budget import budget_by_category, is_paycheck, monthly_amount, paycheck_breakdown
from app.tenancy import HouseholdCtx, HouseholdDep

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
        paid_by_card=item.paid_by_card,
        gross_amount=item.gross_amount,
        monthly_gross_amount=None if item.gross_amount is None else monthly_amount(item.gross_amount, item.frequency),
        deductions=item.deductions,
    )


def apply(ctx: HouseholdCtx, item: BudgetItem, body: BudgetItemIn) -> None:
    category = get_category(ctx, body.category_id)
    if body.gross_amount is not None or body.deductions:
        if category.kind != CategoryKind.income:
            raise HTTPException(400, "Gross pay and deductions only apply to income")
        if body.gross_amount is None:
            raise HTTPException(400, "Enter gross pay to itemize deductions")
        if body.amount > body.gross_amount:
            raise HTTPException(400, "Take-home pay can't be more than gross pay")
    for key, value in body.model_dump(exclude={"deductions"}).items():
        setattr(item, key, value)
    item.paid_by_card = body.paid_by_card and category.kind == CategoryKind.expense
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


def get_item(ctx: HouseholdCtx, item_id: int) -> BudgetItem:
    item = ctx.db.get(BudgetItem, item_id)
    if item is None or item.household_id != ctx.household_id:
        raise HTTPException(404, "Budget item not found")
    return item


@router.get("/items", response_model=list[BudgetItemOut])
def list_items(ctx: HouseholdDep):
    items = ctx.db.scalars(
        select(BudgetItem).where(BudgetItem.household_id == ctx.household_id).order_by(BudgetItem.name)
    ).unique().all()
    return [to_out(i) for i in items]


@router.post("/items", response_model=BudgetItemOut, status_code=201)
def create_item(body: BudgetItemIn, ctx: HouseholdDep):
    db = ctx.db
    item = BudgetItem(household_id=ctx.household_id)
    apply(ctx, item, body)
    db.add(item)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.put("/items/{item_id}", response_model=BudgetItemOut)
def update_item(item_id: int, body: BudgetItemIn, ctx: HouseholdDep):
    db = ctx.db
    item = get_item(ctx, item_id)
    apply(ctx, item, body)
    db.commit()
    db.refresh(item)
    return to_out(item)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, ctx: HouseholdDep):
    ctx.db.delete(get_item(ctx, item_id))
    ctx.db.commit()


@router.get("/summary", response_model=BudgetSummary)
def summary(ctx: HouseholdDep):
    items = ctx.db.scalars(
        select(BudgetItem).where(BudgetItem.household_id == ctx.household_id).order_by(BudgetItem.name)
    ).unique().all()
    paychecks = [i for i in items if is_paycheck(i)]
    by_category = budget_by_category(ctx.db, ctx.household_id)
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
