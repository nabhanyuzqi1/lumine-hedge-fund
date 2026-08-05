# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for llm_gateway registry resolution + static tier routing.

Covers: ``ModelTier`` enum, ``resolve_model`` (production-only, retired
fail-fast, unknown id), role→tier default map (D6-1), and deterministic
escalation trigger selection. No database here — resolution runs against
an injected in-memory registry triple; the DB-backed loader is exercised
at integration level.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from lumine.llm_gateway.registry import ModelRegistry, resolve_model
from lumine.llm_gateway.router import (
    default_tier_for_role,
    escalation_decision,
    tier_rank,
)
from lumine.llm_gateway.types import ModelRoute, ModelTier
from lumine.shared.errors import ModelUnavailableError

# ── ModelTier enum ─────────────────────────────────────────────────────────────


class TestModelTier:
    def test_enum_values_match_db_enum(self) -> None:
        assert {t.value for t in ModelTier} == {
            "cost-efficient",
            "context-rich",
            "strongest",
        }

    def test_tier_rank_orders_cheapest_first(self) -> None:
        assert tier_rank(ModelTier.COST_EFFICIENT) < tier_rank(ModelTier.CONTEXT_RICH)
        assert tier_rank(ModelTier.CONTEXT_RICH) < tier_rank(ModelTier.STRONGEST)

    def test_tier_rank_accepts_string(self) -> None:
        assert tier_rank("context-rich") == 2


# ── resolve_model ──────────────────────────────────────────────────────────────


def _model(
    model_id: str,
    *,
    tier: str = "cost-efficient",
    status: str = "production",
    provider: str = "deepseek",
    version: str = "v1",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "version": version,
        "status": status,
        "provider": provider,
        "model_id": model_id,
        "tier": tier,
        "context_window": 128000,
        "params": {"temperature": 0.2} if params is None else params,
    }


def _registry(*rows: dict[str, Any]) -> ModelRegistry:
    return ModelRegistry({r["id"]: r for r in rows})


class TestResolveModel:
    def test_resolves_production_row_to_route(self) -> None:
        row = _model("deepseek-v4")
        route = resolve_model(_registry(row), row["id"])
        assert isinstance(route, ModelRoute)
        assert route.model == "deepseek-v4"
        assert route.tier is ModelTier.COST_EFFICIENT
        assert route.provider == "deepseek"

    def test_route_carries_params_and_context_window(self) -> None:
        row = _model("deepseek-v4", params={"temperature": 0.2})
        route = resolve_model(_registry(row), row["id"])
        assert route.params["temperature"] == 0.2
        assert route.context_window == 128000

    def test_retired_row_fails_fast(self) -> None:
        row = _model("gpt-old", status="retired")
        with pytest.raises(ModelUnavailableError, match="retired"):
            resolve_model(_registry(row), row["id"])

    def test_sandbox_and_staging_not_routable_in_live_pipeline(self) -> None:
        for status in ("sandbox", "staging"):
            row = _model("experimental", status=status)
            with pytest.raises(ModelUnavailableError, match="production"):
                resolve_model(_registry(row), row["id"])

    def test_unknown_id_raises(self) -> None:
        with pytest.raises(ModelUnavailableError, match="unknown"):
            resolve_model(_registry(), uuid.uuid4())

    def test_route_pins_version_and_id(self) -> None:
        row = _model("deepseek-v4")
        route = resolve_model(_registry(row), row["id"])
        assert route.model_version_id == row["id"]
        assert route.version == "v1"

    def test_null_params_map_to_empty_dict(self) -> None:
        # _to_route (registry.py:52) tolerates a row with params=None —
        # a model_versions row may carry no params → route.params == {}.
        row = {
            "id": uuid.uuid4(),
            "version": "v1",
            "status": "production",
            "provider": "deepseek",
            "model_id": "deepseek-v4",
            "tier": "cost-efficient",
            "context_window": 128000,
            "params": None,
        }
        route = resolve_model(_registry(row), row["id"])
        assert route.params == {}


# ── ModelRegistry (injected in-memory map) ────────────────────────────────────


class TestModelRegistry:
    def test_len_counts_registered_rows(self) -> None:
        reg = _registry(_model("a"), _model("b"), _model("c"))
        assert len(reg) == 3

    def test_get_returns_none_for_unknown_id(self) -> None:
        assert _registry().get(uuid.uuid4()) is None


# ── role → default tier map (D6-1) ────────────────────────────────────────────


