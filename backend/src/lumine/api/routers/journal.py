"""Trade journal and reflection endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import JournalEntry
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("")
async def list_journal_entries(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:journal")],
    pagination: Annotated[Pagination, Depends()],
    portfolio_id: str | None = Query(default=None),
) -> PaginatedList[JournalEntry]:
    """List trade journal entries (DB-backed: orders + workflow_journal).

    18 Aug 2026: journal kini gabung orders (0 karena fresh start) +
    workflow_journal (204 step AutoGen — analyst/IC/CIO/risk executions).
    Filter portfolio_id opsional. Metadata lengkap (portfolio_id, symbol,
    side, volume, price, status) untuk UI.
    """
    from lumine.data.models import Order, WorkflowJournal
    from lumine.data.session import get_sessionmaker

    items: list[JournalEntry] = []
    try:
        async with get_sessionmaker()() as session:
            # 1) Orders (trading eksekusi nyata).
            q = select(Order).order_by(Order.created_at.desc())
            if portfolio_id:
                q = q.where(Order.portfolio_id == portfolio_id)
            orders = list((await session.execute(q.limit(pagination.limit))).scalars().all())
            for order in orders:
                items.append(
                    JournalEntry(
                        entry_id=order.order_id,
                        trade_id=order.order_id,
                        agent_name="execution_controller",
                        reflection=(
                            f"{order.side.upper()} {order.volume} {order.symbol} "
                            f"{'@ ' + str(order.price) if order.price else ''} — {order.status}"
                        ).strip(),
                        # 22 Aug 2026: alasan keputusan AI (kenapa buy/sell/hold)
                        # langsung dari orders.ai_reason (decision engine).
                        reason=order.ai_reason or None,
                        decision=(order.side or "").upper(),
                        lesson=f"mt5_ticket={order.mt5_ticket}" if order.mt5_ticket else "pending execution",
                        created_at=order.created_at,
                        portfolio_id=order.portfolio_id,
                        symbol=order.symbol,
                        side=order.side,
                        volume=float(order.volume) if order.volume else None,
                        price=float(order.price) if order.price else None,
                        status=order.status,
                    )
                )

            # 2) Workflow journal (AutoGen step log — analyst/IC/risk).
            wq = select(WorkflowJournal).order_by(WorkflowJournal.ts.desc())
            wf = list((await session.execute(wq.limit(pagination.limit))).scalars().all())
            for step in wf:
                out = step.output_snapshot or {}
                symbol = out.get("symbol") or (step.input_snapshot or {}).get("symbol") or "XAUUSD"
                # 22 Aug 2026: reason dari verdict/summary output agent
                # (kenapa analyst/CIO memilih arah) — fallback ke reflection.
                out_reason = (
                    out.get("rationale")
                    or out.get("reason")
                    or out.get("summary")
                    or out.get("verdict_reason")
                )
                out_decision = (
                    out.get("decision")
                    or out.get("direction")
                    or out.get("action")
                    or out.get("verdict")
                )
                items.append(
                    JournalEntry(
                        entry_id=step.id,
                        trade_id=None,
                        agent_name=step.step_name,
                        reflection=(
                            f"{step.step_name} [{step.status}]"
                            + (f" {step.duration_ms}ms" if step.duration_ms else "")
                            + (f" — {symbol}" if symbol else "")
                            + (f" — {step.error_message[:100]}" if step.error_message else "")
                        ),
                        reason=str(out_reason)[:400] if out_reason else None,
                        decision=str(out_decision)[:40] if out_decision else None,
                        lesson=f"workflow={step.workflow_id}",
                        created_at=step.ts,
                        portfolio_id=None,
                        symbol=symbol,
                        status=step.status,
                    )
                )
    except Exception:
        items = []  # DB error → kosong (tidak crash)

    # Gabung + urut created_at desc, batasi pagination.
    items.sort(key=lambda e: e.created_at, reverse=True)
    total = len(items)
    page = items[pagination.offset : pagination.offset + pagination.limit]
    return PaginatedList(
        items=page,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        has_more=pagination.offset + pagination.limit < total,
    )


@router.get("/{entry_id}")
async def get_journal_entry(
    entry_id: str,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:journal")],
) -> JournalEntry:
    """Return a single journal entry (dari gabungan orders + workflow)."""
    from fastapi import HTTPException

    from lumine.data.models import Order, WorkflowJournal
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            try:
                from uuid import UUID as _UUID

                oid = _UUID(entry_id)
            except ValueError:
                oid = None
            if oid is not None:
                order = (
                    await session.execute(select(Order).where(Order.order_id == oid))
                ).scalar_one_or_none()
                if order is not None:
                    return JournalEntry(
                        entry_id=order.order_id,
                        trade_id=order.order_id,
                        agent_name="execution_controller",
                        reflection=(
                            f"{order.side.upper()} {order.volume} {order.symbol} "
                            f"{'@ ' + str(order.price) if order.price else ''} — {order.status}"
                        ).strip(),
                        lesson=f"mt5_ticket={order.mt5_ticket}" if order.mt5_ticket else "pending execution",
                        created_at=order.created_at,
                        portfolio_id=order.portfolio_id,
                        symbol=order.symbol,
                        side=order.side,
                        volume=float(order.volume) if order.volume else None,
                        price=float(order.price) if order.price else None,
                        status=order.status,
                    )
                step = (
                    await session.execute(select(WorkflowJournal).where(WorkflowJournal.id == oid))
                ).scalar_one_or_none()
                if step is not None:
                    return JournalEntry(
                        entry_id=step.id,
                        trade_id=None,
                        agent_name=step.step_name,
                        reflection=f"{step.step_name} [{step.status}]",
                        lesson=f"workflow={step.workflow_id}",
                        created_at=step.ts,
                        symbol=(step.output_snapshot or {}).get("symbol") or "XAUUSD",
                        status=step.status,
                    )
    except Exception:  # nosec B110 — entry tidak ditemukan → 404 di bawah
        pass
    raise HTTPException(status_code=404, detail="journal entry not found")
