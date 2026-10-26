"""Turn a parsed bank statement into transactions.

Importing is two steps. `preview` suggests what to do with each line (a category, or skip it) without
saving anything; the person reviews it, then `commit` saves the transactions, remembers each choice as an
ImportRule for next month, and (optionally) writes the statement's ending balances to the Balance Sheet.

Suggestions come from, in order: a remembered rule for the same description, then built-in keywords
(transfers between the statement's own accounts are skipped, payroll is Salary, card payments go to the
card payments category), then a catch-all (Other Income / Miscellaneous), marked "Not recognized".
"""

import hashlib
import re
from collections import Counter
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountKind,
    BalanceSnapshot,
    Category,
    CategoryKind,
    ImportRule,
    StatementImport,
    Transaction,
)
from app.schemas import PreviewAccount, PreviewRow, StatementImportIn, StatementPreview
from app.services.statement_parser import ParsedStatement
from app.months import format_month

# Moves between the statement's own accounts ("To Joint Savings - 3222", "From Joint checking balance",
# "To Joint House Vault"). Counting them would add the same money as both income and an expense.
TRANSFER_RE = re.compile(r"^(to|from)\b.*\b(checking|savings|vault)\b", re.IGNORECASE)
CARD_RE = re.compile(
    r"CREDIT CRD|CREDIT CARD|CARD ONLINE PAYMENT|CARD PAYMENT|CARD PMT|SYF PAYMNT|ONLINE PMT|"
    r"AMEX|AMERICAN EXPRESS|DISCOVER|CAPITAL ONE|APPLECARD|CRCARDPMT"
)
# (direction, pattern, category name) checked in order after transfers and card payments.
KEYWORDS: list[tuple[str, re.Pattern, str]] = [
    ("in", re.compile(r"PAYROLL"), "Salary"),
    ("in", re.compile(r"INTEREST"), "Interest & Dividends"),
    ("in", re.compile(r"REWARDS|CASHBACK|CASH BACK"), "Other Income"),
    ("out", re.compile(r"\bMTG\b|MORTGAGE|\bHOA\b"), "Housing"),
]
FALLBACK = {"in": ("Other Income", CategoryKind.income), "out": ("Miscellaneous", CategoryKind.expense)}


def normalize(description: str) -> str:
    """Rule key for a description: uppercase words, without punctuation or tokens holding digits
    (store numbers, reference codes), so "MCDONALD'S F43680" and "MCDONALD'S F11202" match."""
    text = re.sub(r"[^A-Z0-9&' ]+", " ", description.upper())
    words = [t for t in text.split() if not any(c.isdigit() for c in t)]
    return (" ".join(words) or " ".join(text.split()))[:255]


def direction(amount: Decimal) -> str:
    return "in" if amount > 0 else "out"


def account_key(bank: str, last4: str) -> str:
    return f"{bank.lower()}-{last4}"


def card_category(db: Session) -> Category | None:
    return db.scalar(select(Category).where(Category.is_card_payments).limit(1))


def preview(db: Session, statement: ParsedStatement) -> StatementPreview:
    categories = {
        (c.name.lower(), c.kind): c.id
        for c in db.scalars(select(Category).where(Category.is_archived.is_(False)))
    }
    card = card_category(db)
    rules = {(r.pattern, r.direction): r for r in db.scalars(select(ImportRule))}

    accounts: list[PreviewAccount] = []
    rows: list[PreviewRow] = []
    for acct in statement.accounts:
        key = account_key(statement.bank, acct.last4)
        accounts.append(
            PreviewAccount(
                key=key,
                name=f"{statement.bank} {acct.name}",
                kind=acct.kind,
                last4=acct.last4,
                beginning=acct.beginning,
                ending=acct.ending,
                row_total=acct.row_total,
                difference=acct.difference,
                account_id=_guess_account(db, statement.bank, key, acct.kind),
            )
        )
        seen: Counter = Counter()
        for r in acct.rows:
            ident = (r.section, r.txn_id or "", r.date, r.amount, "" if r.txn_id else r.description)
            seen[ident] += 1
            raw = "|".join(str(p) for p in (statement.bank, key, *ident, seen[ident]))
            category_id, skip, reason = _suggest(r.description, r.amount, rules, categories, card)
            rows.append(
                PreviewRow(
                    key=hashlib.sha256(raw.encode()).hexdigest(),
                    date=r.date,
                    account_key=key,
                    section=r.section,
                    bank_type=r.bank_type,
                    description=r.description[:255],
                    amount=r.amount,
                    category_id=category_id,
                    skip=skip,
                    reason=reason,
                    duplicate=False,
                )
            )

    existing = imported_keys(db, [r.key for r in rows])
    for row in rows:
        row.duplicate = row.key in existing
    return StatementPreview(
        bank=statement.bank,
        period_start=statement.period_start,
        period_end=statement.period_end,
        month=format_month(statement.period_end),
        accounts=accounts,
        rows=rows,
    )


