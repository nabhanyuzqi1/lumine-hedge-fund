# Copyright (c) 2026 Lumine. All rights reserved.
"""Reasoning trace storage (D7-11, D3-11).

Every LLM call in the decision pipeline writes exactly one
``reasoning_traces`` row: the full prompt sent, the raw model response,
the parsed output, and both hashes. This gives legal/audit the "why"
behind a decision, not just the "what" (ADR-0029).

Per D3-11 each row is written in its own transaction, synchronously,
immediately after the call returns and the output is validated, and a
write failure blocks stage advance. ``reasoning_traces`` is referenced
from ``lineage_records.proposal.reasoning_trace_ids``.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from lumine.data.models import ReasoningTrace
from lumine.security.hashchain import (
    CANONICALIZATION_VERSION,
    append_chained,
    orm_payload,
    with_chain_lock,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class ReasoningTraceError(RuntimeError):
    """Trace write failure — blocks stage advance (D7-11)."""


def _sha256_hex(data: str) -> str:
    """Return the hex SHA-256 of ``data`` (the trace/response hash)."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def write_trace(
    session: AsyncSession,
    *,
    workflow_run_id: str,
    stage_run_id: str,
    role: str,
    model_version_id: uuid.UUID,
    prompt_sent: str,
    response_raw: str,
    parsed_output: dict[str, Any] | None,
    prompt_hash: str,
    lineage_id: uuid.UUID | None = None,
    prompt_version_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Append one ``reasoning_traces`` row and commit (own transaction).

    The row is committed before the stage advances. Commit failure is
    raised as :class:`ReasoningTraceError`, blocking progress (safe-state
    by default).

    Returns the new ``trace_id``.
    """
    response_hash = _sha256_hex(response_raw)
    # ADR-0017: every persisted column must be known pre-insert so the
    # hash payload byte-matches the verifier's re-read — PK, ``ts`` and
    # ``canonicalization_version`` are set explicitly (no Python/DB
    # defaults).
    trace = ReasoningTrace(
        trace_id=uuid4(),
        ts=datetime.now(UTC),
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        role=role,
        model_version_id=model_version_id,
        prompt_version_id=prompt_version_id,
        prompt_sent=prompt_sent,
        response_raw=response_raw,
        parsed_output=parsed_output,
        prompt_hash=prompt_hash,
        response_hash=response_hash,
        lineage_id=lineage_id,
        canonicalization_version=CANONICALIZATION_VERSION,
    )

    # Chain append is serialized per table: read head + hash + insert
    # must be atomic, or concurrent writers fork the chain (ADR-0017).
    async def _append() -> None:
        prev_hash, self_hash = await append_chained(session, "reasoning_traces", orm_payload(trace))
        trace.prev_hash = prev_hash
        trace.self_hash = self_hash
        session.add(trace)

    await with_chain_lock(session, "reasoning_traces", _append)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        message = f"failed to persist reasoning trace for {role}: {exc}"
        raise ReasoningTraceError(message) from exc
    await session.refresh(trace)
    return trace.trace_id


__all__ = ("ReasoningTraceError", "write_trace")
