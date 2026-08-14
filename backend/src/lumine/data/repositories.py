# Copyright (c) 2026 Lumine. All rights reserved.
"""SQLAlchemy repositories (B-05) — DB-backed domain access.

Routers use these when ``DEMO_DATA=0``; the demo path (demo_data.py)
remains the default so the stack works without Postgres wiring.

Single-portfolio v1: portfolio_id is accepted but not filtered.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumine.data.models import Order, Position


class OrderRepository:
    """Orders CRUD against the physical ``orders`` table (0011)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        portfolio_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        """Return (items, total) with optional status filter."""
        query = select(Order)
        count_query = select(func.count()).select_from(Order)
        if status:
            query = query.where(Order.status == status)
            count_query = count_query.where(Order.status == status)
        total = (await self._session.execute(count_query)).scalar_one()
        items = list(
            (
                await self._session.execute(
                    query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
                )
            ).scalars()
        )
        return items, total

    async def get(self, order_id: UUID) -> Order | None:
        return await self._session.get(Order, order_id)

    async def create(
        self,
        *,
        order_id: UUID,
        portfolio_id: str,
        symbol: str,
        side: str,
        order_type: str,
        volume: Decimal,
        price: Decimal | None = None,
        status: str = "pending",
    ) -> Order:
        order = Order(
            order_id=order_id,
            portfolio_id=portfolio_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            volume=volume,
            price=price,
            status=status,
            filled_volume=Decimal(0),
        )
        self._session.add(order)
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def update_status(self, order_id: UUID, *, status: str, rejected_reason: str | None = None) -> Order | None:
        """Transition an order to a new status (cancel/modify core)."""
        order = await self._session.get(Order, order_id)
        if order is None:
            return None
        order.status = status
        if rejected_reason is not None:
            order.rejected_reason = rejected_reason
        order.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def modify(
        self,
        order_id: UUID,
        *,
        price: Decimal | None = None,
        volume: Decimal | None = None,
    ) -> Order | None:
        """Update price/volume of a pending order (PATCH contract)."""
        order = await self._session.get(Order, order_id)
        if order is None:
            return None
        if order.status != "pending":
            raise ValueError(f"order {order_id} is {order.status}, only pending orders are modifiable")
        if price is not None:
            order.price = price
        if volume is not None:
            order.volume = volume
        order.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def cancel_all_pending(self) -> int:
        """Cancel every pending order; returns the number cancelled."""
        items = list(
            (
                await self._session.execute(select(Order).where(Order.status == "pending"))
            ).scalars()
        )
        now = datetime.now(UTC)
        for order in items:
            order.status = "cancelled"
            order.updated_at = now
        await self._session.commit()
        return len(items)

    async def bulk_status(self, order_ids: list[UUID]) -> dict[str, str]:
        """Return the status of many orders (unknown ids omitted)."""
        rows = list(
            (
                await self._session.execute(select(Order).where(Order.order_id.in_(order_ids)))
            ).scalars()
        )
        return {str(order.order_id): order.status for order in rows}


class PositionRepository:
    """Open positions against the ``positions`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_open(self) -> list[Position]:
        items = list(
            (
                await self._session.execute(
                    select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
                )
            ).scalars()
        )
        return items

    async def get(self, position_id: UUID) -> Position | None:
        return await self._session.get(Position, position_id)

    async def exposure_summary(self, mid_prices: dict[str, Decimal]) -> dict[str, object]:
        """Notional exposure per symbol + totals (priced with mid_prices)."""
        positions = await self.list_open()
        by_symbol: dict[str, Decimal] = {}
        for pos in positions:
            price = mid_prices.get(pos.symbol, Decimal(0))
            notional = price * abs(pos.size)
            by_symbol[pos.symbol] = by_symbol.get(pos.symbol, Decimal(0)) + notional
        gross = sum(by_symbol.values(), Decimal(0))
        return {
            "symbols": sorted(by_symbol),
            "notionals": {s: str(v) for s, v in by_symbol.items()},
            "gross_exposure": str(gross),
            "position_count": len(positions),
        }
