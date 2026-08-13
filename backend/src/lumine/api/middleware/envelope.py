# Copyright (c) 2026 Lumine. All rights reserved.
"""Common envelope middleware and exception handler.

Wraps successful JSON responses in the standard envelope and converts
application exceptions into the structured error contract.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from lumine.api.schemas.common import APIErrorDetail, Envelope, Meta
from lumine.shared.errors import (
    AuthError,
    DuplicateRecordError,
    KillSwitchError,
    LumineError,
    RecordNotFoundError,
    RiskRejectionError,
    ScopeError,
    ValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import HTTPException, Request
    from fastapi.exceptions import RequestValidationError


def _normalize_chunk(raw_chunk: bytes | str | memoryview) -> bytes:
    """Convert a response chunk to bytes."""
    if isinstance(raw_chunk, memoryview):
        return raw_chunk.tobytes()
    if isinstance(raw_chunk, str):
        return raw_chunk.encode()
    return raw_chunk


def _consume_plain_body(response: Response) -> bytes:
    """Return the body of a non-streaming response."""
    raw_body = response.body
    if raw_body is None:
        return b""
    return _normalize_chunk(raw_body)


async def _consume_response_body(response: Response) -> bytes:
    """Consume and return the response body as bytes."""
    if hasattr(response, "body_iterator"):
        return b"".join([_normalize_chunk(chunk) async for chunk in response.body_iterator])
    return _consume_plain_body(response)


class CommonEnvelopeMiddleware(BaseHTTPMiddleware):
    """Wrap JSON responses in the common envelope when the client requests it.

    Always envelopes application/json responses; passes through streaming and
    binary responses untouched.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Wrap JSON responses in the common envelope."""
        response = await call_next(request)

        if not response.headers.get("content-type", "").startswith("application/json"):
            return response

        body = await _consume_response_body(response)

        try:
            parsed = json.loads(body)
        except Exception:  # noqa: BLE001
            parsed = None

        if isinstance(parsed, dict) and "meta" in parsed:
            # Already enveloped (e.g., from exception handler).
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )

        enveloped = Envelope(
            meta=Meta(
                timestamp=datetime.now(UTC),
                # Honor the inbound trace id so envelope meta.request_id
                # matches the echoed X-Request-ID (logging middleware).
                request_id=request.headers.get("X-Request-ID") or str(uuid.uuid4()),
                status="ok" if response.status_code < 400 else "error",
            ),
            data=parsed,
        ).model_dump(mode="json", exclude_none=True)
        filtered_headers = {
            k: v for k, v in response.headers.items() if k.lower() != "content-length"
        }
        return JSONResponse(
            content=enveloped,
            status_code=response.status_code,
            headers=filtered_headers,
        )


def _make_error_response(  # noqa: PLR0913, PLR0917 — internal error-builder helper
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    envelope: Envelope[Any] = Envelope(
        meta=Meta(
            timestamp=datetime.now(UTC),
            request_id=request_id,
            status="error",
        ),
        error=APIErrorDetail(
            code=code,
            message=message,
            details=details or {},
            trace_id=request_id,
        ),
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def lumine_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map LumineError subclasses to HTTP status + error envelope."""
    mapping: dict[type[LumineError], tuple[int, str]] = {
        AuthError: (401, "INVALID_SIGNATURE"),
        ScopeError: (403, "INSUFFICIENT_SCOPE"),
        RecordNotFoundError: (404, "NOT_FOUND"),
        DuplicateRecordError: (409, "DUPLICATE_IDEMPOTENCY"),
        ValidationError: (400, "VALIDATION_FAILED"),
        RiskRejectionError: (422, "RISK_REJECTED"),
        KillSwitchError: (403, "KILL_SWITCH_ACTIVE"),
    }
    lumine_exc = cast("LumineError", exc)
    status_code, default_code = mapping.get(type(lumine_exc), (500, "INTERNAL_ERROR"))
    code = getattr(lumine_exc, "code", None) or default_code
    return _make_error_response(request, status_code, code, str(lumine_exc))


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    """Drop non-JSON-serializable context from pydantic error entries.

    model_validator failures carry the raised exception in ``ctx.error``;
    the envelope serializer cannot encode arbitrary exception objects, so
    every ctx value is coerced to a scalar before the envelope is built.
    """
    sanitized: list[dict] = []
    for entry in errors:
        item = dict(entry)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                key: (
                    str(value)
                    if value is not None and not isinstance(value, (bool, int, float, str))
                    else value
                )
                for key, value in ctx.items()
            }
        elif ctx is not None:
            item["ctx"] = str(ctx)
        sanitized.append(item)
    return sanitized


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Convert FastAPI request validation failures into the error envelope."""
    validation_exc = cast("RequestValidationError", exc)
    details = {"errors": _sanitize_validation_errors(validation_exc.errors())}
    return _make_error_response(
        request, 400, "VALIDATION_FAILED", "request validation failed", details
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert FastAPI HTTPException into the common error envelope."""
    http_exc = cast("HTTPException", exc)
    code = "INTERNAL_ERROR" if http_exc.status_code >= 500 else "INVALID_REQUEST"
    if http_exc.status_code == 401:
        code = "MISSING_AUTH"
    if http_exc.status_code == 403:
        code = "INSUFFICIENT_SCOPE"
    if http_exc.status_code == 404:
        code = "NOT_FOUND"
    if http_exc.status_code == 429:
        code = "RATE_LIMITED"
    return _make_error_response(
        request,
        http_exc.status_code,
        code,
        http_exc.detail or "",
        headers=http_exc.headers or None,
    )
