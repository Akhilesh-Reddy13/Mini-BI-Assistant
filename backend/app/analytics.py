"""Deterministic sales analytics backed by fixed, read-only SQLite queries."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, connect_database


COMPLETED_STATUS = "Completed"
MONTH_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
REVENUE_SQL = "(quantity * unit_price_minor - discount_minor)"
REVENUE_METRIC = (
    "Completed transactions only; quantity × unit price − transaction discount. "
    "Amounts use two-decimal minor units; the source currency is unspecified."
)


class InvalidMonth(ValueError):
    """A month parameter is not a valid YYYY-MM calendar month."""


class SameMonthComparison(ValueError):
    """A comparison requires two distinct months."""


def _amount(minor_units: int) -> str:
    """Render minor units exactly as a two-decimal amount, without a currency."""
    return f"{Decimal(minor_units) / Decimal(100):,.2f}"


def _amount_fields(minor_units: int) -> dict[str, int | str]:
    return {"amount_minor": minor_units, "amount": _amount(minor_units)}


def _validate_month(month: str) -> tuple[str, str]:
    if not isinstance(month, str) or not MONTH_RE.fullmatch(month):
        raise InvalidMonth("Month must use YYYY-MM format, for example 2026-03.")
    year, month_number = (int(part) for part in month.split("-"))
    start = date(year, month_number, 1)
    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    return start.isoformat(), end.isoformat()


def _open(db_path: str | Path):
    return connect_database(db_path, read_only=True)


def total_revenue(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return completed-only total revenue plus calculation evidence."""
    with closing(_open(db_path)) as connection:
        total = connection.execute(
            f"""SELECT
                    COALESCE(SUM({REVENUE_SQL}), 0) AS net_minor,
                    COALESCE(SUM(quantity * unit_price_minor), 0) AS gross_minor,
                    COALESCE(SUM(discount_minor), 0) AS discounts_minor,
                    COUNT(*) AS completed_count,
                    COALESCE(SUM(CASE WHEN quantity = 0 THEN 1 ELSE 0 END), 0) AS zero_quantity_count
                FROM transactions WHERE status = ?""",
            (COMPLETED_STATUS,),
        ).fetchone()
        returned = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE status = ?", ("Returned",)
        ).fetchone()[0]

    net = int(total["net_minor"])
    return {
        "intent": "total_revenue",
        "answer": f"Total net revenue was {_amount(net)} (currency unspecified).",
        "value": _amount_fields(net),
        "metric": REVENUE_METRIC,
        "supporting_data": {
            "completed_transaction_count": int(total["completed_count"]),
            "gross_sales_minor": int(total["gross_minor"]),
            "gross_sales": _amount(int(total["gross_minor"])),
            "discounts_minor": int(total["discounts_minor"]),
            "discounts": _amount(int(total["discounts_minor"])),
            "zero_quantity_transaction_count": int(total["zero_quantity_count"]),
            "returned_transactions_excluded": int(returned),
        },
    }


def _grouped_revenue(db_path: str | Path, dimension: str) -> list[sqlite3.Row]:
    # Dimension is selected only by internal callers using fixed literals below.
    if dimension not in {"product", "region"}:
        raise ValueError("Unsupported internal grouping dimension")
    with closing(_open(db_path)) as connection:
        return connection.execute(
            f"""SELECT {dimension} AS label,
                       SUM({REVENUE_SQL}) AS revenue_minor,
                       COUNT(*) AS completed_transaction_count
                FROM transactions
                WHERE status = ?
                GROUP BY {dimension}
                ORDER BY revenue_minor DESC, label COLLATE NOCASE ASC""",
            (COMPLETED_STATUS,),
        ).fetchall()


def _top_dimension(
    db_path: str | Path, *, dimension: str, intent: str, label_key: str, phrase: str
) -> dict[str, Any]:
    grouped = _grouped_revenue(db_path, dimension)
    ranked = [
        {
            label_key: row["label"],
            "revenue_minor": int(row["revenue_minor"]),
            "revenue": _amount(int(row["revenue_minor"])),
            "completed_transaction_count": int(row["completed_transaction_count"]),
        }
        for row in grouped
    ]
    if ranked:
        maximum = ranked[0]["revenue_minor"]
        leaders = [item for item in ranked if item["revenue_minor"] == maximum]
        labels = ", ".join(str(item[label_key]) for item in leaders)
        answer = f"{labels} generated the highest {phrase}, {_amount(maximum)}."
        value: dict[str, Any] = {"leaders": leaders, "revenue_minor": maximum, "revenue": _amount(maximum)}
    else:
        leaders = []
        answer = f"There are no completed transactions to determine the highest {phrase}."
        value = {"leaders": [], "revenue_minor": None, "revenue": None}
    return {
        "intent": intent,
        "answer": answer,
        "value": value,
        "metric": REVENUE_METRIC,
        "supporting_data": {"ranked": ranked, "tie_count": len(leaders)},
    }


