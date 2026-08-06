# Copyright (c) 2026 Lumine. All rights reserved.
"""Single-turn LLM stage runner (prompt → gateway → validate → trace).

Every decision-engine role (the four analysts, IC Forum, CIO Proposer)
follows the same narrow pattern, so it lives here once instead of being
copied per role: load+render the prompt from the registry, build a
``RouterRequest``, call the injected ``Gateway`` (which owns budget,
resolution, fallback, and ``llm_usage`` accounting), robustly parse the
model's JSON, validate it against the prompt's output-schema, and write
a ``reasoning_traces`` row.

Strictness (Phase 7): a non-conforming output triggers ONE retry with a
``fix your JSON`` hint that names the violation. A second failure is a
stage failure — never a relaxed parse. Every gateway call (including a
failed attempt) produces a reasoning-trace row, so ``reasoning_traces``
stays a faithful one-row-per-LLM-call audit log (D7-11, ADR-0029).

``trade_core`` never touches this module; it is the LLM orchestration
layer that depends on ``data`` + ``llm_gateway`` + ``prompts``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lumine.autogen_pipeline.traces import write_trace
from lumine.llm_gateway.types import ChatMessage, ModelTier, RouterRequest
from lumine.prompts.registry import PromptBundle, render
from lumine.schemas.validation import validation_problem
from lumine.shared.errors import SchemaValidationError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from lumine.llm_gateway.gateway import Gateway, GatewayResult
    from lumine.prompts.registry import Registry

_MAX_ATTEMPTS = 2  # first pass + one "fix your JSON" retry (Phase 7)

# registry.yaml hints (prompt-storage.md / D4) → gateway ModelTier enum.
# The gateway and llm_usage.tier expect the Phase 3 enum values.
TIER_HINT_MAP: dict[str, ModelTier] = {
    "cost-efficient": ModelTier.COST_EFFICIENT,
    "context-rich": ModelTier.CONTEXT_RICH,
    "balanced": ModelTier.CONTEXT_RICH,
    "specialized": ModelTier.CONTEXT_RICH,
    "frontier": ModelTier.STRONGEST,
}

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


@dataclass(frozen=True)
class StageContext:
    """Everything needed to run one deterministic single-turn LLM stage."""

    role: str  # llm_usage.role / trace role
    prompt_sub_role: str  # registry key, e.g. "technical_analyst"
    prompt_version: str  # registry key version, e.g. "v1"
    model_version_id: uuid.UUID  # production model row for this role
    lineage_id: uuid.UUID
    workflow_run_id: str
    stage_run_id: str
    variables: dict[str, object]  # template variables for the prompt
    idempotency_key: str
    prompt_version_id: uuid.UUID | None = None  # prompt_versions.id, if known
    # Reasoning-trace lineage link. Left ``None`` during a cycle because
    # the lineage row does not exist yet (write-before-dispatch, D3-7);
    # the orchestrator backfills it after the lineage commit (D3-11).
    trace_lineage_id: uuid.UUID | None = None


@dataclass(frozen=True)
class StageResult:
    """Outcome of a single LLM stage: validated parsed output + provenance."""

    parsed: dict[str, Any]
    trace_ids: list[uuid.UUID]  # one per gateway call made (≥1)
    raw_response: str
    model_used: str
    degraded: bool
    fallback_hops: int


def tier_from_hint(hint: str) -> ModelTier:
    """Map a registry tier hint to a gateway :class:`ModelTier`."""
    try:
        return TIER_HINT_MAP[hint]
    except KeyError as exc:
        msg = f"unknown model tier hint: {hint!r}"
        raise ValueError(msg) from exc


def _try_parse(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object from ``raw``, tolerating code fences / prose.

    Returns ``None`` if no JSON object can be extracted.
    """
    text = _FENCE_RE.sub("", raw.strip())
    start = text.find("{")
    if start == -1:
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text, start)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _messages(bundle: PromptBundle, ctx: StageContext) -> list[ChatMessage]:
    """Render the user prompt message for ``ctx`` from ``bundle``.

    ``output_schema`` and ``sub_role`` are injected from the bundle/context
    (the registry manifest lists them as template variables); the caller
    only supplies domain variables.
    """
    render_vars = dict(ctx.variables)
    render_vars.setdefault("output_schema", json.dumps(bundle.output_schema, indent=2))
    render_vars.setdefault("sub_role", ctx.prompt_sub_role)
    body = render(bundle, render_vars)
    return [ChatMessage(role="user", content=body)]


