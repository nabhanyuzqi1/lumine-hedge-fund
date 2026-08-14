# Copyright (c) 2026 Lumine. All rights reserved.
"""LLM gateway orchestrator — the single production entry point (D6-2).

``Gateway.complete`` wires the deterministic pieces together in order:

1. **Budget gate (D6-4, cost-control.md)** — read today's accumulated
   spend, compare against ``policy_versions.cost`` caps, block or
   degrade before any call reaches the gateway. Blocking raises
   ``LLMBudgetExceededError`` — a stage failure, never a silent skip.
2. **Resolution** — ``resolve_model`` turns the requested
   ``model_version_id`` into a production route (D6-3).
3. **Fallback chain (D6-6, llm-gateway.md)** — try the primary route,
   then per-tier hops, retrying transient failures once.
4. **Accounting (D6-7)** — every call lands exactly one append-only
   ``llm_usage`` row with the post-fallback model, token counts,
   computed cost, hop count, and the degrade flag.

The orchestrator is synchronous — the pipeline calls the gateway
synchronously (same discipline as ``RouterClient.complete``). The
budget gate and the chain are synchronous by contract; only the usage
writer is async and is driven with ``asyncio.run``.

Everything is injected: registry rows, policy (inside ``BudgetGate``),
spend, client, fallbacks, prices, and the optional session. Production
callers inject a session + spend aggregation; unit tests inject fakes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from lumine.llm_gateway.fallback import run_chain
from lumine.llm_gateway.registry import ModelRegistry, resolve_model
from lumine.llm_gateway.usage import write_usage

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable, Coroutine, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.budget import BudgetDecision, BudgetGate
    from lumine.llm_gateway.client import RouterClient
    from lumine.llm_gateway.types import GatewayResponse, ModelTier, RouterRequest

    # Prices are injected per model_id (model_versions is the only
    # place concrete models are named; their cost curve is a Phase 14
    # value). (tier) -> (primary route dict, [hop route dicts]) from
    # ``policy_versions.routing.fallbacks``; None means "primary only".
    PriceCurve = Mapping[str, tuple[Decimal, Decimal]]
    FallbackProvider = Callable[[ModelTier], tuple[dict[str, Any], list[dict[str, Any]]]]


@dataclass(frozen=True)
class GatewayResult:
    """Outcome of one complete gateway call."""

    response: GatewayResponse
    primary: dict[str, Any]  # the route dict actually used as primary
    decision: BudgetDecision
    degraded: bool
    fallback_hops: int
    usage: Any | None = None  # the LLMUsage row, or None without a session


class Gateway:
    """Wire up budget gate → resolution → fallback chain → usage row."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        budget: BudgetGate,
        client: RouterClient,
        spend: Mapping[str, float] | None = None,
        session: AsyncSession | None = None,
        prices: PriceCurve | None = None,
        fallbacks: FallbackProvider | None = None,
        prompt_version_id: uuid.UUID | None = None,
        lane: str | None = None,
    ) -> None:
        """Configure the orchestrator.

        ``spend`` is today's accumulated spend per tier (USD), the
        same mapping ``budget_decision`` consumes; production callers
        aggregate it from ``llm_usage`` (cost-control.md: budget
        counters derive from that table — one source of truth).
        ``session`` enables post-call accounting; without it no usage
        row is written (research/test mode, never silent in production).
        ``fallbacks`` returns the per-tier route list from
        ``policy_versions.routing.fallbacks``; default is primary only.
        """
        self._registry = registry
        self._budget = budget
        self._client = client
        self._spend = dict(spend or {})
        self._session = session
        self._prices = dict(prices or {})
        self._fallbacks = fallbacks
        self._prompt_version_id = prompt_version_id
        self._lane = lane

    def complete(
        self,
        request: RouterRequest,
        *,
        spend: Mapping[str, float] | None = None,
    ) -> GatewayResult:
        """Run the full gateway flow for ``request`` (synchronous).

        Raises:
            LLMBudgetExceededError: budget gate blocked the call
                (never any client call in that case).
            ModelUnavailableError: ``model_version_id`` is unknown or
                not ``production`` (D6-3, fails fast).
            FallbackExhaustedError / NoFallbacksConfiguredError: every
                route (including retries) failed.

        """
        decision = self._budget.check(
            spend=dict(spend or self._spend),
            tier=request.tier,
            role=request.role,
        )
        primary, hops = self._routes_for(request)
        response = run_chain(
            primary=primary,
            hops=hops,
            call=self._call_for(request),
            request=request,
        )
        fallback_hops = self._hops_used(primary, hops, response)
        usage = None
        if self._session is not None:
            used = self._used_route(primary, hops, response)
            price_in, price_out = self._prices.get(
                used["model"], (Decimal("0.000000"), Decimal("0.000000"))
            )
            # D6-7: llm_usage.model_version_id is the actual model used
            # (post-fallback) — the request is re-pinned to the used route.
            usage = asyncio.run(
                write_usage(
                    self._session,
                    request=request.model_copy(
                        update={
                            "model_version_id": used["model_version_id"],
                            "model": used["model"],
                        }
                    ),
                    response=response,
                    prompt_version_id=self._prompt_version_id,
                    price_per_1k_in=price_in,
                    price_per_1k_out=price_out,
                    fallback_hops=fallback_hops,
                    degraded=decision.degraded,
                    lane=self._lane,
                )
            )
        return GatewayResult(
            response=response,
            primary=primary,
            decision=decision,
            degraded=decision.degraded,
            fallback_hops=fallback_hops,
            usage=usage,
        )

    # ── internals ──────────────────────────────────────────────────────────

    def _routes_for(self, request: RouterRequest) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Return (primary route, hop routes) for ``request``.

        With a fallback provider, the primary comes from the policy's
        per-tier fallback list; otherwise the requested
        ``model_version_id`` is resolved (D6-3) and used as primary
        with no hops.
        """
        if self._fallbacks is not None:
            return self._fallbacks(request.tier)
        route = resolve_model(self._registry, request.model_version_id)
        return route.model_dump(), []

    def _call_for(
        self, request: RouterRequest
    ) -> Callable[[dict[str, Any]], Coroutine[Any, Any, GatewayResponse]]:
        """Build the async per-route caller: switch model, then call."""

        async def call(route: dict[str, Any]) -> GatewayResponse:
            hop_request = request.model_copy(
                update={
                    "model": route["model"],
                    "model_version_id": route["model_version_id"],
                }
            )
            return await self._client.complete_async(hop_request)

        return call

    @staticmethod
    def _used_route(
        primary: dict[str, Any],
        hops: list[dict[str, Any]],
        response: GatewayResponse,
    ) -> dict[str, Any]:
        """Return the route the gateway actually used (first match on model)."""
        for route in [primary, *hops]:
            if route["model"] == response.model_used:
                return route
        return primary  # unknown model_used — assume primary (best effort)

    @staticmethod
    def _hops_used(
        primary: dict[str, Any],
        hops: list[dict[str, Any]],
        response: GatewayResponse,
    ) -> int:
        """Derive the hop count from the model the gateway actually used."""
        if response.model_used == primary["model"]:
            return 0
        for index, hop in enumerate(hops, start=1):
            if hop["model"] == response.model_used:
                return index
        return 0  # unknown model_used — assume primary (best effort)


__all__ = ("Gateway", "GatewayResult")
