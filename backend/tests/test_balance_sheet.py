from datetime import date, datetime, timedelta, timezone

from sqlalchemy import update

from app.database import SessionLocal
from app.models import BalanceSnapshot
from app.months import add_months, current_month, format_month
from app.services.prices import refresh_all


def make_account(client, name, kind, subtype, **extra):
    response = client.post("/api/accounts", json={"name": name, "kind": kind, "subtype": subtype, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_net_worth_and_copy_previous(client):
    checking = make_account(client, "Checking", "asset", "checking")
    savings = make_account(client, "Savings", "asset", "savings")
    card = make_account(client, "Visa", "liability", "credit_card")

    sheet = client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": checking, "balance": 5000},
        {"account_id": savings, "balance": 20000},
        {"account_id": card, "balance": 1200.50},
    ]}).json()
    assert sheet["total_assets"] == 25000
    assert sheet["total_liabilities"] == 1200.5
    assert sheet["net_worth"] == 23799.5

    # February: enter checking only, then copy the rest from January.
    client.put("/api/balance-sheet", params={"month": "2026-02"}, json={"balances": [
        {"account_id": checking, "balance": 6000},
    ]})
    feb = client.post("/api/balance-sheet/copy-previous", params={"month": "2026-02"}).json()
    balances = {r["account"]["name"]: (r["balance"], r["previous_balance"]) for r in feb["rows"]}
    assert balances == {"Checking": (6000, 5000), "Savings": (20000, 20000), "Visa": (1200.5, 1200.5)}

    trend = client.get("/api/balance-sheet/trend", params={"months": 240}).json()
    assert [(p["month"], p["net_worth"]) for p in trend] == [("2026-01", 23799.5), ("2026-02", 24799.5)]



def test_trend_timeline(client):
    checking = make_account(client, "Checking", "asset", "checking")
    loan = make_account(client, "Loan", "liability", "auto_loan")
    month = lambda n: format_month(add_months(current_month(), n))  # noqa: E731
    put = lambda m, balances: client.put("/api/balance-sheet", params={"month": m}, json={"balances": balances})  # noqa: E731

    put(month(-5), [{"account_id": loan, "balance": 900}])  # debt history before any assets: skipped
    put(month(-4), [{"account_id": loan, "balance": 800}, {"account_id": checking, "balance": 5000}])
    put(month(-2), [{"account_id": loan, "balance": 600}, {"account_id": checking, "balance": 5500}])
    put(month(1), [{"account_id": loan, "balance": 400}])  # future: excluded

    trend = client.get("/api/balance-sheet/trend", params={"months": 24}).json()
    assert [(p["month"], p["assets"], p["liabilities"], p["net_worth"]) for p in trend] == [
        (month(-4), 5000, 800, 4200),
        (month(-3), None, None, None),  # nothing recorded: a gap, not zero
        (month(-2), 5500, 600, 4900),
    ]

def test_clearing_a_balance(client):
    checking = make_account(client, "Checking", "asset", "checking")
    client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": checking, "balance": 100},
    ]})
    sheet = client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": checking, "balance": None},
    ]}).json()
    assert sheet["rows"][0]["balance"] is None


def test_archived_account_hidden_without_balance(client):
    old = make_account(client, "Old Bank", "asset", "checking")
    client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": old, "balance": 50},
    ]})
    client.patch(f"/api/accounts/{old}", json={"is_archived": True})

    jan = client.get("/api/balance-sheet", params={"month": "2026-01"}).json()
    feb = client.get("/api/balance-sheet", params={"month": "2026-02"}).json()
    assert [r["account"]["name"] for r in jan["rows"]] == ["Old Bank"]
    assert feb["rows"] == []


def test_brokerage_synced_from_holdings(client, fake_prices):
    fake_prices["VTI"] = [250.0, 260.0]
    fake_prices["BTC-USD"] = [60000.0]
    brokerage = make_account(client, "Brokerage", "asset", "brokerage", sync_from_holdings=True)

    client.post("/api/holdings", json={"ticker": "VTI", "asset_type": "etf", "quantity": 10, "account_id": brokerage})
    client.post("/api/holdings", json={"ticker": "BTC", "asset_type": "crypto", "quantity": 0.5})  # unlinked

    month = format_month(current_month())
    sheet = client.get("/api/balance-sheet", params={"month": month}).json()
    assert sheet["rows"][0]["balance"] == 2600

    # Synced accounts can't be hand-edited for the current month...
    response = client.put("/api/balance-sheet", params={"month": month}, json={"balances": [
        {"account_id": brokerage, "balance": 1},
    ]})
    assert response.status_code == 400
    # ...or for a future month, which has no value until it arrives...
    response = client.put("/api/balance-sheet", params={"month": format_month(add_months(current_month(), 1))},
                          json={"balances": [{"account_id": brokerage, "balance": 1}]})
    assert response.status_code == 400
    # ...but past months can be backfilled by hand.
    last_month = format_month(add_months(current_month(), -1))
    response = client.put("/api/balance-sheet", params={"month": last_month}, json={"balances": [
        {"account_id": brokerage, "balance": 2400},
    ]})
    assert response.status_code == 200


def test_month_end_balance_captured_after_the_fact(client, fake_prices):
    """If the app was off on the last day of the month, the next refresh revalues last month at month-end closes."""
    today = date.today()
    month_end = current_month() - timedelta(days=1)
    # One close per day for the last 60 days; the price on a day is 1000 minus how many days ago it was.
    fake_prices["VTI"] = [1000.0 - d for d in range(59, -1, -1)]
    price_on = lambda day: 1000 - (today - day).days  # noqa: E731

    brokerage = make_account(client, "Brokerage", "asset", "brokerage", sync_from_holdings=True)
    ira = make_account(client, "IRA", "asset", "retirement", sync_from_holdings=True)
    new = make_account(client, "New", "asset", "brokerage", sync_from_holdings=True)
    for account in (brokerage, ira, new):
        client.post("/api/holdings", json={"ticker": "VTI", "asset_type": "etf", "quantity": 2, "account_id": account})

    last_month = format_month(add_months(current_month(), -1))
    client.put("/api/balance-sheet", params={"month": last_month}, json={"balances": [
        {"account_id": brokerage, "balance": 111},  # written by the app mid-month (made stale below)
        {"account_id": ira, "balance": 222},  # edited by hand after the month ended
    ]})
    mid_month = datetime.combine(month_end - timedelta(days=10), datetime.min.time(), tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.execute(update(BalanceSnapshot).where(BalanceSnapshot.account_id == brokerage).values(updated_at=mid_month))
        db.commit()

    with SessionLocal() as db:
        refresh_all(db)

    rows = {r["account"]["id"]: r["balance"]
            for r in client.get("/api/balance-sheet", params={"month": last_month}).json()["rows"]}
    assert rows[brokerage] == 2 * price_on(month_end)  # month-end close, not today's
    assert rows[ira] == 222  # a later manual edit wins
    assert new not in rows or rows[new] is None  # missing months aren't backfilled

    # Finalized once: a later refresh doesn't touch it again.
    with SessionLocal() as db:
        db.execute(update(BalanceSnapshot).where(BalanceSnapshot.account_id == brokerage).values(balance=5))
        db.commit()
        refresh_all(db)
    rows = {r["account"]["id"]: r["balance"]
            for r in client.get("/api/balance-sheet", params={"month": last_month}).json()["rows"]}
    assert rows[brokerage] == 5
