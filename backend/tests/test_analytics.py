from __future__ import annotations

import sqlite3

import pytest

from app.analytics import (
    InvalidMonth,
    SameMonthComparison,
    compare_months,
    monthly_revenue_trend,
    top_product,
    top_region,
    total_revenue,
)
from app.database import connect_database


def test_total_revenue_uses_completed_rows_and_discounts(sales_db):
    result = total_revenue(sales_db)

    assert result["value"] == {"amount_minor": 4900, "amount": "49.00"}
    assert result["supporting_data"]["completed_transaction_count"] == 4
    assert result["supporting_data"]["gross_sales_minor"] == 5500
    assert result["supporting_data"]["discounts_minor"] == 600
    assert result["supporting_data"]["returned_transactions_excluded"] == 1
    assert result["supporting_data"]["zero_quantity_transaction_count"] == 1


def test_top_product_returns_highest_net_revenue(sales_db):
    result = top_product(sales_db)

    assert result["value"]["leaders"] == [
        {
            "product": "Office Chair",
            "revenue_minor": 2500,
            "revenue": "25.00",
            "completed_transaction_count": 1,
        }
    ]


def test_monthly_trend_is_chronological_and_keeps_zero_revenue_month(sales_db):
    result = monthly_revenue_trend(sales_db)

    assert [(item["month"], item["revenue_minor"]) for item in result["value"]["months"]] == [
        ("2026-01", 2400),
        ("2026-02", 2500),
        ("2026-03", 0),
    ]


def test_top_region_uses_net_revenue_and_excludes_returns(sales_db):
    result = top_region(sales_db)

    assert result["value"]["leaders"][0]["region"] == "South"
    assert result["value"]["revenue_minor"] == 2500


def test_month_comparison_calculates_absolute_and_percentage_change(sales_db):
    result = compare_months("2026-01", "2026-02", sales_db)

    assert result["value"]["absolute_change_minor"] == 100
    assert result["value"]["absolute_change"] == "1.00"
    assert result["value"]["percentage_change"] == "4.17"


def test_month_comparison_zero_start_revenue_has_no_percentage(sales_db):
    result = compare_months("2026-03", "2026-02", sales_db)

    assert result["value"]["from_revenue_minor"] == 0
    assert result["value"]["absolute_change_minor"] == 2500
    assert result["value"]["percentage_change"] is None
    assert "undefined" in result["supporting_data"]["note"]


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "yesterday", "2026-00"])
def test_invalid_month_is_rejected(sales_db, month):
    with pytest.raises(InvalidMonth):
        compare_months(month, "2026-02", sales_db)


def test_same_month_comparison_is_rejected(sales_db):
    with pytest.raises(SameMonthComparison):
        compare_months("2026-02", "2026-02", sales_db)


def test_analytics_connection_cannot_write(sales_db):
    connection = connect_database(sales_db, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM transactions")
    finally:
        connection.close()
