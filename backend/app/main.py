import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import system_session
from app.routers import balance_sheet, budget, categories, companies, credit_cards, me, statements, stocks, transactions
from app.tenancy import ensure_local_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auth_mode == "none":
        log.warning(
            "AUTH_MODE=none: there's no sign-in, and anyone who can reach this app sees and edits everything. "
            "Only run it this way on your own computer or a trusted network."
        )
        with system_session() as db:
            ensure_local_user(db)
    scheduler = None
    if settings.enable_scheduler:
        from app.services.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="MoneySage", lifespan=lifespan)

for module in (me, categories, budget, balance_sheet, transactions, statements, stocks, credit_cards, companies):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
