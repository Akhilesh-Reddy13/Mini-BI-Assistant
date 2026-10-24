# Automated tests

The backend test suite uses pytest and temporary SQLite databases. It does not depend on the supplied production database, network access, or Groq credentials.

Run from the backend directory:

```powershell
cd backend
pytest -q
```

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
- Import rejection reporting for missing price and impossible date; retaining zero quantity.
- Idempotent repeat imports, all-invalid import protection, duplicate transaction IDs, and invalid CSV headers.

The API tests use FastAPI's `TestClient` and an injected temporary database. At this stage, the verified suite contains 44 passing test cases.
