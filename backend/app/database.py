"""SQLite connection and schema setup for the sales dataset."""

from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sales.sqlite3"
SCHEMA_VERSION = 1


_SCHEMA = """
CREATE TABLE IF NOT EXISTS import_runs (
    import_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL CHECK (length(trim(source_name)) > 0),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN (
        'started', 'completed', 'completed_with_rejections', 'failed'
    )),
    accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0)
);

CREATE TABLE IF NOT EXISTS import_rejections (
    rejection_id INTEGER PRIMARY KEY,
    import_id INTEGER NOT NULL REFERENCES import_runs(import_id) ON DELETE CASCADE,
    source_row INTEGER NOT NULL CHECK (source_row >= 2),
    transaction_id TEXT,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    UNIQUE (import_id, source_row)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY CHECK (length(trim(transaction_id)) > 0),
    order_date TEXT NOT NULL CHECK (
        length(order_date) = 10
        AND order_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    ),
    product TEXT NOT NULL CHECK (length(trim(product)) > 0),
    category TEXT NOT NULL CHECK (length(trim(category)) > 0),
    region TEXT NOT NULL CHECK (length(trim(region)) > 0),
    sales_channel TEXT NOT NULL CHECK (length(trim(sales_channel)) > 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor >= 0),
    discount_minor INTEGER NOT NULL CHECK (
        discount_minor >= 0 AND discount_minor <= quantity * unit_price_minor
    ),
    status TEXT NOT NULL CHECK (status IN ('Completed', 'Returned')),
    import_id INTEGER NOT NULL REFERENCES import_runs(import_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_transactions_order_date ON transactions(order_date);
CREATE INDEX IF NOT EXISTS idx_transactions_product ON transactions(product);
CREATE INDEX IF NOT EXISTS idx_transactions_region ON transactions(region);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
"""


def connect_database(
    db_path: str | Path = DEFAULT_DB_PATH, *, read_only: bool = False
) -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign-key enforcement.

    Analytics callers can use ``read_only=True`` so question answering cannot
    modify the database. Schema setup and the future importer use read-write.
    """
    path = Path(db_path).expanduser().resolve()
    if read_only:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Create the schema if needed; safe to call more than once."""
    with connect_database(db_path) as connection:
        connection.executescript(_SCHEMA)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

