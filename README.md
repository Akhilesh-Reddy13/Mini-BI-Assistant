# SalesLens — Mini AI Business Intelligence Assistant

SalesLens lets a user ask natural-language questions about the supplied sales transactions. A Groq model classifies a question into a small supported intent set; fixed, parameterized SQLite queries calculate all figures. If Groq credentials are unavailable or the response is invalid, a limited local parser can recognize common phrasings.

The project targets the RSG Research Private Limited GET AI-Assisted Development Challenge. It is a local demonstration app, not a production analytics platform.

## Supported questions

- What is the total revenue?
- Which product generated the highest revenue?
- What is the monthly revenue trend?
- Which region generated the highest sales?
- How did revenue change between two named months?

Every answer includes its metric definition and supporting figures. The UI presents the calculation evidence below the answer.

## Business rules and data quality

- Revenue is `quantity × unit price − transaction discount`.
- Only `Completed` transactions are counted. `Returned` rows remain in the database for auditability but are excluded because the CSV has no return amount or returned quantity.
- Discounts are interpreted as transaction-level amounts, applied once to the line gross.
- A zero quantity is valid, retained, and contributes zero revenue. Missing or invalid required values are rejected and reported.
- The supplied file contains 51 transaction rows. Import accepts 50, rejects `TXN0051` because its unit price is blank, and warns on `TXN0034` because its quantity is zero.
- Monetary values are stored as integer minor units at a disclosed two-decimal precision. Currency is unspecified in the source, so the UI does not attach a currency label.
- The importer replaces the active dataset atomically and preserves the old data if a new import fails. Re-importing does not append duplicate transactions.

See [CSV validation decisions](docs/CSV_VALIDATION.md), [database schema and metric semantics](docs/DATABASE_SCHEMA.md), and [analytics details](docs/ANALYTICS.md).

## Requirements

- Python 3.10 or newer.
- Node.js 20.19+ or 22.12+ for Vite 7.
- pnpm 11.25.0 (the frontend pins this version in `package.json`). Install it with `npm install --global pnpm@11.25.0` if it is not already available.
- A Groq API key is optional. Without it, the local parser handles a limited set of common phrasings.

## Local setup (Windows PowerShell)

### 1. Install and import the backend data

```powershell
cd mini-bi-assistant\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.importer
```

The importer reads `data/sales.csv` relative to the project root and creates `data/sales.sqlite3`. To import another CSV:

```powershell
python -m app.importer "D:\path\to\sales.csv"
```

The importer prints accepted/rejected counts, rejected row reasons, and data-quality warnings.

### 2. Configure Groq (optional)

In the same PowerShell window, before starting the API:

```powershell
$env:GROQ_API_KEY = "your-groq-api-key"
$env:GROQ_MODEL = "openai/gpt-oss-120b"
```

The API key is read only by the backend. Do not put it in the frontend or commit it. If you omit the key, the deterministic fallback parser is used. The Groq adapter, configuration, and limitations are described in [INTERPRETATION.md](docs/INTERPRETATION.md).

### 3. Start the backend

From the activated `backend` terminal:

```powershell
uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. OpenAPI docs are at `http://127.0.0.1:8000/docs`; health check is `http://127.0.0.1:8000/api/health`.

To use a different SQLite file, set `SALES_DB_PATH` before starting Uvicorn:

```powershell
python -m app.importer "data\sales.csv" --db "D:\path\to\sales.sqlite3"
$env:SALES_DB_PATH = "D:\path\to\sales.sqlite3"
```

### 4. Start the React interface

Open another PowerShell window:

```powershell
cd mini-bi-assistant\frontend
pnpm install
pnpm run dev
```

Open the Vite URL printed in the terminal (normally `http://127.0.0.1:5173`). Vite proxies `/api` calls to the local FastAPI server on port 8000.

## Run automated tests

From the backend directory with its virtual environment active:

```powershell
cd mini-bi-assistant\backend
pytest -q
```

The default test suite uses isolated temporary SQLite databases and mocked Groq calls; it does not need a Groq API key or network access. Live Groq integration testing has also been performed using the opt-in suite. To repeat it, set `GROQ_API_KEY` in the same terminal and run `pytest -q --run-groq-live -m groq_live` from `backend`; this makes six short provider requests. The default `pytest -q` never calls the live API. See [TESTING.md](docs/TESTING.md) for the observed result and coverage details.

## Architecture and AI development report

- [Architecture diagrams and component responsibilities](docs/ARCHITECTURE.md)
- [AI-assisted development report](docs/AI_DEVELOPMENT_REPORT.md)
- [API contract](docs/API.md)

## Known limitations

- Currency is not present in the CSV. Amounts are displayed without a currency symbol and use a two-decimal storage assumption.
- Returns are excluded rather than netted because refund amounts and returned quantities are absent.
- The local fallback parser supports only common phrasings and requires explicit years for month comparisons. Use clear wording if a question is not understood.
- Groq was exercised through live API requests; all six opt-in cases passed with the strict JSON Schema response format, including month comparison.
- Category, region, channel, and status values are validated against values observed in the supplied file. New valid dimension values require updating the importer allowlists.
- The app is designed for one local dataset and demonstration use. It has no authentication, roles, hosted deployment setup, or large-scale query optimization.
- The React interface has been production-built; it does not yet have a separate automated browser test suite.

## Demo flow

1. Import the CSV and start the backend and frontend.
2. Ask “Which product generated the highest revenue?” and point out the ranked supporting data.
3. Ask “How did revenue change between January and February 2026?” and explain the absolute and percentage change.
4. Ask an unrelated question to demonstrate the unsupported response.
5. Explain that Groq classifies intent while SQLite and deterministic code calculate every number.
