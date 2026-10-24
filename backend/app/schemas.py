"""Public API request and response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("question must not be blank")
        return value


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class AskResponse(BaseModel):
    status: Literal["ok", "unsupported", "error"]
    intent: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    answer: str | None = None
    value: dict[str, Any] | None = None
    metric: str | None = None
    supporting_data: dict[str, Any] = Field(default_factory=dict)
    interpretation_source: Literal["groq", "fallback"] | None = None
    error: ApiError | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ready"]
