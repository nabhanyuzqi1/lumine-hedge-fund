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


@router.get("/series")
async def research_series(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:portfolio")],
) -> dict[str, Any]:
    """P&L time-series kumulatif per book (paper vs real) + insight."""
    async with get_sessionmaker()() as session:
        rows = (
            (
                await session.execute(
                    select(Position).where(
                        Position.status == "closed",
                        Position.book.in_(["paper", "default"]),
                        Position.mt5_profit.isnot(None),
                    ).order_by(Position.updated_at.asc())
                )
            )
            .scalars()
            .all()
        )
    return _build_series(rows)


def _build_series(rows: list[Any]) -> dict[str, Any]:
    """Pure builder: closed positions -> kumulatif P&L series + insight.

    Dipisahkan dari handler supaya bisa di-unit-test tanpa DB.
    """
    paper_series: list[dict[str, object]] = []
    real_series: list[dict[str, object]] = []
    pnl_paper = 0.0
    pnl_real = 0.0
    for p in rows:
        ts = p.updated_at.isoformat() if p.updated_at else ""
        profit = float(p.mt5_profit or 0)
        if p.book == "paper":
            pnl_paper += profit
            paper_series.append({"ts": ts, "pnl": round(pnl_paper, 2)})
        else:
            pnl_real += profit
            real_series.append({"ts": ts, "pnl": round(pnl_real, 2)})

    delta = round(pnl_real - pnl_paper, 2)
    if pnl_paper > pnl_real:
        summary = (
            f"Paper outperforms Real by ${delta:+.2f}. "
            f"Paper P&L=${pnl_paper:+.2f}, Real P&L=${pnl_real:+.2f}. "
            "Keputusan AI bagus, tapi eksekusi real (slippage/spread) lebih buruk."
        )
    elif pnl_real > pnl_paper:
        summary = (
            f"Real outperforms Paper by ${abs(delta):+.2f}. "
            f"Paper P&L=${pnl_paper:+.2f}, Real P&L=${pnl_real:+.2f}. "
            "Eksekusi real lebih baik dari simulasi."
        )
    else:
        summary = f"Paper dan Real seimbang (${pnl_paper:+.2f})."

    return {
        "paper": paper_series,
        "real": real_series,
        "paper_final_pnl": round(pnl_paper, 2),
        "real_final_pnl": round(pnl_real, 2),
        "insight": summary,
    }
