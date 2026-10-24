from __future__ import annotations

import pytest

from app.interpreter import (
    InvalidQuestion,
    Interpretation,
    GroqError,
    interpret_question,
    validate_classification,
)


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

