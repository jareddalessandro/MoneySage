import io

import pytest
from reportlab.pdfgen import canvas

from app.services.statement_parser import StatementError, parse_statement

# Column x positions on a SoFi statement.
X_DATE, X_TYPE, X_DESC, X_AMOUNT, X_BALANCE = 21, 106, 219, 470, 556


class Page:
    def __init__(self, c):
        self.c, self.y = c, 760

    def line(self, *cells: tuple[float, str]):
        for x, text in cells:
            self.c.drawString(x, self.y, text)
        self.y -= 15


def fmt(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def sofi_pdf(accounts, period=("Aug 1, 2026", "Aug 31, 2026")) -> bytes:
    """A PDF laid out like a SoFi statement. accounts: [(kind, last4, beginning, ending, sections)],
    sections: [(heading or None, rows)], rows: [(date, type, description, amount, txn_id)].
    Each section's rows are split across two pages to cover continuation pages."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 8)
    for kind, last4, beginning, ending, sections in accounts:
        title = f"{kind} Account - {last4}"
        p = Page(c)
        p.line((312, "Monthly Statement Period"))
        p.line((312, f"{period[0]} - {period[1]}"))
        p.line((24, title))
        p.line((24, "Current Balance"), (168, "Monthly Interest Paid1"))
        p.line((24, fmt(ending)), (168, "$1.00"))
        p.line((24, "Beginning Balance"), (168, "Year-to-date Interest Paid"))
        p.line((24, fmt(beginning)), (168, "$9.00"))
        p.line((18, "Transaction Details"))
        for heading, rows in sections:
            p.line((X_DATE, heading or title))
            p.line((X_DATE, "DATE"), (X_TYPE, "TYPE"), (X_DESC, "DESCRIPTION"), (466, "AMOUNT"), (554, "BALANCE"))
            half = (len(rows) + 1) // 2
            for i, (day, type_, desc, amount, txn_id) in enumerate(rows):
                if i == half and heading is None:
                    p.line((18, "Contact Information"))
                    p.line((21, "SoFi Checking and Savings accounts are offered through SoFi Bank, N.A., Member FDIC"))
                    c.showPage()
                    c.setFont("Helvetica", 8)
                    p = Page(c)
                    p.line((X_DATE, title))
                p.line((X_DATE, day), (X_TYPE, type_), (X_DESC, desc), (X_AMOUNT, fmt(amount)), (X_BALANCE, "$1,234.56"))
                p.line((X_DESC, f"Transaction ID: {txn_id}"))
        p.line((18, "Contact Information"))
        p.line((21, "www.sofi.com"))
        c.showPage()
        c.setFont("Helvetica", 8)
    c.save()
    return buf.getvalue()


CHECKING_ROWS = [
    ("Aug 31, 2026", "Interest Earned", "Interest earned", 2.58, "300-1"),
    ("Aug 29, 2026", "Direct Payment", "CHASE CREDIT CRD EPAY", -428.73, "299-1"),
    ("Aug 27, 2026", "Withdrawal", "To Joint Savings - 3222", -500.00, "298-1"),
    ("Aug 26, 2026", "Direct Deposit", "CHSPSC, LLC PAYROLL", 858.65, "297-1"),
    ("Aug 24, 2026", "Direct Payment", "Zelle® Payment from Jerilyn Challenger", 66.00, "296-1"),
    ("Aug 20, 2026", "Direct Payment", "VERIZON WIRELESS PAYMENTS", -132.37, "295-1"),
    ("Aug 5, 2026", "Direct Deposit", "TUCSON ELECTRIC PAYROLL", 2987.36, "294-1"),
    ("Aug 3, 2026", "Direct Payment", "WF HOME MTG AUTO PAY", -2061.46, "293-1"),
]
SAVINGS_ROWS = [
    ("Aug 31, 2026", "Interest Earned", "Interest earned", 172.88, "229-1"),
    ("Aug 27, 2026", "Direct Payment", "SoFi Credit Card", -480.91, "228-1"),
    ("Aug 27, 2026", "Deposit", "From Joint Checking - 2845", 500.00, "227-1"),
]
VAULT_ROWS = [
    ("Aug 31, 2026", "Interest Earned", "Interest earned", 0.34, "20-1"),
    ("Aug 24, 2026", "Deposit", "From Joint checking balance", 200.00, "19-1"),
]
# Checking: 2.58 - 428.73 - 500 + 858.65 + 66 - 132.37 + 2987.36 - 2061.46 = 792.03
# Savings: 172.88 - 480.91 + 500 + 0.34 + 200 = 392.31


def august(checking_end=5792.03):
    return sofi_pdf([
        ("Checking", "2845", 5000.00, checking_end, [(None, CHECKING_ROWS)]),
        ("Savings", "3222", 40000.00, 40392.31, [(None, SAVINGS_ROWS), ("Joint House Vault", VAULT_ROWS)]),
    ])


@pytest.fixture
def accounts(client):
    ids = {}
    for name, subtype in [("SoFi Checking", "checking"), ("SoFi Savings", "savings"), ("Wells Fargo Checking", "checking")]:
        ids[name] = client.post("/api/accounts", json={"name": name, "kind": "asset", "subtype": subtype}).json()["id"]
    return ids


def upload(client, data: bytes, name="august.pdf"):
    return client.post("/api/statements/preview", files={"file": (name, data, "application/pdf")})


def commit_body(preview, **overrides):
    body = {
        "bank": preview["bank"],
        "file_name": "august.pdf",
        "period_start": preview["period_start"],
        "period_end": preview["period_end"],
        "accounts": [
            {k: a[k] for k in ("key", "name", "beginning", "ending", "account_id")} for a in preview["accounts"]
        ],
        "rows": [
            {k: r[k] for k in ("key", "date", "account_key", "description", "amount", "category_id", "skip")}
            for r in preview["rows"]
        ],
    }
    body.update(overrides)
    return body


def by_desc(rows):
    return {(r["description"], r["account_key"]): r for r in rows}


def test_parser_reads_accounts_sections_and_continuation_pages():
    s = parse_statement(august())
    assert s.bank == "SoFi" and str(s.period_start) == "2026-08-01" and str(s.period_end) == "2026-08-31"
    checking, savings = s.accounts
    assert (checking.name, len(checking.rows), str(checking.difference)) == ("Checking 2845", 8, "0.00")
    assert (savings.name, len(savings.rows), str(savings.difference)) == ("Savings 3222", 5, "0.00")
    assert [r.section for r in savings.rows] == ["Savings Account - 3222"] * 3 + ["Joint House Vault"] * 2
    first = checking.rows[0]
    assert (first.bank_type, first.description, str(first.amount), first.txn_id) == (
        "Interest Earned", "Interest earned", "2.58", "300-1"
    )
    assert checking.rows[3].description == "CHSPSC, LLC PAYROLL"


def test_parser_reports_missing_rows():
    checking = parse_statement(august(checking_end=5800.00)).accounts[0]
    assert str(checking.difference) == "7.97"


def test_rejects_other_files(client):
    assert upload(client, b"not a pdf").status_code == 400
    other_bank = io.BytesIO()
    c = canvas.Canvas(other_bank)
    c.drawString(72, 720, "Example Bank statement")
    c.save()
    response = upload(client, other_bank.getvalue())
    assert response.status_code == 400 and "SoFi" in response.json()["detail"]
    with pytest.raises(StatementError):
        parse_statement(b"%PDF-1.4 broken")


def test_preview_suggests_categories(client, accounts, category_id):
    p = upload(client, august()).json()
    assert p["month"] == "2026-08"
    assert [(a["key"], a["name"], a["account_id"], a["difference"]) for a in p["accounts"]] == [
        ("sofi-2845", "SoFi Checking 2845", accounts["SoFi Checking"], 0),
        ("sofi-3222", "SoFi Savings 3222", accounts["SoFi Savings"], 0),
    ]
    rows = by_desc(p["rows"])
    expect = {
        ("CHSPSC, LLC PAYROLL", "sofi-2845"): (category_id("Salary"), False, "Keyword match"),
        ("CHASE CREDIT CRD EPAY", "sofi-2845"): (category_id("Credit Card Payments"), False, "Credit card payment"),
        ("SoFi Credit Card", "sofi-3222"): (category_id("Credit Card Payments"), False, "Credit card payment"),
        ("To Joint Savings - 3222", "sofi-2845"): (None, True, "Transfer between your accounts"),
        ("From Joint Checking - 2845", "sofi-3222"): (None, True, "Transfer between your accounts"),
        ("From Joint checking balance", "sofi-3222"): (None, True, "Transfer between your accounts"),
        ("WF HOME MTG AUTO PAY", "sofi-2845"): (category_id("Housing"), False, "Keyword match"),
        ("VERIZON WIRELESS PAYMENTS", "sofi-2845"): (category_id("Miscellaneous"), False, "Not recognized"),
        ("Zelle® Payment from Jerilyn Challenger", "sofi-2845"): (category_id("Other Income"), False, "Not recognized"),
        ("Interest earned", "sofi-2845"): (category_id("Interest & Dividends"), False, "Keyword match"),
    }
    for key, (cat, skip, reason) in expect.items():
        assert (rows[key]["category_id"], rows[key]["skip"], rows[key]["reason"]) == (cat, skip, reason), key
    assert rows[("VERIZON WIRELESS PAYMENTS", "sofi-2845")]["amount"] == -132.37
    assert not any(r["duplicate"] for r in p["rows"])
    assert len({r["key"] for r in p["rows"]}) == 13
    # Nothing saved yet.
    assert client.get("/api/transactions", params={"month": "2026-08"}).json() == []


def test_import_saves_transactions_balances_and_rules(client, accounts, category_id):
    p = upload(client, august()).json()
    body = commit_body(p)
    for r in body["rows"]:
        if r["description"] == "VERIZON WIRELESS PAYMENTS":
            r["category_id"] = category_id("Utilities")
    response = client.post("/api/statements", json=body)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["transaction_count"] == 10  # 13 lines, 3 transfers skipped

    txns = client.get("/api/transactions", params={"month": "2026-08"}).json()
    assert len(txns) == 10 and all(t["source"] == "statement" for t in txns)
    verizon = next(t for t in txns if t["description"] == "VERIZON WIRELESS PAYMENTS")
    assert (verizon["amount"], verizon["category"]["name"], verizon["account_id"]) == (
        132.37, "Utilities", accounts["SoFi Checking"]
    )

    sheet = client.get("/api/balance-sheet", params={"month": "2026-08"}).json()
    balances = {r["account"]["name"]: r["balance"] for r in sheet["rows"]}
    assert balances["SoFi Checking"] == 5792.03 and balances["SoFi Savings"] == 40392.31
    assert balances["Wells Fargo Checking"] is None

    # Same statement again: everything is a duplicate, and the corrected category is remembered.
    again = upload(client, august()).json()
    assert all(r["duplicate"] for r in again["rows"])
    verizon_row = by_desc(again["rows"])[("VERIZON WIRELESS PAYMENTS", "sofi-2845")]
    assert (verizon_row["category_id"], verizon_row["reason"]) == (category_id("Utilities"), "Remembered from a past import")
    assert client.post("/api/statements", json=commit_body(again)).status_code == 409

    s = client.get("/api/income-statement", params={"month": "2026-08"}).json()
    assert s["has_statement"] and s["totals_from"] == "statement"
    assert s["total_income"] == round(2.58 + 858.65 + 66 + 2987.36 + 172.88 + 0.34, 2)
    assert s["total_expenses"] == round(428.73 + 132.37 + 2061.46 + 480.91, 2)

    # Undo removes the transactions; balances stay.
    assert client.get("/api/statements", params={"month": "2026-08"}).json()[0]["id"] == record["id"]
    assert client.delete(f"/api/statements/{record['id']}").status_code == 204
    assert client.get("/api/transactions", params={"month": "2026-08"}).json() == []
    assert client.get("/api/statements", params={"month": "2026-08"}).json() == []


def test_remembered_account_mapping(client, accounts):
    p = upload(client, august()).json()
    body = commit_body(p)
    body["accounts"][0]["account_id"] = accounts["Wells Fargo Checking"]
    assert client.post("/api/statements", json=body).status_code == 201
    later = upload(client, august()).json()
    assert later["accounts"][0]["account_id"] == accounts["Wells Fargo Checking"]


def test_import_validation(client, accounts, category_id):
    p = upload(client, august()).json()

    def attempt(edit):
        body = commit_body(p)
        edit(body)
        return client.post("/api/statements", json=body)

    def payroll(body):
        return next(r for r in body["rows"] if r["description"] == "CHSPSC, LLC PAYROLL")

    r = attempt(lambda b: payroll(b).update(category_id=None))
    assert r.status_code == 400 and "Pick a category" in r.json()["detail"]
    r = attempt(lambda b: payroll(b).update(category_id=category_id("Groceries")))
    assert r.status_code == 400 and "income category" in r.json()["detail"]
    r = attempt(lambda b: b["accounts"][0].update(account_id=999))
    assert r.status_code == 400
    r = attempt(lambda b: b.update(update_balances=False))
    assert r.status_code == 201
    sheet = client.get("/api/balance-sheet", params={"month": "2026-08"}).json()
    assert all(row["balance"] is None for row in sheet["rows"])


def test_statement_month_totals_and_unexpected_items(client, accounts, category_id):
    client.post("/api/statements", json=commit_body(upload(client, august()).json()))
    # Manual entries in a statement month explain it but don't add to it.
    client.post("/api/transactions", json={
        "date": "2026-08-12", "description": "Car repair", "amount": 400,
        "category_id": category_id("Transportation"), "is_unexpected": True,
    })
    client.post("/api/transactions", json={
        "date": "2026-08-13", "description": "Birthday money", "amount": 100,
        "category_id": category_id("Gifts Received"), "is_unexpected": True,
    })
    client.post("/api/transactions", json={
        "date": "2026-08-14", "description": "Cash groceries", "amount": 50, "category_id": category_id("Groceries"),
    })

    s = client.get("/api/income-statement", params={"month": "2026-08"}).json()
    income, expenses = 4087.81, 3103.47
    assert (s["total_income"], s["total_expenses"]) == (income, expenses)
    assert (s["unexpected_expenses"], s["unexpected_income"]) == (400, 100)
    names = {c["name"] for c in s["categories"]}
    assert "Transportation" not in names and "Groceries" not in names

    trend = {p["month"]: p for p in client.get("/api/income-statement/trend", params={"months": 120}).json()}
    assert (trend["2026-08"]["income"], trend["2026-08"]["expenses"]) == (income, expenses)
    assert trend["2026-08"]["unexpected_expenses"] == 400

    # Switched to manual entries, the statement rows are ignored.
    assert client.put("/api/income-statement/totals-from", json={"month": "2026-08", "totals_from": "manual"}).status_code == 204
    s = client.get("/api/income-statement", params={"month": "2026-08"}).json()
    assert s["totals_from"] == "manual" and s["has_statement"]
    assert (s["total_income"], s["total_expenses"]) == (100, 450)
    assert (s["unexpected_expenses"], s["unexpected_income"]) == (400, 100)
    trend = {p["month"]: p for p in client.get("/api/income-statement/trend", params={"months": 120}).json()}
    assert (trend["2026-08"]["income"], trend["2026-08"]["expenses"]) == (100, 450)


def test_month_without_statement_ignores_saved_choice(client, category_id):
    client.put("/api/income-statement/totals-from", json={"month": "2026-07", "totals_from": "statement"})
    client.post("/api/transactions", json={
        "date": "2026-07-02", "description": "Groceries", "amount": 80, "category_id": category_id("Groceries"),
    })
    s = client.get("/api/income-statement", params={"month": "2026-07"}).json()
    assert (s["totals_from"], s["has_statement"], s["total_expenses"]) == ("manual", False, 80)


def test_card_paid_budget_items_grouped_in_statement_months(client, accounts, category_id):
    groceries, housing = category_id("Groceries"), category_id("Housing")
    for name, cat, amount, card in [
        ("Groceries", groceries, 900, True), ("Netflix", category_id("Subscriptions"), 9, True),
        ("Mortgage", housing, 2061.46, False),
    ]:
        r = client.post("/api/budget/items", json={
            "name": name, "category_id": cat, "amount": amount, "frequency": "monthly", "paid_by_card": card,
        })
        assert r.status_code == 201 and r.json()["paid_by_card"] is card
    client.post("/api/statements", json=commit_body(upload(client, august()).json()))

    s = client.get("/api/income-statement", params={"month": "2026-08"}).json()
    lines = {c["name"]: c for c in s["categories"]}
    card = lines["Credit Card Payments"]
    assert (card["budgeted"], card["actual"], card["card_items"]) == (909, 909.64, ["Groceries", "Netflix"])
    assert "Groceries" not in lines and "Subscriptions" not in lines
    assert (lines["Housing"]["budgeted"], lines["Housing"]["actual"]) == (2061.46, 2061.46)
    assert s["budgeted_expenses"] == 2970.46

    # A manual month compares each category on its own.
    client.post("/api/transactions", json={
        "date": "2026-09-02", "description": "Costco", "amount": 300, "category_id": groceries,
    })
    lines = {c["name"]: c for c in client.get("/api/income-statement", params={"month": "2026-09"}).json()["categories"]}
    assert lines["Groceries"]["budgeted"] == 900 and lines["Groceries"]["card_items"] == []
    assert "Credit Card Payments" not in lines


def test_paid_by_card_only_for_expenses(client, category_id):
    r = client.post("/api/budget/items", json={
        "name": "Pay", "category_id": category_id("Salary"), "amount": 1000, "frequency": "monthly", "paid_by_card": True,
    })
    assert r.json()["paid_by_card"] is False


def test_recategorizing_imported_row_is_remembered(client, accounts, category_id):
    client.post("/api/statements", json=commit_body(upload(client, august()).json()))
    zelle = next(
        t for t in client.get("/api/transactions", params={"month": "2026-08"}).json()
        if t["description"].startswith("Zelle")
    )
    client.put(f"/api/transactions/{zelle['id']}", json={
        "date": zelle["date"], "description": zelle["description"], "amount": zelle["amount"],
        "category_id": category_id("Refunds & Reimbursements"), "account_id": zelle["account_id"],
    })
    row = by_desc(upload(client, august()).json()["rows"])[("Zelle® Payment from Jerilyn Challenger", "sofi-2845")]
    assert row["category_id"] == category_id("Refunds & Reimbursements")


def test_notes_keep_the_default_totals_source(client, accounts):
    client.post("/api/statements", json=commit_body(upload(client, august()).json()))
    client.put("/api/income-statement/notes", json={"month": "2026-08", "notes": "Paid HOA early"})
    s = client.get("/api/income-statement", params={"month": "2026-08"}).json()
    assert (s["totals_from"], s["notes"]) == ("statement", "Paid HOA early")

    # A saved totals choice keeps the notes, and vice versa.
    client.put("/api/income-statement/totals-from", json={"month": "2026-08", "totals_from": "manual"})
    s = client.get("/api/income-statement", params={"month": "2026-08"}).json()
    assert (s["totals_from"], s["notes"]) == ("manual", "Paid HOA early")
