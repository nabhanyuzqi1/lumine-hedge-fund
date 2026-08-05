# Context-Window Budget Policy

## Overview

`memory-policy.md` fixes the stateless V1 contract: the context
builder assembles each prompt from DB + registry per cycle. It does
not bound the assembled prompt against the model's context window.
Rich feature snapshots, extended journal context, and news payloads
will silently overflow a cost-efficient model's 8k window — and
silent truncation by the gateway is a reproducibility bug, because
two runs with the same pinned versions can produce different prompts
if the gateway's truncation is nondeterministic or unlogged.

This document fixes the per-role, per-tier token budget table, the
prioritized content layers, the deterministic truncation order, the
full-prompt storage and lineage-hash rule, the near-budget alert, and
the truncation-event record. It amends `memory-policy.md` (Phase 6)
and is consumed by the Phase 7 context builder.

## Decision: D6-6 — Explicit budget per role per tier, deterministic truncation

### Per-role, per-tier budget table

Every agent call resolves a `(sub_role, model_tier)` pair at decision
time (model tier from `model_versions.tier`). The context builder
fetches the token budget for that pair before assembling the prompt.

V1 budgets (tokens, prompt-side, excluding model max output tokens):

| sub_role \ tier | cost-efficient | context-rich | strongest |
|-----------------|----------------|--------------|-----------|
| technical_analyst | 4,000 | 16,000 | 32,000 |
| macro_analyst | 6,000 | 24,000 | 48,000 |
| news_analyst | 6,000 | 24,000 | 48,000 |
| smc_analyst | 4,000 | 16,000 | 32,000 |
| ic_forum | 12,000 | 32,000 | 64,000 |
| cio_proposer | 12,000 | 32,000 | 64,000 |
| risk_validator | 4,000 | 16,000 | 32,000 |

These numbers are policy and live in `policy_versions` scope
`context_budget` — not hardcoded. They are tuned in Phase 14 from
measured prompt sizes. The contract is that a budget EXISTS per pair
and is enforced; the exact numbers are promotable.

Smaller-window cost-efficient models get smaller budgets than
strongest models. A budget never exceeds `model_versions.context_window
- output_reserve`.

### Prioritized content layers

The context builder assembles content in three layers, in priority
order:

| Layer | Contents | Truncation rank |
|-------|----------|-----------------|
| MUST_HAVE | current features snapshot, current open positions, registry version pins, current regime, policy snapshot | never dropped |
| NICE_TO_HAVE | recent journal entries (last N decisions for this strategy/book), recent fills | dropped second, oldest first |
| OPTIONAL | news context, extended history, research notes, macro backdrop | dropped first, oldest first |

### Deterministic truncation

When assembled content exceeds the budget:

1. Drop OPTIONAL first, oldest-first, until within budget or OPTIONAL
   is exhausted.
2. If still over, drop NICE_TO_HAVE oldest-first.
3. NEVER drop MUST_HAVE. If MUST_HAVE alone exceeds budget, the call
   fails safe — `FAILED_SAFE` with code `context_budget_exceeded`.
   This is a design error (prompt too large for tier), not a runtime
   truncation.

Truncation is deterministic given the same inputs and the same
budget. Two runs with the same pinned versions and the same DB state
produce the same truncated prompt.

### Full prompt stored, hash contributes to lineage

The FULL prompt actually sent to the model — after truncation — is
stored in `reasoning_traces` (see reasoning-trace-storage). Its SHA-
256 hash contributes to the lineage record. Therefore truncation is
reproducible: replaying a decision reproduces the same truncated
prompt, because the same layers were dropped in the same order.

This closes the silent-truncation reproducibility hole. The gateway
may still enforce its own hard cap, but the context builder's
deterministic truncation runs first and is the recorded artifact.

### Near-budget alert

If the final prompt size is within 10% of the budget (i.e.
`size >= 0.9 * budget`), emit a `near_budget` alert. This is design
pressure to shrink the prompt or promote to a higher tier — not a
runtime failure. Persistent near-budget alerts on a role signal the
Review worker to recommend a prompt trim or tier bump.

### Truncation event recorded

Every truncation writes a `truncation_event` into the reasoning
trace:

```json
{
  "truncation_event": {
    "budget_tokens": 4000,
    "assembled_tokens": 5200,
    "final_tokens": 3950,
    "layers_dropped": ["OPTIONAL"],
    "items_dropped": [
      { "layer": "OPTIONAL", "kind": "news_context", "count": 3, "oldest_ts": "..." }
    ],
    "must_have_exceeded": false
  }
}
```

If `must_have_exceeded` is true, the event is a failure record, not a
truncation — the call did not proceed.

## What this document does NOT define

- Context builder selection logic (which DB rows become MUST_HAVE vs
  NICE_TO_HAVE) — Phase 7 orchestration + Phase 14 code.
- Token counting implementation (tokenizer choice per model) — Phase
  14, must match the gateway's tokenizer.
- Prompt text content — Phase 4.
- Gateway-side hard cap behavior — Phase 6 `llm-gateway.md`; this
  policy ensures the builder's deterministic truncation runs first.

## Phase boundary

This document amends `memory-policy.md` (Phase 6) by bounding the
stateless context assembly against the model window. It is consumed
by the Phase 7 context builder. It does not define selection logic,
tokenizer code, or prompt text.
