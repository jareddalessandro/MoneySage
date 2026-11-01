"""Households and companies are private to the people they're shared with."""

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError

from app.database import SessionLocal, set_session_user, system_session
from app.models import Account, Category, Company, CompanyEntry
from tests.conftest import RLS

needs_rls = pytest.mark.skipif(not RLS, reason="row-level security is off (TEST_WITHOUT_RLS=1)")


def _id(categories, name):
    return next(c["id"] for c in categories if c["name"] == name)


def fill_household(client) -> dict:
    """One of everything in the current user's household; returns their ids."""
    categories = client.get("/api/categories").json()
    groceries = _id(categories, "Groceries")
    account = client.post("/api/accounts", json={"name": "Checking", "kind": "asset", "subtype": "checking"}).json()
    client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": account["id"], "balance": 5000},
    ]})
    item = client.post("/api/budget/items", json={
        "name": "Food", "category_id": groceries, "amount": 600, "frequency": "monthly",
    }).json()
    txn = client.post("/api/transactions", json={
        "date": "2026-01-05", "description": "Market", "amount": 82.5, "category_id": groceries,
    }).json()
    holding = client.post("/api/holdings", json={
        "ticker": "", "asset_type": "cash", "quantity": 1200, "account_id": account["id"],
    }).json()
    card = client.post("/api/credit-cards", json={"name": "Sapphire", "annual_fee": 95}).json()
    client.put("/api/income-statement/notes", json={"month": "2026-01", "notes": "Private note"})
    return {
        "category": groceries, "account": account["id"], "item": item["id"], "transaction": txn["id"],
        "holding": holding["id"], "card": card["id"],
    }


def test_households_are_isolated(client, people):
    mine = fill_household(client)
    wife = people.add("wife@example.com")
    people.act_as(wife)

    # Her own household starts empty, with its own default categories.
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/budget/items").json() == []
    assert client.get("/api/transactions", params={"month": "2026-01"}).json() == []
    assert client.get("/api/holdings").json() == []
    assert client.get("/api/credit-cards").json() == []
    assert client.get("/api/balance-sheet", params={"month": "2026-01"}).json()["rows"] == []
    assert client.get("/api/income-statement", params={"month": "2026-01"}).json()["notes"] is None
    assert mine["category"] not in {c["id"] for c in client.get("/api/categories").json()}
    assert client.get("/api/portfolio/summary").json()["total_value"] == 0

    # Nothing of mine can be reached or changed by id.
    for method, url, body in [
        ("patch", f"/api/categories/{mine['category']}", {"name": "Mine now"}),
        ("delete", f"/api/categories/{mine['category']}", None),
        ("patch", f"/api/accounts/{mine['account']}", {"name": "Mine now"}),
        ("delete", f"/api/accounts/{mine['account']}", None),
        ("put", f"/api/budget/items/{mine['item']}", {"name": "x", "category_id": mine["category"], "amount": 1, "frequency": "monthly"}),
        ("delete", f"/api/budget/items/{mine['item']}", None),
        ("put", f"/api/transactions/{mine['transaction']}", {"date": "2026-01-05", "description": "x", "amount": 1, "category_id": mine["category"]}),
        ("delete", f"/api/transactions/{mine['transaction']}", None),
        ("delete", f"/api/holdings/{mine['holding']}", None),
        ("post", f"/api/holdings/{mine['holding']}/trade", {"side": "sell", "quantity": 1}),
        ("put", f"/api/credit-cards/{mine['card']}", {"name": "x"}),
        ("delete", f"/api/credit-cards/{mine['card']}", None),
    ]:
        response = client.request(method, url, json=body)
        assert response.status_code == 404, (method, url, response.status_code)

    # Nor can my categories or accounts be attached to her data.
    her_groceries = _id(client.get("/api/categories").json(), "Groceries")
    assert client.post("/api/transactions", json={
        "date": "2026-01-05", "description": "x", "amount": 1, "category_id": mine["category"],
    }).status_code == 404
    assert client.post("/api/transactions", json={
        "date": "2026-01-05", "description": "x", "amount": 1, "category_id": her_groceries, "account_id": mine["account"],
    }).status_code == 404
    assert client.post("/api/holdings", json={
        "ticker": "", "asset_type": "cash", "quantity": 1, "account_id": mine["account"],
    }).status_code == 404
    assert client.put("/api/balance-sheet", params={"month": "2026-01"}, json={"balances": [
        {"account_id": mine["account"], "balance": 1},
    ]}).status_code == 404

    # Asking for my household directly is refused.
    assert client.get("/api/accounts", headers={"X-Household-Id": str(people.local["household_id"])}).status_code == 404

    people.act_as(None)
    assert client.get("/api/transactions", params={"month": "2026-01"}).json()[0]["amount"] == 82.5
    assert client.get("/api/balance-sheet", params={"month": "2026-01"}).json()["net_worth"] == 5000


