# Copyright (c) 2026 Lumine. All rights reserved.
"""Redis-backed sliding-window rate limiter.

Uses the caller's API key as the bucket key and enforces the per-minute
limit configured in Settings.api_rate_limit_per_minute.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from lumine.data.redis_client import get_redis
from lumine.shared.config import Settings, get_settings

from .auth import AuthenticatedPrincipal, authenticate_request


async def rate_limit_dependency(
    _request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[AuthenticatedPrincipal, Depends(authenticate_request)],
) -> AuthenticatedPrincipal:
    """Dependency that enforces a per-key per-minute request limit.

    Skips accounting for the special bootstrap/admin key to avoid locking
    out deployment automation.
    """
    limit = settings.api_rate_limit_per_minute
    if limit <= 0:
        return principal

    # Degrade gracefully when Redis is not configured (local/dev mode):
    # rate limiting is an enhancement, not a gate on API availability.
    if not settings.redis_url:
        return principal

    window_seconds = 60
    now = time.time()
    bucket = f"lumine:rate_limit:{principal.key_id}"

    try:
        r = await get_redis()
    except Exception:  # noqa: BLE001 — Redis down must not 500 write endpoints
        return principal

    cutoff = now - window_seconds
    await r.zremrangebyscore(bucket, 0, cutoff)
    current = await r.zcard(bucket)
    if current >= limit and principal.key_id != "bootstrap":
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(window_seconds - int(now) % window_seconds)},
        )

    await r.zadd(bucket, {str(now): now})
    await r.expire(bucket, window_seconds)
    return principal
