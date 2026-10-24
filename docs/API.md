# API contract

The FastAPI app is exposed from `backend/app/main.py`.

## `POST /api/ask`

Request JSON:

```json
{
  "question": "How did revenue change between January and February 2026?"
}
```

Question text must be non-empty and no longer than 1000 characters. Extra JSON fields are rejected. Successful responses use `status: "ok"` and contain the interpreted intent, validated parameters, human-readable answer, exact minor-unit result plus display amount, metric definition, supporting figures, and whether interpretation came from Groq or the local fallback.

```json
{
  "status": "ok",
  "intent": "compare_months",
  "parameters": {"from_month": "2026-01", "to_month": "2026-02"},
  "answer": "Revenue increased by 24,350.00 from 2026-01 to 2026-02. Percentage change: 11.58%.",
  "value": {
    "from_revenue_minor": 21025000,
    "from_revenue": "210,250.00",
    "to_revenue_minor": 23460000,
    "to_revenue": "234,600.00",
    "absolute_change_minor": 2435000,
    "absolute_change": "24,350.00",
    "percentage_change": "11.58"
  },
  "metric": "Completed transactions only; quantity × unit price − transaction discount. Amounts use two-decimal minor units; the source currency is unspecified.",
  "supporting_data": {"months": []},
  "interpretation_source": "groq",
  "error": null
}
```

The numbers above illustrate response shape; actual values are computed from the current database. For an unsupported question, HTTP 200 returns `status: "unsupported"` and an `unsupported_question` error object. Malformed requests and invalid parameters return HTTP 422 with a stable error schema. Database or internal errors return a generic message, a request ID, and no SQL, stack trace, or secret.

## `GET /api/health`

Returns `{"status":"ok","database":"ready"}` when the SQLite database and transactions table can be read. Returns HTTP 503 when the database is not ready. It does not make a Groq request.

## Run locally

From the backend directory after installing `requirements.txt` and importing the CSV:

```powershell
uvicorn app.main:app --reload
```

Set `SALES_DB_PATH` to override the default `data/sales.sqlite3` path. API credentials remain in the backend process environment.
