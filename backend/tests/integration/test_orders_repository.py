# Copyright (c) 2026 Lumine. All rights reserved.
"""Integration tests for OrderRepository / PositionRepository (B-05)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from lumine.data.models import LineageRecord, PolicyVersion, Position, StrategyVersion
from lumine.data.repositories import OrderRepository, PositionRepository


async def test_order_crud_roundtrip(db_session) -> None:  # type: ignore[no-untyped-def]
    """Create → list → modify → cancel persists across fresh queries."""
    repo = OrderRepository(db_session)
    order_id = uuid4()

    created = await repo.create(
        order_id=order_id,
        portfolio_id="default",
        symbol="XAUUSD",
        side="buy",
        order_type="limit",
        volume=Decimal("2.00"),
        price=Decimal("2450.00"),
    )
    assert created.status == "pending"
    assert created.filled_volume == Decimal(0)

    items, total = await repo.list()
    assert total >= 1
    assert items[0].order_id == order_id

    modified = await repo.modify(order_id, price=Decimal("2460.00"), volume=Decimal("1.50"))
    assert modified is not None
    assert modified.price == Decimal("2460.00")
    assert modified.volume == Decimal("1.50")

    cancelled = await repo.update_status(order_id, status="cancelled")
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    assert await repo.get(order_id) is not None
    assert await repo.get(uuid4()) is None


async def test_order_modify_rejects_non_pending(db_session) -> None:  # type: ignore[no-untyped-def]
    """PATCH contract: only pending orders are modifiable."""
    repo = OrderRepository(db_session)
    order_id = uuid4()
    await repo.create(
        order_id=order_id,
        portfolio_id="default",
        symbol="EURUSD",
        side="sell",
        order_type="market",
        volume=Decimal("1.00"),
    )
    await repo.update_status(order_id, status="filled")

    import pytest

    with pytest.raises(ValueError, match="only pending"):
        await repo.modify(order_id, price=Decimal("1.10"))


async def test_position_repository_exposure(db_session) -> None:  # type: ignore[no-untyped-def]
    """Exposure summary prices open positions with provided mids."""
    now = datetime.now(UTC)
    lineage_id = uuid4()
    strategy_id = uuid4()
    policy_id = uuid4()
    db_session.add(
        StrategyVersion(
            id=strategy_id,
            version="v1",
            status="sandbox",
            name="test-strategy",
            book="default",
            params={},
            entry_rules={},
            exit_rules={},
            source="test",
        )
    )
    db_session.add(
        PolicyVersion(
            id=policy_id,
            version="v1",
            status="sandbox",
            scope="XAUUSD",
            policy_hash="a" * 64,
            policy={},
            effective_from=now,
        )
    )
    # Flush FK parents first: plain-FK inserts are not reordered by the UoW.
    await db_session.flush()
    db_session.add(
        LineageRecord(
            lineage_id=lineage_id,
            decision_ts=now,
            book="default",
            strategy_id=strategy_id,
            symbol="XAUUSD",
            side="LONG",
            verdict="BUY",
            model_version_ids={},
            prompt_version_ids={},
            policy_version_id=policy_id,
            strategy_version_id=strategy_id,
            trigger={"type": "test"},
            proposal={"version": "v1", "action": "BUY"},
            risk_context={"violations": []},
            prev_hash="0" * 64,
            self_hash="1" * 64,
            canonicalization_version=1,
        )
    )
    await db_session.flush()
    for symbol, size in (("XAUUSD", Decimal(2)), ("EURUSD", Decimal(-100000))):
        db_session.add(
            Position(
                position_id=uuid4(),
                symbol=symbol,
                book="default",
                strategy_id=uuid4(),
                side="LONG" if size > 0 else "SHORT",
                size=size,
                avg_entry=Decimal(2450),
                opened_at=now,
                opened_lineage=lineage_id,
                status="open",
            )
        )
    await db_session.commit()

    repo = PositionRepository(db_session)
    summary = await repo.exposure_summary(
        mid_prices={"XAUUSD": Decimal(2500), "EURUSD": Decimal("1.10")}
    )
    assert summary["position_count"] == 2
    assert summary["symbols"] == ["EURUSD", "XAUUSD"]
    assert Decimal(summary["gross_exposure"]) == Decimal(115000)
