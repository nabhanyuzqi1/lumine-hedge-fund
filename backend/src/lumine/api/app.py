# Copyright (c) 2026 Lumine. All rights reserved.
"""FastAPI application factory for the Lumine public REST API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from lumine.api.middleware.envelope import (
    CommonEnvelopeMiddleware,
    http_exception_handler,
    lumine_exception_handler,
    validation_exception_handler,
)
from lumine.api.middleware.idempotency import IdempotencyMiddleware
from lumine.api.middleware.logging import RequestLoggingMiddleware
from lumine.api.routers import (
    admin,
    journal,
    lineage,
    market,
    orders,
    portfolio,
    rpc,
    streams,
    workflows,
)
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import LumineError


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: validate settings on startup."""
    _ = get_settings()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Lumine API",
        description="Institutional AI-native quantitative hedge fund API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(CommonEnvelopeMiddleware)
    # Added last → outermost: idempotency sees the already-enveloped
    # response (error-contract.md:178-189).
    app.add_middleware(IdempotencyMiddleware)
    # Added last → outermost: request logging observes every response,
    # including idempotent replays, and echoes trace_id as X-Request-ID.
    app.add_middleware(RequestLoggingMiddleware)

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    app.add_exception_handler(LumineError, lumine_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # Register under the base class: routing and rate-limit middleware raise
    # starlette.exceptions.HTTPException, which an MRO lookup would not match
    # against a handler keyed to the fastapi subclass.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Phase 9 rest-api.md: URL-prefix versioning — every domain router is
    # mounted under /api/v1. /health stays at the root (infra probe).
    for router in (
        portfolio.router,
        orders.router,
        workflows.router,
        lineage.router,
        market.router,
        journal.router,
        streams.router,
        admin.router,
        rpc.router,
    ):
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
