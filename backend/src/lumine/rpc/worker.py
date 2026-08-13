# Copyright (c) 2026 Lumine. All rights reserved.
"""RPC command worker — Redis Streams consumer (B-04).

Consumes ``rpc:commands`` via the ``rpc-workers`` consumer group and
executes each command handler. Handlers are deterministic in demo mode
(no LLM gateway / storage wiring yet — same contract as demo_data.py);
``halt_trading``/``resume_trading`` operate the real Redis kill switch,
``cancel_order`` mirrors the orders router's demo cancel semantics.

Delivery: at-least-once (XACK after processing). Handlers are idempotent
per command_id (result already stored → skip).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from lumine.api.middleware.auth import AuthenticatedPrincipal  # noqa: F401  (re-exported for handlers)
from lumine.api.sse.publisher import SSEEvent, SSEPublisher
from lumine.data.redis_client import get_redis
from lumine.rpc.queue import GROUP, STREAM, get_result, set_result
from lumine.shared.config import Settings

logger = logging.getLogger(__name__)


async def _handle_run_decision_cycle(payload: dict[str, Any], publisher: SSEPublisher) -> dict[str, Any]:
    """Deterministic demo decision cycle (LLM gateway not wired in demo)."""
    symbol = payload.get("symbol", "XAUUSD")
    decision = payload.get("decision", "hold")
    result = {
        "run_id": "demo-run-" + symbol.lower(),
        "symbol": symbol,
        "decision": decision,
        "status": "completed",
        "finished_at": datetime.now(UTC).isoformat(),
    }
    await publisher.publish(
        SSEEvent(
            event_type="decision_cycle_completed",
            channel="ic-decisions",
            data=result,
        )
    )
    return result


async def _handle_halt_trading(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Arm the global kill switch (operational halt)."""
    r = await get_redis()
    await r.hset(
        settings.kill_switch_key,
        mapping={"armed": "1", "tier": "global", "reason": payload.get("reason", "rpc:halt-trading")},
    )
    return {"armed": True, "tier": "global"}


async def _handle_resume_trading(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Disarm the kill switch."""
    r = await get_redis()
    await r.hset(settings.kill_switch_key, mapping={"armed": "0", "reason": payload.get("reason", "rpc:resume-trading")})
    return {"armed": False}


async def _handle_cancel_order(payload: dict[str, Any], publisher: SSEPublisher) -> dict[str, Any]:
    """Demo cancel: mark the order cancelled and notify the orders channel."""
    order_id = payload.get("order_id", "unknown")
    result = {
        "order_id": order_id,
        "status": "cancelled",
        "cancelled_at": datetime.now(UTC).isoformat(),
    }
    await publisher.publish(
        SSEEvent(
            event_type="order_cancelled",
            channel="orders",
            data=result,
        )
    )
    return result


HANDLERS: dict[str, Any] = {
    "run_decision_cycle": _handle_run_decision_cycle,
    "halt_trading": _handle_halt_trading,
    "resume_trading": _handle_resume_trading,
    "cancel_order": _handle_cancel_order,
}


async def _process(
    command_id: str,
    command: str,
    payload: dict[str, Any],
    publisher: SSEPublisher,
    settings: Settings,
) -> None:
    existing = await get_result(command_id)
    if existing and existing.get("status") in {"completed", "failed"}:
        return  # idempotent redelivery
    try:
        handler = HANDLERS[command]
        if command in {"halt_trading", "resume_trading"}:
            result = await handler(payload, settings)  # type: ignore[arg-type]
        else:
            result = await handler(payload, publisher)  # type: ignore[arg-type]
        await set_result(command_id, "completed", result=result)
        logger.info("rpc %s %s completed", command, command_id)
    except Exception as exc:  # noqa: BLE001 — worker must not die on one bad command
        logger.exception("rpc %s %s failed", command, command_id)
        await set_result(command_id, "failed", error=str(exc))


async def run_worker(
    publisher: SSEPublisher,
    settings: Settings,
    *,
    consumer: str = "worker-1",
    block_ms: int = 2000,
) -> None:
    """Consume the rpc stream until cancelled (runs as a lifespan task)."""
    r = await get_redis()
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception:  # noqa: BLE001 — group already exists
        pass
    logger.info("rpc worker %s listening on %s", consumer, STREAM)
    while True:
        try:
            response = await r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=8, block=block_ms)
        except Exception:  # noqa: BLE001 — redis blips must not kill the worker
            await asyncio.sleep(1)
            continue
        for _stream, messages in response or []:
            for message_id, fields in messages:
                payload = json.loads(fields.get("payload", "{}"))
                await _process(fields["command_id"], fields["command"], payload, publisher, settings)
                await r.xack(STREAM, GROUP, message_id)
