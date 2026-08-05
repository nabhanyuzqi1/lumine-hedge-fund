# Copyright (c) 2026 Lumine. All rights reserved.
"""CIO Proposer agent (D4-6/D4-7).

Single-turn: receives the IC output plus all four original analyst
outputs and produces the full ``proposal_v1`` JSON that is pinned to
``lineage_records.proposal``. May override the IC recommendation with a
documented ``override_reason``.
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


async def run_cio_proposer(  # noqa: PLR0913 — stage/pin contract is fixed
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
    ic_output: dict[str, object],
    analyst_inputs: list[dict[str, object]],
    portfolio_context: dict[str, object],
    policy_version_id: str,
    model_version_ids: dict[str, str],
    prompt_version_ids: dict[str, str],
    debate_held: bool,
    session: AsyncSession | None = None,
    spend: Mapping[str, float] | None = None,
    prompt_version_id: uuid.UUID | None = None,
) -> StageResult:
    """Run the CIO Proposer stage and return the validated proposal.

    The serialized version pins are passed to the prompt (the schema
    requires them) but the orchestrator re-stamps the authoritative pins
    on the parsed output — the LLM's echoed pins are never trusted as
    the source of truth.
    """
    ctx = StageContext(
        role="cio_proposer",
        prompt_sub_role="cio_proposer",
        prompt_version="v1",
        model_version_id=model_version_id,
        lineage_id=lineage_id,
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        variables={
            "symbol": symbol,
            "decision_ts": decision_ts,
            "ic_output": json.dumps(ic_output, indent=2),
            "analyst_inputs": json.dumps(analyst_inputs, indent=2),
            "portfolio_context": json.dumps(portfolio_context, indent=2),
            "policy_version_id": policy_version_id,
            "model_version_ids": json.dumps(model_version_ids),
            "prompt_version_ids": json.dumps(prompt_version_ids),
            "debate_held": "true" if debate_held else "false",
        },
        idempotency_key=idempotency_key,
        prompt_version_id=prompt_version_id,
    )
    return await run_llm_stage(gateway, registry, ctx, session=session, spend=spend)


__all__ = ("run_cio_proposer",)
