# Phase 6 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Static tier routing + deterministic escalation** | Every agent role is pinned to a default model tier — the Phase 3 `model_versions.tier` enum (`cost-efficient` cheap reasoning, `context-rich` standard, `strongest` premium) — recorded in `policy_versions.routing`. Phase 6 introduces no new tier vocabulary. Escalation to a higher tier happens only when deterministic conditions fire (low confidence, high inter-analyst disagreement, CIO override of IC, debate round triggered). Keeps model choice reproducible (principle #6) — replaying a decision must select the same model. Dynamic LLM-router rejected: non-deterministic, unauditable. |
| 2 | **9router = single egress for all LLM calls** | All model traffic flows through the 9router gateway. Code never calls a provider SDK directly. Enables provider replaceability (principle #9), centralized cost accounting into `llm_usage`, and per-tier fallback when a provider is down. |
| 3 | **Model identity resolved from registry, never hardcoded** | Code references `model_version_id`; the concrete provider/model string is resolved from `model_versions` at call time. Same pattern as prompts (Phase 4 D4-1). Promoting a model = new registry row + CIO human gate (Phase 3 lifecycle `sandbox → staging → production → retired`), no code change. Only `production` rows are routable by the live pipeline. |
| 4 | **Daily budget per tier + circuit breaker** | `policy_versions.cost` sets a daily USD cap per tier plus a global cap. A deterministic budget check runs before every LLM call. On breach: degrade to cheaper tier for non-critical roles; block non-essential reasoning (research, journal summarization); never block the live decision pipeline below its minimum tier. Every degrade/block event is written to `lineage_records` with `verdict='degraded'` context so cost incidents are auditable (principle #10). |
| 5 | **V1 agents are stateless (no persistent memory)** | Each decision is computed fully from current market data + registry state. No rolling summaries, no RAG, no vector store. `llm_usage` and `lineage_records` already give us the raw material to build memory later; adding memory now would break pure replayability and is YAGNI before a measured need. Deferred: retrieval-augmented context re-enters as its own justified decision when the Research/Review sandbox (Phase 2) produces a consumer. |
| 6 | **Fallback chain per tier, not per role** | If a tier's primary provider fails, the gateway tries the tier's declared alternates in order (same tier first, then next tier down: strongest → context-rich → cost-efficient). Never silently upgrade to a more expensive tier on failure — that hides cost. Fallback events are logged. |
| 7 | **Cost attribution at lineage granularity via new `llm_usage` table** | Phase 3 never defined an `llm_usage` table (only `model_versions.context_window`). Phase 6 introduces it: append-only, FK to `lineage_records` + `model_versions`, carrying tokens/cost/fallback/degraded per call. Budget, post-mortems, and per-strategy cost analysis all reuse this one join. Physical profile joins the Phase 5 decision-table class. |

## Principles honored

- **#6 Reproducibility before adaptation**: deterministic routing, deterministic escalation, deterministic budget check, stateless agents.
- **#9 Replaceability**: provider-agnostic gateway, registry-resolved model IDs, per-tier fallback chains.
- **#10 Safe state by default**: circuit breaker degrades rather than hides overspend; blocked reasoning is recorded, not silent.
- **YAGNI**: no fine-tuning, no vector store, no dynamic router until a measured consumer exists.

## Phase boundary respected

Phase 6 fixes routing tiers, gateway role, cost policy, memory policy,
and registry curation. It does NOT define: prompt contents (Phase 4),
AutoGen recovery/observability (Phase 7), risk math (Phase 7/8), API
(Phase 9), or code (Phase 14+).
