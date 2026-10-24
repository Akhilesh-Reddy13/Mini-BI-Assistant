"""ASGI entry point: ``uvicorn app.main:app --reload``."""

from .api import app

__all__ = ["app"]
