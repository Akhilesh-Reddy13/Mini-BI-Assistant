from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError

from app.interpreter import (
    DEFAULT_GROQ_MODEL,
    InvalidQuestion,
    Interpretation,
    GroqError,
    classify_with_groq,
    interpret_question,
    validate_classification,
)


class _FakeGroqClient:
    def __init__(self, completion_create):
        completions = SimpleNamespace(create=completion_create)
        self.chat = SimpleNamespace(completions=completions)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("What is the total revenue?", "total_revenue"),
        ("Which product generated the highest revenue?", "top_product"),
        ("Show the monthly revenue trend", "monthly_trend"),
        ("Which region generated the highest sales?", "top_region"),
    ],
)
def test_local_fallback_recognizes_unparameterized_supported_intents(question, expected_intent):
    result = interpret_question(question, api_key="")

    assert result.intent == expected_intent
    assert result.source == "fallback"
    assert result.supported


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Compare revenue between January and February 2026", ("2026-01", "2026-02")),
        ("How did sales change from 2026-01 to 2026-02?", ("2026-01", "2026-02")),
        ("Compare Jan vs Feb 2026 revenue", ("2026-01", "2026-02")),
    ],
)
def test_local_fallback_extracts_explicit_months(question, expected):
    result = interpret_question(question, api_key="")

    assert result.intent == "compare_months"
    assert (result.parameters["from_month"], result.parameters["to_month"]) == expected


def test_local_fallback_asks_for_year_when_comparison_is_ambiguous():
    result = interpret_question("Compare revenue between January and February", api_key="")

    assert result.intent == "unsupported"
    assert "years" in result.message


def test_unrelated_question_is_unsupported():
    result = interpret_question("How is the weather today?", api_key="")

    assert result.intent == "unsupported"
    assert not result.supported


def test_empty_or_overlong_question_is_rejected():
    with pytest.raises(InvalidQuestion):
        interpret_question("  ", api_key="")
    with pytest.raises(InvalidQuestion):
        interpret_question("x" * 1001, api_key="")


def test_groq_classification_is_validated_and_marked_as_groq(monkeypatch):
    monkeypatch.setattr(
        "app.interpreter._call_groq",
        lambda question, api_key, model, timeout: {"intent": "top_product", "parameters": {}},
    )

    result = interpret_question("top product", api_key="test-secret")

    assert result == Interpretation("top_product", source="groq")


def test_direct_groq_classification_has_no_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.interpreter._call_groq",
        lambda *args: {"intent": "total_revenue", "parameters": {}},
    )

    result = classify_with_groq("total revenue", api_key="test-secret")

    assert result.intent == "total_revenue"
    assert result.source == "groq"


def test_direct_groq_classification_requires_a_key():
    with pytest.raises(GroqError, match="not configured"):
        classify_with_groq("total revenue", api_key="")


def test_gpt_oss_120b_is_the_default_model(monkeypatch):
    selected_model = {}

    def capture_model(question, api_key, model, timeout):
        selected_model["model"] = model
        return {"intent": "total_revenue", "parameters": {}}

    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setattr("app.interpreter._call_groq", capture_model)

    result = classify_with_groq("total revenue", api_key="test-secret")

    assert result.intent == "total_revenue"
    assert selected_model["model"] == "openai/gpt-oss-120b"
    assert DEFAULT_GROQ_MODEL == "openai/gpt-oss-120b"


def test_groq_sdk_request_uses_strict_json_schema_and_closes_client(monkeypatch):
    from app.interpreter import _call_groq

    client_args = {}
    request_args = {}
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"intent":"total_revenue","from_month":"","to_month":""}'))]
    )

    def create_client(**kwargs):
        client_args.update(kwargs)

        def create_completion(**request_kwargs):
            request_args.update(request_kwargs)
            return completion

        return _FakeGroqClient(create_completion)

    monkeypatch.setattr("app.interpreter.Groq", create_client)
    result = _call_groq("total revenue", "test-secret", "test-model", 12)

    assert result == {"intent": "total_revenue", "parameters": {}}
    assert client_args == {"api_key": "test-secret", "timeout": 12, "max_retries": 0}
    assert request_args["model"] == "test-model"
    response_format = request_args["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["required"] == [
        "intent", "from_month", "to_month"
    ]
    assert request_args["reasoning_effort"] == "low"
    assert request_args["temperature"] == 0


