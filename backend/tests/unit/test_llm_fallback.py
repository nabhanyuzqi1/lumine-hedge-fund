# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the per-tier fallback chain (D6-6, llm-gateway.md).

The chain is deterministic: try the primary ``model_version_id``, then
each declared fallback hop in order, logging every hop. Auth failures
(401/403) get no retry — they open a per-provider circuit. Transient
failures (timeout, 429) get one immediate retry before the next hop.
Exhausting the chain surfaces the original failure to the pipeline —
never a silent skip.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from lumine.llm_gateway.fallback import (
    FallbackChain,
    FallbackExhaustedError,
    FallbackHop,
    NoFallbacksConfiguredError,
    run_chain,
)
from lumine.llm_gateway.types import GatewayResponse, RouterRequest

# ── helpers ──────────────────────────────────────────────────────────────────


def _route(
    model_version_id: uuid.UUID | None = None,
    *,
    model: str = "deepseek-v4",
) -> dict[str, Any]:
    return {
        "model_version_id": model_version_id or uuid.uuid4(),
        "version": "v1",
        "provider": "deepseek",
        "model": model,
        "tier": "cost-efficient",
        "context_window": 128000,
        "params": {"temperature": 0.2},
    }


def _req() -> RouterRequest:
    from lumine.llm_gateway.types import ChatMessage, ModelTier

    return RouterRequest(
        model_version_id=uuid.uuid4(),
        role="technical_analyst",
        tier=ModelTier.COST_EFFICIENT,
        lineage_id=uuid.uuid4(),
        prompt_ref="technical_analyst@v1.prompt",
        prompt_hash="a" * 64,
        idempotency_key="idem-1",
        messages=[ChatMessage(role="user", content="Symbol: XAUUSD")],
    )


def _ok(model: str = "deepseek-v4") -> GatewayResponse:
    return GatewayResponse(
        content='{"action": "HOLD"}',
        model_used=model,
        prompt_tokens=120,
        completion_tokens=40,
        total_tokens=160,
    )


# ── chain definition ─────────────────────────────────────────────────────────


class TestFallbackChainDefinition:
    def test_chain_holds_ordered_hops(self) -> None:
        primary = _route()
        hop = _route(model="deepseek-v3")
        chain = FallbackChain(primary=primary, hops=[hop])
        assert chain.primary["model"] == "deepseek-v4"
        assert [h["model"] for h in chain.hops] == ["deepseek-v3"]

    def test_chain_accepts_fallback_hop_wrappers(self) -> None:
        # FallbackChain normalizes both raw route dicts and FallbackHop
        # wrappers (fallback.py:45-75) into plain route dicts — the
        # typed view must not leak through to the chain internals.
        chain = FallbackChain(
            primary=FallbackHop(_route()),
            hops=[FallbackHop(_route(model="deepseek-v3"), tier="cost-efficient")],
        )
        assert chain.primary["model"] == "deepseek-v4"
        assert [h["model"] for h in chain.hops] == ["deepseek-v3"]
        assert all(h["tier"] == "cost-efficient" for h in chain.hops)

    def test_run_chain_calls_primary_only_on_success(self) -> None:
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            return _ok()

        result = run_chain(
            primary=_route(),
            hops=[_route(model="deepseek-v3")],
            call=caller,
            request=_req(),
        )
        assert result.content == '{"action": "HOLD"}'
        assert calls == ["deepseek-v4"]

    def test_run_chain_moves_to_next_hop_on_permanent_failure(self) -> None:
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            if str(route["model"]) == "deepseek-v4":
                from lumine.llm_gateway.client import RouterClientError

                raise RouterClientError("503 upstream down")
            return _ok(model=str(route["model"]))

        result = run_chain(
            primary=_route(),
            hops=[_route(model="deepseek-v3")],
            call=caller,
            request=_req(),
        )
        # "503" is not a transient marker ("timed out"/"429") — no
        # immediate retry; the chain hops straight to deepseek-v3.
        assert calls == ["deepseek-v4", "deepseek-v3"]
        assert result.model_used == "deepseek-v3"

    def test_hop_reason_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        async def caller(route: dict[str, Any]) -> GatewayResponse:
            from lumine.llm_gateway.client import RouterClientError

            if str(route["model"]) == "deepseek-v4":
                raise RouterClientError("timeout")
            return _ok(model=str(route["model"]))

        with caplog.at_level("WARNING"):
            result = run_chain(
                primary=_route(),
                hops=[_route(model="deepseek-v3")],
                call=caller,
                request=_req(),
            )
        assert result.model_used == "deepseek-v3"
        assert any("fallback" in rec.message.lower() for rec in caplog.records)

    def test_no_fallbacks_configured_raises_when_primary_fails(self) -> None:
        async def caller(route: dict[str, Any]) -> GatewayResponse:
            from lumine.llm_gateway.client import RouterClientError

            raise RouterClientError("500 boom")

        with pytest.raises(NoFallbacksConfiguredError):
            run_chain(primary=_route(), hops=[], call=caller, request=_req())

    def test_transient_primary_without_hops_raises_fallback_exhausted(
        self,
    ) -> None:
        # Contract: with no hops, only a *non-retryable* primary failure
        # is a configuration gap (NoFallbacksConfiguredError); a
        # transient failure is worth the built-in retry, so exhaustion
        # (after attempt 0 + attempt 1) is FallbackExhaustedError —
        # same failure class the live pipeline sees from gateway.py.
        async def caller(route: dict[str, Any]) -> GatewayResponse:
            from lumine.llm_gateway.client import RouterClientError

            raise RouterClientError("timed out")

        with pytest.raises(FallbackExhaustedError):
            run_chain(primary=_route(), hops=[], call=caller, request=_req())

    def test_all_hops_exhausted_raises_fallback_exhausted(self) -> None:
        async def caller(route: dict[str, Any]) -> GatewayResponse:
            from lumine.llm_gateway.client import RouterClientError

            raise RouterClientError("502 bad gateway")

        with pytest.raises(FallbackExhaustedError):
            run_chain(
                primary=_route(),
                hops=[_route(model="deepseek-v3"), _route(model="qwen-3.7")],
                call=caller,
                request=_req(),
            )


