from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CASH_TICKER, Account, AssetType, Holding, PriceRefreshRun
from app.routers.balance_sheet import get_account
from app.schemas import (
    HoldingIn,
    HoldingOut,
    PortfolioPoint,
    PortfolioSummary,
    RefreshRunOut,
    TradeIn,
)
from app.services.portfolio import (
    latest_prices,
    portfolio_history,
    sync_account_snapshots,
    value_holding,
)
from app.services.prices import PriceFetchError, last_successful_run, load_ticker, refresh_all, runs_for
from app.tenancy import HouseholdCtx, HouseholdDep

router = APIRouter(prefix="/api", tags=["stocks"])


def normalize_ticker(ticker: str, asset_type: AssetType) -> str:
    ticker = ticker.strip().upper()
    # Yahoo quotes crypto as e.g. BTC-USD; accept plain "BTC" too.
    if asset_type == AssetType.crypto and "-" not in ticker:
        ticker = f"{ticker}-USD"
    return ticker


def get_holding(ctx: HouseholdCtx, holding_id: int) -> Holding:
    holding = ctx.db.get(Holding, holding_id)
    if holding is None or holding.household_id != ctx.household_id:
        raise HTTPException(404, "Holding not found")
    return holding


def find_position(
    db: Session,
    household_id: int,
    asset_type: AssetType,
    ticker: str,
    account_id: int | None,
    exclude_id: int | None = None,
) -> Holding | None:
    """The holding of this ticker in this account, if there is one (there's at most one per account)."""
    query = select(Holding).where(
        Holding.household_id == household_id,
        Holding.asset_type == asset_type,
        Holding.ticker == ticker,
        Holding.account_id.is_(None) if account_id is None else Holding.account_id == account_id,
    )
    if exclude_id is not None:
        query = query.where(Holding.id != exclude_id)
    return db.scalars(query).first()


def _quantity(value: Decimal) -> str:
    return f"{value.normalize():,f}"


def buy_more(holding: Holding, quantity: Decimal, price: Decimal | None) -> None:
    """Add shares to a holding. Its cost per share becomes the share-weighted average of old and new.

    Cash just adds the dollars. If the existing shares have no cost entered, the average stays unknown.
    """
    if holding.asset_type != AssetType.cash and holding.cost_per_unit is not None:
        if price is None:
            raise HTTPException(
                400, f"Enter the price paid per share, so the average cost of your {holding.ticker} stays accurate"
            )
        total = holding.quantity * holding.cost_per_unit + quantity * price
        holding.cost_per_unit = (total / (holding.quantity + quantity)).quantize(Decimal("0.000001"), ROUND_HALF_UP)
    holding.quantity += quantity


def _apply(ctx: HouseholdCtx, holding: Holding, body: HoldingIn) -> None:
    if body.account_id is not None:
        get_account(ctx, body.account_id)
    data = body.model_dump()
    if body.asset_type == AssetType.cash:
        # Quantity is the dollar amount; there's no ticker to look up and no gain to track.
        data.update(ticker=CASH_TICKER, cost_per_unit=None)
        for key, value in data.items():
            setattr(holding, key, value)
        return
    data["ticker"] = normalize_ticker(body.ticker, body.asset_type)
    try:
        found = load_ticker(ctx.db, data["ticker"])
    except PriceFetchError as exc:
        raise HTTPException(502, f"Couldn't reach the price service: {exc}")
    if not found:
        hint = " Crypto tickers look like BTC-USD." if body.asset_type == AssetType.crypto else ""
        raise HTTPException(400, f"No price data found for '{data['ticker']}'.{hint}")
    for key, value in data.items():
        setattr(holding, key, value)


def _holdings_out(ctx: HouseholdCtx, holdings: list[Holding]) -> list[HoldingOut]:
    db = ctx.db
    prices = latest_prices(db, {h.ticker for h in holdings})
    account_names = dict(
        db.execute(select(Account.id, Account.name).where(Account.household_id == ctx.household_id)).all()
    )
    result = []
    for h in holdings:
        v = value_holding(h, prices.get(h.ticker))
        result.append(
            HoldingOut(
                id=h.id,
                ticker=h.ticker,
                asset_type=h.asset_type,
                quantity=h.quantity,
                cost_per_unit=h.cost_per_unit,
                cost_basis=h.cost_basis,
                account_id=h.account_id,
                account_name=account_names.get(h.account_id),
                notes=h.notes,
                price=v.price.close if v.price else None,
                price_date=v.price.date if v.price else None,
                previous_close=v.price.previous_close if v.price else None,
                market_value=v.market_value,
                day_change=v.day_change,
                gain=v.gain,
            )
        )
    return result


def _household_holdings(ctx: HouseholdCtx) -> list[Holding]:
    return list(
        ctx.db.scalars(
            select(Holding).where(Holding.household_id == ctx.household_id).order_by(Holding.ticker, Holding.id)
        ).all()
    )


