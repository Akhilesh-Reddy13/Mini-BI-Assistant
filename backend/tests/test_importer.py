from __future__ import annotations

import csv

import pytest

from app.database import connect_database, initialize_database
from app.importer import EXPECTED_HEADERS, ImportFileError, import_csv

from conftest import SAMPLE_ROWS


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=EXPECTED_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_invalid_rows_are_reported_and_zero_quantity_is_retained(tmp_path):
    rows = [dict(row) for row in SAMPLE_ROWS]
    missing_price = dict(SAMPLE_ROWS[0], Transaction_Id="TXN-BAD-PRICE", Unit_price="")
    invalid_date = dict(SAMPLE_ROWS[0], Transaction_Id="TXN-BAD-DATE", Order_date="31-02-2026")
    rows.extend([missing_price, invalid_date])
    csv_path = tmp_path / "input.csv"
    db_path = tmp_path / "db.sqlite3"
    _write_csv(csv_path, rows)

    result = import_csv(csv_path, db_path)

    assert result.accepted_count == 5
    assert result.rejected_count == 2
    assert any("Unit_price" in item.reason for item in result.rejected)
    assert any("calendar date" in item.reason for item in result.rejected)
    assert any("zero quantity" in warning for warning in result.warnings)
    with connect_database(db_path, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 5
        assert connection.execute(
            "SELECT quantity FROM transactions WHERE transaction_id = 'TXN-E'"
        ).fetchone()[0] == 0


def test_reimport_replaces_active_rows_without_duplicates(tmp_path):
    csv_path = tmp_path / "input.csv"
    db_path = tmp_path / "db.sqlite3"
    _write_csv(csv_path, SAMPLE_ROWS)

    import_csv(csv_path, db_path)
    second_result = import_csv(csv_path, db_path)

    assert second_result.accepted_count == len(SAMPLE_ROWS)
    with connect_database(db_path, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == len(SAMPLE_ROWS)
        assert connection.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 2


def test_invalid_only_import_does_not_erase_active_rows(tmp_path):
    good_csv = tmp_path / "good.csv"
    bad_csv = tmp_path / "bad.csv"
    db_path = tmp_path / "db.sqlite3"
    _write_csv(good_csv, SAMPLE_ROWS)
    import_csv(good_csv, db_path)
    invalid_rows = [dict(SAMPLE_ROWS[0], Unit_price="")]
    _write_csv(bad_csv, invalid_rows)

    with pytest.raises(ImportFileError, match="no valid transaction rows"):
        import_csv(bad_csv, db_path)
    with connect_database(db_path, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == len(SAMPLE_ROWS)


def test_duplicate_transaction_id_is_rejected(tmp_path):
    csv_path = tmp_path / "duplicates.csv"
    db_path = tmp_path / "db.sqlite3"
    duplicate = dict(SAMPLE_ROWS[0], Product="Keyboard")
    _write_csv(csv_path, [SAMPLE_ROWS[0], duplicate])

    result = import_csv(csv_path, db_path)

    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert result.rejected[0].reason == "duplicate Transaction_Id"


def test_header_mismatch_fails_before_database_replacement(tmp_path):
    csv_path = tmp_path / "bad-header.csv"
    db_path = tmp_path / "db.sqlite3"
    initialize_database(db_path)
    csv_path.write_text("Transaction_Id,Wrong_Header\nTXN1,value\n", encoding="utf-8")

    with pytest.raises(ImportFileError, match="headers do not match"):
        import_csv(csv_path, db_path)

    with connect_database(db_path, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
