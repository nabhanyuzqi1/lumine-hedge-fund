# Copyright (c) 2026 Lumine. All rights reserved.
"""Investment Committee Forum agent (D4-4).

Single-turn: receives the four analyst outputs as static context and
emits an ``ic_output`` recommendation (consensus / split / no-consensus
are all expressible through the schema — HOLD/REJECT plus dissent).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lumine.autogen_pipeline._base import StageContext, StageResult, run_llm_stage

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.gateway import Gateway
    from lumine.prompts.registry import Registry


async def run_ic_forum(  # noqa: PLR0913 — stage contract is fixed
    *,
    gateway: Gateway,
    registry: Registry,
    lineage_id: uuid.UUID,
    workflow_run_id: str,
    stage_run_id: str,
    model_version_id: uuid.UUID,
    idempotency_key: str,
    symbol: str,
    decision_ts: str,
    analyst_inputs: list[dict[str, object]],
    debate_summary: str = "",
    session: AsyncSession | None = None,
    spend: Mapping[str, float] | None = None,
    prompt_version_id: uuid.UUID | None = None,
) -> StageResult:
    """Run the IC Forum stage and return its validated ``ic_output``.

    ``analyst_inputs`` is a list of the four validated analyst outputs
    (original, pre-debate) serialized into the prompt as static context.
    """
    ctx = StageContext(
        role="ic_forum",
        prompt_sub_role="ic_forum",
        prompt_version="v1",
        model_version_id=model_version_id,
        lineage_id=lineage_id,
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        variables={
            "symbol": symbol,
            "decision_ts": decision_ts,
            "analyst_inputs": json.dumps(analyst_inputs, indent=2),
            "debate_summary": debate_summary,
        },
        idempotency_key=idempotency_key,
        prompt_version_id=prompt_version_id,
    )
    return await run_llm_stage(gateway, registry, ctx, session=session, spend=spend)


__all__ = ("run_ic_forum",)
