# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the LLM gateway orchestrator (D6-2/D6-4/D6-6/D6-7 wire-up).

``Gateway.complete`` is the single entry point that production code
calls: deterministic budget gate (D6-4) before the call, model
resolution, the per-tier fallback chain (D6-6) through an injected
client, and the append-only ``llm_usage`` row (D6-7) after the call.

Everything is injected — registry rows, policy, spend, client,
session — so the flow is unit-testable without a database or network.
The orchestrator is synchronous (same discipline as
``RouterClient.complete``); only the usage writer is driven with
``asyncio.run``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from lumine.data.models import LLMUsage
from lumine.llm_gateway.budget import BudgetGate
from lumine.llm_gateway.client import RouterClientError
from lumine.llm_gateway.gateway import Gateway, GatewayResult
from lumine.llm_gateway.registry import ModelRegistry
from lumine.llm_gateway.types import (
    ChatMessage,
    GatewayResponse,
    ModelTier,
    RouterRequest,
)
from lumine.shared.errors import LLMBudgetExceededError, ModelUnavailableError

if TYPE_CHECKING:
    from collections.abc import Callable

# ── helpers ──────────────────────────────────────────────────────────────────

# One resolvable id shared by the request helper and the default
# registry, so a plain ``_req()`` resolves by default.
_MVID = uuid.uuid4()


def _req(**overrides: Any) -> RouterRequest:
    base: dict[str, Any] = {
        "model_version_id": _MVID,
        "model": "deepseek-v4",
        "role": "technical_analyst",
        "tier": ModelTier.COST_EFFICIENT,
        "lineage_id": uuid.uuid4(),
        "prompt_ref": "technical_analyst@v1.prompt",
        "prompt_hash": "a" * 64,
        "idempotency_key": "idem-1",
        "messages": [ChatMessage(role="user", content="Symbol: XAUUSD")],
    }
    base.update(overrides)
    return RouterRequest(**base)


def _resp(*, model_used: str = "deepseek-v4") -> GatewayResponse:
    return GatewayResponse(
        content='{"action": "HOLD"}',
        model_used=model_used,
        prompt_tokens=120,
        completion_tokens=40,
        total_tokens=160,
    )


def _row(
    _model_version_id: uuid.UUID,
    *,
    model_id: str = "deepseek-v4",
    status: str = "production",
    tier: str = "cost-efficient",
) -> dict[str, Any]:
    """model_versions row dict, the shape ``registry._row_to_dict`` produces."""
    return {
        "version": "v1",
        "status": status,
        "provider": "deepseek",
        "model_id": model_id,
        "tier": tier,
        "context_window": 128000,
        "params": {"temperature": 0.2},
    }


def _route(
    model_version_id: uuid.UUID | None = None,
    *,
    model: str = "deepseek-v4",
    tier: str = "cost-efficient",
) -> dict[str, Any]:
    """Route dict, the shape ``resolve_model`` produces for the chain."""
    return {
        "model_version_id": model_version_id or uuid.uuid4(),
        "version": "v1",
        "provider": "deepseek",
        "model": model,
        "tier": tier,
        "context_window": 128000,
        "params": {"temperature": 0.2},
    }


def _policy() -> dict[str, Any]:
    """Full policy dict; the cost section lives in ``policy_versions.cost``."""
    return {
        "cost": {
            "daily_cap_usd": {
                "cost-efficient": 10.0,
                "context-rich": 20.0,
                "strongest": 30.0,
                "global": 50.0,
            },
            "degrade_order": ["journal", "research_sandbox", "analyst_rerun", "debate"],
            "protected_roles": [
                "technical_analyst",
                "macro_analyst",
                "news_analyst",
                "smc_analyst",
                "ic_forum",
                "cio_proposer",
            ],
            "soft_warn_pct": 0.8,
        }
    }


class _FakeClient:
    """RouterClient stand-in: records calls, fails a model on demand."""

    def __init__(self) -> None:
        self.calls: list[RouterRequest] = []
        self.fail_on: dict[str, str] = {}  # model -> RouterClientError message

    async def complete_async(self, req: RouterRequest) -> GatewayResponse:
        self.calls.append(req)
        message = self.fail_on.get(req.model)
        if message is not None:
            raise RouterClientError(message)
        return _resp(model_used=req.model)