def _retry_messages(
    messages: Sequence[ChatMessage],
    raw_response: str,
    problem: str,
) -> list[ChatMessage]:
    """Append a ``fix your JSON`` correction deterministically (Phase 7)."""
    hint = (
        "Your previous output was rejected by schema validation because it "
        f"was not valid JSON: {problem}\n\n"
        f"Your previous output was:\n{raw_response}\n\n"
        "Return ONLY a single valid JSON object matching the requested schema. "
        "No markdown, no code fences, no prose."
    )
    return [*messages, ChatMessage(role="user", content=hint)]


async def run_llm_stage(
    gateway: Gateway,
    registry: Registry,
    ctx: StageContext,
    *,
    session: AsyncSession | None = None,
    spend: Mapping[str, float] | None = None,
) -> StageResult:
    """Run one single-turn stage with strict validation and trace writes.

    ``session`` enables reasoning-trace persistence (one row per gateway
    call). When ``None`` (sandbox/unit-test mode) trace writes are
    skipped and ``trace_ids`` is empty — production callers always pass
    a session so auditability is never lost silently.

    Raises:
        SchemaValidationError: output failed to parse/validate on the final
            permitted attempt (safe-state by default — never a guess).
        lumine.shared.errors.LLMError-derived: gateway-level failure
            (budget blocked, model unavailable, fallbacks exhausted).

    """
    bundle = registry.get_prompt(ctx.prompt_sub_role, ctx.prompt_version)
    tier = tier_from_hint(bundle.model_tier_hint)
    schema = bundle.output_schema
    messages = _messages(bundle, ctx)

    trace_ids: list[uuid.UUID] = []
    declined_reason: str = "unknown failure"
    raw_response: str = ""
    for attempt in range(_MAX_ATTEMPTS):
        attempt_messages = (
            messages if attempt == 0 else _retry_messages(messages, raw_response, declined_reason)
        )
        request = RouterRequest(
            model_version_id=ctx.model_version_id,
            role=ctx.role,
            tier=tier,
            lineage_id=ctx.lineage_id,
            prompt_ref=bundle.pins.prompt_ref,
            prompt_hash=bundle.pins.prompt_hash,
            idempotency_key=ctx.idempotency_key if attempt == 0 else f"{ctx.idempotency_key}-retry",
            messages=attempt_messages,
        )
        result: GatewayResult = gateway.complete(request, spend=spend)
        raw_response = result.response.content
        parsed = _try_parse(raw_response)
        if parsed is not None:
            declined_reason = validation_problem(parsed, schema)
        else:
            declined_reason = "response is not a single valid JSON object"
        if session is not None:
            trace_id = await write_trace(
                session,
                workflow_run_id=ctx.workflow_run_id,
                stage_run_id=ctx.stage_run_id,
                role=ctx.role,
                model_version_id=ctx.model_version_id,
                prompt_version_id=ctx.prompt_version_id,
                prompt_sent=str(attempt_messages[-1].content),
                response_raw=raw_response,
                parsed_output=parsed if declined_reason is None else None,
                prompt_hash=bundle.pins.prompt_hash,
                lineage_id=ctx.trace_lineage_id,
            )
            trace_ids.append(trace_id)
        if declined_reason is None:
            return StageResult(
                parsed=parsed,
                trace_ids=trace_ids,
                raw_response=raw_response,
                model_used=result.response.model_used,
                degraded=result.degraded,
                fallback_hops=result.fallback_hops,
            )
    # Final attempt still invalid — safe state, raise the reason.
    message = (
        f"{ctx.role}@{ctx.prompt_sub_role} returned schema-invalid output "
        f"after {_MAX_ATTEMPTS} attempts: {declined_reason}"
    )
    raise SchemaValidationError(message)


__all__ = (
    "StageContext",
    "StageResult",
    "run_llm_stage",
    "tier_from_hint",
)
