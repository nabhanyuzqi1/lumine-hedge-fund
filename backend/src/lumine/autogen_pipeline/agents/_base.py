# Copyright (c) 2026 Lumine. All rights reserved.
"""Shared single-turn analyst runner (D4-2).

The four analyst sub-roles are identical in mechanics: load the prompt,
call the gateway, validate against ``analyst_output`` schema, write a
reasoning trace. Only the sub-role constant and the domain variables
differ. Each ``agents/<role>_analyst.py`` is a thin wrapper over
:func:`run_analyst` so the role is a first-class, importable symbol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lumine.autogen_pipeline._base import StageContext, StageResult, run_llm_stage

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.gateway import Gateway
    from lumine.prompts.registry import Registry


async def run_analyst(  # noqa: PLR0913 — analyst stage contract is fixed
    sub_role: str,
    *,
    gateway: Gateway,
    registry: Registry,
    lineage_id: uuid.UUID,
    workflow_run_id: str,
    stage_run_id: str,
    model_version_id: uuid.UUID,
    idempotency_key: str,
    variables: Mapping[str, object],
    session: AsyncSession | None = None,
    spend: Mapping[str, float] | None = None,
    prompt_version_id: uuid.UUID | None = None,
) -> StageResult:
    """Run one analyst stage and return the validated output."""
    ctx = StageContext(
        role=sub_role,
        prompt_sub_role=sub_role,
        prompt_version="v1",
        model_version_id=model_version_id,
        lineage_id=lineage_id,
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        variables=dict(variables),
        idempotency_key=idempotency_key,
        prompt_version_id=prompt_version_id,
    )
    return await run_llm_stage(gateway, registry, ctx, session=session, spend=spend)


__all__ = ("run_analyst",)
