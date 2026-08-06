# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 2 integration tests: ``llm_usage`` persistence + spend aggregation.

Verifies D6-7 against the real Postgres container: every gateway call
lands exactly one append-only ``llm_usage`` row, FK violations surface
as ``LLMUsageRecordError``, and ``spend_by_tier`` aggregates today's
per-tier spend from the table (single source of truth for the budget
gate). Requires the migrations (0001-0006) applied via the conftest
``_applied_migrations`` fixture.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from lumine.data.models import (
    LineageRecord,
    LLMUsage,
    ModelVersion,
    PolicyVersion,
    StrategyVersion,
)
from lumine.llm_gateway.budget import spend_by_tier
from lumine.llm_gateway.types import (
    ChatMessage,
    GatewayResponse,
    ModelTier,
    RouterRequest,
)
from lumine.llm_gateway.usage import write_usage
from lumine.shared.errors import LLMUsageRecordError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PRICE_IN = Decimal("0.500000")  # $ per 1k input tokens
PRICE_OUT = Decimal("2.000000")  # $ per 1k output tokens


# ── seeds ─────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _seed_registry(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    """Insert the FK chain every llm_usage row depends on.

    model_versions ← llm_usage.model_version_id
    strategy_versions → policy_versions → lineage_records ← llm_usage.lineage_id
    """
    model = ModelVersion(
        id=uuid.uuid4(),
        version="ds-v4-test",
        status="production",
        provider="deepseek",
        model_id="deepseek-v4",
        tier="cost-efficient",
        context_window=128000,
        params={},
    )
    strategy = StrategyVersion(
        id=uuid.uuid4(),
        version="gold-v1-test",
        status="production",
        name="XAUUSD momentum",
        book="gold",
        params={},
        entry_rules={},
        exit_rules={},
        source="seed",
    )
    policy = PolicyVersion(
        id=uuid.uuid4(),
        version="p-2026-08-05-test",
        status="production",
        scope="XAUUSD",
        policy_hash="a" * 64,
        policy={},
        effective_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    lineage = LineageRecord(
        lineage_id=uuid.uuid4(),
        decision_ts=datetime(2026, 8, 5, 9, 0, tzinfo=UTC),
        book="gold",
        strategy_id=strategy.id,
        symbol="XAUUSD",
        side="LONG",
        verdict="BUY",
        model_version_ids={"technical_analyst": str(model.id)},
        prompt_version_ids={},
        policy_version_id=policy.id,
        strategy_version_id=strategy.id,
        trigger={"type": "test"},
        proposal={"version": "v1", "action": "HOLD"},
        risk_context={"violations": []},
    )
    # Flush the FK parents first: without relationship() edges the unit
    # of work does not reorder plain-FK inserts, so lineage must come
    # after its referenced rows are durable in this transaction.
    db_session.add_all([model, strategy, policy])
    await db_session.flush()
    db_session.add(lineage)
    await db_session.flush()
    return {
        "model_version_id": model.id,
        "lineage_id": lineage.lineage_id,
    }


def _req(*, lineage_id: uuid.UUID, model_version_id: uuid.UUID) -> RouterRequest:
    return RouterRequest(
        model_version_id=model_version_id,
        role="technical_analyst",
        tier=ModelTier.COST_EFFICIENT,
        lineage_id=lineage_id,
        prompt_ref="technical_analyst@v1.prompt",
        prompt_hash="a" * 64,
        idempotency_key=f"idem-{uuid.uuid4()}",
        messages=[ChatMessage(role="user", content="Symbol: XAUUSD")],
    )


def _resp(*, model: str = "deepseek-v4") -> GatewayResponse:
    return GatewayResponse(
        content='{"action": "HOLD"}',
        model_used=model,
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
    )


# ── persistence ───────────────────────────────────────────────────────────────


class TestUsagePersistence:
    """write_usage appends one complete llm_usage row."""

    async def test_write_usage_persists_full_row(
        self, db_session: AsyncSession, _seed_registry: dict[str, uuid.UUID]
    ) -> None:
        request = _req(**_seed_registry)
        response = _resp()

        usage = await write_usage(
            db_session,
            request=request,
            response=response,
            prompt_version_id=None,
            price_per_1k_in=PRICE_IN,
            price_per_1k_out=PRICE_OUT,
            fallback_hops=1,
            degraded=True,
            lane="live",
        )

        # flush happened inside write_usage → id/ts are populated
        assert usage.id is not None
        assert usage.ts is not None
        assert usage.role == "technical_analyst"
        assert usage.tier == "cost-efficient"
        assert usage.model_version_id == _seed_registry["model_version_id"]
        assert usage.tokens_in == 1000
        assert usage.tokens_out == 500
        # 1000 in @ 0.5/1k + 500 out @ 2.0/1k = 0.50 + 1.00
        assert usage.cost_usd == Decimal("1.500000")
        assert usage.fallback_hops == 1
        assert usage.degraded is True
        assert usage.lane == "live"
        assert usage.lineage_id == _seed_registry["lineage_id"]

    async def test_write_usage_is_append_only(
        self, db_session: AsyncSession, _seed_registry: dict[str, uuid.UUID]
    ) -> None:
        request = _req(**_seed_registry)
        first = await write_usage(
            db_session,
            request=request,
            response=_resp(),
            price_per_1k_in=PRICE_IN,
            price_per_1k_out=PRICE_OUT,
        )
        second = await write_usage(
            db_session,
            request=request,
            response=_resp(),
            price_per_1k_in=PRICE_IN,
            price_per_1k_out=PRICE_OUT,
        )
        assert second.id != first.id

        result = await db_session.execute(select(LLMUsage))
        rows = result.scalars().all()
        assert len(rows) == 2

    async def test_unknown_model_version_raises_record_error(
        self, db_session: AsyncSession, _seed_registry: dict[str, uuid.UUID]
    ) -> None:
        request = _req(
            lineage_id=_seed_registry["lineage_id"],
            model_version_id=uuid.uuid4(),  # no FK target
        )
        with pytest.raises(LLMUsageRecordError):
            await write_usage(
                db_session,
                request=request,
                response=_resp(),
                price_per_1k_in=PRICE_IN,
                price_per_1k_out=PRICE_OUT,
            )


# ── spend aggregation ─────────────────────────────────────────────────────────


class TestSpendByTier:
    """spend_by_tier derives today's per-tier spend from llm_usage."""

    async def test_aggregates_per_tier(
        self, db_session: AsyncSession, _seed_registry: dict[str, uuid.UUID]
    ) -> None:
        ce = _req(**_seed_registry)
        cr = _req(**_seed_registry).model_copy(
            update={"role": "ic_forum", "tier": ModelTier.CONTEXT_RICH}
        )
        await write_usage(
            db_session,
            request=ce,
            response=_resp(),
            price_per_1k_in=PRICE_IN,
            price_per_1k_out=PRICE_OUT,
        )
        await write_usage(
            db_session,
            request=ce,
            response=_resp(),
            price_per_1k_in=PRICE_IN,
            price_per_1k_out=PRICE_OUT,
        )
        await write_usage(
            db_session,
            request=cr,
            response=_resp(),
            price_per_1k_in=Decimal("1.000000"),
            price_per_1k_out=Decimal("4.000000"),
        )

        spend = await spend_by_tier(db_session)

        # 2 rows @ 1.50 each = 3.00; 1 row @ 3.00
        assert spend["cost-efficient"] == pytest.approx(3.0)
        assert spend["context-rich"] == pytest.approx(3.0)

    async def test_empty_table_returns_empty_mapping(
        self, db_session: AsyncSession, _seed_registry: dict[str, uuid.UUID]
    ) -> None:
        assert await spend_by_tier(db_session) == {}
