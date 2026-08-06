# Copyright (c) 2026 Lumine. All rights reserved.
"""LLM-assisted risk assessor — advisory only (D8-7, ADR-0016, D3-9).

The assessor outputs exactly ``{veto, regime_bucket, risk_notes}``.
- ``veto`` is a hard boolean: ``true`` rejects the proposal.
- ``regime_bucket`` selects a deterministic multiplier from
  ``policy_versions.risk_adjustments[regime_bucket][volatility_band]``.
- The LLM never produces a float that reaches ``final_volume`` —
  ``final_volume = base_volume * multiplier`` is always computed here,
  deterministically, from the validated bucket.

``risk-engine-determinism.md`` supersedes the deprecated continuous
multiplier formula; this module implements the replacement contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from lumine.autogen_pipeline._base import StageContext, StageResult, run_llm_stage
from lumine.trade_core.sizing_calculator import clamp_volume

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.gateway import Gateway
    from lumine.prompts.registry import Registry

DEFAULT_BUCKET = "calm"
DEFAULT_MULTIPLIER = Decimal(1)


def resolve_risk_adjustment(
    risk_adjustments: Mapping[str, Any],
    regime_bucket: str,
    volatility_band: str,
) -> Decimal:
    """Deterministic multiplier lookup for ``(regime_bucket, volatility_band)``.

    Missing buckets/bands fail closed to ``1.0`` (no surprise scaling)
    and are flagged via ``unmatched`` in the returned context — they are
    a policy gap, not an LLM decision.
    """
    band_map = risk_adjustments.get(regime_bucket)
    if not isinstance(band_map, Mapping):
        return DEFAULT_MULTIPLIER
    raw = band_map.get(volatility_band)
    if raw is None:
        return DEFAULT_MULTIPLIER
    try:
        return Decimal(str(raw))
    except (TypeError, ValueError, InvalidOperation):
        return DEFAULT_MULTIPLIER


@dataclass(frozen=True)
class AssessedSize:
    """The deterministic sizing outcome after the advisory assessment."""

    final_volume: Decimal
    multiplier: Decimal
    regime_bucket: str
    veto: bool
    risk_notes: str


async def run_risk_assessor(  # noqa: PLR0913 — stage contract is fixed
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
    proposal_summary: dict[str, Any],
    portfolio_context: dict[str, Any],
    volatility_band: str,
    session: AsyncSession | None = None,
    spend: Mapping[str, float] | None = None,
    prompt_version_id: uuid.UUID | None = None,
) -> StageResult:
    """Run the advisory risk assessment stage and return its validated output."""
    ctx = StageContext(
        role="risk_officer",
        prompt_sub_role="risk_assessor",
        prompt_version="v1",
        model_version_id=model_version_id,
        lineage_id=lineage_id,
        workflow_run_id=workflow_run_id,
        stage_run_id=stage_run_id,
        variables={
            "symbol": symbol,
            "decision_ts": decision_ts,
            "proposal_summary": json.dumps(proposal_summary, indent=2),
            "portfolio_context": json.dumps(portfolio_context, indent=2),
            "volatility_band": volatility_band,
        },
        idempotency_key=idempotency_key,
        prompt_version_id=prompt_version_id,
    )
    return await run_llm_stage(gateway, registry, ctx, session=session, spend=spend)


def apply_assessment(  # noqa: PLR0913 — sizing inputs are a fixed contract
    *,
    assessment: dict[str, Any],
    base_volume: Decimal,
    risk_adjustments: Mapping[str, Any],
    volatility_band: str,
    min_volume: Decimal = Decimal("0.01"),
    max_volume: Decimal = Decimal(100),
) -> AssessedSize:
    """Apply the advisory assessment to ``base_volume`` deterministically.

    Raises:
        lumine.shared.errors.RiskRejectionError: ``veto`` is true.
            The orchestrator converts the return value's ``veto`` flag
            instead when it wants a lineage record without raising.

    """
    veto = bool(assessment.get("veto", False))
    regime_bucket = str(assessment.get("regime_bucket", DEFAULT_BUCKET))
    risk_notes = str(assessment.get("risk_notes", ""))
    multiplier = resolve_risk_adjustment(risk_adjustments, regime_bucket, volatility_band)
    final_volume = clamp_volume(base_volume * multiplier, min_volume, max_volume)
    return AssessedSize(
        final_volume=final_volume,
        multiplier=multiplier,
        regime_bucket=regime_bucket,
        veto=veto,
        risk_notes=risk_notes,
    )


__all__ = (
    "DEFAULT_BUCKET",
    "DEFAULT_MULTIPLIER",
    "AssessedSize",
    "apply_assessment",
    "resolve_risk_adjustment",
    "run_risk_assessor",
)
