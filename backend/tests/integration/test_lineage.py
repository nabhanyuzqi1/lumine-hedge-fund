# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 3 integration tests for the lineage writer (D3-7)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import select

from lumine.data.lineage import LineageInputs, LineageWriteError, write_lineage
from lumine.data.models import LineageRecord, PolicyVersion, StrategyVersion
from tests.integration.factories import seed_policy, seed_strategy

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_SYMBOL = "XAUUSD"


@pytest_asyncio.fixture
async def _registry_rows(db_session: AsyncSession) -> tuple[StrategyVersion, PolicyVersion]:
    """Seed the strategy + policy rows the lineage record FK-references."""
    strategy = await seed_strategy(db_session)
    policy = await seed_policy(
        db_session,
        policy={"debate": {"min_confidence": 0.6}, "risk_adjustments": {}},
    )
    return strategy, policy


def _inputs(
    strategy_id: uuid.UUID,
    policy_version_id: uuid.UUID,
    **overrides: object,
) -> LineageInputs:
    base = {
        "book": "main",
        "strategy_id": strategy_id,
        "symbol": _SYMBOL,
        "side": "BUY",
        "verdict": "approved",
        "size": Decimal("2.50"),
        "fill_price": None,
        "model_version_ids": {"technical_analyst": str(uuid.uuid4())},
        "prompt_version_ids": {"technical_analyst": str(uuid.uuid4())},
        "policy_version_id": policy_version_id,
        "strategy_version_id": strategy_id,
        "trigger": {"type": "atr_breakout"},
        "features": {"atr_14": 15.0},
        "proposal": {"version": "v1", "action": "BUY"},
        "risk_context": {"per_trade_exposure": 0.01, "veto": False},
    }
    base.update(overrides)
    return LineageInputs(**base)  # type: ignore[arg-type]


class TestLineageWriter:
    async def test_write_lineage_persists_all_pins(
        self,
        db_session,  # type: ignore[no-untyped-def]
        _registry_rows,  # type: ignore[no-untyped-def]
    ) -> None:
        strategy, policy = _registry_rows
        record = await write_lineage(db_session, _inputs(strategy.id, policy.id))

        assert record.lineage_id is not None
        assert record.symbol == _SYMBOL
        assert record.side == "BUY"
        assert record.verdict == "approved"
        assert record.size == Decimal("2.50")
        assert record.proposal["version"] == "v1"
        assert record.risk_context["veto"] is False
        assert "technical_analyst" in record.model_version_ids
        assert "technical_analyst" in record.prompt_version_ids

        # Prove durability from a fresh query.
        stmt = select(LineageRecord).where(LineageRecord.lineage_id == record.lineage_id)
        persisted = (await db_session.execute(stmt)).scalar_one()
        assert persisted.book == "main"

    async def test_commit_failure_raises_and_records_nothing(
        self,
        db_session,  # type: ignore[no-untyped-def]
        _registry_rows,  # type: ignore[no-untyped-def]
    ) -> None:
        strategy, _policy = _registry_rows
        # A bogus policy_version_id → FK violation on commit.
        bogus = uuid.uuid4()
        inputs = _inputs(strategy.id, bogus)

        with pytest.raises(LineageWriteError):
            await write_lineage(db_session, inputs)

        # write-before-dispatch: a failed write must not leave a partial
        # decision behind that could later dispatch.
        stmt = select(LineageRecord).where(LineageRecord.symbol == _SYMBOL)
        rows = (await db_session.execute(stmt)).scalars().all()
        assert all(row.policy_version_id != bogus for row in rows)

    async def test_append_only_by_construction(
        self,
        db_session,  # type: ignore[no-untyped-def]
        _registry_rows,  # type: ignore[no-untyped-def]
    ) -> None:
        strategy, policy = _registry_rows
        first = await write_lineage(db_session, _inputs(strategy.id, policy.id))
        second = await write_lineage(db_session, _inputs(strategy.id, policy.id))
        assert first.lineage_id != second.lineage_id
