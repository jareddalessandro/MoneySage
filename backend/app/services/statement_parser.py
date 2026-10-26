"""Parse bank statement PDFs into transactions.

Only SoFi checking/savings statements are supported. Their text layer places each column separately,
so plain text extraction scrambles the rows; instead words are grouped into lines by position and
split into columns using the x positions of the DATE / TYPE / DESCRIPTION / AMOUNT / BALANCE header.

One SoFi PDF holds several account statements (checking, savings), and a savings statement can hold
Vault sections. Each account statement starts with a summary (current and beginning balance) and
lists transactions newest first, each followed by a "Transaction ID: ..." line.
"""

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import pdfplumber


class StatementError(ValueError):
    """The file isn't a statement this parser understands."""


MONEY_RE = re.compile(r"^-?\$[\d,]+\.\d{2}$")
DATE_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2}), (\d{4})$")
PERIOD_RE = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4}) - ([A-Z][a-z]{2} \d{1,2}, \d{4})")
ACCOUNT_RE = re.compile(r"^(Checking|Savings) Account - (\d{4})$")
TXN_ID_RE = re.compile(r"^Transaction ID: (\S+)$")
HEADER = ["DATE", "TYPE", "DESCRIPTION", "AMOUNT", "BALANCE"]
# Column starts on SoFi statements, used until a header line is seen.
DEFAULT_COLUMNS = {"TYPE": 106.0, "DESCRIPTION": 219.0, "AMOUNT": 466.0}
# Lines that end the transaction area of a page.
STOP_LINES = ("Contact Information", "SoFi Checking and Savings accounts are offered")


@dataclass
class Line:
    top: float
    words: list[dict]

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)


@dataclass
class ParsedRow:
    date: date
    bank_type: str  # the statement's TYPE column, e.g. "Direct Deposit"
    description: str
    amount: Decimal  # signed: deposits positive, withdrawals negative
    section: str  # e.g. "Checking Account - 2845" or "Joint House Vault"
    txn_id: str | None = None


@dataclass
class ParsedAccount:
    kind: str  # "checking" or "savings"
    last4: str
    beginning: Decimal | None = None
    ending: Decimal | None = None
    rows: list[ParsedRow] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.kind.title()} {self.last4}"

    @property
    def row_total(self) -> Decimal:
        return sum((r.amount for r in self.rows), Decimal(0))

    @property
    def difference(self) -> Decimal | None:
        """Ending balance minus (beginning + rows); 0 when every row was read."""
        if self.beginning is None or self.ending is None:
            return None
        return self.ending - self.beginning - self.row_total


@dataclass
class ParsedStatement:
    bank: str
    period_start: date
    period_end: date
    accounts: list[ParsedAccount]


def money(text: str) -> Decimal:
    return Decimal(text.replace("$", "").replace(",", ""))


def parse_date(text: str) -> date:
    return datetime.strptime(text, "%b %d, %Y").date()


def _lines(page) -> list[Line]:
    """Words grouped into lines (same baseline within 3pt), top to bottom, left to right."""
    lines: list[Line] = []
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1].top - w["top"]) <= 3:
            lines[-1].words.append(w)
        else:
            lines.append(Line(w["top"], [w]))
    for line in lines:
        line.words.sort(key=lambda w: w["x0"])
    return lines


def parse_statement(data: bytes) -> ParsedStatement:
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise StatementError("Couldn't read that file as a PDF") from exc

    with pdf:
        pages = [_lines(p) for p in pdf.pages]

    text = "\n".join(line.text for page in pages for line in page)
    if "sofi" not in text.lower():
        raise StatementError("Only SoFi checking and savings statements can be imported right now")
    period = PERIOD_RE.search(text)
    if not period:
        raise StatementError("Couldn't find the statement period in that PDF")

    accounts: list[ParsedAccount] = []
    account: ParsedAccount | None = None
    section = ""
    columns = dict(DEFAULT_COLUMNS)
    pending: str | None = None  # a summary label whose value is on the next line

    for page in pages:
        in_table = False
        previous = ""
        last_row: ParsedRow | None = None
        for line in page:
            txt = line.text
            words = line.words

            if pending:
                values = [w["text"] for w in words if MONEY_RE.match(w["text"])]
                if values and account is not None:
                    setattr(account, pending, money(values[0]))
                pending = None
            if txt.startswith("Current Balance"):
                pending = "ending"
            elif txt.startswith("Beginning Balance"):
                pending = "beginning"

            m = ACCOUNT_RE.match(txt)
            if m:
                kind, last4 = m.group(1).lower(), m.group(2)
                if account is None or (account.kind, account.last4) != (kind, last4):
                    account = ParsedAccount(kind, last4)
                    accounts.append(account)
                    section = txt
                # The account name also heads each continuation page's table.
                in_table = True
                previous = txt
                continue

            if [w["text"] for w in words] == HEADER:
                columns = {w["text"]: w["x0"] for w in words}
                # The line above the header names the section (an account or a Vault).
                section = previous or section
                in_table = True
                previous = txt
                continue

            if txt.startswith(STOP_LINES):
                in_table = False
            previous = txt
            if not in_table or account is None:
                continue

            row = _parse_row(words, columns, section)
            if row:
                account.rows.append(row)
                last_row = row
                continue
            if last_row is None:
                continue
            id_match = TXN_ID_RE.match(txt)
            if id_match:
                last_row.txn_id = id_match.group(1)
            elif words[0]["x0"] >= columns["DESCRIPTION"] - 5 and not any(MONEY_RE.match(w["text"]) for w in words):
                # A description that wrapped onto a second line.
                last_row.description = f"{last_row.description} {txt}"

    accounts = [a for a in accounts if a.rows or a.beginning is not None]
    if not accounts:
        raise StatementError("Couldn't find any accounts in that statement")
    return ParsedStatement(
        bank="SoFi",
        period_start=parse_date(period.group(1)),
        period_end=parse_date(period.group(2)),
        accounts=accounts,
    )


def _parse_row(words: list[dict], columns: dict[str, float], section: str) -> ParsedRow | None:
    """A transaction line: date, type, description, amount, and usually the day's balance."""
    type_x, desc_x = columns["TYPE"] - 5, columns["DESCRIPTION"] - 5
    date_words = [w["text"] for w in words if w["x0"] < type_x]
    if not DATE_RE.match(" ".join(date_words)):
        return None
    amounts = [w for w in words if MONEY_RE.match(w["text"]) and w["x0"] >= desc_x]
    if not amounts:
        return None
    rest = [w for w in words if w["x0"] >= type_x and w not in amounts]
    return ParsedRow(
        date=parse_date(" ".join(date_words)),
        bank_type=" ".join(w["text"] for w in rest if w["x0"] < desc_x),
        description=" ".join(w["text"] for w in rest if w["x0"] >= desc_x),
        # Amount comes before the balance.
        amount=money(amounts[0]["text"]),
        section=section,
    )
