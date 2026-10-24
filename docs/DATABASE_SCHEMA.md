# Database schema and metric semantics

## Metric definitions

The challenge does not define revenue, returns, or currency. The MVP uses these disclosed rules:

- **Net revenue per row:** `quantity × unit price − discount amount`.
- **Included status:** only `Completed` transactions are included in the five revenue analytics. `Returned` rows remain stored for auditability but are excluded. The source has a return status but no refund amount or returned quantity, so a net refund cannot be calculated defensibly.
- **Discount meaning:** `Discount_amount` is a transaction-level amount deducted once from the line gross, not a per-unit deduction. The importer rejects discounts greater than gross line value.
- **Zero quantity:** valid and retained; contributes zero revenue. It is reported as a data-quality warning.
- **Missing or invalid required values:** the row is rejected and explained in the import report, rather than imputed or silently treated as zero.
- **Money representation:** store amounts as integer minor units at two-decimal precision (for example, 12.34 is stored as 1234). The file only contains whole-number amounts. Currency is not specified, so answers must not attach a currency label unless confirmed.
- **Month:** calendar month in the transaction's stored date, represented as `YYYY-MM`.
- **Regional “sales”:** interpreted as completed-only net revenue, and the answer states that interpretation.
- **Ties:** return all products or regions tied at the maximum.
- **Month comparison:** absolute change is `later − earlier`; percentage change is `(later − earlier) / earlier × 100`. If earlier revenue is zero, percentage is `null` with a clear explanation; do not return infinity or a misleading percentage.

These are application metric rules. They are separate from ingestion validation, which handles parsing and record quality.

## Tables

The schema is created by `backend/app/database.py`.

### `transactions`

| Column | Type | Rule / purpose |
|---|---|---|
| `transaction_id` | `TEXT` | Primary key; trimmed non-empty source ID. |
| `order_date` | `TEXT` | Required canonical `YYYY-MM-DD`. Importer strictly parses source `DD-MM-YYYY`; SQLite checks shape and importer verifies calendar validity. |
| `product` | `TEXT` | Required, trimmed product name. |
| `category` | `TEXT` | Required, trimmed category. |
| `region` | `TEXT` | Required, trimmed region. |
| `sales_channel` | `TEXT` | Required, trimmed channel. |
| `quantity` | `INTEGER` | Non-negative whole number; zero is allowed. |
| `unit_price_minor` | `INTEGER` | Non-negative unit price in minor units. |
| `discount_minor` | `INTEGER` | Non-negative row-level discount, bounded by gross row value. |
| `status` | `TEXT` | `Completed` or `Returned`; analytics filters to completed. |
| `import_id` | `INTEGER` | Foreign key to the import run that supplied this active row. |

Indexes cover date, product, region, and status, which are used by the requested aggregations. Revenue is calculated in queries from the stored amount columns; it is not separately stored and cannot drift out of sync.

### `import_runs` and `import_rejections`

`import_runs` stores a row per import attempt, its source name, status, and accepted/rejected counts. `import_rejections` stores the source CSV line, optional transaction ID, and reason for each rejected record. The importer milestone will stage and validate a file, then replace the active transaction set in a database transaction. A failed import must preserve the previous active set. Import history and rejection details remain available for explaining what happened.

The transaction ID is the unique key. If duplicate IDs occur in a file, the first valid instance is retained and later duplicates are rejected and reported. Reimporting replaces the active data instead of appending duplicates.

## Connection boundary

Schema initialization and ingestion use a read-write SQLite connection. Analytics/question answering uses SQLite read-only mode, fixed application-owned query templates, and bound parameters. The LLM is not given database access and does not generate SQL.