def test_shared_household_editor_and_viewer(client, people):
    mine = fill_household(client)
    household = str(people.local["household_id"])
    wife, guest = people.add("wife@example.com"), people.add("guest@example.com")
    people.share_household(int(household), wife, "editor")
    people.share_household(int(household), guest, "viewer")
    shared = {"X-Household-Id": household}

    people.act_as(wife)
    # Without the header she works in her own household.
    assert client.get("/api/accounts").json() == []
    assert [a["name"] for a in client.get("/api/accounts", headers=shared).json()] == ["Checking"]
    assert client.get("/api/income-statement", params={"month": "2026-01"}, headers=shared).json()["notes"] == "Private note"
    renamed = client.patch(f"/api/accounts/{mine['account']}", json={"name": "Joint checking"}, headers=shared)
    assert renamed.status_code == 200
    assert client.post("/api/transactions", headers=shared, json={
        "date": "2026-01-09", "description": "Pharmacy", "amount": 20, "category_id": mine["category"],
    }).status_code == 201

    people.act_as(guest)
    assert len(client.get("/api/transactions", params={"month": "2026-01"}, headers=shared).json()) == 2
    for method, url, body in [
        ("post", "/api/categories", {"name": "New", "kind": "expense"}),
        ("patch", f"/api/accounts/{mine['account']}", {"name": "x"}),
        ("delete", f"/api/transactions/{mine['transaction']}", None),
        ("put", "/api/income-statement/notes", {"month": "2026-01", "notes": "x"}),
        ("post", "/api/prices/refresh", None),
    ]:
        response = client.request(method, url, json=body, headers=shared)
        assert response.status_code == 403, (method, url, response.status_code)
    # Reads that would normally refresh synced balances still work.
    assert client.get("/api/balance-sheet", params={"month": "2026-01"}, headers=shared).status_code == 200


def test_sharing_a_household_never_shares_companies(client, people):
    company = client.post("/api/companies", json={"name": "Side LLC"}).json()
    wife = people.add("wife@example.com")
    people.share_household(people.local["household_id"], wife, "editor")

    people.act_as(wife)
    assert client.get("/api/companies").json() == []
    assert client.get(f"/api/companies/{company['id']}").status_code == 404
    assert client.get(f"/api/companies/{company['id']}/entries").status_code == 404
    assert client.get(f"/api/companies/{company['id']}/statements").status_code == 404
    me = client.get("/api/me").json()
    assert [h["role"] for h in me["households"]] == ["owner", "editor"]
    assert me["companies"] == []


def test_company_sharing(client, people):
    company = client.post("/api/companies", json={"name": "Acme LLC"}).json()
    cid = company["id"]
    assert company["role"] == "owner"
    client.post(f"/api/companies/{cid}/entries", json={"kind": "income", "date": "2026-02-01", "description": "Sale", "amount": 900})
    partner, accountant = people.add("partner@example.com"), people.add("cpa@example.com")

    people.act_as(partner)
    assert client.get(f"/api/companies/{cid}/summary").status_code == 404
    # Names only clash within the companies one person can open.
    assert client.post("/api/companies", json={"name": "Acme LLC"}).status_code == 201

    people.act_as(None)
    people.share_company(cid, partner, "editor")
    people.share_company(cid, accountant, "viewer")

    people.act_as(partner)
    # Their own "Acme LLC" and the shared one.
    assert sorted(c["role"] for c in client.get("/api/companies").json()) == ["editor", "owner"]
    assert client.get(f"/api/companies/{cid}/summary").json()["income"] == 900
    added = client.post(f"/api/companies/{cid}/entries", json={"kind": "expense", "date": "2026-02-03", "description": "Hosting", "amount": 40})
    assert added.status_code == 201
    assert client.delete(f"/api/companies/{cid}").status_code == 403  # only the owner can delete
    # Shared company data doesn't reveal the owner's household.
    assert client.get("/api/accounts", headers={"X-Household-Id": str(people.local["household_id"])}).status_code == 404

    people.act_as(accountant)
    assert client.get(f"/api/companies/{cid}/entries").status_code == 200
    assert client.get(f"/api/companies/{cid}/statements", params={"year": 2026, "format": "xlsx"}).status_code == 200
    assert client.post(f"/api/companies/{cid}/entries", json={"kind": "income", "date": "2026-02-01", "description": "x", "amount": 1}).status_code == 403
    assert client.put(f"/api/companies/{cid}", json={"name": "Renamed"}).status_code == 403

    people.act_as(None)
    assert client.delete(f"/api/companies/{cid}").status_code == 204


