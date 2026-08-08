# Copyright (c) 2026 Lumine. All rights reserved.
"""Market data, features, and signal endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import MarketBar, Signal
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/bars", response_model=PaginatedList[MarketBar])
async def list_bars(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[MarketBar]:
    """Return recent market bars."""
    now = datetime.now(UTC)
    items: list[MarketBar] = [
        MarketBar(
            symbol="XAUUSD",
            timeframe="H1",
            timestamp=now,
            open=Decimal("2420.00"),
            high=Decimal("2430.50"),
            low=Decimal("2418.00"),
            close=Decimal("2435.80"),
            volume=1200,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/signals", response_model=PaginatedList[Signal])
async def list_signals(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:market")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Signal]:
    """Return recent analyst signals."""
    now = datetime.now(UTC)
    items: list[Signal] = [
        Signal(
            signal_id=uuid4(),
            symbol="XAUUSD",
            analyst="technical_analyst",
            direction="bullish",
            confidence=0.78,
            rationale="breakout above resistance",
            generated_at=now,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )
