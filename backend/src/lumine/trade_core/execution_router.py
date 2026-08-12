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

from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from lumine.bridge.client import BridgeClient, BridgeTimeoutError
from lumine.data.models import Fill, ProcessedCommand
from lumine.shared.errors import ExecutionError, IdempotencyError
from lumine.trade_core.tca import persist_tca

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

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


@dataclass(frozen=True)
class TcaDispatchContext:
    """Metadata required to persist a fill and its TCA record atomically."""

    strategy_id: uuid.UUID
    book: str
    regime_id: str
    broker_id: str
    account_id: str
    pip_value: Decimal
    pip_size: Decimal | None = None
    commission: Decimal = Decimal(0)
    decision_ts: datetime | None = None
    calendar: object | None = None


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
        tca_context: TcaDispatchContext | None = None,
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

        # 4. Persist fill + TCA + processed marker in one transaction when
        # execution metadata is available. Missing TCA metadata preserves the
        # existing router contract for callers that only need dispatch.
        try:
            if tca_context is not None and result.status.value in {"filled", "partial"}:
                if result.fill_price is None or result.fill_volume is None:
                    message = "filled bridge result is missing price or volume for TCA"
                    raise ExecutionError(message)  # noqa: TRY301
                fill = Fill(
                    lineage_id=lineage_id,
                    ts=result.timestamp,
                    symbol=command.symbol,
                    side=command.action,
                    size=Decimal(str(result.fill_volume)),
                    price=Decimal(str(result.fill_price)),
                    commission=tca_context.commission,
                    slippage=Decimal(0),
                    book=tca_context.book,
                    strategy_id=tca_context.strategy_id,
                )
                session.add(fill)
                await session.flush()
                await persist_tca(
                    session,
                    fill,
                    decision_ts=tca_context.decision_ts or command.timestamp,
                    regime_id=tca_context.regime_id,
                    broker_id=tca_context.broker_id,
                    account_id=tca_context.account_id,
                    pip_value=tca_context.pip_value,
                    pip_size=tca_context.pip_size,
                    calendar=tca_context.calendar,
                )

            # The claim is released when the caller-owned DB transaction fails;
            # retry must remain possible after benchmark or persistence errors.
            session.add(
                ProcessedCommand(
                    lineage_id=lineage_id,
                    result=result.status.value,
                    replay_count=0,
                )
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            with suppress(Exception):
                await self._redis.delete(
                    self._dedup_key(command.order_id or command.command_id, attempt)
                )
            message = f"failed to persist processed command for {lineage_id}: {exc}"
            raise ExecutionError(message) from exc

        return DispatchResult(
            status=result.status.value,
            ticket=result.ticket,
            fill_price=(Decimal(str(result.fill_price)) if result.fill_price is not None else None),
        )


__all__ = ("DispatchResult", "ExecutionRouter", "TcaDispatchContext")