def _suggest(description, amount, rules, categories, card) -> tuple[int | None, bool, str]:
    """(category_id, skip, reason) for one statement line."""
    way = direction(amount)
    rule = rules.get((normalize(description), way))
    if rule is not None:
        return rule.category_id, rule.skip, "Remembered from a past import"
    if TRANSFER_RE.search(description):
        return None, True, "Transfer between your accounts"
    upper = description.upper()
    kind = CategoryKind.income if way == "in" else CategoryKind.expense
    if way == "out" and card is not None and CARD_RE.search(upper):
        return card.id, False, "Credit card payment"
    for dir_, pattern, name in KEYWORDS:
        if dir_ == way and pattern.search(upper) and (name.lower(), kind) in categories:
            return categories[(name.lower(), kind)], False, "Keyword match"
    name, kind = FALLBACK[way]
    return categories.get((name.lower(), kind)), False, "Not recognized"


def _guess_account(db: Session, bank: str, key: str, kind: str) -> int | None:
    """The Balance Sheet account used for this statement account last time, else the only active
    asset account of that type whose name mentions the bank."""
    remembered = db.scalar(select(Account.id).where(Account.statement_key == key))
    if remembered is not None:
        return remembered
    matches = db.scalars(
        select(Account.id).where(
            Account.kind == AccountKind.asset,
            Account.subtype == kind,
            Account.is_archived.is_(False),
            Account.sync_from_holdings.is_(False),
            Account.name.ilike(f"%{bank}%"),
        )
    ).all()
    return matches[0] if len(matches) == 1 else None


def imported_keys(db: Session, keys: list[str]) -> set[str]:
    """The keys among these that an earlier import saved as a transaction or skipped."""
    found = set(db.scalars(select(Transaction.import_hash).where(Transaction.import_hash.in_(keys))))
    wanted = set(keys)
    for skipped in db.scalars(select(StatementImport.skipped_keys)):
        found.update(wanted.intersection(skipped))
    return found


def remember(db: Session, description: str, amount_direction: str, category_id: int | None, skip: bool) -> None:
    stmt = insert(ImportRule).values(
        pattern=normalize(description), direction=amount_direction, category_id=category_id, skip=skip
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["pattern", "direction"],
            set_={"category_id": stmt.excluded.category_id, "skip": stmt.excluded.skip, "updated_at": func.now()},
        )
    )


def commit(db: Session, body: StatementImportIn) -> StatementImport:
    accounts = {a.key: a for a in body.accounts}
    for a in body.accounts:
        if a.account_id is None:
            continue
        account = db.get(Account, a.account_id)
        if account is None or account.kind != AccountKind.asset:
            raise HTTPException(400, f"Pick an asset account for {a.name}")
        if account.sync_from_holdings:
            raise HTTPException(400, f"{account.name} gets its balance from Investments, so it can't take a statement")
    for r in body.rows:
        if r.account_key not in accounts:
            raise HTTPException(400, f"Unknown statement account {r.account_key}")

    existing = imported_keys(db, [r.key for r in body.rows])
    rows = [r for r in body.rows if r.key not in existing]
    if not rows:
        raise HTTPException(409, "Everything in this statement has already been imported")

    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    for r in rows:
        if r.skip:
            continue
        if r.category_id is None:
            raise HTTPException(400, f"Pick a category for “{r.description}” or skip it")
        if r.category_id not in kinds:
            raise HTTPException(404, "Category not found")
        expected = CategoryKind.income if r.amount > 0 else CategoryKind.expense
        if kinds[r.category_id] != expected:
            word = "an income" if expected == CategoryKind.income else "an expense"
            raise HTTPException(400, f"“{r.description}” needs {word} category")

    record = StatementImport(
        bank=body.bank,
        file_name=body.file_name,
        period_start=body.period_start,
        period_end=body.period_end,
        accounts=[
            {
                "key": a.key,
                "name": a.name,
                "beginning": None if a.beginning is None else str(a.beginning),
                "ending": None if a.ending is None else str(a.ending),
                "account_id": a.account_id,
            }
            for a in body.accounts
        ],
        skipped_keys=[r.key for r in rows if r.skip],
    )
    db.add(record)
    db.flush()

    for r in rows:
        remember(db, r.description, direction(r.amount), None if r.skip else r.category_id, r.skip)
        if r.skip:
            continue
        db.add(
            Transaction(
                date=r.date,
                description=r.description,
                amount=abs(r.amount),
                category_id=r.category_id,
                account_id=accounts[r.account_key].account_id,
                source="statement",
                import_hash=r.key,
                statement_import_id=record.id,
            )
        )

    month = body.period_end.replace(day=1)
    for a in body.accounts:
        # Remember which Balance Sheet account this statement account is, for next time.
        db.execute(update(Account).where(Account.statement_key == a.key).values(statement_key=None))
        if a.account_id is None:
            continue
        db.get(Account, a.account_id).statement_key = a.key
        db.flush()
        if body.update_balances and a.ending is not None:
            snap = db.scalar(
                select(BalanceSnapshot).where(
                    BalanceSnapshot.account_id == a.account_id, BalanceSnapshot.month == month
                )
            )
            if snap is None:
                db.add(BalanceSnapshot(account_id=a.account_id, month=month, balance=a.ending))
            else:
                snap.balance = a.ending

    db.commit()
    db.refresh(record)
    return record
