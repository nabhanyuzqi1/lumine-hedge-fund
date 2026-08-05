# Copyright (c) 2026 Lumine. All rights reserved.
"""Workflow journal — append-only step log for decision cycles (D7 observability).

One ``workflow_journal`` row per checkpoint/stage outcome, written in its
own transaction. The orchestrator emits ANALYSTS_VALIDATED,
DEBATE_VALIDATED, IC_VALIDATED, PROPOSAL_VALIDATED checkpoints plus a
terminal row for the cycle verdict, so an operator can reconstruct any
cycle's progression and failure point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lumine.data.models import WorkflowJournal

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class JournalWriteError(RuntimeError):
    """Journal write failed — treated as a cycle failure (safe state)."""


async def log_step(  # noqa: PLR0913 — journal row contract is fixed
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
    row = WorkflowJournal(
        workflow_id=workflow_id,
        step_name=step_name,
        status=status,
        duration_ms=duration_ms,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        error_message=error_message,
        lineage_id=lineage_id,
    )
    session.add(row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        message = f"journal write failed for {workflow_id}/{step_name}: {exc}"
        raise JournalWriteError(message) from exc


__all__ = ("JournalWriteError", "log_step")
