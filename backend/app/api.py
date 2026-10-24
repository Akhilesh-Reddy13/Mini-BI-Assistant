"""FastAPI routes that connect interpretation to deterministic analytics."""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import analytics
from .database import DEFAULT_DB_PATH, connect_database
from .interpreter import InvalidQuestion, interpret_question
from .schemas import ApiError, AskRequest, AskResponse, HealthResponse


logger = logging.getLogger(__name__)
_ANALYTICS_BY_INTENT = {
    "total_revenue": analytics.total_revenue,
    "top_product": analytics.top_product,
    "monthly_trend": analytics.monthly_revenue_trend,
    "top_region": analytics.top_region,
}


def _error_response(
    *, status_code: int, code: str, message: str, request_id: str | None = None
) -> JSONResponse:
    response = AskResponse(
        status="error",
        error=ApiError(code=code, message=message, request_id=request_id),
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create the API app; ``db_path`` is injectable for deterministic tests."""
    configured_path = db_path if db_path is not None else os.getenv("SALES_DB_PATH", DEFAULT_DB_PATH)
    database_path = Path(configured_path).expanduser().resolve()
    application = FastAPI(
        title="Mini AI Business Intelligence Assistant",
        version="0.1.0",
        description="Answers supported sales questions with deterministic database analytics.",
    )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request, exc
        return _error_response(
            status_code=422,
            code="malformed_request",
            message="Provide a JSON object with a non-empty question of at most 1000 characters.",
        )

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse | JSONResponse:
        try:
            with closing(connect_database(database_path, read_only=True)) as connection:
                connection.execute("SELECT COUNT(*) FROM transactions").fetchone()
        except sqlite3.Error:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "database": "not_ready"},
            )
        return HealthResponse(status="ok", database="ready")

    @application.post("/api/ask", response_model=AskResponse)
    def ask(payload: AskRequest) -> AskResponse | JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        try:
            interpretation = interpret_question(payload.question)
        except InvalidQuestion:
            return _error_response(
                status_code=422,
                code="invalid_question",
                message="Question must be a non-empty string of at most 1000 characters.",
                request_id=request_id,
            )
        except Exception:
            logger.exception("Question interpretation failed; request_id=%s", request_id)
            return _error_response(
                status_code=500,
                code="internal_error",
                message="The request could not be interpreted. Please try again.",
                request_id=request_id,
            )

        if not interpretation.supported:
            return AskResponse(
                status="unsupported",
                intent=None,
                interpretation_source=interpretation.source,
                error=ApiError(
                    code="unsupported_question",
                    message=interpretation.message
                    or "Please ask about total revenue, top product, monthly trend, top region, or a two-month comparison.",
                ),
            )

        try:
            if interpretation.intent == "compare_months":
                result: dict[str, Any] = analytics.compare_months(
                    interpretation.parameters["from_month"],
                    interpretation.parameters["to_month"],
                    database_path,
                )
            else:
                function = _ANALYTICS_BY_INTENT[interpretation.intent]
                result = function(database_path)
        except (KeyError, ValueError) as exc:
            return _error_response(
                status_code=422,
                code="invalid_parameters",
                message=str(exc),
                request_id=request_id,
            )
        except sqlite3.Error:
            logger.exception("Analytics database query failed; request_id=%s", request_id)
            return _error_response(
                status_code=500,
                code="database_error",
                message="Sales data is temporarily unavailable. Please try again.",
                request_id=request_id,
            )
        except Exception:
            logger.exception("Analytics request failed; request_id=%s", request_id)
            return _error_response(
                status_code=500,
                code="internal_error",
                message="The request could not be completed. Please try again.",
                request_id=request_id,
            )

        return AskResponse(
            status="ok",
            intent=interpretation.intent,
            parameters=result.get("parameters", interpretation.parameters),
            answer=result["answer"],
            value=result["value"],
            metric=result["metric"],
            supporting_data=result["supporting_data"],
            interpretation_source=interpretation.source,
        )

    return application


app = create_app()
