"""Validate and atomically load the supplied sales CSV into SQLite."""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from .database import DEFAULT_DB_PATH, connect_database, initialize_database


EXPECTED_HEADERS = (
    "Transaction_Id",
    "Order_date",
    "Product",
    "Category",
    "Region",
    "Sales_channel",
    "Quantity",
    "Unit_price",
    "Discount_amount",
    "Status",
)
ENUM_VALUES = {
    "Category": ("Accessories", "Electronics", "Furniture"),
    "Region": ("East", "North", "South", "West"),
    "Sales_channel": ("Online", "Retail"),
    "Status": ("Completed", "Returned"),
}
INTEGER_RE = re.compile(r"^[0-9]+$")
DATE_RE = re.compile(r"^[0-9]{2}-[0-9]{2}-[0-9]{4}$")
MINOR_UNIT_FACTOR = Decimal("100")


class ImportFileError(ValueError):
    """The source CSV is unreadable or has an invalid header."""


class ImportExecutionError(RuntimeError):
    """The database could not commit an import; prior data remains active."""


@dataclass(frozen=True)
class ValidTransaction:
    transaction_id: str
    order_date: str
    product: str
    category: str
    region: str
    sales_channel: str
    quantity: int
    unit_price_minor: int
    discount_minor: int
    status: str


@dataclass(frozen=True)
class Rejection:
    source_row: int
    transaction_id: str | None
    reason: str


@dataclass
class ImportResult:
    import_id: int
    source_name: str
    accepted_count: int
    rejected: list[Rejection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


def _canonical_enum(field_name: str, value: str) -> str:
    normalized = " ".join(value.split())
    options = ENUM_VALUES[field_name]
    by_casefold = {option.casefold(): option for option in options}
    if normalized.casefold() not in by_casefold:
        raise ValueError(f"unrecognized {field_name} value {normalized!r}")
    return by_casefold[normalized.casefold()]


def _amount_to_minor(value: str, field_name: str) -> int:
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field_name} is missing or is not a valid number") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field_name} must be a finite non-negative amount")
    minor = amount * MINOR_UNIT_FACTOR
    if minor != minor.to_integral_value():
        raise ValueError(f"{field_name} has more than two decimal places")
    return int(minor)


