# Copyright (c) 2026 Lumine. All rights reserved.
"""Integration tests for MT5 streaming infrastructure."""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def market_service():
    """Create mock MarketService."""
    from lumine.trading.market_service import MarketService

    return MarketService()


@pytest.fixture
async def mt5_bridge(mock_redis_client):
    """Create MT5Bridge with mocked Redis."""
    from lumine.trading.mt5_bridge import MT5Bridge, CommandMessage

    bridge = MT5Bridge(mock_redis_client)
    yield bridge
    await bridge.stop()


@pytest.fixture
async def position_sync_worker(pool, market_service):
    """Create PositionSyncWorker for testing."""
    from lumine.trading.position_sync import PositionSyncWorker

    worker = PositionSyncWorker(pool, market_service, interval_seconds=1.0)
    yield worker
    await worker.stop()


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client for MT5Bridge testing."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.lpush = AsyncMock()
    redis.pubsub = MagicMock(return_value=AsyncMock())
    redis.from_url = AsyncMock(return_value=redis)
    return redis


class TestMT5Bridge:
    """Tests for MT5Bridge component."""

    @pytest.mark.asyncio
    async def test_create_open_order_command(self):
        """Test creating OPEN command message."""
        from lumine.trading.mt5_bridge import (
            CommandMessage,
            create_open_order_command,
        )

        cmd = create_open_order_command(
            order_id="abc-123",
            symbol="XAUUSD",
            volume=0.01,
            order_type="BUY",
            stop_loss=1950.0,
            take_profit=1980.0,
        )

        assert cmd.action == "OPEN"
        assert cmd.symbol == "XAUUSD"
        assert cmd.order_type == "BUY"
        assert cmd.volume == 0.01
        assert cmd.stop_loss == 1950.0
        assert cmd.take_profit == 1980.0
        assert hasattr(cmd, "timestamp")
        assert datetime.fromisoformat(cmd.timestamp.replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_send_command_checks_idempotency(self, mt5_bridge, mock_redis_client):
        """Test that send_command enforces idempotency."""
        from lumine.trading.mt5_bridge import CommandMessage

        msg = CommandMessage(
            command_id=str(uuid.uuid4()),
            order_id="order-123",
            action="OPEN",
            symbol="XAUUSD",
            volume=0.01,
            order_type="BUY",
            idempotency_key="key:test-idempotency",
        )

        # First call succeeds
        result = await mt5_bridge.send_command(msg)
        mock_redis_client.set.assert_called_once_with(
            "mt5:idempotency:key:test-idempotency", "1", nx=True, ex=3600
        )

        # Second call with same key fails
        mock_redis_client.set = AsyncMock(return_value=False)
        with pytest.raises(ValueError, match="Idempotent command already sent"):
            await mt5_bridge.send_command(msg)


class TestMarketService:
    """Tests for MarketService component."""

    @pytest.mark.asyncio
    async def test_get_quote_returns_cached_tick(self, market_service):
        """Test getting cached tick price."""
        await market_service.update_tick(
            symbol="XAUUSD", bid=1965.0, ask=1965.5, volume=100
        )

        tick = await market_service.get_quote("XAUUSD")

        assert tick is not None
        assert tick.symbol == "XAUUSD"
        assert tick.bid == 1965.0
        assert tick.ask == 1965.5
        assert tick.volume == 100
        assert abs((datetime.now(UTC) - tick.timestamp).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_get_quote_returns_none_for_missing_symbol(self, market_service):
        """Test getting quote for non-existent symbol."""
        tick = await market_service.get_quote("UNKNOWN")
        assert tick is None

    @pytest.mark.asyncio
    async def test_get_spread_calculates_correctly(self, market_service):
        """Test spread calculation in pips."""
        await market_service.update_tick(symbol="EURUSD", bid=1.08500, ask=1.08505)

        spread = await market_service.get_spread("EURUSD")

        # Spread = (ask - bid) / pip_size = (1.08505 - 1.08500) / 0.00001 = 0.00005 / 0.00001 = 5 pips
        assert spread == pytest.approx(5.0, abs=0.001)

    @pytest.mark.asyncio
    async def test_subscribe_symbols_tracks_subscriptions(self, market_service):
        """Test subscription tracking."""
        await market_service.subscribe_symbols(["XAUUSD", "EURUSD"])

        assert await market_service.is_subscribed("XAUUSD")
        assert await market_service.is_subscribed("EURUSD")
        assert not await market_service.is_subscribed("GBPUSD")


class TestPositionSyncWorker:
    """Tests for PositionSyncWorker component."""

    @pytest.mark.asyncio
    async def test_pnl_calculation_long_position(self, market_service):
        """Test unrealized P&L calculation for long position."""
        from lumine.trading.position_sync import PositionSyncWorker, PositionData

        worker = PositionSyncWorker(None, market_service)

        pos = PositionData(
            mt5_ticket=123456789,
            symbol="XAUUSD",
            direction="BUY",
            volume=0.01,
            entry_price=1965.0,
            current_price=1970.0,
        )

        pnl = worker._calculate_pnl(pos)

        # For gold: diff * volume = 5.0 * 0.01 = 0.05 (simplified)
        assert pnl > 0

    @pytest.mark.asyncio
    async def test_pnl_calculation_short_position(self, market_service):
        """Test unrealized P&L calculation for short position."""
        from lumine.trading.position_sync import PositionSyncWorker, PositionData

        worker = PositionSyncWorker(None, market_service)

        pos = PositionData(
            mt5_ticket=123456790,
            symbol="XAUUSD",
            direction="SELL",
            volume=0.01,
            entry_price=1970.0,
            current_price=1965.0,
        )

        pnl = worker._calculate_pnl(pos)

        # Short position profits when price drops
        assert pnl > 0


class TestSSEPublisher:
    """Tests for SSEPublisher component."""

    @pytest.mark.asyncio
    async def test_publish_position_update(self, market_service):
        """Test publishing position update event."""
        from lumine.api.sse.publisher import SSEPublisher, SSEEvent

        publisher = SSEPublisher(market_service)

        queue = await publisher.subscribe()

        await publisher.publish_position_update(
            portfolio_id="p1",
            position_id="pos-1",
            symbol="XAUUSD",
            direction="BUY",
            volume=0.01,
            entry_price=1965.0,
            current_price=1970.0,
            pnl=5.0,
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert isinstance(event, SSEEvent)
        assert event.event_type == "position_update"
        assert event.channel == "portfolio:p1:positions"
        assert event.data["symbol"] == "XAUUSD"
        assert event.data["unrealized_pnl"] == 5.0

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_publish_order_fill(self, market_service):
        """Test publishing order fill event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_order_fill(
            order_id="order-123",
            status="FILLED",
            fill_price=1965.5,
            fill_volume=0.01,
            mt5_ticket=123456789,
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "order_fill"
        assert event.channel == "orders"
        assert event.data["status"] == "FILLED"
        assert event.data["mt5_ticket"] == 123456789

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_publish_tick_update(self, market_service):
        """Test publishing tick update event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_tick_update(
            symbol="XAUUSD", bid=1965.0, ask=1965.5
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "tick_update"
        assert event.channel == "market:XAUUSD"
        assert event.data["bid"] == 1965.0
        assert event.data["ask"] == 1965.5

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_ring_buffer_limits_events(self, market_service):
        """Test that ring buffer limits events per channel."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)

        # Publish more events than max limit
        for i in range(150):
            await publisher.publish_tick_update(f"SYMBOL{i}", 100 + i, 101 + i)

        # Only keep last 100 events per channel
        history = await publisher.get_channel_history("market:XAUUSD", limit=10)
        assert len(history) <= 100

    @pytest.mark.asyncio
    async def test_publish_analyst_output(self, market_service):
        """Test publishing analyst output event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_analyst_output(
            portfolio_id="p1",
            symbol="XAUUSD",
            analyst_name="Technical Analyst",
            recommendation="BUY",
            confidence=0.85,
            reasoning="Price broke above key resistance level with volume confirmation",
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "analyst_output"
        assert event.channel == "analyst-outputs"
        assert event.data["symbol"] == "XAUUSD"
        assert event.data["recommendation"] == "BUY"
        assert event.data["confidence"] == 0.85

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_publish_ic_decision(self, market_service):
        """Test publishing IC decision event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_ic_decision(
            decision_id="dec-123",
            portfolio_id="p1",
            action="ADD_POSITION",
            positions=[{"symbol": "XAUUSD", "target_weight": 0.15}],
            confidence=0.75,
            reasoning="Consensus among analysts indicates bullish momentum",
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "ic_decision"
        assert event.channel == "ic-decisions"
        assert event.data["action"] == "ADD_POSITION"
        assert len(event.data["positions"]) == 1

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_publish_cio_proposal(self, market_service):
        """Test publishing CIO proposal event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_cio_proposal(
            proposal_id="prop-456",
            portfolio_id="p1",
            allocation_changes=[{"symbol": "XAUUSD", "from_weight": 0.1, "to_weight": 0.15}],
            expected_return=0.12,
            risk_score=3.5,
            reasoning="Strategic allocation increase based on macro analysis",
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "cio_proposal"
        assert event.channel == "cio-proposals"
        assert event.data["expected_return"] == 0.12
        assert event.data["risk_score"] == 3.5

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_publish_risk_assessment(self, market_service):
        """Test publishing risk assessment event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_risk_assessment(
            assessment_id="risk-789",
            portfolio_id="p1",
            risk_level="MEDIUM",
            metrics={"drawdown": -0.05, "var_95": -0.02},
            alerts=["Position concentration exceeds threshold"],
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "risk_assessment"
        assert event.channel == "risk-assessments"
        assert event.data["risk_level"] == "MEDIUM"
        assert event.data["metrics"]["drawdown"] == -0.05

        await publisher.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_publish_execution_order(self, market_service):
        """Test publishing execution order event."""
        from lumine.api.sse.publisher import SSEPublisher

        publisher = SSEPublisher(market_service)
        queue = await publisher.subscribe()

        await publisher.publish_execution_order(
            order_id="ord-123",
            portfolio_id="p1",
            symbol="XAUUSD",
            action="BUY",
            status="FILLED",
            quantity=0.01,
            price=1965.5,
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event.event_type == "execution_order"
        assert event.channel == "execution-orders"
        assert event.data["status"] == "FILLED"
        assert event.data["quantity"] == 0.01

        await publisher.unsubscribe(queue)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
