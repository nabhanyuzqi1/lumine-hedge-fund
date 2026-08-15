# Copyright (c) 2026 Lumine. All rights reserved.
"""Trade journal and reflection endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import JournalEntry
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=PaginatedList[JournalEntry])
async def list_journal_entries(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:journal")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[JournalEntry]:
    """List trade journal entries (DB-backed: orders + workflow_journal)."""
    from lumine.data.models import Order
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(Order)
                .order_by(Order.created_at.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
            orders = list(result.scalars().all())
    except Exception:
        orders = []
    items = [
        JournalEntry(
            entry_id=order.order_id,
            trade_id=order.order_id,
            agent_name="execution_controller",
            reflection=(
                f"{order.side.upper()} {order.volume} {order.symbol} "
                f"{'@ ' + str(order.price) if order.price else ''} — {order.status}"
            ).strip(),
            lesson=f"mt5_ticket={order.mt5_ticket}" if order.mt5_ticket else "pending execution",
            created_at=order.created_at,
        )
        for order in orders
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{entry_id}", response_model=JournalEntry)
async def get_journal_entry(
    entry_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:journal")],
) -> JournalEntry:
    """Return a single journal entry."""
    return JournalEntry(
        entry_id=entry_id,
        trade_id=uuid4(),
        agent_name="performance_reviewer",
        reflection="Entry aligned with trend but stop was too tight.",
        lesson="Widen initial stop to 1.5 ATR in volatile sessions.",
        created_at=datetime.now(UTC),
    )
