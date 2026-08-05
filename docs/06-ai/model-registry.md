# Model Registry Curation

## Overview

Decision **D6-3**: `model_versions` (Phase 3 registry) is the only
place concrete models are named. This document fixes *how rows enter,
promote, and retire* — the curation lifecycle that keeps routing
reproducible while allowing provider replacement (principle #9).

## Row anatomy (logical)

| Field | Meaning |
|-------|---------|
| `model_version_id` | PK, referenced by routing + lineage |
| `provider` | e.g. openai, deepseek, kimi, qwen, glm |
| `model` | provider's model string |
| `params` | temperature, max_tokens, etc. (part of identity — changing params = new row) |
| `tier` | Phase 3 enum: `cost-efficient` / `context-rich` / `strongest` (model-routing.md) |
| `status` | Phase 3 enum: `sandbox` → `staging` → `production` → `retired` |
| `model_hash` | content hash of the row (same audit pattern as prompts) |
| `eval_summary` | offline eval results that justify promotion |
| `created_ts`, `promoted_ts`, `retired_ts` | lifecycle audit |

Params are part of identity: same model at different temperature is a
different row. Replays must reconstruct the exact call.

## Lifecycle

The status enum and promotion gate are **Phase 3 locked decisions**
(`registry-schema.md:26-45,139-148`) — Phase 6 applies them to models,
it does not redefine them:

```
sandbox ──(offline eval passes)──▶ staging ──(CIO human gate)──▶ production ──(superseded/bad)──▶ retired
```

1. **Sandbox**: row added with eval intent. Never routable by the live
   pipeline; usable only by the Research/Review sandbox.
2. **Staging**: offline eval evidence attached (`eval_summary`); shadow
   runs permitted. Still not routable by the live pipeline.
3. **Production**: promoted by the **CIO human gate** — the same gate
   Phase 3 applies to every registry table. Only `production` rows are
   resolvable by the gateway and pinnable to lineage.
4. **Retired**: superseded or provider-deprecated. Retired rows:
   - remain queryable forever (lineage FKs point at them — audit);
   - fail fast if referenced by *new* routing (no silent substitution).

## Promotion discipline

- **One production row per (tier, role-class) slot** at a time. The
  routing policy's default picks exactly one; alternates exist only in
  the fallback chain.
- **No auto-promotion.** A model never reaches production because a
  provider released it. Promotion is a reviewed human decision tied to
  eval evidence — the AI-side mirror of Phase 4's prompt promotion and
  Phase 5's migration review.
- **Shadow eval before promotion**: a sandbox/staging row may run in
  shadow (output logged, not acted on) against live cycles to gather
  comparative evidence. Shadow runs cost money — they consume the
  cost-efficient tier budget by default (cost-control.md).

## Provider replacement scenario (the point of all this)

Replacing e.g. one context-rich provider with another:

1. Add sandbox row(s) for the new provider's model.
2. Shadow/eval → staging → CIO promotes to production → routing policy
   points at new ID.
3. Old row retires. Old lineage still resolves (row kept).
4. Zero code changes; zero prompt changes (prompts are model-agnostic
   by Phase 4 schema discipline).

## Anti-patterns (rejected)

- Editing a row's `provider`/`model`/`params` in place — destroys
  replay. Always a new row.
- Deleting retired rows — breaks lineage FK audit.
- Routing directly to a provider string from code — bypasses the
  registry and this lifecycle.

## What this document does NOT define

- Eval dataset contents / sandbox methodology (Research sandbox,
  later phases).
- Registry DDL (Phase 3) or physical indexes (Phase 5).

## Phase boundary

This document fixes the curation lifecycle and promotion discipline.
It does not define eval methods or schema DDL.
