from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StatementImport, Transaction
from app.months import month_bounds, parse_month
from app.schemas import StatementImportIn, StatementImportOut, StatementPreview
from app.services import statement_import
from app.services.statement_parser import StatementError, parse_statement
from app.tenancy import HouseholdDep

router = APIRouter(prefix="/api/statements", tags=["statement import"])

MAX_BYTES = 20 * 1024 * 1024


def to_out(db: Session, record: StatementImport) -> StatementImportOut:
    count = db.scalar(select(func.count()).where(Transaction.statement_import_id == record.id))
    return StatementImportOut(
        id=record.id,
        bank=record.bank,
        file_name=record.file_name,
        period_start=record.period_start,
        period_end=record.period_end,
        accounts=record.accounts,
        transaction_count=count,
        created_at=record.created_at,
    )


@router.post("/preview", response_model=StatementPreview)
async def preview(ctx: HouseholdDep, file: UploadFile = File(...)):
    """Parse a statement PDF and suggest what to do with each line. Saves nothing."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That file is too large for a bank statement")
    try:
        statement = parse_statement(data)
    except StatementError as exc:
        raise HTTPException(400, str(exc))
    return statement_import.preview(ctx.db, ctx.household_id, statement)


@router.post("", response_model=StatementImportOut, status_code=201)
def import_statement(body: StatementImportIn, ctx: HouseholdDep):
    return to_out(ctx.db, statement_import.commit(ctx.db, ctx.household_id, body))


@router.get("", response_model=list[StatementImportOut])
def list_imports(ctx: HouseholdDep, month: str = Query(pattern=r"^\d{4}-\d{2}$")):
    """Statements whose period overlaps the month."""
    db = ctx.db
    start, end = month_bounds(parse_month(month))
    records = db.scalars(
        select(StatementImport)
        .where(
            StatementImport.household_id == ctx.household_id,
            StatementImport.period_start < end,
            StatementImport.period_end >= start,
        )
        .order_by(StatementImport.period_end, StatementImport.id)
    ).all()
    return [to_out(db, r) for r in records]


@router.delete("/{import_id}", status_code=204)
def undo_import(import_id: int, ctx: HouseholdDep):
    """Delete an import and the transactions it created. Balance Sheet balances are left as they are."""
    db = ctx.db
    record = db.get(StatementImport, import_id)
    if record is None or record.household_id != ctx.household_id:
        raise HTTPException(404, "Import not found")
    db.delete(record)
    db.commit()
