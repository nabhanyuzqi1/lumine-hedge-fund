# Copyright (c) 2026 Lumine. All rights reserved.
"""SMC (Smart Money Concepts) Analyst agent (D4-2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lumine.autogen_pipeline.agents._base import run_analyst

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.gateway import Gateway
    from lumine.prompts.registry import Registry

_SUB_ROLE = "smc_analyst"


async def run_smc_analyst(  # noqa: PLR0913 — analyst stage contract is fixed
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
):
    """Run the SMC Analyst stage (D4-2)."""
    return await run_analyst(
        _SUB_ROLE,
        gateway=gateway,
        registry=registry,
        lineage_id=lineage_id,
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        model_version_id=model_version_id,
        idempotency_key=idempotency_key,
        variables=variables,
        session=session,
        spend=spend,
        prompt_version_id=prompt_version_id,
    )


__all__ = ("run_smc_analyst",)
