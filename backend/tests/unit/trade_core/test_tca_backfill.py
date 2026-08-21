# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for historical TCA backfill (gap B-08)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from lumine.data.models import Fill
from lumine.trade_core.tca_backfill import backfill_missing_tca


def _make_fill(symbol: str = "XAUUSD", ts=None) -> Fill:
    return Fill(
        lineage_id=uuid4(),
        ts=ts or datetime.now(UTC),
        symbol=symbol,
        side="BUY",
        size=Decimal("1.0"),
        price=Decimal("2750.10"),
        commission=Decimal(0),
        slippage=Decimal(0),
        book="default",
        strategy_id=uuid4(),
    )


def _session_returning(fills):
    """AsyncMock session whose execute() returns the given fills."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = fills
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    return session


class TestBackfillMissingTca:
    @pytest.mark.asyncio
    async def test_backfills_fill_without_tca(self):
        fill = _make_fill()
        session = _session_returning([fill])

        with patch("lumine.trade_core.tca_backfill.resolve_benchmark") as mock_resolve:
            bench = MagicMock()
            bench.price = Decimal("2750.00")
            bench.ts = fill.ts
            bench.source = "arrival_mid"
            mock_resolve.return_value = bench

            stats = await backfill_missing_tca(
                session,
                regime_id="backfill",
                broker_id="broker_1",
                account_id="acc_1",
                pip_value=Decimal(10),
            )

        assert stats.scanned == 1
        assert stats.backfilled == 1
        assert stats.skipped_no_tick == 0
        # TcaRecord ditambahkan ke session dengan provenance backfill
        added = session.add.call_args_list[-1].args[0]
        assert added.fill_id == fill.fill_id
        assert added.regime_id == "backfill"
        assert added.benchmark_source == "backfill:arrival_mid"
        assert added.decision_ts == fill.ts

    @pytest.mark.asyncio
    async def test_missing_tick_is_honest_skip_not_guess(self):
        fill = _make_fill()
        session = _session_returning([fill])

        with patch(
            "lumine.trade_core.tca_backfill.resolve_benchmark",
            side_effect=ValueError("benchmark unavailable: arrival tick is missing"),
        ):
            stats = await backfill_missing_tca(session)

        assert stats.backfilled == 0
        assert stats.skipped_no_tick == 1
        assert any("benchmark unavailable" in e for e in stats.errors)

    @pytest.mark.asyncio
    async def test_per_row_isolation_one_bad_row_does_not_abort_batch(self):
        f1, f2 = _make_fill(), _make_fill()
        session = _session_returning([f1, f2])

        responses = [
            ValueError("benchmark unavailable"),  # f1 gagal
            None,  # f2 sukses (diisi di bawah)
        ]

        async def _resolve(*args, **kwargs):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            bench = MagicMock()
            bench.price = Decimal("2749.00")
            bench.source = "arrival_mid"
            return bench

        with patch("lumine.trade_core.tca_backfill.resolve_benchmark", side_effect=_resolve):
            stats = await backfill_missing_tca(session)

        assert stats.skipped_no_tick == 1
        assert stats.backfilled == 1

    @pytest.mark.asyncio
    async def test_filters_symbol_and_window(self):
        session = _session_returning([])
        await backfill_missing_tca(
            session,
            symbol="XAUUSD",
            since=datetime(2026, 8, 1, tzinfo=UTC),
            until=datetime(2026, 8, 20, tzinfo=UTC),
        )
        stmt = session.execute.call_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "XAUUSD" in compiled
        assert "tca_id IS NULL" in compiled or "IS NULL" in compiled
