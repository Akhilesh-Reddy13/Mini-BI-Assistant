from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import initialize_database  # noqa: E402
from app.importer import EXPECTED_HEADERS, import_csv  # noqa: E402


def transaction(
    transaction_id: str,
    date: str,
    product: str,
    region: str,
    quantity: str,
    unit_price: str,
    discount: str = "0",
    status: str = "Completed",
) -> dict[str, str]:
    return {
        "Transaction_Id": transaction_id,
        "Order_date": date,
        "Product": product,
        "Category": "Accessories" if product in {"Wireless Mouse", "Keyboard"} else "Furniture",
        "Region": region,
        "Sales_channel": "Online",
        "Quantity": quantity,
        "Unit_price": unit_price,
        "Discount_amount": discount,
        "Status": status,
    }


SAMPLE_ROWS = [
    transaction("TXN-A", "03-01-2026", "Wireless Mouse", "North", "2", "10", "1"),
    transaction("TXN-B", "20-01-2026", "Monitor", "East", "1", "5"),
    transaction("TXN-C", "02-02-2026", "Office Chair", "South", "1", "30", "5"),
    transaction("TXN-D", "04-02-2026", "Monitor", "South", "10", "100", status="Returned"),
    transaction("TXN-E", "06-03-2026", "Keyboard", "West", "0", "100"),
]


@pytest.fixture
def sales_db(tmp_path: Path) -> Path:
    csv_path = tmp_path / "fixture.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=EXPECTED_HEADERS)
        writer.writeheader()
        writer.writerows(SAMPLE_ROWS)
    db_path = tmp_path / "sales.sqlite3"
    initialize_database(db_path)
    import_csv(csv_path, db_path)
    return db_path
