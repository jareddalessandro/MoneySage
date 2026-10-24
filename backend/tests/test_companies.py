def make_company(client, name="Acme LLC"):
    r = client.post("/api/companies", json={"name": name, "description": " Side business "})
    assert r.status_code == 201, r.text
    return r.json()


def test_company_members_and_equity(client):
    company = make_company(client)
    assert company["description"] == "Side business" and company["members"] == []
    cid = company["id"]

    me = client.post(f"/api/companies/{cid}/members", json={"name": "Jared", "equity_percent": 60}).json()
    partner = client.post(f"/api/companies/{cid}/members", json={"name": "Sam", "equity_percent": 33.3333}).json()
    assert partner["equity_percent"] == 33.3333

    # Ownership can't go past 100%, on add or on edit.
    over = client.post(f"/api/companies/{cid}/members", json={"name": "Lee", "equity_percent": 10})
    assert over.status_code == 400 and "6.6667%" in over.json()["detail"]
    assert client.put(f"/api/companies/{cid}/members/{me['id']}", json={"name": "Jared", "equity_percent": 70}).status_code == 400
    assert client.put(f"/api/companies/{cid}/members/{me['id']}", json={"name": "Jared", "equity_percent": 66.6667}).status_code == 200
    assert client.post(f"/api/companies/{cid}/members", json={"name": "Sam"}).status_code == 409

    names = [m["name"] for m in client.get(f"/api/companies/{cid}").json()["members"]]
    assert names == ["Jared", "Sam"]

    # A member from another company can't be used here.
    other = make_company(client, "Other Co")
    assert client.delete(f"/api/companies/{other['id']}/members/{me['id']}").status_code == 404


def test_company_entries_and_summary(client):
    cid = make_company(client)["id"]
    me = client.post(f"/api/companies/{cid}/members", json={"name": "Jared", "equity_percent": 75}).json()
    sam = client.post(f"/api/companies/{cid}/members", json={"name": "Sam", "equity_percent": 25}).json()

    def add(**body):
        r = client.post(f"/api/companies/{cid}/entries", json={"description": "x", **body})
        assert r.status_code == 201, r.text
        return r.json()

    add(kind="income", date="2026-01-15", amount=1000, category="Consulting", member_id=me["id"])
    add(kind="income", date="2026-03-02", amount=500, category="Consulting")
    add(kind="expense", date="2026-03-20", amount=300, category="Software")
    c = add(kind="contribution", date="2026-01-05", amount=2000, member_id=me["id"], category="ignored")
    assert c["category"] is None
    add(kind="contribution", date="2025-06-01", amount=1000, member_id=sam["id"])
    add(kind="expense", date="2025-12-31", amount=50, category="Fees")

    # Contributions need a member, and only contributions keep one.
    bad = client.post(f"/api/companies/{cid}/entries", json={"kind": "contribution", "date": "2026-01-01", "description": "x", "amount": 5})
    assert bad.status_code == 400
    entries = client.get(f"/api/companies/{cid}/entries", params={"year": 2026}).json()
    assert [e["date"] for e in entries] == ["2026-03-20", "2026-03-02", "2026-01-15", "2026-01-05"]
    assert next(e for e in entries if e["kind"] == "income" and e["amount"] == 1000)["member_id"] is None

    s = client.get(f"/api/companies/{cid}/summary", params={"year": 2026}).json()
    assert (s["income"], s["expenses"], s["net"]) == (1500, 300, 1200)
    assert s["contributions_year"] == 2000 and s["contributions_total"] == 3000
    assert s["equity_assigned"] == 100
    assert s["years"] == [2026, 2025]
    assert s["income_categories"] == ["Consulting"] and s["expense_categories"] == ["Fees", "Software"]
    assert len(s["months"]) == 12 and s["months"][2] == {"month": "2026-03", "income": 500, "expenses": 300}
    jared, sam_s = s["members"]
    assert (jared["contributed_year"], jared["contributed_total"], jared["profit_share"]) == (2000, 2000, 900)
    assert (sam_s["contributed_year"], sam_s["contributed_total"], sam_s["profit_share"]) == (0, 1000, 300)

    listed = client.get("/api/companies", params={"year": 2026}).json()
    assert listed[0]["net"] == 1200 and listed[0]["contributions_total"] == 3000

    # A member with contributions can't be removed; the whole company can.
    assert client.delete(f"/api/companies/{cid}/members/{sam['id']}").status_code == 409
    assert client.delete(f"/api/companies/{cid}").status_code == 204
    assert client.get("/api/companies").json() == []


def test_company_validation(client):
    make_company(client)
    assert client.post("/api/companies", json={"name": "Acme LLC"}).status_code == 409
    assert client.post("/api/companies", json={"name": "  "}).status_code == 422
    cid = client.get("/api/companies").json()[0]["id"]
    for body in (
        {"name": "A", "equity_percent": -1},
        {"name": "A", "equity_percent": 100.5},
    ):
        assert client.post(f"/api/companies/{cid}/members", json=body).status_code == 422, body
    entry = {"kind": "expense", "date": "2026-01-01", "description": "x", "amount": 0}
    assert client.post(f"/api/companies/{cid}/entries", json=entry).status_code == 422


def test_company_distributions(client):
    cid = make_company(client)["id"]
    me = client.post(f"/api/companies/{cid}/members", json={"name": "Jared", "equity_percent": 50}).json()
    sam = client.post(f"/api/companies/{cid}/members", json={"name": "Sam", "equity_percent": 50}).json()

    def add(**body):
        r = client.post(f"/api/companies/{cid}/entries", json={"description": "x", **body})
        assert r.status_code == 201, r.text
        return r.json()

    add(kind="income", date="2026-02-01", amount=10000)
    add(kind="contribution", date="2026-01-01", amount=4000, member_id=me["id"])
    d = add(kind="distribution", date="2026-06-30", amount=3000, member_id=me["id"], category="ignored")
    assert d["category"] is None and d["member_id"] == me["id"]
    add(kind="distribution", date="2026-06-30", amount=3000, member_id=sam["id"])
    add(kind="distribution", date="2025-12-15", amount=500, member_id=sam["id"])

    # A distribution needs a member, like a contribution.
    bad = {"kind": "distribution", "date": "2026-01-01", "description": "x", "amount": 5}
    assert client.post(f"/api/companies/{cid}/entries", json=bad).status_code == 400

    s = client.get(f"/api/companies/{cid}/summary", params={"year": 2026}).json()
    # Distributions are payouts, not expenses: profit and the chart are unchanged.
    assert (s["income"], s["expenses"], s["net"]) == (10000, 0, 10000)
    assert s["months"][5]["expenses"] == 0
    assert (s["distributions_year"], s["distributions_total"]) == (6000, 6500)
    jared, sam_s = s["members"]
    assert (jared["distributed_year"], jared["distributed_total"], jared["profit_share"]) == (3000, 3000, 5000)
    assert (sam_s["distributed_year"], sam_s["distributed_total"]) == (3000, 3500)
    assert client.get("/api/companies").json()[0]["distributions_total"] == 6500

    # A member with only distributions can't be removed either.
    assert client.delete(f"/api/companies/{cid}/members/{sam['id']}").status_code == 409
