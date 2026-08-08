# Copyright (c) 2026 Lumine. All rights reserved.
"""Workflow run status and history endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from lumine.api.middleware.auth import AuthenticatedPrincipal, require_scope
from lumine.api.schemas.api import TriggerWorkflowRequest, WorkflowRun
from lumine.api.schemas.common import PaginatedList, Pagination

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=PaginatedList[WorkflowRun])
async def list_workflow_runs(
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
    pagination: Annotated[Pagination, Depends()],
) -> PaginatedList[WorkflowRun]:
    """List workflow runs."""
    now = datetime.now(UTC)
    items: list[WorkflowRun] = [
        WorkflowRun(
            run_id=uuid4(),
            workflow_name="decision_cycle",
            status="completed",
            input_payload={"symbol": "XAUUSD"},
            output_payload={"decision": "hold"},
            started_at=now,
            finished_at=now,
        ),
    ]
    return PaginatedList(
     items=items,
     total=len(items),
     limit=pagination.limit,
     offset=pagination.offset,
 )


@router.get("/{run_id}", response_model=WorkflowRun)
async def get_workflow_run(
    run_id: UUID,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("read:workflows")],
) -> WorkflowRun:
    """Return a single workflow run."""
    now = datetime.now(UTC)
    return WorkflowRun(
        run_id=run_id,
        workflow_name="decision_cycle",
        status="completed",
        input_payload={"symbol": "XAUUSD"},
        output_payload={"decision": "hold"},
        started_at=now,
        finished_at=now,
    )


@router.post("", response_model=WorkflowRun, status_code=201)
async def trigger_workflow(
    request: TriggerWorkflowRequest,
    _principal: Annotated[AuthenticatedPrincipal, require_scope("write:workflows")],
) -> WorkflowRun:
    """Trigger an ad-hoc workflow run."""
    now = datetime.now(UTC)
    return WorkflowRun(
        run_id=uuid4(),
        workflow_name=request.workflow_name,
        status="pending",
        input_payload=request.input_payload,
        started_at=now,
        finished_at=None,
    )
