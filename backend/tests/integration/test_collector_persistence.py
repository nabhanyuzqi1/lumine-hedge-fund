# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 2 integration tests for collector persistence.

Verifies ticks and bars land in PostgreSQL and Redis as expected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from lumine.data.collector import Tick, build_bar, ingest_tick
from lumine.data.models import Bars1M
from lumine.data.models import Tick as TickModel
from lumine.data.persistence import persist_bar, persist_tick
from lumine.data.redis_client import get_recent_ticks

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def sample_tick() -> Tick:
    return Tick(
        ts=datetime(2026, 8, 3, 12, 0, 5, tzinfo=UTC),
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.10"),
        last=Decimal("2500.05"),
        volume=Decimal("1.5"),
        source="mt5",
    )


class TestPersistTick:
    """Tick → PostgreSQL + Redis buffer."""

    async def test_persist_tick_inserts_to_pg(
        self, db_session: AsyncSession, sample_tick: Tick
    ) -> None:
        await persist_tick(db_session, sample_tick)
        await db_session.flush()

        result = await db_session.execute(
            select(TickModel).where(
                TickModel.ts == sample_tick.ts,
                TickModel.symbol == sample_tick.symbol,
            )
        )
        row = result.scalar_one()
        assert row.last == Decimal("2500.05")
        assert row.volume == Decimal("1.5")
        assert row.source == "mt5"

    async def test_persist_tick_rejects_duplicate(
        self, db_session: AsyncSession, sample_tick: Tick
    ) -> None:
        await persist_tick(db_session, sample_tick)
        await db_session.flush()

        async def _insert_duplicate() -> None:
            await persist_tick(db_session, sample_tick)
            await db_session.flush()

        with pytest.raises(IntegrityError):
            await _insert_duplicate()

    @pytest.mark.usefixtures("redis_client")
    async def test_persist_tick_pushes_to_redis_buffer(
        self, db_session: AsyncSession, sample_tick: Tick
    ) -> None:
        await persist_tick(db_session, sample_tick, push_to_redis=True)
        await db_session.flush()

        recent = await get_recent_ticks("XAUUSD", count=1)
        assert len(recent) == 1
        assert recent[0]["last"] == "2500.05"
        assert recent[0]["symbol"] == "XAUUSD"


class TestPersistBar:
    """Bar → PostgreSQL bar table."""

    async def test_persist_bar_inserts_to_bars_1m(self, db_session: AsyncSession) -> None:
        state = {
            "ts": datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
            "open": Decimal("2500.00"),
            "high": Decimal("2501.00"),
            "low": Decimal("2499.00"),
            "close": Decimal("2500.50"),
            "volume": Decimal("10.0"),
            "source": "mt5",
        }
        bar = build_bar("XAUUSD", state)
        await persist_bar(db_session, bar, Bars1M)
        await db_session.flush()

        result = await db_session.execute(
            select(Bars1M).where(
                Bars1M.ts == bar.ts,
                Bars1M.symbol == bar.symbol,
            )
        )
        row = result.scalar_one()
        assert row.open == Decimal("2500.00")
        assert row.high == Decimal("2501.00")
        assert row.low == Decimal("2499.00")
        assert row.close == Decimal("2500.50")
        assert row.volume == Decimal("10.0")

    async def test_persist_bar_rejects_duplicate(self, db_session: AsyncSession) -> None:
        state = {
            "ts": datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC),
            "open": Decimal("2500.00"),
            "high": Decimal("2501.00"),
            "low": Decimal("2499.00"),
            "close": Decimal("2500.50"),
            "volume": Decimal("10.0"),
            "source": "mt5",
        }
        bar = build_bar("XAUUSD", state)
        await persist_bar(db_session, bar, Bars1M)
        await db_session.flush()

        async def _insert_duplicate() -> None:
            await persist_bar(db_session, bar, Bars1M)
            await db_session.flush()

        with pytest.raises(IntegrityError):
            await _insert_duplicate()


class TestCollectorRoundTrip:
    """Full tick → bar → PG pipeline."""

    async def test_ticks_aggregate_into_bar_and_persist(self, db_session: AsyncSession) -> None:
        timeframe_s = 60
        start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
        state: dict = {}
        for i in range(3):
            tick = Tick(
                ts=start.replace(second=10 * i),
                symbol="XAUUSD",
                bid=Decimal(str(2500.00 + i)),
                ask=Decimal(str(2500.10 + i)),
                last=Decimal(str(2500.05 + i)),
                volume=Decimal("1.0"),
                source="mt5",
            )
            bar = ingest_tick(state, tick, timeframe_s=timeframe_s)
            await persist_tick(db_session, tick)
            if bar is not None:
                await persist_bar(db_session, bar, Bars1M)

        # Cross the boundary to emit the 12:00 bar.
        boundary_tick = Tick(
            ts=start.replace(minute=1),
            symbol="XAUUSD",
            bid=Decimal("2505.00"),
            ask=Decimal("2505.10"),
            last=Decimal("2505.05"),
            volume=Decimal("1.0"),
            source="mt5",
        )
        bar = ingest_tick(state, boundary_tick, timeframe_s=timeframe_s)
        await persist_tick(db_session, boundary_tick)
        if bar is not None:
            await persist_bar(db_session, bar, Bars1M)

        await db_session.flush()

        result = await db_session.execute(
            select(Bars1M).where(
                Bars1M.ts == start,
                Bars1M.symbol == "XAUUSD",
            )
        )
        row = result.scalar_one()
        assert row.open == Decimal("2500.05")
        assert row.high == Decimal("2502.05")
        assert row.low == Decimal("2500.05")
        assert row.close == Decimal("2502.05")
        assert row.volume == Decimal("3.0")

        # 4 ticks persisted
        count_result = await db_session.execute(
            text("SELECT COUNT(*) FROM ticks WHERE symbol = 'XAUUSD'")
        )
        assert count_result.scalar() == 4
