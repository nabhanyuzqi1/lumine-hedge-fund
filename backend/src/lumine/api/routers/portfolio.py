# Copyright (c) 2026 Lumine. All rights reserved.
"""Portfolio, positions, and exposure REST endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import ExposureSummary, PortfolioSummary, Position
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> PortfolioSummary:
    """Return the current portfolio summary."""
    now = datetime.now(UTC)
    return PortfolioSummary(
        portfolio_id="default",
        nav=Decimal("100000.00"),
        cash=Decimal("75000.00"),
        margin_used=Decimal("25000.00"),
        open_pnl=Decimal("1200.50"),
        closed_pnl=Decimal("8450.00"),
        timestamp=now,
    )


@router.get("/positions", response_model=PaginatedList[Position])
async def list_positions(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[Position]:
    """List open positions."""
    items: list[Position] = [
        Position(
            position_id=uuid4(),
            portfolio_id="default",
            symbol="XAUUSD",
            direction="long",
            volume=Decimal("1.50"),
            entry_price=Decimal("2420.30"),
            current_price=Decimal("2435.80"),
            stop_loss=Decimal("2400.00"),
            take_profit=Decimal("2500.00"),
            unrealized_pnl=Decimal("1200.50"),
            opened_at=datetime.now(UTC),
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/positions/{position_id}", response_model=Position)
async def get_position(
    position_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> Position:
    """Return a single open position."""
    return Position(
        position_id=position_id,
        portfolio_id="default",
        symbol="XAUUSD",
        direction="long",
        volume=Decimal("1.50"),
        entry_price=Decimal("2420.30"),
        current_price=Decimal("2435.80"),
        stop_loss=Decimal("2400.00"),
        take_profit=Decimal("2500.00"),
        unrealized_pnl=Decimal("1200.50"),
        opened_at=datetime.now(UTC),
    )


@router.get("/exposure", response_model=PaginatedList[ExposureSummary])
async def get_exposure(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[ExposureSummary]:
    """Return exposure breakdown."""
    items: list[ExposureSummary] = [
        ExposureSummary(symbol="XAUUSD", notional=Decimal("3653.70"), pct_of_nav=Decimal("0.0365")),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )
