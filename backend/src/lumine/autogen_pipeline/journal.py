# Copyright (c) 2026 Lumine. All rights reserved.
"""Workflow journal — append-only step log for decision cycles (D7 observability).

One ``workflow_journal`` row per checkpoint/stage outcome, written in its
own transaction. The orchestrator emits ANALYSTS_VALIDATED,
DEBATE_VALIDATED, IC_VALIDATED, PROPOSAL_VALIDATED checkpoints plus a
terminal row for the cycle verdict, so an operator can reconstruct any
cycle's progression and failure point.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from lumine.data.models import WorkflowJournal
from lumine.security.hashchain import (
    CANONICALIZATION_VERSION,
    append_chained,
    orm_payload,
    with_chain_lock,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class JournalWriteError(RuntimeError):
    """Journal write failed — treated as a cycle failure (safe state)."""


async def log_step(
    session: AsyncSession,
    *,
    workflow_id: str,
    step_name: str,
    status: str,
    duration_ms: int | None = None,
    input_snapshot: dict[str, Any] | None = None,
    output_snapshot: dict[str, Any] | None = None,
    error_message: str | None = None,
    lineage_id: uuid.UUID | None = None,
) -> None:
    """Append one journal row and commit (own transaction)."""
    # ADR-0017: every persisted column must be known pre-insert so the
    # hash payload byte-matches the verifier's re-read — PK, ``ts`` and
    # ``canonicalization_version`` are set explicitly (no Python/DB
    # defaults).
    row = WorkflowJournal(
        id=uuid4(),
        ts=datetime.now(UTC),
        workflow_id=workflow_id,
        step_name=step_name,
        status=status,
        duration_ms=duration_ms,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        error_message=error_message,
        lineage_id=lineage_id,
        canonicalization_version=CANONICALIZATION_VERSION,
    )

    # Chain append is serialized per table: read head + hash + insert
    # must be atomic, or concurrent writers fork the chain (ADR-0017).
    async def _append() -> None:
        prev_hash, self_hash = await append_chained(session, "workflow_journal", orm_payload(row))
        row.prev_hash = prev_hash
        row.self_hash = self_hash
        session.add(row)

    await with_chain_lock(session, "workflow_journal", _append)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        message = f"journal write failed for {workflow_id}/{step_name}: {exc}"
        raise JournalWriteError(message) from exc


__all__ = ("JournalWriteError", "log_step")
