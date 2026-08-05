# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the daily LLM budget check + circuit breaker (D6-4, cost-control.md).

The check is deterministic system code: read today's accumulated spend
per tier, compare against ``policy_versions.cost`` caps, and apply the
degrade policy in order. Cost incidents degrade deliberately and
audibly — they never hide. No database here: spend is injected as a
mapping of tier → USD; the SQL-backed aggregation is exercised at
integration level.
"""

from __future__ import annotations

from typing import Any

import pytest

from lumine.llm_gateway.budget import (
    BudgetGate,
    LLMBudgetExceededError,
    budget_decision,
)
from lumine.llm_gateway.types import ModelTier
from lumine.shared.errors import LLMBudgetExceededError as SharedLLMBudgetExceededError

# ── helpers ──────────────────────────────────────────────────────────────────


def _policy(
    *,
    daily_cap_usd: dict[str, float] | None = None,
    degrade_order: list[str] | None = None,
    protected_roles: list[str] | None = None,
    soft_warn_pct: float = 0.8,
) -> dict[str, Any]:
    """Full policy dict; the cost section lives in ``policy_versions.cost`` (cost-control.md)."""
    return {
        "cost": {
            "daily_cap_usd": daily_cap_usd
            or {
                "cost-efficient": 10.0,
                "context-rich": 20.0,
                "strongest": 30.0,
                "global": 50.0,
            },
            "degrade_order": degrade_order
            or ["journal", "research_sandbox", "analyst_rerun", "debate"],
            "protected_roles": protected_roles
            or [
                "technical_analyst",
                "macro_analyst",
                "news_analyst",
                "smc_analyst",
                "ic_forum",
                "cio_proposer",
            ],
            "soft_warn_pct": soft_warn_pct,
        }
    }


def _spend(
    cost_efficient: float = 0.0, context_rich: float = 0.0, strongest: float = 0.0
) -> dict[str, float]:
    """Today's accumulated spend per tier (USD)."""
    return {
        "cost-efficient": cost_efficient,
        "context-rich": context_rich,
        "strongest": strongest,
    }


# ── budget_decision (pure function) ───────────────────────────────────────────


