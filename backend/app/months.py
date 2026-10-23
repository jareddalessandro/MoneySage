from datetime import date

from fastapi import HTTPException


def parse_month(value: str) -> date:
    """'2026-10' -> date(2026, 10, 1)."""
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid month '{value}', expected YYYY-MM")


def format_month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def current_month() -> date:
    return date.today().replace(day=1)


def add_months(d: date, n: int) -> date:
    index = d.year * 12 + (d.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def month_bounds(month: date) -> tuple[date, date]:
    """Start (inclusive) and end (exclusive) dates of a month."""
    return month, add_months(month, 1)
