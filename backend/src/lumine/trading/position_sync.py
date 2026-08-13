# Copyright (c) 2026 Lumine. All rights reserved.
"""Background worker for syncing MT5 positions to PostgreSQL."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import asyncpg

from lumine.trading.market_service import MarketService


@dataclass
class PositionData:
    """Position data from MT5 or calculated."""

    mt5_ticket: int
    symbol: str
    direction: str  # BUY or SELL
    volume: float
    entry_price: float
    current_price: float | None = None
    pnl: float = 0.0
    opened_at: str = ""


class PositionSyncWorker:
    """
    Background worker that syncs MT5 positions to PostgreSQL.

    Operations:
    1. Fetch open positions from MT5 via direct API (if available)
       or extract from Redis bridge results
    2. Get current prices from MarketService cache
    3. Calculate unrealized P&L
    4. Upsert into PostgreSQL positions table
    5. Emit SSE events on changes
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        market_service: MarketService,
        interval_seconds: float = 5.0,
        redis_client=None,
    ):
        self.pool = pool
        self.market_service = market_service
        self.interval = interval_seconds
        self.redis = redis_client
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start background sync loop."""
        if self._task and not self._task.done():
            return

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())

    async def stop(self) -> None:
        """Stop background sync loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _sync_loop(self) -> None:
        """Main sync loop."""
        while self._running:
            try:
                await self._sync_once()
            except Exception:
                # Log error in production, continue loop
                pass

            await asyncio.sleep(self.interval)

    async def _sync_once(self) -> None:
        """Execute one sync cycle."""
        positions = await self._fetch_positions()
        await self._update_database(positions)

    async def _fetch_positions(self) -> list[PositionData]:
        """
        Fetch open positions from MT5.

        In production, this would use MetaTrader5 package directly
        or extract from Redis bridge. For now, return empty list.
        TODO: Implement MT5 connection when broker account available.
        """
        # Placeholder - will implement actual MT5 fetch here
        # await pymt5.connect(...)
        # positions = await pymt5.get_positions()
        return []

    async def _update_database(
        self,
        positions: list[PositionData],
    ) -> None:
        """Upsert positions into PostgreSQL and emit SSE events."""
        if not positions:
            return

        conn = await self.pool.acquire()
        try:
            for pos in positions:
                # Calculate unrealized P&L
                pos.pnl = self._calculate_pnl(pos)

                # Upsert position
                await conn.execute(
                    """
                    INSERT INTO positions (
                        mt5_ticket, symbol, direction, volume,
                        entry_price, current_price, unrealized_pnl,
                        opened_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (mt5_ticket) DO UPDATE SET
                        direction = EXCLUDED.direction,
                        volume = EXCLUDED.volume,
                        current_price = EXCLUDED.current_price,
                        unrealized_pnl = EXCLUDED.unrealized_pnl,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    pos.mt5_ticket,
                    pos.symbol,
                    pos.direction,
                    pos.volume,
                    pos.entry_price,
                    pos.current_price,
                    pos.pnl,
                    pos.opened_at or datetime.now(UTC).isoformat(),
                )

            await conn.commit()
        finally:
            await self.pool.release(conn)

    def _calculate_pnl(self, pos: PositionData) -> float:
        """Calculate unrealized P&L for a position."""
        if pos.current_price is None:
            return 0.0

        contract_size = 100000  # Standard forex lot
        leverage = 100  # Assume standard leverage

        if pos.direction == "BUY":
            diff = pos.current_price - pos.entry_price
        else:
            diff = pos.entry_price - pos.current_price

        # Adjust for symbol type (forex vs precious metals)
        if pos.symbol.startswith(("XAU", "XAG")):
            # Gold/Silver: price difference * volume
            return diff * pos.volume
        else:
            # Forex: price difference * volume * contract_size
            return diff * pos.volume * contract_size / 100000

    @classmethod
    async def create(
        cls,
        pool: asyncpg.Pool,
        market_service: MarketService,
        interval_seconds: float = 5.0,
    ) -> PositionSyncWorker:
        """Create and start PositionSyncWorker."""
        worker = cls(pool, market_service, interval_seconds)
        await worker.start()
        return worker

    @classmethod
    async def from_pool(
        cls,
        database_url: str,
        market_service: MarketService,
        interval_seconds: float = 5.0,
    ) -> PositionSyncWorker:
        """Create PositionSyncWorker from database URL."""
        import asyncpg
        # asyncpg accepts postgresql:// only — normalize the SQLAlchemy-style
        # postgresql+asyncpg:// DSN used across the rest of the app.
        dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        pool = await asyncpg.create_pool(dsn)
        worker = cls(pool, market_service, interval_seconds)
        await worker.start()
        return worker
