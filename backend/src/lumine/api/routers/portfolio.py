# Copyright (c) 2026 Lumine. All rights reserved.
"""Portfolio, positions, and exposure REST endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from lumine.api.demo_data import mid_price
from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.middleware.rate_limit import rate_limit_dependency
from lumine.api.schemas.api import (
    CancelAllResult,
    CreatePortfolioRequest,
    EquityPoint,
    ExposureSummary,
    PortfolioSummary,
    Position,
    SimulateTradeRequest,
    SimulateTradeResult,
)
from lumine.api.schemas.common import PaginatedList, Pagination
from lumine.shared.config import Settings, get_settings

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_DEMO_NAV = Decimal("100000.00")


def _demo_summary(*, portfolio_id: str = "default", nav: Decimal = _DEMO_NAV) -> PortfolioSummary:
    """Deterministic portfolio snapshot (single-portfolio v1)."""
    return PortfolioSummary(
        portfolio_id=portfolio_id,
        nav=nav,
        cash=Decimal("75000.00"),
        margin_used=Decimal("25000.00"),
        open_pnl=Decimal("1200.50"),
        closed_pnl=Decimal("8450.00"),
        timestamp=datetime.now(UTC),
    )


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> PortfolioSummary:
    """Return the current portfolio summary."""
    return _demo_summary()


@router.get("", response_model=PortfolioSummary)
async def get_portfolio(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> PortfolioSummary:
    """Return the single (default) portfolio (B-06 portfolio CRUD)."""
    return _demo_summary()


@router.post(
    "",
    response_model=PortfolioSummary,
    status_code=201,
    dependencies=[Depends(rate_limit_dependency)],
)
async def create_portfolio(
    _request: CreatePortfolioRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:portfolio")],
) -> PortfolioSummary:
    """Create a portfolio — single-portfolio v1 returns the default book."""
    return _demo_summary()


@router.put(
    "/{portfolio_id}",
    response_model=PortfolioSummary,
    dependencies=[Depends(rate_limit_dependency)],
)
async def update_portfolio(
    portfolio_id: str,
    _request: CreatePortfolioRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:portfolio")],
) -> PortfolioSummary:
    """Rename/update the portfolio (demo echo; single-portfolio v1)."""
    return _demo_summary(portfolio_id=portfolio_id)


@router.delete(
    "/{portfolio_id}",
    response_model=PortfolioSummary,
    dependencies=[Depends(rate_limit_dependency)],
)
async def delete_portfolio(
    portfolio_id: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:portfolio")],
) -> PortfolioSummary:
    """Delete a portfolio — v1 refuses the only book (safe default)."""
    raise HTTPException(status_code=409, detail="single-portfolio v1: the default portfolio cannot be deleted")


@router.get("/{portfolio_id}/equity", response_model=PaginatedList[EquityPoint])
async def get_equity_curve(
    portfolio_id: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[EquityPoint]:
    """Equity curve (B-06) — deterministic demo series until storage wiring.

    Points: nav/equity with a mild upward drift and a drawdown dip at the
    2/3 mark, 1h spacing, newest first.
    """
    now = datetime.now(UTC)
    total = 240
    visible = min(pagination.limit, max(total - pagination.offset, 0))
    items: list[EquityPoint] = []
    for i in range(visible):
        idx = pagination.offset + i
        frac = idx / total
        drift = Decimal("1") + Decimal(str(round(frac * 0.06, 6)))
        drawdown = Decimal("0")
        if 0.55 < frac < 0.75:
            drawdown = Decimal("-0.038")
        nav = (_DEMO_NAV * drift).quantize(Decimal("0.01"))
        items.append(
            EquityPoint(
                ts=now - timedelta(seconds=idx * 3600),
                nav=nav,
                equity=(nav + Decimal("8450.00")).quantize(Decimal("0.01")),
                drawdown=drawdown,
            )
        )
    return PaginatedList(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.delete(
    "/{portfolio_id}/orders",
    response_model=CancelAllResult,
    dependencies=[Depends(rate_limit_dependency)],
)
async def cancel_all_orders(
    portfolio_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:orders")],
) -> CancelAllResult:
    """Cancel every open order in the portfolio (B-06 cancel-all)."""
    if not settings.demo_data:
        from lumine.data.repositories import OrderRepository
        from lumine.data.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            repo = OrderRepository(session)
            cancelled = await repo.cancel_all_pending()
            return CancelAllResult(cancelled=cancelled, portfolio_id=portfolio_id)
    return CancelAllResult(cancelled=3, portfolio_id=portfolio_id)


@router.post(
    "/{portfolio_id}/simulate",
    response_model=SimulateTradeResult,
    dependencies=[Depends(rate_limit_dependency)],
)
async def simulate_trade(
    portfolio_id: str,
    request: SimulateTradeRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> SimulateTradeResult:
    """Project portfolio impact of a hypothetical trade (what-if, no execution)."""
    if portfolio_id not in {"default", "portfolio-demo"}:
        raise HTTPException(status_code=404, detail=f"unknown portfolio: {portfolio_id}")
    mid = mid_price(request.symbol)
    direction = 1.0 if request.side == "buy" else -1.0
    pnl_change = (mid - float(request.price)) * float(request.volume) * direction
    margin_required = float(request.price) * float(request.volume) * 0.01
    return SimulateTradeResult(
        projected_nav=_DEMO_NAV + Decimal(str(round(pnl_change, 2))),
        margin_required=Decimal(str(round(margin_required, 2))),
        pnl_change=Decimal(str(round(pnl_change, 2))),
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
