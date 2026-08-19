"""Research router (19 Aug 2026 — Phase 5).

Halaman Paper Trading / Research: bandingkan PAPER (simulasi/sandbox)
vs REAL (akun live MT5). Memisahkan order paper (portfolio_id="paper")
dari order real (portfolio_id="default"), dan posisi (book="paper" vs
"default"). Tujuan: menjawab "apakah keputusan AI bagus tapi eksekusi
real berbeda?"
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.data.models import Order, Position
from lumine.data.session import get_sessionmaker

router = APIRouter(tags=["research"])


async def _book_metrics(
    session: AsyncSession,
    *,
    order_portfolio: str,
    position_book: str,
) -> dict[str, Any]:
    """Aggregate metrics untuk satu 'book' (paper/real)."""
    order_count = (
        await session.execute(
            select(func.count(Order.order_id)).where(
                Order.portfolio_id == order_portfolio,
                Order.status == "filled",
            )
        )
    ).scalar_one()

    pos_rows = (
        await session.execute(select(Position).where(Position.book == position_book))
    ).scalars().all()
    closed = [p for p in pos_rows if p.status == "closed"]
    win = sum(1 for p in closed if (p.mt5_profit or 0) > 0)
    realized_pnl = sum(float(p.mt5_profit or 0) for p in closed)

    return {
        "orders_filled": int(order_count),
        "positions_total": len(pos_rows),
        "positions_closed": len(closed),
        "win_rate_pct": round(100.0 * win / len(closed), 1) if closed else 0.0,
        "realized_pnl": round(realized_pnl, 2),
    }


@router.get("/summary")
async def research_summary(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> dict[str, Any]:
    """Paper vs Real comparison summary."""
    async with get_sessionmaker()() as session:
        paper = await _book_metrics(
            session, order_portfolio="paper", position_book="paper"
        )
        real = await _book_metrics(
            session, order_portfolio="default", position_book="default"
        )
    return {"paper": paper, "real": real}
