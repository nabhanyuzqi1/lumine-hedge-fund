# Copyright (c) 2026 Lumine. All rights reserved.
"""Common request/response schemas for the public REST API.

Aligned to docs/09-api: common envelope, auth headers, and pagination.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field


class Meta(BaseModel):
    """Envelope metadata carried on every API response."""

    api_version: str = "v1"
    timestamp: datetime
    request_id: str
    status: str = "ok"


class APIErrorDetail(BaseModel):
    """Structured error payload inside the common envelope."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


T = TypeVar("T")


class Envelope[T](BaseModel):
    """Common JSON envelope for all REST responses."""

    meta: Meta
    data: T | None = None
    error: APIErrorDetail | None = None


class Pagination(BaseModel):
    """Pagination cursor helper for list endpoints."""

    limit: int = Field(default=20, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PaginatedList[T](BaseModel):
    """Wrapper for paginated list responses."""

    items: list[T]
    total: int
    limit: int
    offset: int
