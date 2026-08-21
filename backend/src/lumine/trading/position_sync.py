# Copyright (c) 2026 Lumine. All rights reserved.
"""Background worker that syncs MT5 open positions to PostgreSQL (B-04/B1).

Flow (fix B1 — sebelumnya placeholder return []):
1. EA (LumineEA.mq5) kirim snapshot open positions tiap ~10s:
   POST /mt5-proxy/positions → LPUSH mt5:positions
   Body: {snapshot_ts, positions: [{ticket, symbol, type, volume,
   price_open, sl, tp, profit, time}]}
2. Worker ini consume mt5:positions (LRANGE + DELETE) → upsert ke
   tabel positions keyed by mt5_ticket (migration c02228f00013).
3. Posisi yang tidak lagi ada di snapshot MT5 → status closed.
4. Mark-to-market: harga live MarketService; fallback last close bars_1h.

Posisi dari fills (tanpa ticket) tidak disentuh — hanya posisi MT5 yang
disinkronkan, sehingga tidak terjadi duplikasi.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumine.data.models import Position
from lumine.data.session import get_sessionmaker
from lumine.shared.config import Settings
from lumine.trading.market_service import MarketService

logger = logging.getLogger(__name__)

# Redis key: EA push snapshot positions (list, newest first)
POSITIONS_KEY = "mt5:positions"
# Redis key: EA push deals/history (list)
DEALS_KEY = "mt5:deals"


def _parse_side(type_: Any) -> str:
    """MT5 POSITION_TYPE: 0=BUY, 1=SELL."""
    try:
        return "buy" if int(type_) == 0 else "sell"
    except (TypeError, ValueError):
        return "buy"


class PositionSyncWorker:
    """Sync MT5 open positions into PostgreSQL (live)."""

    def __init__(
        self,
        market_service: MarketService,
        interval_seconds: float = 10.0,
        settings: Settings | None = None,
    ) -> None:
        self.market_service = market_service
        self.interval = interval_seconds
        self.settings = settings or Settings()
        self._task: asyncio.Task | None = None
        self._running = False
        self._redis = None

    async def _get_redis(self):
        """Lazy Redis client."""
        if self._redis is None:
            from lumine.data.redis_client import get_redis

            self._redis = await get_redis()
        return self._redis

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
                logger.exception("position sync cycle failed")
            await asyncio.sleep(self.interval)

    async def _sync_once(self) -> None:
        """One sync cycle: consume Redis snapshot → upsert DB."""
        r = await self._get_redis()
        raw_items = await r.lrange(POSITIONS_KEY, 0, -1)
        if not raw_items:
            return
        # Ambil snapshot paling baru (index 0 = LPUSH paling baru)
        newest: dict[str, Any] | None = None
        for raw in raw_items:
            try:
                parsed = json.loads(raw if isinstance(raw, str) else raw.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("positions"), list):
                if newest is None:
                    newest = parsed
        if newest is None:
            # Bersihkan key — data invalid tidak diproses ulang
            await r.delete(POSITIONS_KEY)
            return

        positions_payload = newest.get("positions", [])
        await self._upsert_positions(positions_payload)
        # Clear queue setelah diproses (snapshot sudah dikonsumsi)
        await r.delete(POSITIONS_KEY)

    async def _upsert_positions(self, payload: list[dict[str, Any]]) -> None:
        """Upsert MT5 positions; tutup posisi yang tidak ada di snapshot."""
        tickets: set[int] = set()
        closed_positions: list[Any] = []
        async with get_sessionmaker()() as session:
            for item in payload:
                try:
                    ticket = int(item.get("ticket"))
                except (TypeError, ValueError):
                    continue
                tickets.add(ticket)
                # B9: normalize symbol prefix broker (XAUUSDc → XAUUSD)
                normalized_item = {
                    **item,
                    "symbol": _normalize_symbol(str(item.get("symbol", "XAUUSD"))),
                }
                await self._upsert_one(session, normalized_item, ticket)

            # Tutup posisi MT5 yang tidak ada di snapshot terbaru.
            # PITFALL (17 Aug 2026): snapshot KOSONG ([] — semua posisi
            # ditutup di MT5) TIDAK boleh skip — itu justru sinyal SEMUA
            # posisi harus ditutup. Loop penutupan jalan untuk payload
            # kosong maupun non-kosong.
            existing = (
                await session.execute(
                    select(Position).where(
                        Position.mt5_ticket.isnot(None),
                        Position.status == "open",
                    )
                )
            ).scalars().all()
            for pos in existing:
                if pos.mt5_ticket not in tickets:
                    pos.status = "closed"
                    session.add(pos)
                    logger.info("position %s (ticket %s) closed by sync", pos.position_id, pos.mt5_ticket)
                    # P2 (21 Aug 2026): capture pengalaman ke trade_memories
                    # (self-improvement loop). Commit dulu supaya status
                    # closed terbaca; capture pakai session terpisah agar
                    # gagal capture tidak menggagalkan sync.
                    closed_positions.append(pos)
            await session.commit()
            for closed in closed_positions:
                try:
                    from lumine.trading.trade_memory import capture_closed_position

                    async with get_sessionmaker()() as mem_session:
                        await capture_closed_position(mem_session, closed)
                except Exception:  # nosec B110 — memory tidak boleh matikan sync
                    logger.exception("trade memory capture failed")

    async def _upsert_one(
        self, session: AsyncSession, item: dict[str, Any], ticket: int
    ) -> None:
        """Upsert satu posisi MT5 (ON CONFLICT via mt5_ticket)."""
        symbol = str(item.get("symbol", "XAUUSD"))
        side = _parse_side(item.get("type"))
        volume = Decimal(str(item.get("volume", 0)))
        price_open = Decimal(str(item.get("price_open") or item.get("price") or 0))
        sl = item.get("sl")
        tp = item.get("tp")
        opened_at = _parse_time(item.get("time"))
        profit = Decimal(str(item.get("profit", 0) or 0))

        # Mark-to-market: live quote → fallback last close → price_open
        # (unrealized P&L dihitung API saat serve: (current - avg_entry)*size;
        # profit MT5 disimpan sebagai referensi untuk B8 sync P&L real.)
        current = await self._live_price(symbol)
        if current is None:
            current = await self._last_close(symbol) or price_open

        existing = (
            await session.execute(
                select(Position).where(Position.mt5_ticket == ticket)
            )
        ).scalar_one_or_none()

        if existing:
            existing.symbol = symbol
            existing.side = side
            existing.size = volume
            existing.avg_entry = price_open
            existing.sl = Decimal(str(sl)) if sl not in (None, 0, "0") else None
            existing.tp = Decimal(str(tp)) if tp not in (None, 0, "0") else None
            existing.opened_at = opened_at or existing.opened_at
            existing.status = "open"
            existing.mt5_profit = profit  # B8: P&L real dari broker
            session.add(existing)
        else:
            # Posisi MT5 baru — strategy_id deterministik per ticket (unik,
            # menghindari konflik ix_positions_open UNIQUE (symbol,book,
            # strategy_id) WHERE open — semua posisi MT5 pakai strategy
            # berbeda sehingga bisa banyak posisi XAUUSD open sekaligus).
            # opened_lineage NULL (source broker snapshot, bukan pipeline).
            session.add(
                Position(
                    symbol=symbol,
                    book="default",
                    strategy_id=_lineage_for_ticket(ticket),
                    side=side,
                    size=volume,
                    avg_entry=price_open,
                    sl=Decimal(str(sl)) if sl not in (None, 0, "0") else None,
                    tp=Decimal(str(tp)) if tp not in (None, 0, "0") else None,
                    opened_at=opened_at or datetime.now(UTC),
                    opened_lineage=None,
                    status="open",
                    mt5_ticket=ticket,
                    mt5_profit=profit,  # B8: P&L real dari broker
                )
            )
        logger.debug("position sync upsert ticket=%s symbol=%s side=%s vol=%s", ticket, symbol, side, volume)

    async def _live_price(self, symbol: str) -> Decimal | None:
        """Live quote dari MarketService (tick EA)."""
        try:
            tick = await self.market_service.get_quote(symbol)
            if tick and tick.bid:
                return Decimal(str(tick.bid))
        except Exception:
            pass
        return None

    async def _last_close(self, symbol: str) -> Decimal | None:
        """Last close real dari bars_1h (fallback market libur)."""
        from sqlalchemy import text

        async with get_sessionmaker()() as session:
            row = (
                await session.execute(
                    text("SELECT close FROM bars_1h WHERE symbol = :s ORDER BY ts DESC LIMIT 1"),
                    {"s": symbol},
                )
            ).scalar_one_or_none()
            return Decimal(str(row)) if row is not None else None

    @classmethod
    async def from_pool(
        cls,
        database_url: str,
        market_service: MarketService,
        interval_seconds: float = 10.0,
    ) -> PositionSyncWorker:
        """Create worker (database_url retained for API compatibility)."""
        worker = cls(market_service, interval_seconds)
        await worker.start()
        return worker


def _parse_time(value: Any) -> datetime | None:
    """MT5 datetime (unix seconds) → aware datetime."""
    try:
        ts = int(value)
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _lineage_for_ticket(ticket: int) -> UUID:
    """Deterministic UUID dari ticket (strategy_id posisi MT5 sync)."""
    import hashlib

    digest = hashlib.sha256(f"mt5-sync:{ticket}".encode()).digest()[:16]
    return UUID(bytes=digest)


def _normalize_symbol(raw: str) -> str:
    """B9: broker symbol prefix → base (XAUUSDc → XAUUSD, XAUUSD.stp → XAUUSD)."""
    s = raw.upper()
    if "." in s:
        s = s.split(".", 1)[0]
    if len(s) > 4 and s[-1] in ("C", "M", "X", "I", "Z"):
        s = s[:-1]
    return s
