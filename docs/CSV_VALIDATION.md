# CSV inspection and import decisions

## Source inspected

- Source file: `data/sales.csv` (copied from the supplied `ai_bi_assistant_sales_data - GET.csv`).
- CSV has a header row and 51 transaction records (52 physical lines including the header).
- Headers, in source order: `Transaction_Id`, `Order_date`, `Product`, `Category`, `Region`, `Sales_channel`, `Quantity`, `Unit_price`, `Discount_amount`, `Status`.
- All 51 dates parse as `DD-MM-YYYY`; observed range is 03-01-2026 through 28-06-2026.
- Transaction IDs are unique in this file.

## Observed values and anomalies

| Field | Observed profile |
|---|---|
| `Category` | Accessories, Electronics, Furniture |
| `Region` | East, North, South, West |
| `Sales_channel` | Online, Retail |
| `Status` | 50 Completed, 1 Returned |
| `Quantity` | Integers from 0 to 35; `TXN0034` has quantity 0 |
| `Unit_price` | 50 parseable values from 650 to 12500; no zero values |
| `Discount_amount` | Integers from 0 to 2500; four non-zero discounts |

One required value is missing: `Unit_price` for `TXN0051` (CSV line 52). No other blank field was observed. The supplied data does not establish a currency or the intended business definition of a return.

## Proposed import validation rules

1. Parse the CSV by its header names; fail the import if required headers are missing or duplicated. Trim surrounding whitespace on text fields and reject an empty required value.
2. Require a non-empty `Transaction_Id`. Treat it as the unique transaction key. If duplicates are present, accept the first valid row and report later duplicates rather than silently overwriting an earlier row.
3. Parse `Order_date` strictly as `DD-MM-YYYY` and store it in ISO `YYYY-MM-DD` form. Reject invalid or ambiguous dates.
4. Parse quantity as a whole, non-negative integer. Retain zero quantity and report it as a data-quality warning; its revenue contribution is zero.
5. Parse unit price and discount as non-negative decimal amounts, convert exactly to integer minor units at a disclosed two-decimal precision, and reject values that cannot be represented without rounding. The source amounts are whole numbers; currency is unspecified, so the app will not attach a currency label unless one is confirmed.
6. Reject a row with missing or invalid required values, including `TXN0051` because its unit price is blank. Record source line number, transaction ID when available, and reason in the import report.
7. Accept only recognized statuses (`Completed`, `Returned`) after case/whitespace normalization. Report unrecognized statuses for review rather than treating them as completed.
8. Reject a discount larger than the transaction gross amount (`quantity × unit_price`). A zero price is valid by default but should be reported as a warning; negative price or discount is invalid.

The importer should retain valid returned transactions in storage. The analytics layer, separately, applies the agreed metric rule to include only completed transactions in revenue calculations. This keeps cleaning from silently changing the meaning of the data.

## Metric decisions for this project

- Revenue per transaction is `quantity × unit_price − discount_amount`.
- Only `Completed` transactions contribute to the five requested revenue analytics.
- `Returned` transactions are excluded, not subtracted: the input has no return quantity or refund amount to calculate a reliable net return.
- A valid zero-quantity completed transaction remains in the database and contributes zero revenue.
- Incomplete or invalid records are excluded from the active transaction table and disclosed with row-level rejection reasons.
- Amounts should be stored as integer minor units (not floating point), using two decimal places as an implementation assumption. Since the currency is unspecified, the app must avoid presenting an unsupported currency label.

## Repeat imports and reporting

Validate the whole file in memory before opening the replacement transaction, then replace the active imported dataset inside one SQLite transaction. A successful repeat import therefore produces the same active rows rather than duplicates. Persist accepted/rejected counts and rejected row reasons; print warnings in the import command's report. If the import cannot complete, leave the previous active dataset intact. A file with no valid transaction rows is rejected so it cannot erase a previously loaded dataset.

The implemented importer accepted 50 rows from the supplied CSV, rejected line 52 (`TXN0051`) because `Unit_price` is blank, and warned on line 35 (`TXN0034`) for zero quantity. The accepted rows contain 49 `Completed` transactions and one `Returned` transaction.

## Milestone 1 completion checks

- [x] Inspect actual source headers and all records, not only examples.
- [x] Identify and record the missing unit price, zero quantity, status distribution, and uniqueness of IDs.
- [x] Define proposed validation, rejection, warning, and repeat-import behavior.
- [x] Separate import cleaning decisions from analytics inclusion rules.
- [x] Disclose the two-decimal storage precision assumption; currency remains unspecified and will not be labeled.
- [x] Run the importer on the supplied CSV and confirm its accepted, rejected, and warning counts.