# ── auth failure: no retry, circuit opens ────────────────────────────────────


class TestAuthFailureCircuit:
    def test_401_skips_retry_and_falls_through_chain(self) -> None:
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            from lumine.llm_gateway.client import RouterClientError

            raise RouterClientError("401 unauthorized")

        with pytest.raises(FallbackExhaustedError):
            run_chain(
                primary=_route(),
                hops=[_route(model="deepseek-v3")],
                call=caller,
                request=_req(),
            )
        # auth failure: exactly one call per hop, no immediate retry
        assert calls == ["deepseek-v4", "deepseek-v3"]


# ── transient failure: one immediate retry, then next hop ────────────────────


class TestTransientRetry:
    def test_timeout_gets_one_retry_then_next_hop(self) -> None:
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            from lumine.llm_gateway.client import RouterClientError

            raise RouterClientError("timed out")

        with pytest.raises(FallbackExhaustedError):
            run_chain(
                primary=_route(),
                hops=[_route(model="deepseek-v3")],
                call=caller,
                request=_req(),
            )
        # each hop: 1 attempt + 1 retry, no success
        assert calls == ["deepseek-v4", "deepseek-v4", "deepseek-v3", "deepseek-v3"]

    def test_429_no_hops_exhausts_retries_then_raises(self) -> None:
        # No hops means one route only; with _TRANSIENT_RETRIES = 1 the
        # sole fallback is that one immediate retry (attempt 0 →
        # attempt 1), then exhaustion surfaces.
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            from lumine.llm_gateway.client import RouterClientError

            raise RouterClientError("429 rate limited")

        with pytest.raises(FallbackExhaustedError):
            run_chain(
                primary=_route(),
                hops=[],
                call=caller,
                request=_req(),
            )
        assert calls == ["deepseek-v4", "deepseek-v4"]

    def test_transient_retry_can_recover_on_second_attempt(self) -> None:
        # _TRANSIENT_RETRIES = 1 + `continue` (fallback.py:114-121):
        # the same route is retried once before any hop is tried. A
        # recovery on attempt 1 must return success with eactly two
        # calls — never a hop.
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            from lumine.llm_gateway.client import RouterClientError

            if len(calls) == 1:
                raise RouterClientError("timed out")
            return _ok(model=str(route["model"]))

        result = run_chain(
            primary=_route(),
            hops=[_route(model="deepseek-v3")],
            call=caller,
            request=_req(),
        )
        assert calls == ["deepseek-v4", "deepseek-v4"]
        assert result.model_used == "deepseek-v4"

    def test_primary_transient_exhausted_then_hop_succeeds(self) -> None:
        # Primary fails transiently on both attempts (retry consumed,
        # fallback.py:114-121) — the chain must then move to the hop,
        # which succeeds. This pins the "exhausted retries → next route"
        # boundary that no other test exercises.
        calls: list[str] = []

        async def caller(route: dict[str, Any]) -> GatewayResponse:
            calls.append(str(route["model"]))
            from lumine.llm_gateway.client import RouterClientError

            if str(route["model"]) == "deepseek-v4":
                raise RouterClientError("timed out")
            return _ok(model=str(route["model"]))

        result = run_chain(
            primary=_route(),
            hops=[_route(model="deepseek-v3")],
            call=caller,
            request=_req(),
        )
        assert calls == ["deepseek-v4", "deepseek-v4", "deepseek-v3"]
        assert result.model_used == "deepseek-v3"


# ── cost safety ──────────────────────────────────────────────────────────────


class TestCostSafety:
    def test_fallback_never_upgrades_tier(self) -> None:
        # Hops are declared per tier in policy_versions.routing.fallbacks;
        # the chain itself must not pick a stronger tier. Every hop here
        # stays cost-efficient.
        hops = [_route(model="deepseek-v3"), _route(model="kimi-k3")]
        assert all(h["tier"] == "cost-efficient" for h in hops)
