from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StatementImport, Transaction
from app.months import month_bounds, parse_month
from app.schemas import StatementImportIn, StatementImportOut, StatementPreview
from app.services import statement_import
from app.services.statement_parser import StatementError, parse_statement

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
async def preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Parse a statement PDF and suggest what to do with each line. Saves nothing."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That file is too large for a bank statement")
    try:
        statement = parse_statement(data)
    except StatementError as exc:
        raise HTTPException(400, str(exc))
    return statement_import.preview(db, statement)


@router.post("", response_model=StatementImportOut, status_code=201)
def import_statement(body: StatementImportIn, db: Session = Depends(get_db)):
    return to_out(db, statement_import.commit(db, body))


@router.get("", response_model=list[StatementImportOut])
def list_imports(month: str = Query(pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(get_db)):
    """Statements whose period overlaps the month."""
    start, end = month_bounds(parse_month(month))
    records = db.scalars(
        select(StatementImport)
        .where(StatementImport.period_start < end, StatementImport.period_end >= start)
        .order_by(StatementImport.period_end, StatementImport.id)
    ).all()
    return [to_out(db, r) for r in records]


@router.delete("/{import_id}", status_code=204)
def undo_import(import_id: int, db: Session = Depends(get_db)):
    """Delete an import and the transactions it created. Balance Sheet balances are left as they are."""
    record = db.get(StatementImport, import_id)
    if record is None:
        raise HTTPException(404, "Import not found")
    db.delete(record)
    db.commit()