def top_product(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return all products tied at the highest completed-only net revenue."""
    return _top_dimension(
        db_path,
        dimension="product",
        intent="top_product",
        label_key="product",
        phrase="product revenue",
    )


def monthly_revenue_trend(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return completed-only revenue grouped by calendar month."""
    with closing(_open(db_path)) as connection:
        rows = connection.execute(
            f"""SELECT substr(order_date, 1, 7) AS month,
                       SUM({REVENUE_SQL}) AS revenue_minor,
                       COUNT(*) AS completed_transaction_count
                FROM transactions
                WHERE status = ?
                GROUP BY substr(order_date, 1, 7)
                ORDER BY month ASC""",
            (COMPLETED_STATUS,),
        ).fetchall()
    months = [
        {
            "month": row["month"],
            "revenue_minor": int(row["revenue_minor"]),
            "revenue": _amount(int(row["revenue_minor"])),
            "completed_transaction_count": int(row["completed_transaction_count"]),
        }
        for row in rows
    ]
    return {
        "intent": "monthly_trend",
        "answer": "Monthly net revenue trend for completed transactions.",
        "value": {"months": months},
        "metric": REVENUE_METRIC,
        "supporting_data": {
            "months": months,
            "note": "Only months with completed transactions are listed; omitted months have no completed rows.",
        },
    }


def top_region(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return all regions tied at the highest completed-only net revenue."""
    return _top_dimension(
        db_path,
        dimension="region",
        intent="top_region",
        label_key="region",
        phrase="regional sales (net revenue)",
    )


def _month_revenue(
    connection: sqlite3.Connection, month: str, bounds: tuple[str, str]
) -> dict[str, int | str]:
    start, end = bounds
    row = connection.execute(
        f"""SELECT COALESCE(SUM({REVENUE_SQL}), 0) AS revenue_minor,
                   COUNT(*) AS completed_transaction_count
            FROM transactions
            WHERE status = ? AND order_date >= ? AND order_date < ?""",
        (COMPLETED_STATUS, start, end),
    ).fetchone()
    return {
        "month": month,
        "revenue_minor": int(row["revenue_minor"]),
        "revenue": _amount(int(row["revenue_minor"])),
        "completed_transaction_count": int(row["completed_transaction_count"]),
    }


def compare_months(
    from_month: str, to_month: str, db_path: str | Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Compare two calendar months; the second month is compared to the first."""
    from_bounds = _validate_month(from_month)
    to_bounds = _validate_month(to_month)
    if from_month == to_month:
        raise SameMonthComparison("Choose two different months to compare.")
    with closing(_open(db_path)) as connection:
        earlier = _month_revenue(connection, from_month, from_bounds)
        later = _month_revenue(connection, to_month, to_bounds)

    earlier_minor = int(earlier["revenue_minor"])
    later_minor = int(later["revenue_minor"])
    change_minor = later_minor - earlier_minor
    percentage: str | None = None
    note: str | None = None
    if earlier_minor == 0:
        note = "Percentage change is undefined because the starting month's revenue is zero."
    else:
        percentage_value = (
            Decimal(change_minor) * Decimal(100) / Decimal(earlier_minor)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        percentage = format(percentage_value, ".2f")
    direction = "increased" if change_minor > 0 else "decreased" if change_minor < 0 else "did not change"
    answer = (
        f"Revenue {direction} by {_amount(abs(change_minor))} from {from_month} "
        f"to {to_month}."
    )
    if percentage is not None:
        answer += f" Percentage change: {percentage}%."
    elif note:
        answer += " " + note
    return {
        "intent": "compare_months",
        "parameters": {"from_month": from_month, "to_month": to_month},
        "answer": answer,
        "value": {
            "from_revenue_minor": earlier_minor,
            "from_revenue": _amount(earlier_minor),
            "to_revenue_minor": later_minor,
            "to_revenue": _amount(later_minor),
            "absolute_change_minor": change_minor,
            "absolute_change": _amount(change_minor),
            "percentage_change": percentage,
        },
        "metric": REVENUE_METRIC,
        "supporting_data": {"months": [earlier, later], "note": note},
    }