def _run_out(ctx: HouseholdCtx, run: PriceRefreshRun | None) -> RefreshRunOut | None:
    """A refresh run as this household sees it. A scheduled run covered everyone's tickers, so its
    failures are narrowed to the ones this household holds."""
    if run is None:
        return None
    out = RefreshRunOut.model_validate(run)
    if run.household_id is None:
        held = {h.ticker for h in _household_holdings(ctx)}
        failed = [t for t in run.failed_tickers or [] if t in held]
        out = out.model_copy(update={"message": f"No data for: {', '.join(failed)}" if failed else None})
    return out


@router.get("/holdings", response_model=list[HoldingOut])
def list_holdings(ctx: HouseholdDep):
    return _holdings_out(ctx, _household_holdings(ctx))


@router.post("/holdings", response_model=HoldingOut, status_code=201)
def create_holding(body: HoldingIn, ctx: HouseholdDep):
    """Add a holding. A ticker already held in that account is bought more of instead of listed twice."""
    db = ctx.db
    holding = Holding(household_id=ctx.household_id)
    _apply(ctx, holding, body)
    existing = find_position(db, ctx.household_id, holding.asset_type, holding.ticker, holding.account_id)
    if existing is None:
        db.add(holding)
    else:
        buy_more(existing, holding.quantity, holding.cost_per_unit)
        existing.notes = existing.notes or holding.notes
        holding = existing
    db.flush()
    sync_account_snapshots(db, ctx.household_id)
    db.commit()
    return _holdings_out(ctx, [holding])[0]


@router.put("/holdings/{holding_id}", response_model=HoldingOut)
def update_holding(holding_id: int, body: HoldingIn, ctx: HouseholdDep):
    db = ctx.db
    holding = get_holding(ctx, holding_id)
    _apply(ctx, holding, body)
    if find_position(
        db, ctx.household_id, holding.asset_type, holding.ticker, holding.account_id, exclude_id=holding.id
    ):
        what = "cash" if holding.asset_type == AssetType.cash else holding.ticker
        raise HTTPException(
            409, f"There's already a {what} holding in that account. Buy more on that one, or delete one of them."
        )
    db.flush()
    sync_account_snapshots(db, ctx.household_id)
    db.commit()
    return _holdings_out(ctx, [holding])[0]


@router.post("/holdings/{holding_id}/trade", response_model=HoldingOut | None)
def trade(holding_id: int, body: TradeIn, ctx: HouseholdDep):
    """Buy more or sell some. A sale keeps the average cost per share; selling everything removes the
    holding (and returns null)."""
    db = ctx.db
    holding = get_holding(ctx, holding_id)
    remaining: Holding | None = holding
    if body.side == "buy":
        buy_more(holding, body.quantity, body.price)
    elif body.quantity > holding.quantity:
        unit = "" if holding.asset_type == AssetType.cash else f" {holding.ticker}"
        amount = f"${holding.quantity:,.2f}" if holding.asset_type == AssetType.cash else _quantity(holding.quantity)
        raise HTTPException(400, f"That's more than you hold: {amount}{unit}")
    elif body.quantity == holding.quantity:
        db.delete(holding)
        remaining = None
    else:
        holding.quantity -= body.quantity
    db.flush()
    sync_account_snapshots(db, ctx.household_id)
    db.commit()
    return _holdings_out(ctx, [remaining])[0] if remaining else None


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, ctx: HouseholdDep):
    db = ctx.db
    db.delete(get_holding(ctx, holding_id))
    db.flush()
    sync_account_snapshots(db, ctx.household_id)
    db.commit()


@router.get("/portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary(ctx: HouseholdDep):
    holdings = _holdings_out(ctx, _household_holdings(ctx))
    total_value = sum((h.market_value or Decimal(0) for h in holdings), Decimal(0))
    day_change = sum((h.day_change or Decimal(0) for h in holdings), Decimal(0))
    with_cost = [h for h in holdings if h.cost_basis is not None and h.market_value is not None]
    total_cost = sum((h.cost_basis for h in with_cost), Decimal(0)) if with_cost else None
    total_gain = sum((h.gain for h in with_cost), Decimal(0)) if with_cost else None
    latest_run = ctx.db.scalar(
        select(PriceRefreshRun)
        .where(runs_for(ctx.household_id))
        .order_by(PriceRefreshRun.started_at.desc())
        .limit(1)
    )
    return PortfolioSummary(
        total_value=total_value,
        total_cost=total_cost,
        total_gain=total_gain,
        day_change=day_change,
        last_refresh=_run_out(ctx, latest_run),
    )


@router.get("/portfolio/history", response_model=list[PortfolioPoint])
def history(ctx: HouseholdDep, days: int = Query(365, ge=1, le=3650)):
    return [
        PortfolioPoint(date=d, value=v)
        for d, v in portfolio_history(ctx.db, ctx.household_id, days, ctx.today())
    ]


@router.post("/prices/refresh", response_model=RefreshRunOut)
def refresh_prices(ctx: HouseholdDep):
    """Refresh this household's tickers now."""
    return _run_out(ctx, refresh_all(ctx.db, ctx.household_id))


@router.get("/prices/status", response_model=RefreshRunOut | None)
def price_status(ctx: HouseholdDep):
    return _run_out(ctx, last_successful_run(ctx.db, ctx.household_id))
