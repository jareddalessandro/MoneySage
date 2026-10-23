from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, AssetType, Holding, PriceRefreshRun
from app.routers.balance_sheet import get_account
from app.schemas import (
    HoldingIn,
    HoldingOut,
    PortfolioPoint,
    PortfolioSummary,
    RefreshRunOut,
)
from app.services.portfolio import (
    latest_prices,
    portfolio_history,
    sync_account_snapshots,
    value_holding,
)
from app.services.prices import PriceFetchError, last_successful_run, load_ticker, refresh_all

router = APIRouter(prefix="/api", tags=["stocks"])


def normalize_ticker(ticker: str, asset_type: AssetType) -> str:
    ticker = ticker.strip().upper()
    # Yahoo quotes crypto as e.g. BTC-USD; accept plain "BTC" too.
    if asset_type == AssetType.crypto and "-" not in ticker:
        ticker = f"{ticker}-USD"
    return ticker


def get_holding(db: Session, holding_id: int) -> Holding:
    holding = db.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(404, "Holding not found")
    return holding


def _apply(db: Session, holding: Holding, body: HoldingIn) -> None:
    if body.account_id is not None:
        get_account(db, body.account_id)
    data = body.model_dump()
    data["ticker"] = normalize_ticker(body.ticker, body.asset_type)
    try:
        found = load_ticker(db, data["ticker"])
    except PriceFetchError as exc:
        raise HTTPException(502, f"Couldn't reach the price service: {exc}")
    if not found:
        hint = " Crypto tickers look like BTC-USD." if body.asset_type == AssetType.crypto else ""
        raise HTTPException(400, f"No price data found for '{data['ticker']}'.{hint}")
    for key, value in data.items():
        setattr(holding, key, value)


def _holdings_out(db: Session, holdings: list[Holding]) -> list[HoldingOut]:
    prices = latest_prices(db, {h.ticker for h in holdings})
    account_names = dict(db.execute(select(Account.id, Account.name)).all())
    result = []
    for h in holdings:
        v = value_holding(h, prices.get(h.ticker))
        result.append(
            HoldingOut(
                id=h.id,
                ticker=h.ticker,
                asset_type=h.asset_type,
                quantity=h.quantity,
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


@router.get("/holdings", response_model=list[HoldingOut])
def list_holdings(db: Session = Depends(get_db)):
    holdings = db.scalars(select(Holding).order_by(Holding.ticker, Holding.id)).all()
    return _holdings_out(db, list(holdings))


@router.post("/holdings", response_model=HoldingOut, status_code=201)
def create_holding(body: HoldingIn, db: Session = Depends(get_db)):
    holding = Holding()
    _apply(db, holding, body)
    db.add(holding)
    db.flush()
    sync_account_snapshots(db)
    db.commit()
    return _holdings_out(db, [holding])[0]


@router.put("/holdings/{holding_id}", response_model=HoldingOut)
def update_holding(holding_id: int, body: HoldingIn, db: Session = Depends(get_db)):
    holding = get_holding(db, holding_id)
    _apply(db, holding, body)
    db.flush()
    sync_account_snapshots(db)
    db.commit()
    return _holdings_out(db, [holding])[0]


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    db.delete(get_holding(db, holding_id))
    db.flush()
    sync_account_snapshots(db)
    db.commit()


@router.get("/portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary(db: Session = Depends(get_db)):
    holdings = _holdings_out(db, list(db.scalars(select(Holding)).all()))
    total_value = sum((h.market_value or Decimal(0) for h in holdings), Decimal(0))
    day_change = sum((h.day_change or Decimal(0) for h in holdings), Decimal(0))
    with_cost = [h for h in holdings if h.cost_basis is not None and h.market_value is not None]
    total_cost = sum((h.cost_basis for h in with_cost), Decimal(0)) if with_cost else None
    total_gain = sum((h.gain for h in with_cost), Decimal(0)) if with_cost else None
    latest_run = db.scalar(select(PriceRefreshRun).order_by(PriceRefreshRun.started_at.desc()).limit(1))
    return PortfolioSummary(
        total_value=total_value,
        total_cost=total_cost,
        total_gain=total_gain,
        day_change=day_change,
        last_refresh=latest_run,
    )


@router.get("/portfolio/history", response_model=list[PortfolioPoint])
def history(days: int = Query(365, ge=7, le=3650), db: Session = Depends(get_db)):
    return [PortfolioPoint(date=d, value=v) for d, v in portfolio_history(db, days)]


@router.post("/prices/refresh", response_model=RefreshRunOut)
def refresh_prices(db: Session = Depends(get_db)):
    return refresh_all(db)


@router.get("/prices/status", response_model=RefreshRunOut | None)
def price_status(db: Session = Depends(get_db)):
    return last_successful_run(db)
