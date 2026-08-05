# Copyright (c) 2026 Lumine. All rights reserved.
"""Factories to seed versioned-registry rows for integration tests.

Each factory commits its row(s) and returns the created ORM objects, so
callers get ``id`` values they can use in FKs. Idempotent-ish within a
test because the container DB is session-scoped; callers should rely on
unique ``version`` strings (or a fresh DB per run, as the test schema
reset provides).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from lumine.data.lineage import LineageInputs, write_lineage
from lumine.data.models import (
    LineageRecord,
    ModelVersion,
    PolicyVersion,
    PromptVersion,
    StrategyVersion,
)

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession


async def seed_model(
    session: AsyncSession,
    *,
    version: str | None = None,
    provider: str = "deepseek",
    model_id: str = "deepseek-v4",
    tier: str = "cost-efficient",
    status: str = "production",
) -> ModelVersion:
    """Create and commit a ``model_versions`` row; return it."""
    row = ModelVersion(
        version=version or f"m-{uuid.uuid4().hex[:8]}",
        status=status,
        provider=provider,
        model_id=model_id,
        tier=tier,
        context_window=128000,
        params={"temperature": 0.2},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def seed_prompt(
    session: AsyncSession,
    *,
    version: str | None = None,
    sub_role: str = "technical_analyst",
    status: str = "production",
) -> PromptVersion:
    """Create and commit a ``prompt_versions`` row; return it."""
    row = PromptVersion(
        version=version or f"p-{uuid.uuid4().hex[:8]}",
        status=status,
        sub_role=sub_role,
        prompt_hash="a" * 64,
        prompt_ref=f"{sub_role}@v1.prompt",
        variables={},
        output_schema={},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def seed_strategy(
    session: AsyncSession,
    *,
    version: str | None = None,
    book: str = "main",
    status: str = "production",
) -> StrategyVersion:
    """Create and commit a ``strategy_versions`` row; return it."""
    row = StrategyVersion(
        version=version or f"s-{uuid.uuid4().hex[:8]}",
        status=status,
        name="trend-follow",
        book=book,
        params={},
        entry_rules={},
        exit_rules={},
        source="integration-test",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def seed_policy(
    session: AsyncSession,
    *,
    version: str | None = None,
    policy: dict[str, Any] | None = None,
    status: str = "production",
) -> PolicyVersion:
    """Create and commit a ``policy_versions`` row; return it."""
    row = PolicyVersion(
        version=version or f"pol-{uuid.uuid4().hex[:8]}",
        status=status,
        scope="XAUUSD",
        policy_hash="b" * 64,
        policy=policy if policy is not None else {},
        effective_from=__import__("datetime").datetime(2026, 1, 1),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def seed_lineage(
    session: AsyncSession,
    *,
    book: str = "main",
    symbol: str = "XAUUSD",
    side: str = "BUY",
    verdict: str = "approved",
    size: Decimal | None = None,
) -> LineageRecord:
    """Seed strategy + policy rows and write a real lineage record; return it.

    Execution-router tests need a lineage row that actually exists,
    because ``processed_commands.lineage_id`` is a hard FK (D3-7): a
    command may only be marked processed for a real decision.
    """
    strategy = await seed_strategy(session, book=book)
    policy = await seed_policy(session)
    return await write_lineage(
        session,
        LineageInputs(
            book=book,
            strategy_id=strategy.id,
            symbol=symbol,
            side=side,
            verdict=verdict,
            size=size,
            fill_price=None,
            model_version_ids={"technical_analyst": str(uuid.uuid4())},
            prompt_version_ids={"technical_analyst": str(uuid.uuid4())},
            policy_version_id=policy.id,
            strategy_version_id=strategy.id,
            proposal={"version": "v1", "action": side},
            risk_context={"violations": []},
        ),
    )


__all__ = ("seed_lineage", "seed_model", "seed_policy", "seed_prompt", "seed_strategy")
