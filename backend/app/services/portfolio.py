from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Holding, PriceQuote
from app.months import current_month
from app.services.budget import CENT


@dataclass
class LatestPrice:
    date: date
    close: Decimal
    previous_close: Decimal | None


def latest_prices(db: Session, tickers: set[str]) -> dict[str, LatestPrice]:
    if not tickers:
        return {}
    ranked = (
        select(
            PriceQuote.ticker,
            PriceQuote.date,
            PriceQuote.close,
            func.row_number()
            .over(partition_by=PriceQuote.ticker, order_by=PriceQuote.date.desc())
            .label("rn"),
        )
        .where(PriceQuote.ticker.in_(tickers))
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
    holdings = db.scalars(
        select(Holding).where(Holding.account_id.in_([a.id for a in accounts]))
    ).all()
    prices = latest_prices(db, {h.ticker for h in holdings})
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for h in holdings:
        totals[h.account_id] += value_holding(h, prices.get(h.ticker)).market_value or Decimal(0)

    stmt = insert(BalanceSnapshot).values(
        [{"account_id": a.id, "month": month, "balance": totals[a.id]} for a in accounts]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "month"],
        set_={"balance": stmt.excluded.balance, "updated_at": func.now()},
    )
    db.execute(stmt)
    db.flush()


def portfolio_history(db: Session, days: int) -> list[tuple[date, Decimal]]:
    """Daily value of the *current* holdings over the last N days (prices forward-filled)."""
    holdings = db.scalars(select(Holding)).all()
    if not holdings:
        return []
    quantity_by_ticker: dict[str, Decimal] = defaultdict(Decimal)
    for h in holdings:
        quantity_by_ticker[h.ticker] += h.quantity

    start = date.today() - timedelta(days=days)
    quotes = db.execute(
        select(PriceQuote.ticker, PriceQuote.date, PriceQuote.close)
        .where(PriceQuote.ticker.in_(quantity_by_ticker), PriceQuote.date >= start)
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
    points = []
    for d in sorted(by_date):
        last_close.update(by_date[d])
        if d < chart_start:
            continue
        value = sum(
            (quantity_by_ticker[t] * c for t, c in last_close.items()), start=Decimal(0)
        )
        points.append((d, value.quantize(CENT)))
    return points
