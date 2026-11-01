"""Daily prices from a market-data provider (PRICE_PROVIDER), and the refresh runs that store them.

Everything else calls fetch_history, so providers can be swapped without touching the rest of the app.
"yahoo" (yfinance, unofficial and for personal use) is the default so an offline install works with no
account; "tiingo" needs TIINGO_API_KEY. Showing prices to other people generally needs a provider plan
that allows display or redistribution; see .env.example.
"""

import logging
import re
import warnings
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AssetType, Holding, PriceQuote, PriceRefreshRun

log = logging.getLogger(__name__)

TIINGO_URL = "https://api.tiingo.com"
# Crypto tickers are stored like BTC-USD (normalize_ticker); share classes like BRK-B aren't crypto.
CRYPTO_RE = re.compile(r"^([A-Z0-9]+)-(USD|USDT|USDC|EUR|GBP|BTC|ETH)$")


class PriceFetchError(Exception):
    pass


def fetch_history(ticker: str, period: str) -> list[tuple[date, Decimal]]:
    """Daily closes for a ticker, oldest first. period is like '7d' or '1y'."""
    if settings.price_provider == "tiingo":
        return _tiingo_history(ticker, period)
    return _yahoo_history(ticker, period)


def _period_start(period: str, today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    match = re.fullmatch(r"(\d+)(d|mo|y)", period)
    if not match:
        raise ValueError(f"Unknown period {period!r}")
    n, unit = int(match[1]), match[2]
    days = n if unit == "d" else n * 31 if unit == "mo" else n * 366
    return today - timedelta(days=days)


def _decimal(value) -> Decimal:
    return Decimal(str(round(float(value), 6)))


def _tiingo_history(ticker: str, period: str) -> list[tuple[date, Decimal]]:
    if not settings.tiingo_api_key:
        raise PriceFetchError(f"{ticker}: TIINGO_API_KEY isn't set")
    headers = {"Authorization": f"Token {settings.tiingo_api_key}", "Content-Type": "application/json"}
    start = _period_start(period).isoformat()
    crypto = CRYPTO_RE.match(ticker)
    try:
        if crypto:
            response = httpx.get(
                f"{TIINGO_URL}/tiingo/crypto/prices",
                params={"tickers": f"{crypto[1]}{crypto[2]}".lower(), "startDate": start, "resampleFreq": "1day"},
                headers=headers,
                timeout=20,
            )
        else:
            response = httpx.get(
                f"{TIINGO_URL}/tiingo/daily/{ticker.lower()}/prices",
                params={"startDate": start},
                headers=headers,
                timeout=20,
            )
    except httpx.HTTPError as exc:
        raise PriceFetchError(f"{ticker}: {exc}") from exc
    if response.status_code == 404:
        return []  # Tiingo doesn't know the ticker
    if response.status_code != 200:
        raise PriceFetchError(f"{ticker}: Tiingo answered {response.status_code}")
    data = response.json()
    rows = (data[0].get("priceData", []) if data else []) if crypto else data
    closes = {}
    for row in rows:
        if row.get("close") is not None:
            # Dates come as ISO timestamps (UTC midnight for crypto days, like Yahoo's).
            closes[date.fromisoformat(row["date"][:10])] = _decimal(row["close"])
    return sorted(closes.items())


def _yahoo_history(ticker: str, period: str) -> list[tuple[date, Decimal]]:
    # Imported here so installs on another provider don't load pandas and yfinance (memory on small servers).
    import pandas as pd
    import yfinance as yf

    # yfinance triggers pandas deprecation warnings on every call; they aren't actionable here.
    warnings.filterwarnings("ignore", module="yfinance")
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d", auto_adjust=False)
        if df is None or df.empty or "Close" not in df:
            return []
        closes = df["Close"].copy()
        # Yahoo often leaves today's daily close empty for hours after the bell;
        # fill it from the live quote so the daily refresh captures today's price.
        if pd.isna(closes.iloc[-1]):
            last_price = t.fast_info["last_price"]
            if last_price:
                closes.iloc[-1] = last_price
    except Exception as exc:  # yfinance raises a variety of exception types
        raise PriceFetchError(f"{ticker}: {exc}") from exc
    return [(ts.date(), _decimal(val)) for ts, val in closes.dropna().items()]


def store_quotes(db: Session, ticker: str, quotes: list[tuple[date, Decimal]]) -> None:
    if not quotes:
        return
    stmt = insert(PriceQuote).values([{"ticker": ticker, "date": d, "close": c} for d, c in quotes])
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"], set_={"close": stmt.excluded.close}
    )
    db.execute(stmt)


def has_quotes(db: Session, ticker: str) -> bool:
    return db.scalar(select(PriceQuote.id).where(PriceQuote.ticker == ticker).limit(1)) is not None


def load_ticker(db: Session, ticker: str) -> bool:
    """Backfill a year of history for a newly added ticker. Returns False if the ticker has no data."""
    if has_quotes(db, ticker):
        return True
    quotes = fetch_history(ticker, "1y")
    store_quotes(db, ticker, quotes)
    return bool(quotes)


def refresh_all(db: Session, household_id: int | None = None) -> PriceRefreshRun:
    """Fetch recent closes for one household's tickers, or (household_id None, the scheduled run) everyone's,
    then update synced account balances."""
    from app.services.portfolio import finalize_previous_month, sync_account_snapshots

    run = PriceRefreshRun(status="running", household_id=household_id)
    db.add(run)
    db.commit()

    query = select(Holding.ticker).where(Holding.asset_type != AssetType.cash)
    if household_id is not None:
        query = query.where(Holding.household_id == household_id)
    tickers = sorted(set(db.scalars(query)))
    failures: list[str] = []
    updated = 0
    for ticker in tickers:
        try:
            quotes = fetch_history(ticker, "7d" if has_quotes(db, ticker) else "1y")
        except PriceFetchError as exc:
            log.warning("Price fetch failed: %s", exc)
            failures.append(ticker)
            continue
        if not quotes:
            failures.append(ticker)
            continue
        store_quotes(db, ticker, quotes)
        updated += 1

    finalize_previous_month(db, household_id)
    sync_account_snapshots(db, household_id)

    run.finished_at = datetime.now(timezone.utc)
    run.tickers_updated = updated
    if failures and updated:
        run.status = "partial"
    elif failures:
        run.status = "failed"
    else:
        run.status = "success"
    run.message = f"No data for: {', '.join(failures)}" if failures else None
    run.failed_tickers = failures
    db.commit()
    log.info("Price refresh %s: %d updated, failures=%s", run.status, updated, failures)
    return run


def runs_for(household_id: int | None):
    """Condition for runs that covered a household's tickers: scheduled runs, plus its own refreshes.
    With None, scheduled runs only."""
    if household_id is None:
        return PriceRefreshRun.household_id.is_(None)
    return or_(PriceRefreshRun.household_id.is_(None), PriceRefreshRun.household_id == household_id)


def last_successful_run(db: Session, household_id: int | None = None) -> PriceRefreshRun | None:
    return db.scalar(
        select(PriceRefreshRun)
        .where(PriceRefreshRun.status.in_(["success", "partial"]), runs_for(household_id))
        .order_by(PriceRefreshRun.started_at.desc())
        .limit(1)
    )


def is_stale(db: Session, max_age: timedelta = timedelta(hours=20)) -> bool:
    run = last_successful_run(db)
    return run is None or datetime.now(timezone.utc) - run.started_at > max_age
