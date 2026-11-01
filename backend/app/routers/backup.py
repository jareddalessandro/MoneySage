from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import select

from app.models import AccessRole, Company, CompanyAccess
from app.services.backup import ExportFile, ImportResult, build_export, import_file
from app.tenancy import CompanyDep, HouseholdCtx, HouseholdDep

router = APIRouter(prefix="/api", tags=["export and import"])

MAX_BYTES = 50 * 1024 * 1024


def _download(file: ExportFile, name: str) -> Response:
    return Response(
        file.model_dump_json(indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _owned_companies(ctx: HouseholdCtx) -> list[Company]:
    return list(
        ctx.db.scalars(
            select(Company)
            .join(CompanyAccess, CompanyAccess.company_id == Company.id)
            .where(CompanyAccess.user_id == ctx.user.id, CompanyAccess.role == AccessRole.owner)
            .order_by(Company.name, Company.id)
        )
    )


@router.get("/export")
def export_everything(ctx: HouseholdDep):
    """This household and every company you own, in one file (for moving to another MoneySage, or a copy)."""
    file = build_export(ctx.db, ctx.household, _owned_companies(ctx))
    return _download(file, f"moneysage-export-{ctx.today().isoformat()}.json")


@router.get("/export/household")
def export_household(ctx: HouseholdDep):
    file = build_export(ctx.db, ctx.household, [])
    return _download(file, f"moneysage-household-{ctx.today().isoformat()}.json")


@router.get("/companies/{company_id}/export")
def export_company(company_id: int, ctx: CompanyDep):
    file = build_export(ctx.db, None, [ctx.company])
    safe = "".join(ch if ch.isalnum() else "-" for ch in ctx.company.name).strip("-") or "company"
    return _download(file, f"moneysage-{safe}.json")


@router.post("/import", response_model=ImportResult)
async def import_export(ctx: HouseholdDep, file: UploadFile = File(...)):
    """Import a MoneySage export: its household into this one (which must be empty; owners only), and each
    of its companies as a new company you own. All or nothing."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That file is too large")
    try:
        parsed = ExportFile.model_validate_json(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        if first["loc"][:1] in (("format",), ("version",)) or first["type"] == "json_invalid":
            raise HTTPException(400, "That isn't a MoneySage export file")
        where = " → ".join(str(p) for p in first["loc"])
        raise HTTPException(400, f"The file has a problem at {where}: {first['msg']}")
    household = ctx.household if ctx.role == AccessRole.owner else None
    return import_file(ctx.db, ctx.user, household, parsed)
