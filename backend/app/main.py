import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import google_oauth
from app.config import settings
from app.database import system_session
from app.routers import (
    auth,
    backup,
    balance_sheet,
    budget,
    categories,
    companies,
    credit_cards,
    me,
    sharing,
    statements,
    stocks,
    transactions,
)
from app.tenancy import READ_METHODS, ensure_local_user

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
    else:
        if not google_oauth.configured():
            log.error("AUTH_MODE=google but GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET aren't set, so nobody can sign in.")
        if not settings.app_db_password:
            log.warning("APP_DB_PASSWORD isn't set, so row-level security isn't protecting households from each other.")
        if not settings.secure_cookies:
            log.warning("PUBLIC_URL isn't https, so the session cookie isn't Secure. Fine on localhost, not on a server.")
    scheduler = None
    if settings.enable_scheduler:
        from app.services.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="MoneySage", lifespan=lifespan)

# Requests that change something must carry this header, which the app's own fetches add. A form or link on
# another website can't add custom headers (and a script there can't without a CORS preflight, which this
# app never allows), so this blocks cross-site request forgery, with or without sign-in.
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "moneysage"


@app.middleware("http")
async def require_csrf_header(request: Request, call_next):
    if (
        request.method not in READ_METHODS
        and request.url.path.startswith("/api/")
        and request.headers.get(CSRF_HEADER) != CSRF_VALUE
    ):
        return JSONResponse({"detail": "This request didn't come from the MoneySage app"}, status_code=403)
    return await call_next(request)


for module in (auth, me, sharing, categories, budget, balance_sheet, transactions, statements, stocks, credit_cards, companies, backup):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
