# Copyright (c) 2026 Lumine. All rights reserved.
"""Append-only cost-accounting writer for every LLM call (D6-7, cost-control.md).

Every gateway call lands exactly one row in ``llm_usage`` — role, tier,
model_version_id (post-fallback), prompt_version_id, tokens_in/out,
cost_usd, fallback_hops, degraded, lineage_id, lane. Budget counters
derive from this table (one source of truth, no parallel accounting).

``record_usage`` is a pure constructor: it maps a ``RouterRequest`` +
``GatewayResponse`` + call context onto an ``LLMUsage`` row so the
mapping is unit-testable without a database. ``write_usage`` is the
thin async adapter that appends the row through a session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from lumine.data.models import LLMUsage
from lumine.shared.errors import LLMUsageRecordError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.types import GatewayResponse, RouterRequest


def _utcnow() -> datetime:
    """UTC now with tzinfo, matching data/models.py's default."""
    return datetime.now(UTC)


def _cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    price_per_1k_in: Decimal,
    price_per_1k_out: Decimal,
) -> Decimal:
    """Cost in USD at 6-decimal precision (Numeric(12,6))."""
    cost = (
        Decimal(prompt_tokens) * price_per_1k_in + Decimal(completion_tokens) * price_per_1k_out
    ) / Decimal(1000)
    return cost.quantize(Decimal("0.000001"))


def record_usage(
    *,
    request: RouterRequest,
    response: GatewayResponse,
    prompt_version_id: uuid.UUID | None = None,
    price_per_1k_in: Decimal = Decimal("0.000000"),
    price_per_1k_out: Decimal = Decimal("0.000000"),
    fallback_hops: int = 0,
    degraded: bool = False,
    lane: str | None = None,
) -> LLMUsage:
    """Build an append-only ``LLMUsage`` row (DB-free, deterministic).

    Fields not derivable from the request/response (prompt version,
    prices, hop count, degraded flag, lane) are injected so callers —
    e.g. the fallback chain or the router — keep this mapping pure and
    unit-testable.
    """
    return LLMUsage(
        role=request.role,
        tier=request.tier.value if hasattr(request.tier, "value") else str(request.tier),
        model_version_id=request.model_version_id,
        prompt_version_id=prompt_version_id,
        tokens_in=response.prompt_tokens,
        tokens_out=response.completion_tokens,
        cost_usd=_cost_usd(
            response.prompt_tokens,
            response.completion_tokens,
            price_per_1k_in=price_per_1k_in,
            price_per_1k_out=price_per_1k_out,
        ),
        fallback_hops=fallback_hops,
        degraded=degraded,
        lane=lane,
        lineage_id=request.lineage_id,
    )


async def write_usage(
    session: AsyncSession,
    *,
    request: RouterRequest,
    response: GatewayResponse,
    **kwargs: Any,
) -> LLMUsage:
    """Append one ``LLMUsage`` row via ``session`` (idempotent per call).

    Flushes so the row's ``id``/``ts`` are populated and FK failures
    surface here — the caller's transaction decides commit/rollback.
    """
    usage = record_usage(request=request, response=response, **kwargs)
    session.add(usage)
    try:
        await session.flush()
    except Exception as exc:  # pragma: no cover — DB errors surface upstream
        message = f"failed to persist llm_usage row: {exc}"
        raise LLMUsageRecordError(message) from exc
    return usage


__all__ = ("record_usage", "write_usage")
