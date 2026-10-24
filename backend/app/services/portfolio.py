from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Account, AssetType, BalanceSnapshot, Holding, PriceQuote
from app.months import add_months, current_month
from app.services.budget import CENT


@dataclass
class LatestPrice:
    date: date
    close: Decimal
    previous_close: Decimal | None


def latest_prices(
    db: Session, tickers: set[str], on_or_before: date | None = None
) -> dict[str, LatestPrice]:
    """Each ticker's latest close (and the one before it), optionally as of a past day."""
    if not tickers:
        return {}
    quotes = select(PriceQuote).where(PriceQuote.ticker.in_(tickers))
    if on_or_before is not None:
        quotes = quotes.where(PriceQuote.date <= on_or_before)
    quotes = quotes.subquery()
    ranked = (
        select(
            quotes.c.ticker,
            quotes.c.date,
            quotes.c.close,
            func.row_number()
            .over(partition_by=quotes.c.ticker, order_by=quotes.c.date.desc())
            .label("rn"),
        )
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.ticker, ranked.c.date, ranked.c.close, ranked.c.rn)
        .where(ranked.c.rn <= 2)
        .order_by(ranked.c.ticker, ranked.c.rn)
    ).all()
    result: dict[str, LatestPrice] = {}
    for ticker, d, close, rn in rows:
        if rn == 1:
            result[ticker] = LatestPrice(d, close, None)
        else:
            result[ticker].previous_close = close
    return result


@dataclass
class Valuation:
    price: LatestPrice | None
    market_value: Decimal | None
    day_change: Decimal | None
    gain: Decimal | None


def value_holding(holding: Holding, price: LatestPrice | None) -> Valuation:
    if holding.asset_type == AssetType.cash:
        # Cash is worth its face value: no price, no daily movement, and no gain to track.
        return Valuation(None, holding.quantity.quantize(CENT), Decimal(0), None)
    if price is None:
        return Valuation(None, None, None, None)
    value = (holding.quantity * price.close).quantize(CENT)
    day_change = (
        (holding.quantity * (price.close - price.previous_close)).quantize(CENT)
        if price.previous_close is not None
        else None
    )
    gain = value - holding.cost_basis if holding.cost_basis is not None else None
    return Valuation(price, value, day_change, gain)


def sync_account_snapshots(db: Session, month: date | None = None) -> None:
    """Write the current-month balance for accounts that track their linked holdings.

    Past months are left alone, so each month keeps the value from its last refresh.
    """
    month = month or current_month()
    accounts = db.scalars(
        select(Account).where(Account.sync_from_holdings.is_(True), Account.is_archived.is_(False))
    ).all()
    if not accounts:
        return
    totals = _account_values(db, [a.id for a in accounts])
    stmt = insert(BalanceSnapshot).values(
        [{"account_id": a.id, "month": month, "balance": totals[a.id]} for a in accounts]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "month"],
        set_={"balance": stmt.excluded.balance, "updated_at": func.now()},
    )
    db.execute(stmt)
    db.flush()


def _account_values(
    db: Session, account_ids: list[int], on_or_before: date | None = None
) -> dict[int, Decimal]:
    """Value of each account's linked holdings at the latest closes (or as of a past day)."""
    holdings = db.scalars(select(Holding).where(Holding.account_id.in_(account_ids))).all()
    prices = latest_prices(db, {h.ticker for h in holdings}, on_or_before)
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for h in holdings:
        totals[h.account_id] += value_holding(h, prices.get(h.ticker)).market_value or Decimal(0)
    return totals


def finalize_previous_month(db: Session) -> None:
    """Lock last month's synced balances in at its month-end closes.

    Normally the evening refresh on the month's last day already wrote them. If the app wasn't
    running then, last month still holds an earlier day's value, so revalue every synced snapshot
    that hasn't been written since the month ended. Run this after storing fresh quotes, so the
    month-end closes are present. A snapshot written after the month ended (including a manual
    edit) is left alone, and missing months aren't created.
    """
    this_month = current_month()
    month_end = this_month - timedelta(days=1)
    month_ended_at = datetime.combine(this_month, time.min).astimezone()  # local midnight on the 1st
    stale = db.scalars(
        select(BalanceSnapshot)
        .join(Account)
        .where(
            Account.sync_from_holdings.is_(True),
            Account.is_archived.is_(False),
            BalanceSnapshot.month == add_months(this_month, -1),
            BalanceSnapshot.updated_at < month_ended_at,
        )
    ).all()
    if not stale:
        return
    totals = _account_values(db, [s.account_id for s in stale], on_or_before=month_end)
    for snapshot in stale:
        snapshot.balance = totals[snapshot.account_id]
        snapshot.updated_at = func.now()  # so it's finalized once, even if the value is unchanged
    db.flush()


OPENING_LOOKBACK_DAYS = 10


def portfolio_history(db: Session, days: int) -> list[tuple[date, Decimal]]:
    """Daily value of the *current* holdings over the last N days (prices forward-filled)."""
    holdings = db.scalars(select(Holding)).all()
    if not holdings:
        return []
    # Cash adds the same amount every day; everything else follows its price history.
    cash = sum((h.quantity for h in holdings if h.asset_type == AssetType.cash), Decimal(0))
    quantity_by_ticker: dict[str, Decimal] = defaultdict(Decimal)
    for h in holdings:
        if h.asset_type != AssetType.cash:
            quantity_by_ticker[h.ticker] += h.quantity
    if not quantity_by_ticker:
        return []

    start = date.today() - timedelta(days=days)
    # Reach back past weekends and holidays so the line can open on `start` itself (e.g. Dec 31
    # for year to date) with the last close on or before it, giving range performance a true base.
    quotes = db.execute(
        select(PriceQuote.ticker, PriceQuote.date, PriceQuote.close)
        .where(
            PriceQuote.ticker.in_(quantity_by_ticker),
            PriceQuote.date >= start - timedelta(days=OPENING_LOOKBACK_DAYS),
        )
        .order_by(PriceQuote.date)
    ).all()
    if not quotes:
        return []

    by_date: dict[date, dict[str, Decimal]] = defaultdict(dict)
    first_seen: dict[str, date] = {}
    for ticker, d, close in quotes:
        by_date[d][ticker] = close
        first_seen.setdefault(ticker, d)

    # Begin once every priced ticker has a quote, so the line doesn't jump when one appears.
    chart_start = max(first_seen.values())
    last_close: dict[str, Decimal] = {}

    def value_now() -> Decimal:
        total = cash + sum((quantity_by_ticker[t] * c for t, c in last_close.items()), Decimal(0))
        return total.quantize(CENT)

    points = []
    for d in sorted(by_date):
        if d > start and not points and chart_start <= start:
            points.append((start, value_now()))  # no trading on `start`: open with the prior close
        last_close.update(by_date[d])
        if d >= start and d >= chart_start:
            points.append((d, value_now()))
    return points
