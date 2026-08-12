# Copyright (c) 2026 Lumine. All rights reserved.
"""Lineage writer — append-only decision records (D3-7, lineage-schema.md).

The write-before-dispatch gate: a proposal may only reach the execution
router after its ``lineage_records`` row is durably committed. Commit
failure is raised and dispatch is skipped — safe state by default.
``lineage_records`` is append-only by design (no UPDATE/DELETE paths
exist); replay and reconciliation read from it.

The record carries all seven version pins (ARCHITECTURE.md Invariant #1):
per-agent model/prompt maps (JSONB) plus policy, strategy, feature,
regime, and calendar scalar FKs. ``proposal`` holds the validated
``proposal_v1`` document (including ``reasoning_trace_ids`` added by the
orchestrator), and ``risk_context`` holds the deterministic verdict plus
the advisory assessment pins (D3-9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from lumine.data.models import LineageRecord
from lumine.security.anchoring import maybe_anchor
from lumine.security.hashchain import (
    CANONICALIZATION_VERSION,
    append_chained,
    orm_payload,
    with_chain_lock,
)
from lumine.security.worm_stub import NullWorm, WormSink

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession


class LineageWriteError(RuntimeError):
    """Lineage commit failed — safe state, dispatch must not proceed."""


@dataclass(frozen=True)
class LineageInputs:
    """Everything pinned into one immutable decision record."""

    book: str
    strategy_id: uuid.UUID
    symbol: str
    side: str
    verdict: str
    size: Decimal | None
    fill_price: Decimal | None
    model_version_ids: Mapping[str, Any]
    prompt_version_ids: Mapping[str, Any]
    policy_version_id: uuid.UUID
    strategy_version_id: uuid.UUID
    # Explicit PK: the orchestrator pre-generates one so reasoning traces
    # and journal rows (written before the record exists, D3-11) link to
    # it. When ``None`` the server default (gen_random_uuid) applies.
    lineage_id: uuid.UUID | None = None
    feature_version_id: uuid.UUID | None = None
    regime_version_id: uuid.UUID | None = None
    calendar_version_id: uuid.UUID | None = None
    trigger: Mapping[str, Any] | None = None
    features: Mapping[str, Any] | None = None
    proposal: Mapping[str, Any] | None = None
    risk_context: Mapping[str, Any] | None = None
    decision_ts: datetime | None = None


async def write_lineage(
    session: AsyncSession,
    inputs: LineageInputs,
    *,
    commit: bool = True,
    worm: WormSink | None = None,
) -> LineageRecord:
    """Append one ``lineage_records`` row.

    When ``commit`` is ``True`` (default) the row is committed before
    returning — the write-before-dispatch gate (D3-7). When ``False``,
    the row is flushed but not committed, so a caller that needs to keep
    the lineage INSERT atomic with follow-on writes (e.g. the
    orchestrator's trace/journal backfill) can drive its own single
    commit and roll everything back together on failure.

    Raises:
        LineageWriteError: the INSERT (or commit, when ``commit=True``)
            failed. Callers must treat this as a hard stop — no dispatch
            may follow a failed lineage write (write-before-dispatch,
            D3-7).

    Returns the persisted record; ``lineage_id`` is ``inputs.lineage_id``
    when supplied, else server-generated (gen_random_uuid).

    """
    record_kwargs: dict[str, Any] = {
        "decision_ts": inputs.decision_ts or datetime.now(UTC),
        "book": inputs.book,
        "strategy_id": inputs.strategy_id,
        "symbol": inputs.symbol,
        "side": inputs.side,
        "verdict": inputs.verdict,
        "size": inputs.size,
        "fill_price": inputs.fill_price,
        "model_version_ids": dict(inputs.model_version_ids),
        "prompt_version_ids": dict(inputs.prompt_version_ids),
        "policy_version_id": inputs.policy_version_id,
        "strategy_version_id": inputs.strategy_version_id,
        "feature_version_id": inputs.feature_version_id,
        "regime_version_id": inputs.regime_version_id,
        "calendar_version_id": inputs.calendar_version_id,
        "trigger": dict(inputs.trigger or {}),
        "features": dict(inputs.features) if inputs.features is not None else None,
        "proposal": dict(inputs.proposal or {}),
        "risk_context": dict(inputs.risk_context or {}),
        # ADR-0017: explicit hash-chain inputs. The PK must be known
        # pre-insert so the hash payload byte-matches the verifier's
        # re-read; the server default cannot apply. ``created_at`` is
        # set explicitly for the same reason (Python default fires at
        # flush time — too late for the pre-insert hash).
        "lineage_id": inputs.lineage_id or uuid4(),
        "created_at": datetime.now(UTC),
        "canonicalization_version": CANONICALIZATION_VERSION,
    }
    record = LineageRecord(**record_kwargs)

    # Chain append is serialized per table: read head + hash + insert
    # must be atomic, or concurrent writers fork the chain (ADR-0017).
    async def _append() -> None:
        prev_hash, self_hash = await append_chained(session, "lineage_records", orm_payload(record))
        record.prev_hash = prev_hash
        record.self_hash = self_hash
        session.add(record)
        # ADR-0017: anchor cadence inside the same chain-lock transaction
        # so the head read + state upsert cannot race concurrent writers.
        # Default sink is the Phase-11 stub (DB copy only).
        await maybe_anchor(session, table_name="lineage_records", row_count=1, worm=worm or NullWorm())

    await with_chain_lock(session, "lineage_records", _append)
    try:
        if commit:
            await session.commit()
        else:
            # Flush so the row (and its pre-generated PK) is visible
            # inside the caller's transaction; the caller owns the
            # final commit/rollback.
            await session.flush()
    except Exception as exc:
        await session.rollback()
        message = f"lineage commit failed for {inputs.symbol}: {exc}"
        raise LineageWriteError(message) from exc
    await session.refresh(record)
    return record


__all__ = ("LineageInputs", "LineageWriteError", "write_lineage")
