"""Opt-in tests that call the configured Groq API for real."""

from __future__ import annotations

import os

import pytest

from app.interpreter import DEFAULT_GROQ_MODEL, GroqError, classify_with_groq


pytestmark = pytest.mark.groq_live


@pytest.fixture(scope="module", autouse=True)
def require_groq_credentials():
    if not os.getenv("GROQ_API_KEY", "").strip():
        pytest.skip("Set GROQ_API_KEY to run live Groq integration tests.")


@pytest.mark.parametrize(
    ("question", "expected_intent", "expected_parameters"),
    [
        ("What is the total revenue?", "total_revenue", {}),
        ("Which product generated the highest revenue?", "top_product", {}),
        ("Show the monthly revenue trend.", "monthly_trend", {}),
        ("Which region generated the highest sales?", "top_region", {}),
        (
            "How did revenue change between January and February 2026?",
            "compare_months",
            {"from_month": "2026-01", "to_month": "2026-02"},
        ),
        ("What is the weather forecast for Mumbai?", "unsupported", {}),
    ],
)
def test_live_groq_classifies_question_without_fallback(
    question: str, expected_intent: str, expected_parameters: dict[str, str]
):
    try:
        result = classify_with_groq(question, model=DEFAULT_GROQ_MODEL, timeout=30)
    except (GroqError, ValueError) as exc:
        # Avoid pytest printing local variables from the request frame; those
        # include the API key when --showlocals is enabled by the environment.
        pytest.fail(f"Live Groq classification failed: {exc}", pytrace=False)

    assert result.source == "groq", "This suite must verify a real provider response, not local fallback."
    assert result.intent == expected_intent
    assert result.parameters == expected_parameters
