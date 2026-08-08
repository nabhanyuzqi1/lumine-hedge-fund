# Copyright (c) 2026 Lumine. All rights reserved.
"""Decision lineage audit endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import LineageRecord
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/lineage", tags=["lineage"])


@router.get("", response_model=PaginatedList[LineageRecord])
async def list_lineage(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:lineage")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[LineageRecord]:
    """List decision lineage records."""
    now = datetime.now(UTC)
    items: list[LineageRecord] = [
        LineageRecord(
            lineage_id=uuid4(),
            decision_id="dec-1",
            decision_type="order_proposal",
            agent_name="technical_analyst",
            inputs_hash="a1b2",
            outputs_hash="c3d4",
            policy_version="v1.2.0",
            created_at=now,
        ),
    ]
    return PaginatedList(
        items=items,
        total=len(items),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{lineage_id}", response_model=LineageRecord)
async def get_lineage_record(
    lineage_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:lineage")],
) -> LineageRecord:
    """Return a single lineage record."""
    return LineageRecord(
        lineage_id=lineage_id,
        decision_id="dec-1",
        decision_type="order_proposal",
        agent_name="technical_analyst",
        inputs_hash="a1b2",
        outputs_hash="c3d4",
        policy_version="v1.2.0",
        created_at=datetime.now(UTC),
    )