def test_company_entries_cannot_cross_companies(client, people):
    theirs = people.add("partner@example.com")
    people.act_as(theirs)
    other = client.post("/api/companies", json={"name": "Theirs"}).json()["id"]
    member = client.post(f"/api/companies/{other}/members", json={"name": "Pat", "equity_percent": 100}).json()["id"]
    people.act_as(None)
    mine = client.post("/api/companies", json={"name": "Mine"}).json()["id"]
    assert client.post(f"/api/companies/{mine}/entries", json={
        "kind": "contribution", "date": "2026-01-01", "description": "x", "amount": 5, "member_id": member,
    }).status_code == 404
    assert client.delete(f"/api/companies/{other}/members/{member}").status_code == 404


def test_price_refresh_is_per_household(client, people, fake_prices):
    fake_prices.update({"VTI": [100, 101], "QQQ": [400, 401]})
    client.post("/api/holdings", json={"ticker": "VTI", "asset_type": "etf", "quantity": 1})
    other = people.add("other@example.com")
    people.act_as(other)
    client.post("/api/holdings", json={"ticker": "QQQ", "asset_type": "etf", "quantity": 1})
    fake_prices["QQQ"] = []  # QQQ now fails, which only its holder should hear about
    run = client.post("/api/prices/refresh").json()
    assert run["tickers_updated"] == 0 and run["message"] == "No data for: QQQ"

    people.act_as(None)
    with system_session() as db:
        from app.services.prices import refresh_all

        refresh_all(db)  # the scheduled run covers everyone
    assert client.get("/api/prices/status").json()["message"] is None
    people.act_as(other)
    assert client.get("/api/prices/status").json()["message"] == "No data for: QQQ"


# ---------- Row-level security (the database's own check) ----------

@needs_rls
def test_database_policies_hide_other_households(client, people):
    fill_household(client)
    company_id = client.post("/api/companies", json={"name": "Acme"}).json()["id"]
    mine = people.local
    other = people.add("other@example.com")

    with SessionLocal() as db:
        assert db.scalar(text("SELECT current_user")) == "moneysage_test_app"
        # No user set: nothing at all is visible.
        assert db.scalars(select(Category)).all() == []

    with SessionLocal() as db:
        set_session_user(db, other["id"])
        # A query that forgets to filter still sees only their own rows.
        assert {c.household_id for c in db.scalars(select(Category))} == {other["household_id"]}
        assert db.scalars(select(Account)).all() == []
        assert db.scalars(select(Company)).all() == []
        assert db.scalars(select(CompanyEntry)).all() == []
        db.commit()
        assert db.scalars(select(Account)).all() == []  # still applies after a commit
        with pytest.raises(DBAPIError):
            db.execute(insert(Account).values(household_id=mine["household_id"], name="Sneaky", kind="asset", subtype="cash"))
        db.rollback()
        # Updates to rows they can't see change nothing.
        assert db.execute(text("UPDATE accounts SET name = 'Hacked'")).rowcount == 0
        assert db.execute(text("DELETE FROM companies WHERE id = :id"), {"id": company_id}).rowcount == 0
        db.commit()

    with system_session() as db:
        assert db.scalars(select(Account.name)).all() == ["Checking"]


@needs_rls
def test_database_policies_block_viewer_writes(client, people):
    fill_household(client)
    guest = people.add("guest@example.com", with_household=False)
    people.share_household(people.local["household_id"], guest, "viewer")
    with SessionLocal() as db:
        set_session_user(db, guest["id"])
        assert [a.name for a in db.scalars(select(Account))] == ["Checking"]
        assert db.execute(text("UPDATE accounts SET name = 'Hacked'")).rowcount == 0
        assert db.execute(text("DELETE FROM balance_snapshots")).rowcount == 0
        db.commit()
    assert client.get("/api/accounts").json()[0]["name"] == "Checking"
