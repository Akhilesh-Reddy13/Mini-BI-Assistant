# Deterministic analytics

`backend/app/analytics.py` implements the five supported metrics. Each function opens SQLite in read-only mode and executes fixed SQL with bound values. Product and region query dimensions are selected only from internal constant literals; the question text and Groq output are never interpolated into SQL.

## Results and precision

Each result includes an `intent`, human-readable `answer`, structured `value`, metric definition, and `supporting_data`. Amounts are returned both as integer minor units (the exact calculation value) and as comma-grouped two-decimal strings for display. No currency label is attached because the source file does not specify one. Percentage change is rounded to two decimal places using decimal arithmetic with half-up rounding.

## Functions and SQL strategy

| Function / intent | Query behavior | Evidence returned |
|---|---|---|
| `total_revenue` | Sums `quantity * unit_price_minor - discount_minor` for `Completed` rows. | Net revenue, completed count, gross sales, discounts, zero-quantity count, returned rows excluded. |
| `top_product` | Groups the same net revenue by product and ranks the result. | All top ties and the ranked product totals with transaction counts. |
| `monthly_revenue_trend` | Groups by the first seven characters of canonical ISO order date. | Ordered `YYYY-MM` totals and completed transaction counts. Months without completed transactions are omitted and disclosed. |
| `top_region` | Groups the same net revenue by region and ranks the result. | All top ties and each region's revenue and transaction count. “Sales” is explicitly reported as net revenue. |
| `compare_months` | Validates `YYYY-MM`; queries each month by inclusive start and exclusive next-month boundary. | Both totals, absolute change, and percentage change or a zero-baseline explanation. |

All amount calculations are performed in SQLite integer minor units. There are no floating-point calculations in revenue aggregation. The application owns the formula and status filter; the LLM only classifies an intent and extracts month parameters.

## Edge behavior

- An empty completed dataset returns zero total revenue and no top product or region.
- Returned rows remain in storage but are excluded from revenue totals.
- Zero quantity is included and contributes zero.
- Invalid month strings and same-month comparisons raise clear `ValueError` subclasses for the API layer to map to a client error.
- A missing month in a comparison is treated as zero revenue. Percentage change is `null` when the starting month's revenue is zero, with an explanatory note.
- Ties at the maximum are all returned; ranking order is stable by label for display.

## Supplied dataset spot-check

Against the imported CSV, the analytics functions returned 1,439,200.00 completed-only net revenue, Monitor as the highest-revenue product at 473,000.00, South as the highest-revenue region at 411,200.00, six monthly periods, and January-to-February change of 24,350.00 (11.58%). These amounts have no currency label by design. The import excluded the invalid-price transaction and retained the returned row only for audit, not as revenue.
