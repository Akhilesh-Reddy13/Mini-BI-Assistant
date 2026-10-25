# Automated tests

The default backend suite uses pytest and temporary SQLite databases. It does not depend on the supplied production database, network access, or Groq credentials. Live Groq tests are separate and run only when explicitly enabled.

Run from the backend directory:

```powershell
cd backend
pytest -q
```

To send six short requests to the real Groq API, set the key in the same PowerShell session and opt in:

```powershell
$env:GROQ_API_KEY = "your-groq-api-key"
pytest -q --run-groq-live -m groq_live
```

These cases call Groq directly through `classify_with_groq`, which has no local fallback. Each requires `source == "groq"`; a missing key skips the cases, while a provider or classification failure fails them. Regular `pytest -q` always skips live cases, even when a key is configured, to avoid unexpected requests or usage charges.

## Live Groq test status

Live requests have been run against the Groq API using `openai/gpt-oss-120b`. The latest six-case live run passed all six cases, including month comparison. The request uses strict JSON Schema output with fixed `intent`, `from_month`, and `to_month` fields; a local regression test also verifies that a valid comparison response is normalized and validated. Re-run the six-case command above after configuring the API key to repeat the integration check.

`pytest.ini` directs temporary test databases to an ignored project-local directory because some managed environments do not permit writes to the default user-profile temp path.

## Current coverage

- Total completed-only revenue, transaction count, gross amount, discount amount, returned exclusion, and zero-quantity contribution.
- Highest-revenue product and region.
- Chronological monthly aggregation, including a month with zero revenue.
- Month comparison absolute and percentage changes, plus a zero starting balance.
- Rejection of invalid month strings and same-month comparisons.
- Read-only enforcement on analytics database connections.
- Groq output validation, unexpected-field rejection, timeout/API-failure fallback, local intent recognition, and ambiguous month clarification without external network calls or credentials.
- FastAPI health, success dispatch, unsupported and malformed requests, invalid parameters, and database-error responses with internal details hidden.
- End-to-end natural-language requests through local intent fallback, FastAPI, and analytics; adversarial SQL-like wording; and Groq failure fallback with provider details hidden.
- Opt-in live Groq cases for all five intents and one unsupported question; the latest real API run passed all six cases. These cases remain excluded from the default run.
- Import rejection reporting for missing price and impossible date; retaining zero quantity.
- Idempotent repeat imports, all-invalid import protection, duplicate transaction IDs, and invalid CSV headers.

The API tests use FastAPI's `TestClient` and an injected temporary database. The offline suite has 51 passing cases before the latest interpreter regression test; six live cases are skipped unless explicitly enabled. The interpreter-focused suite, including the strict-schema regression test, passes 23 tests.
