# Model Routing — Static Tiers + Deterministic Escalation

## Overview

Decision **D6-1**: model choice is a function of (role, tier, registry) —
never of a live LLM judgment call. This is what makes a decision
replayable: given the same `policy_versions` row and the same inputs,
the same model is selected.

## Tiers

Tier names are the Phase 3 `model_versions.tier` enum
(`registry-schema.md`) — Phase 6 introduces no new vocabulary:

| Tier (Phase 3 enum) | Class | Typical use | Relative cost |
|------|-------|-------------|---------------|
| `cost-efficient` | cheap reasoning (Kimi K3 / Qwen 3.7 / GLM 5.2 class) | bulk analyst passes, journal summarization, non-critical narrative | 1× |
| `context-rich` | standard frontier (GPT-5.5 / DeepSeek V4 class) | IC Forum, CIO Proposer default, debate round | ~10× |
| `strongest` | premium frontier (top of family) | escalation only: high-stakes or disagreement resolution | ~30× |

Shorthand: `cost-efficient` ≡ "tier1", `context-rich` ≡ "tier2",
`strongest` ≡ "tier3" elsewhere in this folder. The enum values are
what land in the database (`model_versions.tier`, `llm_usage.tier`,
`policy_versions.routing`).

Concrete provider/model strings live in `model_versions` — this document
fixes the *tier semantics*, not specific SKUs. Adding a new model family
= new registry row mapped to a tier.

## Role → default tier mapping

Stored in `policy_versions.routing` (JSONB). V1 baseline:

| Role | Default tier | Escalation target |
|------|--------------|-------------------|
| Technical Analyst | cost-efficient | context-rich |
| Macro Analyst | cost-efficient | context-rich |
| News Analyst | cost-efficient | context-rich |
| SMC Analyst | cost-efficient | context-rich |
| IC Forum | context-rich | strongest |
| CIO Proposer | context-rich | strongest |
| Risk Officer (LLM parts) | context-rich | strongest |
| Journal / narrative jobs | cost-efficient | (none) |
| Research sandbox | cost-efficient | context-rich (manual flag only) |

Rationale: analysts run most frequently and in parallel (4× per cycle) —
they dominate token volume, so they get the cheap tier. IC/CIO run once
per cycle and carry the decision — they get context-rich by default.

## Escalation triggers (deterministic)

Escalation is system code, not an LLM hint. A role runs at its
escalation target only when one of these fires:

1. **Low confidence**: role output `confidence < policy.escalation.min_confidence`
   → re-run same role at next tier, keep higher-confidence result.
2. **High disagreement**: analyst-pairwise action conflict above
   `policy.escalation.disagreement_threshold` (same check that arms the
   Phase 4 debate trigger) → debate round runs at strongest, not
   context-rich.
3. **CIO overrides IC**: when `overrode_ic=true`, the CIO Proposer call
   itself must have run at strongest — if it ran at context-rich, re-run
   at strongest before committing. Override is the highest-stakes act;
   it pays for the best model.
4. **Kill-switch-adjacent context**: if the risk engine flags the cycle
   as near-breach (drawdown within `policy.escalation.near_breach_pct`
   of limit), the whole cycle escalates one tier. Cautious-by-default.

Every escalation is recorded: the `lineage_records.proposal` already
carries `debate_held` / `overrode_ic`; the model actually used is pinned
in `model_version_id`. No hidden swaps.

## De-escalation

None. Tiers only move up within a cycle, never down. Moving down
mid-cycle would create ambiguity about which model's output governs.

## Anti-patterns (explicitly rejected)

- **Dynamic LLM router** ("ask a model which model to use"): breaks
  reproducibility, adds a meta-call cost, and is unauditable.
- **Hardcoded model strings in agent code**: violates D6-3; blocks
  provider replacement.
- **Silent upgrade on provider failure**: see D6-6 — fallback never
  climbs a tier on its own.

## What this document does NOT define

- Specific provider SKUs / pricing (registry + Phase 11 infra).
- Budget numbers (cost-control.md).
- Retry/timeout mechanics (llm-gateway.md).

## Phase boundary

This document fixes tier semantics, role mapping, and escalation rules.
It does not define prompts, budgets, or gateway internals.