def _parse_row(raw: dict[str, str | None], source_row: int) -> tuple[ValidTransaction, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    raw_id = (raw.get("Transaction_Id") or "").strip()
    transaction_id = raw_id.upper() or None
    if transaction_id is None:
        errors.append("Transaction_Id is required")

    raw_date = (raw.get("Order_date") or "").strip()
    order_date = ""
    if not DATE_RE.fullmatch(raw_date):
        errors.append("Order_date must use DD-MM-YYYY format")
    else:
        try:
            order_date = datetime.strptime(raw_date, "%d-%m-%Y").date().isoformat()
        except ValueError:
            errors.append("Order_date is not a valid calendar date")

    text_values: dict[str, str] = {}
    for field_name in ("Product", "Category", "Region", "Sales_channel", "Status"):
        value = " ".join((raw.get(field_name) or "").split())
        if not value:
            errors.append(f"{field_name} is required")
        elif field_name in ENUM_VALUES:
            try:
                value = _canonical_enum(field_name, value)
            except ValueError as exc:
                errors.append(str(exc))
        text_values[field_name] = value

    raw_quantity = (raw.get("Quantity") or "").strip()
    quantity: int | None = None
    if not INTEGER_RE.fullmatch(raw_quantity):
        errors.append("Quantity must be a non-negative whole number")
    else:
        quantity = int(raw_quantity)
        if quantity == 0:
            warnings.append(f"row {source_row}: zero quantity for {transaction_id or 'unknown transaction'}")

    try:
        unit_price_minor = _amount_to_minor(raw.get("Unit_price") or "", "Unit_price")
        if unit_price_minor == 0:
            warnings.append(f"row {source_row}: zero unit price for {transaction_id or 'unknown transaction'}")
    except ValueError as exc:
        errors.append(str(exc))
        unit_price_minor = 0

    try:
        discount_minor = _amount_to_minor(raw.get("Discount_amount") or "", "Discount_amount")
    except ValueError as exc:
        errors.append(str(exc))
        discount_minor = 0

    if quantity is not None and discount_minor > quantity * unit_price_minor:
        errors.append("Discount_amount exceeds gross line value")

    if errors:
        raise ValueError("; ".join(errors))

    return (
        ValidTransaction(
            transaction_id=transaction_id or "",
            order_date=order_date,
            product=text_values["Product"],
            category=text_values["Category"],
            region=text_values["Region"],
            sales_channel=text_values["Sales_channel"],
            quantity=quantity if quantity is not None else 0,
            unit_price_minor=unit_price_minor,
            discount_minor=discount_minor,
            status=text_values["Status"],
        ),
        warnings,
    )


def _read_csv(csv_path: Path) -> tuple[list[ValidTransaction], list[Rejection], list[str]]:
    if not csv_path.is_file():
        raise ImportFileError(f"CSV file not found: {csv_path}")

    accepted: list[ValidTransaction] = []
    rejected: list[Rejection] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None:
                raise ImportFileError("CSV is empty or has no header row")
            headers = [name.strip() if name is not None else "" for name in reader.fieldnames]
            if len(headers) != len(set(headers)):
                raise ImportFileError("CSV contains duplicate column headers")
            if set(headers) != set(EXPECTED_HEADERS):
                missing = sorted(set(EXPECTED_HEADERS) - set(headers))
                unexpected = sorted(set(headers) - set(EXPECTED_HEADERS))
                raise ImportFileError(
                    f"CSV headers do not match expected schema; missing={missing}, unexpected={unexpected}"
                )
            reader.fieldnames = headers

            for raw in reader:
                source_row = reader.line_num
                if None in raw:
                    rejected.append(
                        Rejection(source_row, (raw.get("Transaction_Id") or "").strip() or None,
                                  "row has more values than the header")
                    )
                    continue
                try:
                    transaction, row_warnings = _parse_row(raw, source_row)
                except ValueError as exc:
                    rejected.append(
                        Rejection(source_row, (raw.get("Transaction_Id") or "").strip() or None, str(exc))
                    )
                    continue
                if transaction.transaction_id in seen_ids:
                    rejected.append(
                        Rejection(source_row, transaction.transaction_id, "duplicate Transaction_Id")
                    )
                    continue
                seen_ids.add(transaction.transaction_id)
                accepted.append(transaction)
                warnings.extend(row_warnings)
    except csv.Error as exc:
        raise ImportFileError(f"CSV parsing failed near source line {reader.line_num}: {exc}") from None
    except UnicodeDecodeError:
        raise ImportFileError("CSV must be encoded as UTF-8") from None

    return accepted, rejected, warnings


def import_csv(csv_path: str | Path, db_path: str | Path = DEFAULT_DB_PATH) -> ImportResult:
    """Validate a complete CSV, then replace active transactions atomically."""
    source_path = Path(csv_path).expanduser().resolve()
    accepted, rejected, warnings = _read_csv(source_path)
    if not accepted:
        raise ImportFileError(
            "CSV contains no valid transaction rows; the active dataset was left unchanged."
        )
    initialize_database(db_path)
    connection = connect_database(db_path)
    import_id: int | None = None
    try:
        with connection:
            cursor = connection.execute(
                "INSERT INTO import_runs (source_name, status) VALUES (?, 'started')",
                (source_path.name,),
            )
            import_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO import_rejections
                   (import_id, source_row, transaction_id, reason) VALUES (?, ?, ?, ?)""",
                [(import_id, item.source_row, item.transaction_id, item.reason) for item in rejected],
            )
            connection.execute("DELETE FROM transactions")
            connection.executemany(
                """INSERT INTO transactions (
                       transaction_id, order_date, product, category, region, sales_channel,
                       quantity, unit_price_minor, discount_minor, status, import_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item.transaction_id, item.order_date, item.product, item.category,
                        item.region, item.sales_channel, item.quantity, item.unit_price_minor,
                        item.discount_minor, item.status, import_id,
                    )
                    for item in accepted
                ],
            )
            final_status = "completed_with_rejections" if rejected else "completed"
            connection.execute(
                """UPDATE import_runs
                   SET status = ?, finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                       accepted_count = ?, rejected_count = ?
                   WHERE import_id = ?""",
                (final_status, len(accepted), len(rejected), import_id),
            )
    except sqlite3.Error as exc:
        # The transaction context rolls back the replacement, preserving the
        # previous active data. Record a failed attempt separately if possible.
        if import_id is not None:
            try:
                with connection:
                    cursor = connection.execute(
                        """INSERT INTO import_runs
                           (source_name, status, finished_at, accepted_count, rejected_count)
                           VALUES (?, 'failed', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?, ?)""",
                        (source_path.name, len(accepted), len(rejected)),
                    )
                    failed_id = int(cursor.lastrowid)
                    connection.executemany(
                        """INSERT INTO import_rejections
                           (import_id, source_row, transaction_id, reason) VALUES (?, ?, ?, ?)""",
                        [(failed_id, item.source_row, item.transaction_id, item.reason) for item in rejected],
                    )
            except sqlite3.Error:
                pass
        raise ImportExecutionError(
            "Database import failed; the previous active transaction set was preserved."
        ) from exc
    finally:
        connection.close()

    return ImportResult(
        import_id=import_id or 0,
        source_name=source_path.name,
        accepted_count=len(accepted),
        rejected=rejected,
        warnings=warnings,
    )


def _print_result(result: ImportResult) -> None:
    print(f"Import {result.import_id}: {result.source_name}")
    print(f"Accepted: {result.accepted_count}; rejected: {result.rejected_count}; warnings: {len(result.warnings)}")
    for item in result.rejected:
        print(f"  rejected CSV line {item.source_row} ({item.transaction_id or 'no ID'}): {item.reason}")
    for warning in result.warnings:
        print(f"  warning: {warning}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and import sales CSV data into SQLite.")
    parser.add_argument("csv_path", nargs="?", default=str(Path(__file__).resolve().parents[2] / "data" / "sales.csv"))
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    args = parser.parse_args(argv)
    try:
        _print_result(import_csv(args.csv_path, args.db))
    except (ImportFileError, ImportExecutionError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
