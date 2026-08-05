# Copyright (c) 2026 Lumine. All rights reserved.
"""Debate trigger + bounded moderator round (D4-5, D3-7).

The trigger is deterministic system code (orchestration.md): debate fires
when predicted IC confidence is below a threshold OR the inter-analyst
disagreement score exceeds a threshold. Both thresholds come from
``policy_versions``. The moderator round is a single bounded LLM call;
its output is ``debate_output`` (summary + consensus_direction), and per
D3-7 only the ``debate_held`` flag plus the summary (merged into
``ic_output.summary``) are pinned to lineage — the original analyst
outputs are always preserved for reproducibility.
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

WEIGHT_DIRECTION = 0.7
WEIGHT_SPREAD = 0.3


def ic_confidence_predicted(analyst_outputs: list[dict[str, object]]) -> float:
    """Weighted-mean analyst confidence (equal weights) — orchestration.md."""
    if not analyst_outputs:
        return 0.0
    return sum(float(a["confidence"]) for a in analyst_outputs) / len(analyst_outputs)


def disagreement_score(analyst_outputs: list[dict[str, object]]) -> float:
    """Inter-analyst disagreement in [0, 1]; 0 = consensus, 1 = full split.

    ``0.7 * direction_disagreement + 0.3 * confidence_spread`` per
    orchestration.md. Direction disagreement is ``1 - majority_share``;
    confidence spread is ``max(conf) - min(conf)`` (bounded to 1.0).
    """
    if not analyst_outputs:
        return 0.0
    biases = [str(a["bias"]) for a in analyst_outputs]
    confidences = [float(a["confidence"]) for a in analyst_outputs]
    total = len(biases)
    majority = max(biases.count(b) for b in ("bullish", "bearish", "neutral"))
    direction_disagreement = 1.0 - (majority / total)
    confidence_spread = max(confidences) - min(confidences)
    score = WEIGHT_DIRECTION * direction_disagreement + WEIGHT_SPREAD * confidence_spread
    return max(0.0, min(1.0, score))


def should_debate(
    analyst_outputs: list[dict[str, object]],
    *,
    ic_confidence_threshold: float,
    disagreement_threshold: float,
) -> bool:
    """Deterministic debate trigger (orchestration.md formula)."""
    predicted = ic_confidence_predicted(analyst_outputs)
    disagreement = disagreement_score(analyst_outputs)
    return predicted < ic_confidence_threshold or disagreement > disagreement_threshold


async def run_debate(  # noqa: PLR0913 — stage contract is fixed
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
    session: AsyncSession | None = None,
    spend: Mapping[str, float] | None = None,
    prompt_version_id: uuid.UUID | None = None,
) -> StageResult:
    """Run one bounded moderator round (recursion forbidden by prompt).

    Runs before the IC Forum (orchestration.md ordering); the moderator
    synthesizes the analyst outputs, and the IC folds the summary in.
    """
    ctx = StageContext(
        role="debate_moderator",
        prompt_sub_role="debate_moderator",
        prompt_version="v1",
        model_version_id=model_version_id,
        lineage_id=lineage_id,
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        variables={
            "symbol": symbol,
            "decision_ts": decision_ts,
            "analyst_inputs": json.dumps(analyst_inputs, indent=2),
        },
        idempotency_key=idempotency_key,
        prompt_version_id=prompt_version_id,
    )
    return await run_llm_stage(gateway, registry, ctx, session=session, spend=spend)


__all__ = (
    "disagreement_score",
    "ic_confidence_predicted",
    "run_debate",
    "should_debate",
)
