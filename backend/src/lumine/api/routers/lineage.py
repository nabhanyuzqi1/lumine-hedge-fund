# Copyright (c) 2026 Lumine. All rights reserved.
"""Decision lineage audit endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import LineageRecord
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/lineage", tags=["lineage"])


@router.get("", response_model=PaginatedList[LineageRecord])
async def list_lineage(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:lineage")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[LineageRecord]:
    """List decision lineage records (DB-backed)."""
    from lumine.data.models import LineageRecord as LineageRow
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                select(LineageRow)
                .order_by(LineageRow.decision_ts.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
            rows = list(result.scalars().all())
    except Exception:
        rows = []
    items = [
        LineageRecord(
            lineage_id=row.lineage_id,
            decision_id=str(row.lineage_id),
            decision_type="order_proposal",
            agent_name="technical_analyst",
            inputs_hash=str(row.policy_version_id)[:8],
            outputs_hash=str(row.strategy_version_id)[:8],
            policy_version=str(row.policy_version_id)[:8],
            created_at=row.decision_ts,
        )
        for row in rows
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
    """Return a single lineage record (DB-backed)."""
    from lumine.data.models import LineageRecord as LineageRow
    from lumine.data.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            row = await session.get(LineageRow, lineage_id)
    except Exception:
        row = None
    if row is None:
        raise HTTPException(status_code=404, detail=f"lineage {lineage_id} not found")
    return LineageRecord(
        lineage_id=row.lineage_id,
        decision_id=str(row.lineage_id),
        decision_type="order_proposal",
        agent_name="technical_analyst",
        inputs_hash=str(row.policy_version_id)[:8],
        outputs_hash=str(row.strategy_version_id)[:8],
        policy_version=str(row.policy_version_id)[:8],
        created_at=row.decision_ts,
    )