class TestRoleTierMap:
    def test_analysts_default_to_cost_efficient(self) -> None:
        for role in ("technical_analyst", "macro_analyst", "news_analyst", "smc_analyst"):
            assert default_tier_for_role(role) is ModelTier.COST_EFFICIENT

    def test_ic_and_cio_default_to_context_rich(self) -> None:
        for role in ("ic_forum", "cio_proposer", "risk_assessor"):
            assert default_tier_for_role(role) is ModelTier.CONTEXT_RICH

    def test_journal_defaults_to_cost_efficient(self) -> None:
        assert default_tier_for_role("journal") is ModelTier.COST_EFFICIENT

    def test_unknown_role_defaults_to_context_rich(self) -> None:
        # Unknown roles are unknown risk — never the cheapest tier.
        assert default_tier_for_role("unknown_role") is ModelTier.CONTEXT_RICH

    def test_escalation_target_one_tier_up(self) -> None:
        # escalation_decision returns the next tier when a trigger fires.
        decision = escalation_decision(
            role="technical_analyst",
            low_confidence=True,
            high_disagreement=False,
            cio_override=False,
            near_breach=False,
        )
        assert decision == ModelTier.CONTEXT_RICH


# ── escalation triggers (deterministic, model-routing.md) ────────────────────


class TestEscalation:
    def test_no_triggers_keeps_default_tier(self) -> None:
        decision = escalation_decision(
            role="technical_analyst",
            low_confidence=False,
            high_disagreement=False,
            cio_override=False,
            near_breach=False,
        )
        assert decision is ModelTier.COST_EFFICIENT

    def test_low_confidence_escalates_one_tier(self) -> None:
        decision = escalation_decision(
            role="news_analyst",
            low_confidence=True,
            high_disagreement=False,
            cio_override=False,
            near_breach=False,
        )
        assert decision is ModelTier.CONTEXT_RICH

    def test_cio_override_escalates_to_strongest(self) -> None:
        # CIO override is the highest-stakes act — it pays for strongest.
        decision = escalation_decision(
            role="cio_proposer",
            low_confidence=False,
            high_disagreement=False,
            cio_override=True,
            near_breach=False,
        )
        assert decision is ModelTier.STRONGEST

    def test_high_disagreement_escalates_one_tier(self) -> None:
        # high_disagreement alone (no other trigger) must escalate —
        # the branch in router.py:79-80 is keyed on any of the three.
        decision = escalation_decision(
            role="smc_analyst",
            low_confidence=False,
            high_disagreement=True,
            cio_override=False,
            near_breach=False,
        )
        assert decision is ModelTier.CONTEXT_RICH

    def test_trigger_chain_reaches_strongest_without_override(self) -> None:
        # From context-rich, low_confidence escalates to strongest
        # through _next_tier (router.py:80) — the chain, not the
        # cio_override shortcut, must also land there.
        decision = escalation_decision(
            role="ic_forum",
            low_confidence=True,
            high_disagreement=False,
            cio_override=False,
            near_breach=False,
        )
        assert decision is ModelTier.STRONGEST

    def test_unknown_role_trigger_escalates_from_context_rich(self) -> None:
        # Unknown roles default to context-rich (router.py:32) — a
        # trigger then escalates to strongest, never below default.
        decision = escalation_decision(
            role="some_new_role",
            low_confidence=True,
            high_disagreement=False,
            cio_override=False,
            near_breach=False,
        )
        assert decision is ModelTier.STRONGEST

    def test_near_breach_escalates_whole_cycle(self) -> None:
        decision = escalation_decision(
            role="macro_analyst",
            low_confidence=False,
            high_disagreement=False,
            cio_override=False,
            near_breach=True,
        )
        assert decision is ModelTier.CONTEXT_RICH

    def test_escalation_never_goes_down(self) -> None:
        # Even with triggers, the result must never be below the default.
        decision = escalation_decision(
            role="cio_proposer",
            low_confidence=False,
            high_disagreement=True,
            cio_override=False,
            near_breach=False,
        )
        assert tier_rank(decision) >= tier_rank(ModelTier.CONTEXT_RICH)

    def test_strongest_escalation_stays_strongest(self) -> None:
        decision = escalation_decision(
            role="cio_proposer",
            low_confidence=True,
            high_disagreement=True,
            cio_override=True,
            near_breach=True,
        )
        assert decision is ModelTier.STRONGEST
