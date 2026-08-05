# Copyright (c) 2026 Lumine. All rights reserved.
"""Execution router — dedup gates then dispatch to MT5 (D8-9, D3-7, D3-10).

Dispatch order is fixed (D3-10):

1. **Lineage-level dedup** (D3-7): if ``processed_commands`` already has
   a row for this ``lineage_id``, the decision was fully processed —
   return the stored result and skip everything (no Redis publish, no
   order). This makes replay idempotent at the decision granularity.
2. **Order-level idempotency** (D8-9): atomic ``SET NX order_id:attempt
   EX 3600`` guards against duplicate dispatches of the same order
   within the retry window.
3. **Dispatch**: ``LPUSH`` the command and await its result (30s, via
   the bridge client). No auto-retry — a rejected/failed result stays
   failed; FAILED never silently becomes anything else.
4. **Record**: insert the ``processed_commands`` row so later replays
   short-circuit at step 1.

The router is deterministic and DB/Redis/bridge I/O only — no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from lumine.bridge.client import BridgeClient, BridgeTimeoutError
from lumine.data.models import ProcessedCommand
from lumine.shared.errors import ExecutionError, IdempotencyError

if TYPE_CHECKING:
    import uuid

    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.bridge.types import BridgeCommand, BridgeResult

_DEDUP_TTL_S = 3600  # D8-9: order idempotency window


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one dispatch attempt (or a replay of a prior one)."""

    status: str
    ticket: int | None = None
    fill_price: Decimal | None = None
    replayed: bool = False


class ExecutionRouter:
    """Dispatch commands through the MT5 bridge with both dedup gates."""

    def __init__(
        self,
        *,
        redis: aioredis.Redis,
        bridge: BridgeClient,
    ) -> None:
        """Configure the router with injected Redis + bridge client."""
        self._redis = redis
        self._bridge = bridge

    @staticmethod
    def _dedup_key(order_id: str, attempt: int) -> str:
        return f"mt5:dedup:{order_id}:{attempt}"

    async def dispatch(
        self,
        session: AsyncSession,
        *,
        lineage_id: uuid.UUID,
        command: BridgeCommand,
        attempt: int = 1,
    ) -> DispatchResult:
        """Dispatch ``command`` once; returns the result (or replay)."""
        # 1. Lineage-level dedup (D3-7): whole decision already processed.
        existing = await session.get(ProcessedCommand, lineage_id)
        if existing is not None:
            return DispatchResult(status=existing.result, replayed=True)

        # 2. Order-level idempotency (D8-9): atomic claim within the window.
        claimed = await self._redis.set(
            self._dedup_key(command.order_id or command.command_id, attempt),
            "1",
            nx=True,
            ex=_DEDUP_TTL_S,
        )
        if not claimed:
            message = (
                f"duplicate dispatch for {command.order_id or command.command_id} "
                f"attempt {attempt} within {_DEDUP_TTL_S}s window"
            )
            raise IdempotencyError(message)

        # 3. Dispatch and await the fill/verdict (no auto-retry).
        try:
            result: BridgeResult = await self._bridge.send_and_wait(command)
        except BridgeTimeoutError as exc:
            message = f"no bridge result for {command.command_id}: {exc}"
            raise ExecutionError(message) from exc

        # 4. Persist the processed marker for future replays.
        session.add(
            ProcessedCommand(
                lineage_id=lineage_id,
                result=result.status.value,
                replay_count=0,
            )
        )
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            message = f"failed to persist processed command for {lineage_id}: {exc}"
            raise ExecutionError(message) from exc

        return DispatchResult(
            status=result.status.value,
            ticket=result.ticket,
            fill_price=(
                Decimal(str(result.fill_price)) if result.fill_price is not None else None
            ),
        )


__all__ = ("DispatchResult", "ExecutionRouter")