def test_groq_flat_schema_normalizes_month_comparison(monkeypatch):
    from app.interpreter import _call_groq

    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"intent":"compare_months","from_month":"2026-01","to_month":"2026-02"}'
                )
            )
        ]
    )
    fake_client = _FakeGroqClient(lambda **kwargs: completion)
    monkeypatch.setattr("app.interpreter.Groq", lambda **kwargs: fake_client)

    result = _call_groq("compare January and February 2026", "test-secret", "test-model", 10)

    assert result == {
        "intent": "compare_months",
        "parameters": {"from_month": "2026-01", "to_month": "2026-02"},
    }


def test_http_error_is_diagnostic_and_redacts_credentials(monkeypatch):
    secret = "gsk_testSecret123"

    def rejected_request(**kwargs):
        response = httpx.Response(
            401,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            content=('{"error":{"message":"Invalid API key ' + secret + '"}}').encode(),
        )
        raise APIStatusError("Unauthorized", response=response, body=None)

    monkeypatch.setattr("app.interpreter.Groq", lambda **kwargs: _FakeGroqClient(rejected_request))

    from app.interpreter import _call_groq

    with pytest.raises(GroqError, match="HTTP 401: Invalid API key") as exc_info:
        _call_groq("total revenue", secret, "test-model", 10)

    assert secret not in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)


def test_http_error_includes_groq_permission_code(monkeypatch):
    def forbidden_request(**kwargs):
        body = (
            '{"error":{"message":"The model is blocked at the project level.",'
            '"type":"permissions_error","code":"model_permission_blocked_project"}}'
        ).encode()
        response = httpx.Response(
            403,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            content=body,
        )
        raise APIStatusError("Forbidden", response=response, body=None)

    monkeypatch.setattr("app.interpreter.Groq", lambda **kwargs: _FakeGroqClient(forbidden_request))

    from app.interpreter import _call_groq

    with pytest.raises(GroqError, match="HTTP 403") as exc_info:
        _call_groq("total revenue", "test-secret", "test-model", 10)

    assert "model_permission_blocked_project" in str(exc_info.value)


def test_http_error_includes_sanitized_plain_text_body(monkeypatch):
    def forbidden_request(**kwargs):
        response = httpx.Response(
            403,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            content=b"Access denied by upstream gateway",
        )
        raise APIStatusError("Forbidden", response=response, body=None)

    monkeypatch.setattr("app.interpreter.Groq", lambda **kwargs: _FakeGroqClient(forbidden_request))

    from app.interpreter import _call_groq

    with pytest.raises(GroqError, match="HTTP 403: Access denied by upstream gateway"):
        _call_groq("total revenue", "test-secret", "test-model", 10)


def test_groq_month_parameters_must_be_valid(monkeypatch):
    monkeypatch.setattr(
        "app.interpreter._call_groq",
        lambda *args: {
            "intent": "compare_months",
            "parameters": {"from_month": "2026-13", "to_month": "2026-02"},
        },
    )

    result = interpret_question("compare January 2026 to February 2026 revenue", api_key="test-secret")

    assert result.intent == "compare_months"
    assert result.source == "fallback"
    assert result.parameters == {"from_month": "2026-01", "to_month": "2026-02"}


def test_extra_model_fields_are_rejected_then_local_fallback_is_used(monkeypatch):
    monkeypatch.setattr(
        "app.interpreter._call_groq",
        lambda *args: {"intent": "top_product", "parameters": {}, "sql": "DROP TABLE transactions"},
    )

    result = interpret_question("Which product generated the highest revenue?", api_key="test-secret")

    assert result.intent == "top_product"
    assert result.source == "fallback"


def test_groq_failure_uses_fallback_without_exposing_details(monkeypatch):
    def unavailable(*args):
        raise GroqError("private provider error")

    monkeypatch.setattr("app.interpreter._call_groq", unavailable)
    result = interpret_question("What is total revenue?", api_key="test-secret")

    assert result.intent == "total_revenue"
    assert result.source == "fallback"
    assert result.message is None


def test_classification_rejects_unknown_intent_and_wrong_parameters():
    with pytest.raises(ValueError):
        validate_classification({"intent": "execute_sql", "parameters": {}}, source="groq")
    with pytest.raises(ValueError):
        validate_classification({"intent": "top_region", "parameters": {"region": "North"}}, source="groq")

