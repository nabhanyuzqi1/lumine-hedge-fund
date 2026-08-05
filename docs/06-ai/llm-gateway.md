# LLM Gateway — 9router Role & Contract

## Overview

Decision **D6-2**: 9router is the single egress for all LLM traffic.
Application code holds no provider SDK, no provider credentials, and no
provider URLs. This is the enforcement point for replaceability
(principle #9) and centralized accounting.

## Position in the stack

```
agent / orchestrator
      │  (role, model_version_id, prompt_ref, lineage_id, payload)
      ▼
9router gateway
      │  resolves model_version_id → provider + model string
      │  applies per-tier fallback chain
      │  emits usage record → llm_usage (async)
      ▼
provider API (OpenAI / DeepSeek / Kimi / Qwen / GLM / ...)
```

## Request contract (logical)

Every call carries:

| Field | Source | Purpose |
|-------|--------|---------|
| `model_version_id` | registry | resolves provider + model + params |
| `prompt_ref` + `prompt_hash` | Phase 4 | audit: which prompt text ran |
| `lineage_id` | orchestrator | cost attribution to decision |
| `role` | orchestrator | per-role cost analytics |
| `tier` | routing policy | fallback chain selection |
| `idempotency_key` | orchestrator | dedupe retries at gateway |
| payload (messages, schema) | Phase 4 schemas | the actual prompt |

The gateway response echoes back the *actual* model used (after any
fallback), token counts, and cost estimate — all of which land in
`llm_usage`.

## Resolution & registry

`model_versions` is the source of truth:

- one row per (provider, model, parameter set) promotion;
- `status` in the Phase 3 enum (`sandbox`, `staging`, `production`,
  `retired`);
- only `production` rows are resolvable by the gateway; `retired` rows
  fail fast with a clear error (never silently substitute another
  model). `sandbox`/`staging` rows are routable only from the Research
  sandbox, never the live pipeline.

Promotion and retirement are curation actions (see model-registry.md),
not code deploys.

## Fallback chain (D6-6)

Per tier, `policy_versions.routing.fallbacks` declares an ordered list
of alternate `model_version_id`s:

1. Try primary.
2. On provider error (5xx, timeout, rate-limit): try next alternate
   **in the same tier**.
3. If same-tier alternates exhausted: degrade to next tier **down**
   (strongest → context-rich → cost-efficient), never up.
4. If cost-efficient also fails: the call fails; the pipeline treats it
   as a stage failure (Phase 7 recovery), not a silent skip.

Every fallback hop is logged with reason. Fallback never upgrades cost
without an explicit deterministic escalation trigger (model-routing.md).

## Timeouts & retries (policy level)

| Failure | Gateway behavior |
|---------|------------------|
| Provider timeout | 1 immediate retry, then fallback hop |
| Rate limit (429) | respect `Retry-After`, 1 retry, then fallback |
| Auth failure (401/403) | no retry — circuit-open that provider, alert |
| Malformed output vs schema | NOT a gateway concern — Phase 4 schema validation handles it at the orchestrator |

Auth failures open a per-provider circuit for
`policy.gateway.circuit_open_seconds` so a dead provider doesn't tax
every call.

## What the gateway does NOT do

- No caching of completions in V1 (decisions are point-in-time; cached
  reasoning would be stale by construction). Revisit only for
  deterministic batch jobs (journal summarization) if cost demands it.
- No content filtering/moderation layer — institutional internal use.
- No streaming in V1 (outputs are small JSON objects; streaming adds
  parser complexity for zero user benefit). UI streaming of *status*
  is Phase 9/10, not LLM token streaming.

## What this document does NOT define

- 9router deployment/hosting (Phase 11).
- Provider credentials & rotation (Phase 12).
- Exact timeout numbers (tuned in Phase 14 from measured latency).

## Phase boundary

This document fixes the gateway's role, request contract, resolution,
fallback, and retry policy. It does not define deployment, secrets, or
orchestration recovery.
