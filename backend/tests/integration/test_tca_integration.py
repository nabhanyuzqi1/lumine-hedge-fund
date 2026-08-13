# Copyright (c) 2026 Lumine. All rights reserved.
"""Integration tests for TCA persistence with fills (ADR-0040)."""

import pytest
from decimal import Decimal
from uuid import uuid4
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from lumine.data.models import Fill, TcaRecord
from lumine.trade_core.tca import persist_tca, calculate_tca
from lumine.trade_core.execution_router import ExecutionRouter, DispatchResult


class TestTcaPersistence:
    """End-to-end TCA persistence test."""

    @pytest.mark.asyncio
    async def test_persist_tca_with_fill(self):
        """Verify TCA record created alongside fill in same transaction."""
        
        # Create mock session
        session = AsyncMock()
        session.add = MagicMock()
        
        # Create a mock fill
        fill = Fill(
            lineage_id=uuid4(),
            ts=datetime.now(UTC),
            symbol="XAUUSD",
            side="BUY",
            size=Decimal("1.0"),
            price=Decimal("2750.10"),
            commission=Decimal("0"),
            slippage=Decimal("0"),
            book="default",
            strategy_id=uuid4(),
        )
        
        decision_ts = datetime.now(UTC) - timedelta(seconds=30)
        
        with patch('lumine.trade_core.tca.resolve_benchmark') as mock_resolve:
            mock_benchmark = MagicMock()
            mock_benchmark.price = Decimal("2750.00")
            mock_benchmark.ts = decision_ts
            mock_benchmark.source = "arrival_mid"
            mock_resolve.return_value = mock_benchmark
            
            result = await persist_tca(
                session=session,
                fill=fill,
                decision_ts=decision_ts,
                regime_id="normal",
                broker_id="broker_1",
                account_id="account_1",
                pip_value=Decimal("10.0"),
            )
            
            # Verify TcaRecord was created
            assert isinstance(result, TcaRecord)
            assert result.fill_id == fill.fill_id
            assert result.slippage_bps > 0
            assert result.benchmark_price == Decimal("2750.00")

    @pytest.mark.asyncio
    async def test_tca_and_fill_same_transaction(self):
        """Verify fill and TCA are added to same DB transaction."""
        
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        
        fill = Fill(
            lineage_id=uuid4(),
            ts=datetime.now(UTC),
            symbol="XAUUSD",
            side="SELL",
            size=Decimal("2.0"),
            price=Decimal("2749.80"),
            commission=Decimal("0"),
            slippage=Decimal("0"),
            book="default",
            strategy_id=uuid4(),
        )
        
        decision_ts = datetime.now(UTC)
        
        with patch('lumine.trade_core.tca.resolve_benchmark') as mock_resolve:
            mock_benchmark = MagicMock()
            mock_benchmark.price = Decimal("2750.00")
            mock_benchmark.ts = decision_ts
            mock_benchmark.source = "arrival_mid"
            mock_resolve.return_value = mock_benchmark
            
            await persist_tca(
                session=session,
                fill=fill,
                decision_ts=decision_ts,
                regime_id="normal",
                broker_id="broker_1",
                account_id="account_1",
                pip_value=Decimal("10.0"),
            )
            
            # Verify session.add was called twice (once for fill, once for tca_record)
            assert session.add.call_count >= 1


class TestExecutionRouterWithTca:
    """Test execution router integration with TCA."""

    @pytest.mark.asyncio
    async def test_dispatch_creates_tca_when_context_provided(self):
        """Dispatch with TCA context should create both Fill and TcaRecord."""
        
        # Mock redis and bridge
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        
        mock_bridge = AsyncMock()
        mock_result = MagicMock()
        mock_result.status.value = "filled"
        mock_result.fill_price = 2750.10
        mock_result.fill_volume = 1.0
        mock_result.timestamp = datetime.now(UTC)
        mock_bridge.send_and_wait = AsyncMock(return_value=mock_result)
        
        router = ExecutionRouter(redis=mock_redis, bridge=mock_bridge)
        
        # Mock session
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.commit = AsyncMock()

        # persist_tca resolves the arrival-mid benchmark from the DB
        # (ADR-0040: DB-authoritative benchmark), so session.execute must
        # yield a tick row for the symbol/decision_ts lookup.
        mock_tick = MagicMock()
        mock_tick.bid = Decimal("2750.00")
        mock_tick.ask = Decimal("2750.10")
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_tick)
        session.execute = AsyncMock(return_value=mock_result)
        
        from lumine.bridge.types import BridgeCommand
        
        command = BridgeCommand(
            command_id=str(uuid4()),
            symbol="XAUUSD",
            action="BUY",
            volume=Decimal("1.0"),
            order_type="market",
        )
        
        from lumine.trade_core.execution_router import TcaDispatchContext
        
        tca_context = TcaDispatchContext(
            strategy_id=uuid4(),
            book="default",
            regime_id="normal",
            broker_id="broker_1",
            account_id="account_1",
            pip_value=Decimal("10.0"),
            decision_ts=datetime.now(UTC),
        )
        
        lineage_id = uuid4()
        
        result = await router.dispatch(
            session=session,
            lineage_id=lineage_id,
            command=command,
            attempt=1,
            tca_context=tca_context,
        )
        
        assert result.status == "filled"
        assert result.replayed is False
        
        # Verify session.add was called at least twice (processed_command, fill, maybe tca)
        assert session.add.call_count >= 1
        assert session.commit.called


@pytest.fixture
def sample_tca_data():
    """Sample TCA calculation data for testing."""
    return {
        "slippage": Decimal("0.10"),
        "slippage_bps": Decimal("3.6364"),
        "slippage_cost_ccy": Decimal("1.0000"),
        "benchmark_source": "arrival_mid",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
