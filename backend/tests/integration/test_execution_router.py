# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 3 integration tests for the execution router (D8-9, D3-7, D3-10).

Redis is real (testcontainers); the MT5 EA is simulated with a fake
bridge that records dispatched commands and returns scripted fills.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from lumine.bridge.client import BridgeClient
from lumine.bridge.types import BridgeCommand, BridgeResult, BridgeStatus
from lumine.data.models import ProcessedCommand
from lumine.shared.errors import IdempotencyError
from lumine.trade_core.execution_router import ExecutionRouter
from tests.integration.factories import seed_lineage


class FakeBridge(BridgeClient):
    """Substitute bridge: records commands, returns a scripted fill."""

    def __init__(self, result: BridgeResult | None = None) -> None:
        """Record dispatched commands; return ``result`` (or a default fill)."""
        self.calls: list[BridgeCommand] = []
        self._result = result or BridgeResult(
            command_id="x",
            status=BridgeStatus.FILLED,
            ticket=1001,
            fill_price=2734.5,
            fill_volume=2.5,
        )

    async def send_and_wait(self, command: BridgeCommand) -> BridgeResult:
        self.calls.append(command)
        return self._result


def _command(order_id: str) -> BridgeCommand:
    return BridgeCommand(
        command_id=f"cmd-{order_id}",
        order_id=order_id,
        action="BUY",
        symbol="XAUUSD",
        volume=2.5,
        stop_loss=2720.0,
    )


class TestExecutionRouter:
    async def test_fresh_dispatch_calls_bridge_and_records(
        self, db_session, redis_client  # type: ignore[no-untyped-def]  # noqa: ANN001
    ) -> None:
        bridge = FakeBridge()
        router = ExecutionRouter(redis=redis_client, bridge=bridge)
        lineage = await seed_lineage(db_session)
        lineage_id = lineage.lineage_id

        result = await router.dispatch(
            db_session, lineage_id=lineage_id, command=_command("o-1")
        )

        assert result.status == "filled"
        assert result.ticket == 1001
        assert result.replayed is False
        assert len(bridge.calls) == 1
        # The processed marker is durably recorded.
        stmt = select(ProcessedCommand).where(
            ProcessedCommand.lineage_id == lineage_id
        )
        row = (await db_session.execute(stmt)).scalar_one()
        assert row.result == "filled"

    async def test_replay_short_circuits_without_bridge(
        self, db_session, redis_client  # type: ignore[no-untyped-def]  # noqa: ANN001
    ) -> None:
        bridge = FakeBridge()
        router = ExecutionRouter(redis=redis_client, bridge=bridge)
        lineage = await seed_lineage(db_session)
        lineage_id = lineage.lineage_id

        await router.dispatch(db_session, lineage_id=lineage_id, command=_command("o-2"))
        replay = await router.dispatch(
            db_session, lineage_id=lineage_id, command=_command("o-2")
        )

        assert replay.replayed is True
        assert replay.status == "filled"
        assert len(bridge.calls) == 1  # the replay never touched the bridge

    async def test_order_idempotency_rejects_second_attempt(
        self, db_session, redis_client  # type: ignore[no-untyped-def]  # noqa: ANN001
    ) -> None:
        bridge = FakeBridge()
        router = ExecutionRouter(redis=redis_client, bridge=bridge)
        first = await seed_lineage(db_session)
        second = await seed_lineage(db_session)

        await router.dispatch(
            db_session, lineage_id=first.lineage_id, command=_command("o-3"), attempt=1
        )
        # Same order, different lineage → lineage dedup passes, order-level
        # SET NX (D8-9) rejects within the 3600s window.
        with pytest.raises(IdempotencyError):
            await router.dispatch(
                db_session, lineage_id=second.lineage_id, command=_command("o-3"), attempt=1
            )
        assert len(bridge.calls) == 1

    async def test_different_attempt_is_a_distinct_dispatch(
        self, db_session, redis_client  # type: ignore[no-untyped-def]  # noqa: ANN001
    ) -> None:
        bridge = FakeBridge()
        router = ExecutionRouter(redis=redis_client, bridge=bridge)
        first = await seed_lineage(db_session)
        second = await seed_lineage(db_session)

        await router.dispatch(
            db_session, lineage_id=first.lineage_id, command=_command("o-4"), attempt=1
        )
        # attempt=2 is a new key → allowed by D8-9.
        await router.dispatch(
            db_session, lineage_id=second.lineage_id, command=_command("o-4"), attempt=2
        )
        assert len(bridge.calls) == 2
