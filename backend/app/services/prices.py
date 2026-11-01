"""Price fetching via yfinance, kept behind this module so the provider can be swapped."""

import logging
import warnings
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import yfinance as yf
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import AssetType, Holding, PriceQuote, PriceRefreshRun

log = logging.getLogger(__name__)

# yfinance triggers pandas deprecation warnings on every call; they aren't actionable here.
warnings.filterwarnings("ignore", module="yfinance")


class PriceFetchError(Exception):
    pass


def fetch_history(ticker: str, period: str) -> list[tuple[date, Decimal]]:
    """Daily closes for a ticker. period is a yfinance period string such as '7d' or '1y'."""
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
    return [(ts.date(), Decimal(str(round(float(val), 6)))) for ts, val in closes.dropna().items()]


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
