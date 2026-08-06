# Copyright (c) 2026 Lumine. All rights reserved.
"""Redis client with connection pool.

Follows Phase 5 redis-roles.md: one instance, AOF everysec, volatile-lru
eviction. Provides typed helpers for the command queue, pub/sub, feature
cache, and snapshot cache namespaces.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from lumine.shared.config import get_settings

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the singleton async Redis client. Lazy-creates the pool."""
    global _pool, _client
    if _client is None:
        settings = get_settings()
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_pool_size,
        )
        _client = aioredis.Redis.from_pool(_pool)
    return _client


async def close_redis() -> None:
    """Close the Redis connection pool. Called on shutdown."""
    global _pool, _client
    if _client is not None:
        await _client.aclose()
        _client = None
        _pool = None


# ── Command queue ────────────────────────────────────────────────────────────


async def push_command(payload: dict[str, Any]) -> None:
    """Push a command to the MT5 command queue (Redis LIST, LPUSH)."""
    r = await get_redis()
    settings = get_settings()
    await r.lpush(settings.mt5_command_channel, json.dumps(payload))


async def pop_command(timeout: float = 0) -> str | None:
    """Blocking pop from the MT5 command queue (Redis LIST, BRPOP).

    Returns the raw JSON string or None on timeout.
    """
    r = await get_redis()
    settings = get_settings()
    result = await r.brpop(settings.mt5_command_channel, timeout=timeout)
    if result is None:
        return None
    _, value = result
    return value.decode() if isinstance(value, bytes) else value


# ── Results pub/sub ──────────────────────────────────────────────────────────


async def publish_result(payload: dict[str, Any]) -> None:
    """Publish a result to the MT5 results channel."""
    r = await get_redis()
    settings = get_settings()
    await r.publish(settings.mt5_result_channel, json.dumps(payload))


async def subscribe_results() -> aioredis.client.PubSub:
    """Subscribe to the MT5 results channel. Returns a PubSub object."""
    r = await get_redis()
    settings = get_settings()
    pubsub = r.pubsub()
    await pubsub.subscribe(settings.mt5_result_channel)
    return pubsub


# ── Feature cache ────────────────────────────────────────────────────────────


async def cache_feature(
    symbol: str,
    name: str,
    value: float | dict[str, Any],
    ttl: int = 60,
) -> None:
    """Cache a feature value under feat:{symbol}:{name} with TTL."""
    r = await get_redis()
    key = f"feat:{symbol}:{name}"
    if isinstance(value, dict):
        await r.setex(key, ttl, json.dumps(value))
    else:
        await r.setex(key, ttl, str(value))


async def get_cached_feature(symbol: str, name: str) -> float | dict[str, Any] | None:
    """Get a cached feature value. Returns None on miss."""
    r = await get_redis()
    key = f"feat:{symbol}:{name}"
    raw = await r.get(key)
    if raw is None:
        return None
    decoded = raw.decode() if isinstance(raw, bytes) else raw
    try:
        return json.loads(decoded)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return float(decoded)


# ── Snapshot cache ───────────────────────────────────────────────────────────


async def cache_snapshot(kind: str, data: dict[str, Any], ttl: int = 5) -> None:
    """Cache a snapshot under snap:{kind} with TTL."""
    r = await get_redis()
    key = f"snap:{kind}"
    await r.setex(key, ttl, json.dumps(data))


async def get_cached_snapshot(kind: str) -> dict[str, Any] | None:
    """Get a cached snapshot. Returns None on miss."""
    r = await get_redis()
    key = f"snap:{kind}"
    raw = await r.get(key)
    if raw is None:
        return None
    decoded = raw.decode() if isinstance(raw, bytes) else raw
    return json.loads(decoded)  # type: ignore[no-any-return]


# ── Tick circular buffer ─────────────────────────────────────────────────────


async def push_tick(symbol: str, tick_data: dict[str, Any], maxlen: int = 1000) -> None:
    """Push a tick to the circular buffer for a symbol."""
    r = await get_redis()
    key = f"ticks:{symbol}"
    await r.lpush(key, json.dumps(tick_data))
    await r.ltrim(key, 0, maxlen - 1)


async def get_recent_ticks(symbol: str, count: int = 100) -> list[dict[str, Any]]:
    """Get the most recent N ticks for a symbol."""
    r = await get_redis()
    key = f"ticks:{symbol}"
    raw = await r.lrange(key, 0, count - 1)
    return [json.loads(item.decode() if isinstance(item, bytes) else item) for item in raw]


# ── Dedup helpers ────────────────────────────────────────────────────────────


async def check_dedup(order_id: str, attempt: int) -> bool:
    """Check if an order_id:attempt was already processed. Returns True if duplicate."""
    r = await get_redis()
    key = f"mt5:dedup:{order_id}:{attempt}"
    return bool(await r.exists(key))


async def set_dedup(order_id: str, attempt: int, ttl: int = 3600) -> None:
    """Mark an order_id:attempt as processed."""
    r = await get_redis()
    key = f"mt5:dedup:{order_id}:{attempt}"
    await r.setex(key, ttl, "1")