class TestBudgetDecision:
    def test_under_all_caps_returns_allow(self) -> None:
        d = budget_decision(
            policy=_policy(),
            spend=_spend(cost_efficient=1.0, context_rich=2.0),
            tier=ModelTier.COST_EFFICIENT,
            role="technical_analyst",
        )
        assert d.action == "allow"
        assert d.degraded is False

    def test_tier_cap_breach_degrades_journal_first(self) -> None:
        # journal is first in degrade_order; it must be blocked while
        # the live pipeline keeps running.
        d = budget_decision(
            policy=_policy(
                daily_cap_usd={
                    "cost-efficient": 10.0,
                    "context-rich": 20.0,
                    "strongest": 30.0,
                    "global": 50.0,
                }
            ),
            spend=_spend(cost_efficient=11.0),  # cap breached
            tier=ModelTier.COST_EFFICIENT,
            role="journal",
        )
        assert d.action == "block"
        assert d.degraded is True

    def test_global_cap_breach_blocks_non_protected_role(self) -> None:
        d = budget_decision(
            policy=_policy(),
            spend=_spend(cost_efficient=60.0),  # > global 50.0
            tier=ModelTier.COST_EFFICIENT,
            role="research_sandbox",
        )
        assert d.action == "block"
        assert d.degraded is True

    def test_global_cap_breach_protects_live_pipeline(self) -> None:
        d = budget_decision(
            policy=_policy(),
            spend=_spend(cost_efficient=60.0),
            tier=ModelTier.COST_EFFICIENT,
            role="technical_analyst",
        )
        assert d.action == "allow"
        assert d.degraded is False

    def test_tier_cap_breach_skips_escalation_for_analyst(self) -> None:
        # analyst_rerun is in degrade_order; when tier is breached the
        # analyst call still runs (protected) but marks degraded.
        d = budget_decision(
            policy=_policy(),
            spend=_spend(cost_efficient=11.0),
            tier=ModelTier.COST_EFFICIENT,
            role="analyst_rerun",
        )
        assert d.action == "allow"
        assert d.degraded is True

    def test_soft_warn_pct_sets_warn_flag(self) -> None:
        d = budget_decision(
            policy=_policy(soft_warn_pct=0.8),
            spend=_spend(cost_efficient=8.5),  # 85% of 10.0
            tier=ModelTier.COST_EFFICIENT,
            role="technical_analyst",
        )
        assert d.action == "allow"
        assert d.warn is True

    def test_unknown_role_defaults_to_blockable(self) -> None:
        d = budget_decision(
            policy=_policy(),
            spend=_spend(cost_efficient=11.0),
            tier=ModelTier.COST_EFFICIENT,
            role="some_new_role",
        )
        assert d.action == "block"

    def test_warn_surfaces_for_non_protected_role(self) -> None:
        # budget.py:159 computes warn for the *general* under-caps path —
        # every test above runs the protected-role warn (budget.py:130).
        # A non-protected role under the tier cap must still warn the
        # same way, with degraded False and reason "under caps".
        d = budget_decision(
            policy=_policy(soft_warn_pct=0.8),
            spend=_spend(cost_efficient=8.5),  # 85% of 10.0, cap not breached
            tier=ModelTier.COST_EFFICIENT,
            role="journal",
        )
        assert d.action == "allow"
        assert d.degraded is False
        assert d.warn is True
        assert d.reason == "under caps"

    def test_empty_policy_disables_all_caps(self) -> None:
        # _policy_cost (budget.py:67-70) and _caps (budget.py:73-78) are
        # empty-safe — a policy without a cost section (or a non-dict
        # daily_cap_usd) means no caps are enforced anywhere. Anchors the
        # current contract: absent caps → every role runs, no warn.
        d = budget_decision(
            policy={},
            spend=_spend(cost_efficient=999.0),
            tier=ModelTier.COST_EFFICIENT,
            role="journal",
        )
        assert d.action == "allow"
        assert d.degraded is False
        assert d.warn is False

    def test_non_dict_daily_cap_is_ignored(self) -> None:
        # _caps (budget.py:76-77): a non-dict daily_cap_usd must be
        # treated as "no caps" rather than crashing with a TypeError.
        d = budget_decision(
            policy={"cost": {"daily_cap_usd": "not-a-dict", "soft_warn_pct": 0.8}},
            spend=_spend(cost_efficient=11.0),
            tier=ModelTier.COST_EFFICIENT,
            role="journal",
        )
        assert d.action == "allow"
        assert d.warn is False

    def test_soft_warn_at_exact_threshold_sets_warn(self) -> None:
        # Boundary contract: warn fires at spend == cap * soft_warn_pct
        # (>= in budget.py, not >) — anchoring so an operator change to
        # strict inequality would be caught here.
        d = budget_decision(
            policy=_policy(soft_warn_pct=0.8),
            spend=_spend(cost_efficient=8.0),  # exactly 80% of 10.0
            tier=ModelTier.COST_EFFICIENT,
            role="technical_analyst",
        )
        assert d.action == "allow"
        assert d.warn is True

    def test_empty_protected_roles_falls_back_to_defaults(self) -> None:
        # budget.py:113-114 — `cost.get("protected_roles") or list(...)`:
        # an explicitly empty list must NOT disable protection; it falls
        # back to the default set. Anchors the fail-safe: ops clearing
        # the list cannot expose the live pipeline to global blocking.
        policy = _policy()
        policy["cost"]["protected_roles"] = []
        d = budget_decision(
            policy=policy,
            spend=_spend(cost_efficient=60.0),  # > global 50.0
            tier=ModelTier.COST_EFFICIENT,
            role="technical_analyst",
        )
        assert d.action == "allow"
        assert d.degraded is False

    def test_empty_degrade_order_falls_back_to_defaults(self) -> None:
        # budget.py:116 — `cost.get("degrade_order") or ...`: an
        # explicitly empty list falls back to the default order, so
        # journal keeps degrading on a tier breach even when ops cleared
        # the field (fail safe — never silently allowed).
        policy = _policy()
        policy["cost"]["degrade_order"] = []
        d = budget_decision(
            policy=policy,
            spend=_spend(cost_efficient=11.0),
            tier=ModelTier.COST_EFFICIENT,
            role="journal",
        )
        assert d.action == "block"
        assert d.degraded is True

    def test_tier_breach_blocks_on_context_rich_and_strongest(self) -> None:
        # _caps (budget.py:73-78) maps every tier key to a float cap —
        # the breach path must apply to context-rich and strongest, not
        # just cost-efficient (the only tier the other breach tests run).
        for tier, spent in (
            (ModelTier.CONTEXT_RICH, 21.0),  # cap 20.0
            (ModelTier.STRONGEST, 31.0),  # cap 30.0
        ):
            d = budget_decision(
                policy=_policy(),
                # spend only the tier under test — any second tier entry
                # would push global_spend toward the 50.0 global cap and
                # hit the global-breach branch (budget.py:133) instead.
                spend={tier.value: spent},
                tier=tier,
                role="debate",
            )
            assert d.action == "block"
            assert d.reason == "tier cap breached"


# ── BudgetGate (class, DB-free: spend injected) ───────────────────────────────


class TestBudgetGate:
    def test_allow_returns_without_raising(self) -> None:
        gate = BudgetGate(policy=_policy())
        gate.check(spend=_spend(), tier=ModelTier.COST_EFFICIENT, role="technical_analyst")

    def test_blocked_role_raises_budget_exceeded(self) -> None:
        gate = BudgetGate(policy=_policy())
        with pytest.raises(LLMBudgetExceededError):
            gate.check(
                spend=_spend(cost_efficient=11.0),
                tier=ModelTier.COST_EFFICIENT,
                role="journal",
            )

    def test_block_message_carries_role_tier_reason(self) -> None:
        # budget.py:211-213 builds the raise message as
        # "{role} blocked: {reason} (tier={tier})" — the audit trail in
        # the exception text, anchored so it cannot drift silently.
        gate = BudgetGate(policy=_policy())
        pattern = r"journal blocked: tier cap breached \(tier=cost-efficient\)"
        with pytest.raises(LLMBudgetExceededError, match=pattern):
            gate.check(
                spend=_spend(cost_efficient=11.0),
                tier=ModelTier.COST_EFFICIENT,
                role="journal",
            )

    def test_shared_error_type_is_subclassed(self) -> None:
        assert issubclass(LLMBudgetExceededError, SharedLLMBudgetExceededError)
