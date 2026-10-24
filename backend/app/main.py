import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import SessionLocal
from app.routers import balance_sheet, budget, categories, credit_cards, stocks, transactions
from app.seed import seed_categories

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        seed_categories(db)
    scheduler = None
    if settings.enable_scheduler:
        from app.services.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="MoneySage", lifespan=lifespan)

for module in (categories, budget, balance_sheet, transactions, stocks, credit_cards):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
