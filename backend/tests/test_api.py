from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import create_app
from app.interpreter import Interpretation


def _set_interpretation(monkeypatch, interpretation):
    monkeypatch.setattr("app.api.interpret_question", lambda question: interpretation)


def test_health_check_confirms_database_is_available(sales_db):
    client = TestClient(create_app(sales_db))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}


def test_ask_returns_total_revenue_and_supporting_figures(sales_db, monkeypatch):
    _set_interpretation(monkeypatch, Interpretation("total_revenue", source="groq"))
    client = TestClient(create_app(sales_db))

    response = client.post("/api/ask", json={"question": "What is total revenue?"})

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["intent"] == "total_revenue"
    assert body["value"] == {"amount_minor": 4900, "amount": "49.00"}
    assert body["supporting_data"]["returned_transactions_excluded"] == 1
    assert body["interpretation_source"] == "groq"


def test_ask_dispatches_month_comparison_with_validated_parameters(sales_db, monkeypatch):
    interpretation = Interpretation(
        "compare_months",
        {"from_month": "2026-01", "to_month": "2026-02"},
        source="fallback",
    )
    _set_interpretation(monkeypatch, interpretation)
    client = TestClient(create_app(sales_db))

    response = client.post("/api/ask", json={"question": "compare revenue"})

    assert response.status_code == 200
    assert response.json()["parameters"] == {"from_month": "2026-01", "to_month": "2026-02"}
    assert response.json()["value"]["percentage_change"] == "4.17"


def test_unsupported_question_returns_structured_response(sales_db, monkeypatch):
    _set_interpretation(
        monkeypatch,
        Interpretation("unsupported", source="fallback", message="Please ask a sales question."),
    )
    client = TestClient(create_app(sales_db))

    response = client.post("/api/ask", json={"question": "weather"})

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["error"]["code"] == "unsupported_question"
    assert response.json()["error"]["message"] == "Please ask a sales question."


def test_malformed_request_returns_stable_validation_error(sales_db):
    client = TestClient(create_app(sales_db))

    response = client.post("/api/ask", json={"question": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "malformed_request"
    assert "question" in response.json()["error"]["message"]


def test_invalid_parameters_return_client_error(sales_db, monkeypatch):
    _set_interpretation(
        monkeypatch,
        Interpretation(
            "compare_months",
            {"from_month": "2026-13", "to_month": "2026-02"},
            source="groq",
        ),
    )
    client = TestClient(create_app(sales_db))

    response = client.post("/api/ask", json={"question": "compare revenue"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_parameters"


def test_database_error_does_not_expose_internal_details(tmp_path, monkeypatch):
    _set_interpretation(monkeypatch, Interpretation("total_revenue", source="fallback"))
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))

    response = client.post("/api/ask", json={"question": "total revenue"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "database_error"
    assert response.json()["error"]["request_id"]
    assert "sqlite" not in response.text.lower()


def test_health_check_reports_missing_database():
    client = TestClient(create_app("missing-database.sqlite3"))

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "not_ready"}