class _GhostModelClient:
    """RouterClient stand-in that echoes a model not in any route.

    ``_FakeClient.complete_async`` always reports ``model_used ==
    req.model``; this stand-in reports a name outside both the primary
    and hop routes, exercising the "unknown model_used — assume
    primary" defensive path in ``Gateway._used_route``/_hops_used.
    """

    def __init__(self, ghost: str) -> None:
        self.ghost = ghost
        self.calls: list[RouterRequest] = []

    async def complete_async(self, req: RouterRequest) -> GatewayResponse:
        self.calls.append(req)
        return _resp(model_used=self.ghost)


class _FakeSession:
    """AsyncSession stand-in: records adds, fails flush on demand."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _gateway(
    *,
    registry: ModelRegistry | None = None,
    budget: BudgetGate | None = None,
    client: _FakeClient | None = None,
    spend: dict[str, float] | None = None,
    session: _FakeSession | None = None,
    prices: dict[str, tuple[Decimal, Decimal]] | None = None,
    fallbacks: Callable[[ModelTier], tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
    prompt_version_id: uuid.UUID | None = None,
    lane: str | None = None,
) -> Gateway:
    # is not None: an empty registry must stay empty (falsy otherwise).
    registry = registry if registry is not None else ModelRegistry({_MVID: _row(_MVID)})
    budget = budget or BudgetGate(policy=_policy())
    client = client or _FakeClient()
    return Gateway(
        registry=registry,
        budget=budget,
        client=client,
        spend=spend,
        session=session,
        prices=prices,
        fallbacks=fallbacks,
        prompt_version_id=prompt_version_id,
        lane=lane,
    )


# ── happy path: allow → call → usage row ─────────────────────────────────────


class TestHappyPath:
    def test_allow_calls_primary_and_writes_usage(self) -> None:
        client = _FakeClient()
        session = _FakeSession()
        gw = _gateway(client=client, session=session)
        result = gw.complete(_req())
        assert isinstance(result, GatewayResult)
        assert len(client.calls) == 1
        assert result.fallback_hops == 0
        assert result.degraded is False
        assert result.usage is not None
        assert isinstance(result.usage, LLMUsage)
        assert result.usage.role == "technical_analyst"
        assert result.usage.tier == "cost-efficient"
        assert session.added == [result.usage]

    def test_usage_lands_without_session_is_none(self) -> None:
        gw = _gateway()
        result = gw.complete(_req())
        assert result.usage is None
        assert result.response.content == '{"action": "HOLD"}'

    def test_cost_usd_computed_from_injected_prices(self) -> None:
        session = _FakeSession()
        prices = {"deepseek-v4": (Decimal("0.500000"), Decimal("1.500000"))}
        gw = _gateway(session=session, prices=prices)
        result = gw.complete(_req())
        assert result.usage is not None
        # 120 in @ 0.5/1K + 40 out @ 1.5/1K → 0.06 + 0.06.
        assert result.usage.cost_usd == Decimal("0.120000")

    def test_request_model_version_id_reaches_the_client(self) -> None:
        client = _FakeClient()
        req = _req()
        gw = _gateway(client=client)
        gw.complete(req)
        assert client.calls[0].model_version_id == req.model_version_id

    def test_result_carries_budget_decision_fields(self) -> None:
        # GatewayResult (gateway.py:57-66) must surface the BudgetDecision
        # untouched — decision.action/reason are what the pipeline's audit
        # trail reads, and result.primary is the route actually used as
        # primary (resolve path, no fallback provider). technical_analyst
        # is protected (budget.py:38-47) — zero spend yields the neutral
        # allow decision, not a soft warning.
        gw = _gateway()
        result = gw.complete(_req())
        assert result.decision.action == "allow"
        assert result.decision.reason == "protected role runs"
        assert result.primary["model"] == "deepseek-v4"

    def test_decision_warn_surfaces_through_gateway(self) -> None:
        # BudgetGate.check (budget.py:202-214) only flips to an exception
        # on action == "block"; a soft-warning (spend >= cap * pct) must
        # pass through as decision.warn without blocking the call or
        # degrading it.
        client = _FakeClient()
        gw = _gateway(
            client=client,
            spend={"cost-efficient": 9.0},  # 10.0 cap * 0.8 soft_pct = 8.0
        )
        result = gw.complete(_req())
        assert result.decision.warn is True
        assert result.decision.action == "allow"
        assert result.degraded is False
        assert len(client.calls) == 1  # soft warning never blocks the call

    def test_constructor_prompt_version_id_and_lane_flow_to_usage(
        self,
    ) -> None:
        # gateway.py:103-104 — prompt_version_id and lane are carried at
        # construction and injected into write_usage (gateway.py:154-159);
        # both are null by default (append-only safe), and non-null
        # constructor values must land on the usage row. An empty lane
        # string is *not* None, so it must also survive the trip.
        pvid = uuid.uuid4()
        session = _FakeSession()
        gw = _gateway(session=session, prompt_version_id=pvid, lane="ic_forum")
        result = gw.complete(_req())
        assert result.usage is not None
        assert result.usage.prompt_version_id == pvid
        assert result.usage.lane == "ic_forum"

        plain_session = _FakeSession()
        plain_gw = _gateway(session=plain_session)
        plain_result = plain_gw.complete(_req())
        assert plain_result.usage is not None
        assert plain_result.usage.prompt_version_id is None
        assert plain_result.usage.lane is None


# ── budget gate: block before the call, no usage row ─────────────────────────


class TestBudgetGateWireUp:
    def test_blocked_role_raises_and_never_calls_the_client(self) -> None:
        client = _FakeClient()
        session = _FakeSession()
        gw = _gateway(
            client=client,
            session=session,
            spend={"cost-efficient": 11.0},  # tier cap breached
        )
        with pytest.raises(LLMBudgetExceededError):
            gw.complete(_req(role="journal"))
        assert client.calls == []
        assert session.added == []

    def test_analyst_rerun_degrade_flags_usage_row(self) -> None:
        client = _FakeClient()
        session = _FakeSession()
        gw = _gateway(
            client=client,
            session=session,
            spend={"cost-efficient": 11.0},
        )
        result = gw.complete(_req(role="analyst_rerun"))
        assert result.degraded is True
        assert result.usage is not None
        assert result.usage.degraded is True
        assert len(client.calls) == 1


# ── fallback chain: hop count lands in the usage row ─────────────────────────


class TestFallbackWireUp:
    def test_fallback_hop_records_hops_in_usage(self) -> None:
        client = _FakeClient()
        client.fail_on["deepseek-v4"] = "timed out"
        session = _FakeSession()
        primary = _route(model="deepseek-v4")
        hop = _route(model="deepseek-v3")

        def fallbacks(tier: ModelTier) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            assert tier == ModelTier.COST_EFFICIENT
            return primary, [hop]

        gw = _gateway(
            client=client,
            session=session,
            fallbacks=fallbacks,
            prices={"deepseek-v3": (Decimal("0.300000"), Decimal("0.900000"))},
        )
        result = gw.complete(_req())
        assert result.response.model_used == "deepseek-v3"
        assert result.fallback_hops == 1
        assert result.usage is not None
        assert result.usage.fallback_hops == 1
        assert result.usage.model_version_id == hop["model_version_id"]

    def test_registry_bypassed_when_fallback_provider_injected(self) -> None:
        # _routes_for (gateway.py:181-182): a fallback provider
        # short-circuits model resolution entirely — GatewayResult.primary
        # is the policy's primary route dict, and an empty registry must
        # not matter (nothing resolvable, yet the call succeeds).
        client = _FakeClient()
        primary = _route(model="deepseek-v4")
        hop = _route(model="deepseek-v3")

        def fallbacks(
            tier: ModelTier,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            return primary, [hop]

        gw = _gateway(
            client=client,
            registry=ModelRegistry({}),  # provider wins over resolution
            fallbacks=fallbacks,
        )
        result = gw.complete(_req())
        assert result.primary["model"] == "deepseek-v4"
        assert result.primary["model_version_id"] == primary["model_version_id"]
        assert result.fallback_hops == 0
        # Even the primary attempt is re-pinned to the provider's route —
        # the request's own model_version_id never reaches the client.
        assert client.calls[0].model_version_id == primary["model_version_id"]

    def test_hop_call_repins_model_and_version(self) -> None:
        # _call_for (gateway.py:191-198): each attempted route is sent as
        # a model_copy re-pinned to that route's model/version — the wire
        # call for a hop must carry the hop's identity, never the
        # primary's; and GatewayResult.primary still reports the policy
        # primary even when the chain landed on a hop.
        client = _FakeClient()
        client.fail_on["deepseek-v4"] = "500 boom"  # permanent — no retry
        primary = _route(model="deepseek-v4")
        hop = _route(model="deepseek-v3")

        def fallbacks(
            tier: ModelTier,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            return primary, [hop]

        gw = _gateway(client=client, fallbacks=fallbacks)
        result = gw.complete(_req())
        assert [c.model for c in client.calls] == ["deepseek-v4", "deepseek-v3"]
        assert client.calls[-1].model_version_id == hop["model_version_id"]
        assert result.response.model_used == "deepseek-v3"
        assert result.primary["model"] == "deepseek-v4"
        assert result.fallback_hops == 1

    def test_unknown_model_used_falls_back_to_primary(self) -> None:
        # Defensive contract: a model_used outside every route must not
        # be counted as a hop nor pin llm_usage to a ghost model — the
        # usage row keeps the primary route (D6-7: the row must stay
        # resolvable to a real model_version).
        primary = _route(model="deepseek-v4")
        hop = _route(model="deepseek-v3")
        session = _FakeSession()

        def fallbacks(tier: ModelTier) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            return primary, [hop]

        gw = _gateway(
            client=_GhostModelClient(ghost="ghost-model-9"),
            session=session,
            fallbacks=fallbacks,
            prices={"deepseek-v4": (Decimal("0.500000"), Decimal("1.500000"))},
        )
        result = gw.complete(_req())
        assert result.response.model_used == "ghost-model-9"
        assert result.fallback_hops == 0  # not counted as a hop
        assert result.usage is not None
        assert result.usage.model_version_id == primary["model_version_id"]
        assert result.usage.fallback_hops == 0


# ── resolution failures surface before any call ──────────────────────────────


class TestResolutionFailure:
    def test_unknown_model_version_raises_without_calling(self) -> None:
        client = _FakeClient()
        gw = _gateway(
            client=client,
            registry=ModelRegistry({}),  # nothing resolvable
        )
        with pytest.raises(ModelUnavailableError):
            gw.complete(_req())
        assert client.calls == []

    def test_resolve_path_without_fallback_provider(self) -> None:
        # _routes_for (gateway.py:173-184): with fallbacks=None the
        # primary comes from resolve_model (D6-3), not from any policy
        # provider — the used route must carry the resolved version_id,
        # and hops stay empty so a failure exhausts as expected.
        client = _FakeClient()
        gw = _gateway(client=client)
        result = gw.complete(_req())
        assert result.primary["model_version_id"] == _MVID
        assert result.fallback_hops == 0
        assert result.usage is None  # no session — no row, per contract

    def test_retired_model_fails_fast(self) -> None:
        mvid = uuid.uuid4()
        client = _FakeClient()
        gw = _gateway(
            client=client,
            registry=ModelRegistry({mvid: _row(mvid, status="retired")}),
        )
        with pytest.raises(ModelUnavailableError):
            gw.complete(_req(model_version_id=mvid))
        assert client.calls == []


# ── injected spend override per call ─────────────────────────────────────────


class TestSpendOverride:
    def test_complete_accepts_per_call_spend(self) -> None:
        client = _FakeClient()
        gw = _gateway(client=client)
        with pytest.raises(LLMBudgetExceededError):
            gw.complete(_req(role="journal"), spend={"cost-efficient": 11.0})
        assert client.calls == []
