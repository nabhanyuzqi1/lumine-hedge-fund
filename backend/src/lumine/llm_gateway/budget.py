# Copyright (c) 2026 Lumine. All rights reserved.
"""Deterministic daily budget check + circuit breaker (D6-4, cost-control.md).

The pre-call gate is code, not an LLM judgment: read today's
accumulated spend per tier, compare against ``policy_versions.cost``
caps, apply the degrade policy in order, and return a decision that
either allows the call (possibly degraded) or blocks it. Cost incidents
degrade deliberately and audibly — they never hide. Blocking raises
``LLMBudgetExceededError`` so the pipeline treats it as a stage
failure, not a silent skip.

Spend is injected as a mapping of tier → USD so the gate is unit-
testable without a database; the SQL-backed running-sum aggregation
lives at integration level.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from lumine.data.models import LLMUsage
from lumine.shared.errors import LLMBudgetExceededError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.types import ModelTier

# Roles that may never be blocked: the primary pass of the live decision
# pipeline at its default tier (cost-control.md "Never degraded/blocked").
# Unknown roles are blockable by default — fail safe.
_DEFAULT_PROTECTED_ROLES: frozenset[str] = frozenset(
    {
        "technical_analyst",
        "macro_analyst",
        "news_analyst",
        "smc_analyst",
        "ic_forum",
        "cio_proposer",
    }
)

# Degrade order from cost-control.md, used when no policy override
# declares one. The list marks which roles are subject to degradation
# at all when a tier cap is breached.
_DEFAULT_DEGRADE_ORDER: tuple[str, ...] = (
    "journal",
    "research_sandbox",
    "analyst_rerun",
    "debate",
)

# Of the degradable roles, only analyst re-runs/escalations degrade to a
# *flagged run* — skip escalation, keep the original tier output, mark
# the lineage `degraded=true` (cost-control.md item 3). Every other
# degradable role blocks for the cycle. If ops removes this role from
# `degrade_order`, it falls back to block — fail safe.
_DEGRADE_AS_FLAGGED_RUN: frozenset[str] = frozenset({"analyst_rerun"})


def _policy_cost(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return the ``cost`` section of a policy dict (empty-safe)."""
    cost = policy.get("cost") or {}
    return cost if isinstance(cost, dict) else {}


def _caps(policy: Mapping[str, Any]) -> dict[str, float]:
    """Return per-tier + global daily caps from the policy cost section."""
    daily = _policy_cost(policy).get("daily_cap_usd") or {}
    if not isinstance(daily, dict):
        return {}
    return {str(k): float(v) for k, v in daily.items()}


@dataclass(frozen=True)
class BudgetDecision:
    """Outcome of the deterministic pre-call check."""

    action: str  # "allow" | "block"
    degraded: bool
    warn: bool
    reason: str


def budget_decision(
    *,
    policy: Mapping[str, Any],
    spend: Mapping[str, float],
    tier: ModelTier,
    role: str,
) -> BudgetDecision:
    """Decide whether the call may proceed (cost-control.md D6-4).

    Checks, in order:
    1. Tier spend ≥ tier cap → degrade policy applies: analyst
       re-runs/escalations keep the original tier output flagged
       ``degraded``; every other non-protected role blocks (fail safe).
    2. Global spend ≥ global cap → only protected roles run (never
       flagged degraded); everything else blocks until reset.
    3. Spend ≥ ``soft_warn_pct`` of the tier cap → warn flag for ops.
    """
    caps = _caps(policy)
    cost = _policy_cost(policy)
    tier_spend = spend.get(tier.value, 0.0)
    global_spend = sum(spend.values())

    protected = frozenset(cost.get("protected_roles") or list(_DEFAULT_PROTECTED_ROLES))
    degrade_order = tuple(cost.get("degrade_order") or _DEFAULT_DEGRADE_ORDER)
    soft_pct = float(cost.get("soft_warn_pct", 0.8))

    tier_cap = caps.get(tier.value)
    tier_breach = tier_cap is not None and tier_spend >= tier_cap
    global_cap = caps.get("global")
    global_breach = global_cap is not None and global_spend >= global_cap

    if role in protected:
        # Never degraded/blocked: the primary pass of the live decision
        # pipeline at its default tier (cost-control.md).
        return BudgetDecision(
            action="allow",
            degraded=False,
            warn=tier_cap is not None and tier_spend >= tier_cap * soft_pct,
            reason="protected role runs",
        )
    if global_breach:
        # Only the protected minimum pipeline runs past the global cap.
        return BudgetDecision(
            action="block",
            degraded=True,
            warn=True,
            reason="global cap breached",
        )
    if tier_breach:
        if role in degrade_order and role in _DEGRADE_AS_FLAGGED_RUN:
            # Analyst re-runs/escalations: skip escalation, keep the
            # original tier output, flag degraded=true (cost-control.md).
            return BudgetDecision(
                action="allow",
                degraded=True,
                warn=True,
                reason="analyst re-run keeps original tier output (degraded)",
            )
        # Degrade-order roles and unknown roles alike block for the
        # cycle — an unknown role must never slip through a breach.
        return BudgetDecision(
            action="block",
            degraded=True,
            warn=True,
            reason="tier cap breached",
        )
    warn = tier_cap is not None and tier_spend >= tier_cap * soft_pct
    return BudgetDecision(
        action="allow",
        degraded=False,
        warn=warn,
        reason="under caps",
    )


async def spend_by_tier(
    session: AsyncSession,
    *,
    start: datetime | None = None,
) -> dict[str, float]:
    """Return today's spend per tier (USD) from ``llm_usage``.

    This is the SQL-backed companion to the injected ``spend`` mapping
    consumed by :func:`budget_decision` — the single source of truth
    promised in cost-control.md (D6-7): budget counters derive from the
    ``llm_usage`` table, no parallel accounting. Rows are filtered to
    ``ts >= start`` (defaults to today's UTC midnight) like the daily
    cap cycle; tiers with no spend are absent from the result.
    """
    since = start or datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await session.execute(
        select(LLMUsage.tier, func.sum(LLMUsage.cost_usd))
        .where(LLMUsage.ts >= since)
        .group_by(LLMUsage.tier)
    )
    return {tier: float(total) for tier, total in rows.all()}


class BudgetGate:
    """Pre-call gate: turn a :class:`BudgetDecision` into an exception.

    Kept as a thin class so callers can carry one gate per policy
    version; the actual decision is the pure function above.
    """

    def __init__(self, policy: Mapping[str, Any]) -> None:
        """Carry one policy version per gate instance."""
        self.policy = policy

    def check(
        self,
        *,
        spend: Mapping[str, float],
        tier: ModelTier,
        role: str,
    ) -> BudgetDecision:
        """Raise :class:`LLMBudgetExceededError` when the call is blocked."""
        decision = budget_decision(policy=self.policy, spend=spend, tier=tier, role=role)
        if decision.action == "block":
            message = f"{role} blocked: {decision.reason} (tier={tier.value})"
            raise LLMBudgetExceededError(message)
        return decision


__all__ = (
    "BudgetDecision",
    "BudgetGate",
    "LLMBudgetExceededError",
    "budget_decision",
    "spend_by_tier",
)
