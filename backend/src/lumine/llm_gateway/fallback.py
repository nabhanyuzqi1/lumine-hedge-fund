# Copyright (c) 2026 Lumine. All rights reserved.
"""Per-tier fallback chain (D6-6).

The chain is deterministic: try the primary ``model_version_id``, then
each declared fallback hop in order, logging every hop. Auth failures
(401/403) get no retry — they open a per-provider circuit. Transient
failures (timeout, 429) get one immediate retry before the next hop.
Exhausting the chain surfaces the original failure to the pipeline —
never a silent skip.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from lumine.llm_gateway.client import RouterClientError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence

    from lumine.llm_gateway.types import GatewayResponse, RouterRequest

logger = logging.getLogger("lumine.llm_gateway.fallback")

# One extra attempt for transient failures (timeout/429), per D6-6.
_TRANSIENT_RETRIES = 1
# Auth failures never retry; they open the provider circuit instead.
_AUTH_MARKERS = ("401", "403")
_TRANSIENT_MARKERS = ("timed out", "429")


class FallbackExhaustedError(RuntimeError):
    """All hops failed; the original failure must surface to the pipeline."""


class NoFallbacksConfiguredError(RuntimeError):
    """The primary failed and no fallback hops were declared."""


class FallbackHop:
    """One fallback candidate: a route dict plus its cost tier."""

    def __init__(self, route: dict[str, Any], *, tier: str | None = None) -> None:
        """Wrap ``route`` with its cost tier, defaulting to the route's."""
        self.route = route
        self.tier = tier or str(route.get("tier", "cost-efficient"))

    def __repr__(self) -> str:
        """Debug view: model + tier."""
        return f"FallbackHop(model={self.route.get('model')!r}, tier={self.tier!r})"


class FallbackChain:
    """An ordered chain: a primary route plus declared fallback hops.

    Both ``primary`` and ``hops`` are raw route dicts (the shape
    ``_route()`` produces in tests and ``policy_versions.routing.
    fallbacks`` declares); ``FallbackHop`` wraps one route when callers
    want a typed view.
    """

    def __init__(
        self,
        primary: dict[str, Any] | FallbackHop,
        hops: Sequence[dict[str, Any] | FallbackHop] = (),
    ) -> None:
        """Normalize primary + hops into raw route dicts."""
        self.primary: dict[str, Any] = (
            primary.route if isinstance(primary, FallbackHop) else primary
        )
        self.hops: list[dict[str, Any]] = [
            hop.route if isinstance(hop, FallbackHop) else hop for hop in hops
        ]


def _classify(error: RouterClientError) -> str:
    """Return ``auth`` or ``transient`` for a ``RouterClientError``."""
    msg = str(error).lower()
    if any(marker in msg for marker in _AUTH_MARKERS):
        return "auth"
    if any(marker in msg for marker in _TRANSIENT_MARKERS):
        return "transient"
    return "permanent"


def run_chain(
    *,
    primary: dict[str, Any] | FallbackHop,
    hops: Sequence[dict[str, Any] | FallbackHop] = (),
    call: Callable[[dict[str, Any]], Coroutine[Any, Any, GatewayResponse]],
    request: RouterRequest,
) -> GatewayResponse:
    """Run the chain: primary, then each hop, retrying transient failures once.

    Returns the first successful ``GatewayResponse``. Raises
    ``NoFallbacksConfiguredError`` when the primary fails and no hops
    exist; ``FallbackExhaustedError`` when every route (including
    retries) failed. Auth failures never retry — they fall through to
    the next hop so the circuit can open at the client layer.
    """
    chain = FallbackChain(primary=primary, hops=hops)
    routes = [chain.primary, *chain.hops]
    last_error: RouterClientError | None = None
    for route in routes:
        for attempt in range(_TRANSIENT_RETRIES + 1):
            try:
                return asyncio.run(call(route))
            except RouterClientError as exc:
                last_error = exc
                kind = _classify(exc)
                reason = f"{kind} failure: {exc}"
                if attempt == 0 and kind == "transient":
                    logger.warning(
                        "llm_gateway.fallback retry model=%s request=%s reason=%s",
                        route.get("model"),
                        request.idempotency_key,
                        reason,
                    )
                    continue
                logger.warning(
                    "llm_gateway.fallback hop model=%s request=%s reason=%s",
                    route.get("model"),
                    request.idempotency_key,
                    reason,
                )
                break
    # Surface the failure — never a silent skip.
    if not chain.hops and last_error is not None and _classify(last_error) != "transient":
        # Non-retryable primary failure with no declared hops is a
        # configuration gap — nothing to try, nothing worth retrying.
        message = f"primary failed and no fallback hops configured: {last_error}"
        raise NoFallbacksConfiguredError(message) from last_error
    message = f"all {len(routes)} route(s) exhausted; last failure: {last_error}"
    raise FallbackExhaustedError(message) from last_error


__all__ = (
    "FallbackChain",
    "FallbackExhaustedError",
    "FallbackHop",
    "NoFallbacksConfiguredError",
    "run_chain",
)
