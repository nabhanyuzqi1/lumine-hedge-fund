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

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    app.add_exception_handler(LumineError, lumine_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # Register under the base class: routing and rate-limit middleware raise
    # starlette.exceptions.HTTPException, which an MRO lookup would not match
    # against a handler keyed to the fastapi subclass.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    app.include_router(portfolio.router)
    app.include_router(orders.router)
    app.include_router(workflows.router)
    app.include_router(lineage.router)
    app.include_router(market.router)
    app.include_router(journal.router)
    app.include_router(streams.router)
    app.include_router(admin.router)
    app.include_router(rpc.router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
