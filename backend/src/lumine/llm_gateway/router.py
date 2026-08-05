# Copyright (c) 2026 Lumine. All rights reserved.
"""Static tier routing (D6-1) — model choice is a pure function.

The function takes (role, tier, registry), never an LLM judgment.
Escalation is system code, not an LLM hint: a role runs at its
escalation target only when a deterministic trigger fires
(low confidence, high disagreement, CIO override, near-breach).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lumine.llm_gateway.types import ModelTier

if TYPE_CHECKING:
    from collections.abc import Sequence

# Role → default tier (V1 baseline from model-routing.md).
_ROLE_DEFAULT_TIER: dict[str, ModelTier] = {
    "technical_analyst": ModelTier.COST_EFFICIENT,
    "macro_analyst": ModelTier.COST_EFFICIENT,
    "news_analyst": ModelTier.COST_EFFICIENT,
    "smc_analyst": ModelTier.COST_EFFICIENT,
    "ic_forum": ModelTier.CONTEXT_RICH,
    "cio_proposer": ModelTier.CONTEXT_RICH,
    "risk_assessor": ModelTier.CONTEXT_RICH,
    "journal": ModelTier.COST_EFFICIENT,
    "research_sandbox": ModelTier.COST_EFFICIENT,
}

_UNKNOWN_ROLE_TIER = ModelTier.CONTEXT_RICH

# Tier ranks for ordering: cheapest → strongest.
_TIER_RANK: dict[ModelTier, int] = {
    ModelTier.COST_EFFICIENT: 1,
    ModelTier.CONTEXT_RICH: 2,
    ModelTier.STRONGEST: 3,
}


def tier_rank(tier: ModelTier | str) -> int:
    """Return the numeric rank of a tier (1 = cheapest, 3 = strongest)."""
    return _TIER_RANK[ModelTier(tier)]


def _next_tier(tier: ModelTier) -> ModelTier | None:
    """Return the tier one rank up, or None if already strongest."""
    rank = _TIER_RANK[tier]
    for candidate, candidate_rank in _TIER_RANK.items():
        if candidate_rank == rank + 1:
            return candidate
    return None


def default_tier_for_role(role: str) -> ModelTier:
    """Return the default tier for ``role`` (unknown roles → context-rich)."""
    return _ROLE_DEFAULT_TIER.get(role, _UNKNOWN_ROLE_TIER)


def escalation_decision(
    *,
    role: str,
    low_confidence: bool,
    high_disagreement: bool,
    cio_override: bool,
    near_breach: bool,
) -> ModelTier:
    """Deterministically select the tier for this call.

    Triggers (model-routing.md): low confidence, high disagreement,
    CIO override (highest stakes → strongest), near-breach (whole
    cycle escalates one tier). The result never goes below the role's
    default and never exceeds ``strongest``.
    """
    tier = default_tier_for_role(role)
    if cio_override:
        return ModelTier.STRONGEST
    if low_confidence or high_disagreement or near_breach:
        return _next_tier(tier) or tier
    return tier


__all__: Sequence[str] = (
    "default_tier_for_role",
    "escalation_decision",
    "tier_rank",
)
