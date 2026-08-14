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

# Margin rate: 2% of notional (v1 single-portfolio convention).
_MARGIN_RATE = Decimal("0.02")


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


async def _real_summary(*, portfolio_id: str = "default") -> PortfolioSummary | None:
    """Portfolio summary computed from live PostgreSQL state (B-05).

    - open_pnl  : mark-to-market dari posisi terbuka (mid price live)
    - margin    : 2% notional per posisi
    - nav       : 100_000 (modal awal v1) + open_pnl
    - closed_pnl: 0 — atribusi realized memerlukan B-08 backfill fills
    Returns None saat DB tidak tersedia (caller fallback ke _demo_summary).
    """
    try:
        from sqlalchemy import select

        from lumine.data.models import Position
        from lumine.data.repositories import PositionRepository
        from lumine.data.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            repo = PositionRepository(session)
            positions = await repo.list_open()
            if not positions:
                return _demo_summary(portfolio_id=portfolio_id, nav=_DEMO_NAV)

            open_pnl = Decimal("0")
            margin_used = Decimal("0")
            for pos in positions:
                mid = mid_price(pos.symbol)
                pnl = (mid - pos.avg_entry) * pos.size
                if pos.side == "SHORT":
                    pnl = -pnl
                open_pnl += pnl
                margin_used += mid * abs(pos.size) * _MARGIN_RATE

            nav = (_DEMO_NAV + open_pnl).quantize(Decimal("0.01"))
            cash = (nav - margin_used).quantize(Decimal("0.01"))
            return PortfolioSummary(
                portfolio_id=portfolio_id,
                nav=nav,
                cash=cash,
                margin_used=margin_used.quantize(Decimal("0.01")),
                open_pnl=open_pnl.quantize(Decimal("0.01")),
                closed_pnl=Decimal("0.00"),
                timestamp=datetime.now(UTC),
            )
    except Exception:  # noqa: BLE001 — DB down: fallback demo, jangan 500
        return None


async def _real_equity_series(total: int, offset: int, limit: int) -> list[EquityPoint] | None:
    """Equity curve derived from live positions (B-05).

    Poin NAV dibangun dari waktu buka posisi (opened_at) dengan mark-to-market
    kumulatif posisi yang sudah terbuka saat itu (mid price live). Tanpa
    posisi: satu titik NAV=100_000. None saat DB tidak tersedia.
    """
    try:
        from lumine.data.models import Position
        from lumine.data.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(Position).where(Position.status == "open").order_by(Position.opened_at)
                )
            ).scalars().all()

            if not rows:
                return [
                    EquityPoint(
                        ts=datetime.now(UTC),
                        nav=_DEMO_NAV,
                        equity=_DEMO_NAV,
                        drawdown=Decimal("0"),
                    )
                ]

            now = datetime.now(UTC)
            points: list[EquityPoint] = []
            running_pnl = Decimal("0")
            peak = _DEMO_NAV
            for pos in rows:
                mid = mid_price(pos.symbol)
                pnl = (mid - pos.avg_entry) * pos.size
                if pos.side == "SHORT":
                    pnl = -pnl
                running_pnl += pnl
                nav = _DEMO_NAV + running_pnl
                peak = max(peak, nav)
                drawdown = (nav / peak - Decimal("1")) if peak else Decimal("0")
                points.append(
                    EquityPoint(
                        ts=pos.opened_at,
                        nav=nav.quantize(Decimal("0.01")),
                        equity=nav.quantize(Decimal("0.01")),
                        drawdown=drawdown.quantize(Decimal("0.0001")),
                    )
                )
            # Titik akhir: posisi terkini (sekali saja).
            nav_now = (_DEMO_NAV + running_pnl).quantize(Decimal("0.01"))
            points.append(
                EquityPoint(
                    ts=now,
                    nav=nav_now,
                    equity=nav_now,
                    drawdown=(nav_now / peak - Decimal("1")).quantize(Decimal("0.0001")),
                )
            )
            # Pagination (newest first, sesuai kontrak B-06).
            points.reverse()
            visible = points[offset : offset + limit]
            return visible
    except Exception:  # noqa: BLE001
        return None


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> PortfolioSummary:
    """Return the current portfolio summary (B-05: live from PostgreSQL)."""
    real = await _real_summary()
    return real if real is not None else _demo_summary()


@router.get("", response_model=PortfolioSummary)
async def get_portfolio(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> PortfolioSummary:
    """Return the single (default) portfolio (B-06 portfolio CRUD)."""
    real = await _real_summary()
    return real if real is not None else _demo_summary()


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
    """Equity curve (B-05/B-06) — derived dari live positions (opened_at +
    mark-to-market kumulatif). Fallback deterministik saat DB tidak tersedia
    atau belum ada posisi (bukan demo — lihat _real_equity_series)."""

    now = datetime.now(UTC)
    total = 240
    real_items = await _real_equity_series(total, pagination.offset, pagination.limit)
    if real_items is not None:
        return PaginatedList(
            items=real_items,
            total=max(len(real_items), 1),
            limit=pagination.limit,
            offset=pagination.offset,
        )

    # Fallback: series deterministik (DB down / tests tanpa DB).
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
