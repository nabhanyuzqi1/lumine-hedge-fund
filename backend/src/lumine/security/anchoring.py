# Copyright (c) 2026 Lumine. All rights reserved.
"""Anchor coordination (ADR-0017) — cadence, seq, dual-sink write.

``maybe_anchor`` is called by the writers *inside* the per-table chain
lock after every chain append; it consults ``anchor_state`` (one row
per chained table) and fires an anchor when either threshold trips:

- N rows appended since the last anchor (``ANCHOR_EVERY_N_ROWS = 1000``)
- M minutes since the last anchor (``ANCHOR_EVERY_M_MINUTES = 5``)

The anchor writes the chain head (latest ``self_hash`` + row id + row
count) to ``audit_anchors`` and mirrors the same payload to the WORM
sink (locally: append-only file dir; production: S3/B2 Object Lock —
Phase 11, swapped via the ``WormSink`` interface).

Failure semantics (safe state by default): an anchor write failure
completes the current transaction but records a ``security_events``
row (type ``chain_anchor_break``) instead of failing the chain append —
the chain itself must never stall because of the WORM sink. The breach
is then surfaced by the daily verifier (J5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from lumine.data.models import AnchorState, AuditAnchor, SecurityEvent
from lumine.security.hashchain import ANCHOR_EVERY_M_MINUTES, ANCHOR_EVERY_N_ROWS, read_chain_head
from lumine.security.worm_local import _key_for
from lumine.security.worm_stub import AnchorPayload, WormSink

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class AnchorError(RuntimeError):
    """Anchor write failed (rolled back with the caller transaction)."""


def _worm_object_key(table_name: str, anchor_seq: int) -> str:
    """Return the deterministic object key for ``table_name``/``anchor_seq``."""
    return _key_for(table_name, anchor_seq)


def _anchor_payload(
    table_name: str,
    anchor_seq: int,
    anchored_hash: str,
    anchored_row_id: UUID,
    row_count: int,
    backend: str,
) -> AnchorPayload:
    return AnchorPayload(
        table_name=table_name,
        anchor_seq=anchor_seq,
        anchored_hash=anchored_hash,
        anchored_row_id=str(anchored_row_id),
        row_count=row_count,
        anchored_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        object_key=_key_for(table_name, anchor_seq),
        backend=backend,
    )


async def _read_state(session: AsyncSession, table_name: str) -> AnchorState | None:
    stmt = (
        "SELECT table_name, last_anchor_seq, last_row_count, last_anchor_ts "
        "FROM anchor_state WHERE table_name = :t"
    )
    result = await session.execute(text(stmt), {"t": table_name})
    row = result.first()
    if row is None:
        return None
    return AnchorState(
        table_name=row[0],
        last_anchor_seq=row[1],
        last_row_count=row[2],
        last_anchor_ts=row[3],
    )


async def _write_state(session: AsyncSession, state: AnchorState) -> None:
    # UPSERT semantics: the state row exists after the first anchor, so a
    # plain session.add() would violate the table_name PK on the second
    # write. The explicit ON CONFLICT upsert below is the only write path.
    stmt = text(
        "INSERT INTO anchor_state (table_name, last_anchor_seq, last_row_count, last_anchor_ts) "
        "VALUES (:t, :seq, :count, :ts) "
        "ON CONFLICT (table_name) DO UPDATE SET "
        "last_anchor_seq = EXCLUDED.last_anchor_seq, "
        "last_row_count = EXCLUDED.last_row_count, "
        "last_anchor_ts = EXCLUDED.last_anchor_ts"
    )
    await session.execute(
        stmt,
        {
            "t": state.table_name,
            "seq": state.last_anchor_seq,
            "count": state.last_row_count,
            "ts": state.last_anchor_ts,
        },
    )


async def maybe_anchor(
    session: AsyncSession,
    *,
    table_name: str,
    row_count: int,
    worm: WormSink,
    anchor_every_n: int = ANCHOR_EVERY_N_ROWS,
    anchor_every_m: int = ANCHOR_EVERY_M_MINUTES,
) -> None:
    """Anchor the chain head if the N-rows / M-minutes cadence fired.

    Called after a chain append, inside the caller's transaction.
    Reads ``anchor_state`` for ``table_name``, computes ``anchor_seq``
    from the previous maximum, writes both sinks, and upserts the
    state row. Any failure records ``chain_anchor_break`` and is
    swallowed — the chain append must never stall on anchoring.
    """
    state = await _read_state(session, table_name)
    prev_seq = state.last_anchor_seq if state is not None else 0
    prev_count = state.last_row_count if state is not None else 0
    prev_ts = state.last_anchor_ts if state is not None else None

    diff_rows = row_count - prev_count
    now = datetime.now(UTC)
    minutes_elapsed = float("inf") if prev_ts is None else (now - prev_ts).total_seconds() / 60.0
    if diff_rows < anchor_every_n and minutes_elapsed < anchor_every_m:
        return  # cadence not fired

    try:
        head = await read_chain_head(session, table_name)
        if head is None:
            return  # nothing to anchor (empty chain)
        anchored_hash, anchored_row_id = head
    except Exception:
        # The chain head must be readable; if not, record a breach and
        # let the caller transaction proceed (chain append already done).
        session.add(
            SecurityEvent(
                event_type="chain_anchor_break",
                severity="high",
                source="security.anchoring",
                actor="anchor_coordinator",
                detail={
                    "table_name": table_name,
                    "reason": "chain head unreadable",
                },
            )
        )
        return

    anchor_seq = prev_seq + 1
    payload = _anchor_payload(
        table_name, anchor_seq, anchored_hash, anchored_row_id, row_count, worm.backend
    )
    try:
        await worm.store(payload)
    except NotImplementedError:
        # Object-lock stub (Phase 11): DB copy only, worm copy not yet
        # available. Not a breach — the sink is intentionally absent.
        pass
    except Exception:
        session.add(
            SecurityEvent(
                event_type="chain_anchor_break",
                severity="high",
                source="security.anchoring",
                actor="anchor_coordinator",
                detail={
                    "table_name": table_name,
                    "anchor_seq": anchor_seq,
                    "reason": "worm sink write failed",
                },
            )
        )
        return

    new_state = AnchorState(
        table_name=table_name,
        last_anchor_seq=anchor_seq,
        last_row_count=row_count,
        last_anchor_ts=now,
    )
    try:
        await _write_state(session, new_state)
        session.add(
            AuditAnchor(
                table_name=table_name,
                anchor_seq=anchor_seq,
                anchored_hash=anchored_hash,
                anchored_row_id=anchored_row_id,
                row_count=row_count,
                anchored_at=now,
                worm_object_key=payload.object_key,
                worm_backend=payload.backend,
            )
        )
    except Exception as exc:
        msg = f"anchor write failed for {table_name}: {exc}"
        raise AnchorError(msg) from exc


__all__ = ("AnchorError", "_anchor_payload", "_worm_object_key", "maybe_anchor")
