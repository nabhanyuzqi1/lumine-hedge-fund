# Copyright (c) 2026 Lumine. All rights reserved.
"""RPC command queue — Redis Streams producer (B-04).

Commands are appended to the ``rpc:commands`` stream; the worker
(``lumine.rpc.worker``) consumes them with a consumer group so every
command is processed exactly-once-per-attempt (at-least-once delivery,
XACK after processing). Results are stored under ``rpc:results:{id}``
(24h TTL) and surfaced via ``GET /api/v1/rpc/commands/{command_id}``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from lumine.data.redis_client import get_redis

STREAM = "rpc:commands"
GROUP = "rpc-workers"
RESULT_TTL_SECONDS = 24 * 60 * 60

_RECEIPT_PREFIX = "rpc:receipts:"
_RESULT_PREFIX = "rpc:results:"


async def enqueue_command(command: str, payload: dict[str, Any] | None = None) -> str:
    """Append a command to the stream and return its command_id."""
    command_id = str(uuid4())
    now = datetime.now(UTC)
    fields = {
        "command_id": command_id,
        "command": command,
        "payload": json.dumps(payload or {}),
        "enqueued_at": now.isoformat(),
    }
    r = await get_redis()
    await r.xadd(STREAM, fields)
    await r.hset(
        _RECEIPT_PREFIX + command_id,
        mapping={"command": command, "status": "queued", "enqueued_at": now.isoformat()},
    )
    await r.expire(_RECEIPT_PREFIX + command_id, RESULT_TTL_SECONDS)
    return command_id


async def set_result(command_id: str, status: str, result: Any = None, error: str | None = None, command: str | None = None) -> None:
    """Store the worker outcome for a command id."""
    r = await get_redis()
    record = {
        "command_id": command_id,
        "command": command,
        "status": status,
        "result": result,  # nested JSON serializes fine via json.dumps(record)
        "error": error,
        "processed_at": datetime.now(UTC).isoformat(),
    }
    await r.set(_RESULT_PREFIX + command_id, json.dumps(record), ex=RESULT_TTL_SECONDS)
    await r.hset(_RECEIPT_PREFIX + command_id, mapping={"status": status})


async def get_result(command_id: str) -> dict[str, Any] | None:
    """Return the stored result for a command id, or None."""
    r = await get_redis()
    raw = await r.get(_RESULT_PREFIX + command_id)
    if raw is None:
        # No result yet — fall back to the receipt (queued/processing).
        # redis-py returns hash fields as bytes — decode keys/values.
        receipt_raw = await r.hgetall(_RECEIPT_PREFIX + command_id)
        if not receipt_raw:
            return None
        receipt = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in receipt_raw.items()
        }
        return {
            "command_id": command_id,
            "command": receipt.get("command", "unknown"),
            "status": receipt.get("status", "queued"),
            "result": None,
            "error": None,
            "enqueued_at": receipt.get("enqueued_at"),
            "processed_at": None,
        }
    return json.loads(raw)
