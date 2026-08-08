# Copyright (c) 2026 Lumine. All rights reserved.
"""Trade journal and reflection endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import JournalEntry
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=PaginatedList[JournalEntry])
async def list_journal_entries(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:journal")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[JournalEntry]:
    """List trade journal entries."""
    now = datetime.now(UTC)
    items: list[JournalEntry] = [
        JournalEntry(
            entry_id=uuid4(),
            trade_id=uuid4(),
            agent_name="performance_reviewer",
            reflection="Entry aligned with trend but stop was too tight.",
            lesson="Widen initial stop to 1.5 ATR in volatile sessions.",
            created_at=now,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{entry_id}", response_model=JournalEntry)
async def get_journal_entry(
    entry_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:journal")],
) -> JournalEntry:
    """Return a single journal entry."""
    return JournalEntry(
        entry_id=entry_id,
        trade_id=uuid4(),
        agent_name="performance_reviewer",
        reflection="Entry aligned with trend but stop was too tight.",
        lesson="Widen initial stop to 1.5 ATR in volatile sessions.",
        created_at=datetime.now(UTC),
    )
