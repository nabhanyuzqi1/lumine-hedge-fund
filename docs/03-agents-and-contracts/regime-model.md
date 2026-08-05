# Regime Model — Deterministic Classifier & Strategy Gating

## Overview

`risk-engine.md` lists "volatility regime (low/medium/high)" as an LLM
input but treats regime as a free-text flavor the model interprets.
That is unsafe: a strategy tuned for trending markets can silently run
inside a range regime, and the only thing stopping it is LLM judgment.
Phase 8 risk engine consumes regime; Phase 3 must own the contract so
regime is first-class, versioned, deterministic, and pinned to lineage.

This document defines the deterministic regime classifier, the
`regime_versions` registry table, per-regime policy overrides, the
strategy-to-regime compatibility gate, regime transition journaling,
and the crisis halt. It amends `risk-engine.md` (Phase 8) and the
policy registry (Phase 3).

## Decision: D3-9 — Regime is deterministic, versioned, and pinned

The source of truth for the current regime is a **deterministic
classifier** — rule-based or model-based, but always versioned, hash-
pinned, and replayable. The LLM may PROPOSE a regime label as
reasoning input, but the classifier output is what gates execution.

Rationale:

- **Reproducibility (#6).** A regime label that depends on LLM
  judgment cannot be replayed. A pinned classifier with hash-pinned
  params can.
- **Safe state (#10).** Strategy gating must fail closed: a strategy
  not explicitly compatible with the current regime is blocked, not
  allowed.
- **Auditability (#4).** `regime_version_id` and the resolved
  `regime_id` are pinned to every lineage record so the regime
  context of a past decision is recoverable forever.
- **LLMs reason, deterministic code decides.** Regime classification
  is a decision that gates capital. Per the platform constitution,
  such decisions stay deterministic.

## Regime buckets

```sql
CREATE TYPE regime_bucket AS ENUM (
  'low_vol_trend',
  'low_vol_range',
  'high_vol_trend',
  'high_vol_range',
  'crisis'
);
```

Five buckets is the V1 set. The set is fixed by the registry row's
`regime_buckets` array — a new bucket requires a new major version of
the classifier, not a runtime mutation.

## Registry table: `regime_versions`

```sql
CREATE TABLE regime_versions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version            SEMVER NOT NULL,
  classifier_kind    TEXT NOT NULL,                  -- 'rule' | 'model'
  classifier_code_hash TEXT NOT NULL,                -- SHA-256 of pinned classifier code
  params             JSONB NOT NULL,                 -- thresholds, lookback windows, model weights
  regime_buckets     regime_bucket[] NOT NULL,       -- buckets this classifier may emit
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  retired_at         TIMESTAMPTZ,
  status             registry_status NOT NULL,       -- sandbox | staging | production | retired
  superseded_by      UUID REFERENCES regime_versions(id),
  UNIQUE (version)
);
```

This follows the shared registry column contract and status lifecycle
from `registry-schema.md` (sandbox -> staging -> production -> retired;
production only is pinnable; retired never deleted). Supersession is
explicit via `superseded_by`.

## Per-regime policy overrides

`policy_versions` (registry-schema.md) gains a `scope='regime'` row
whose `policy` JSONB carries per-regime overrides:

```json
{
  "low_vol_trend":  { "risk_multiplier": 1.0, "strategy_gating": "matrix" },
  "low_vol_range":  { "risk_multiplier": 0.8, "strategy_gating": "matrix" },
  "high_vol_trend": { "risk_multiplier": 0.6, "strategy_gating": "matrix" },
  "high_vol_range": { "risk_multiplier": 0.4, "strategy_gating": "matrix" },
  "crisis":         { "risk_multiplier": 0.0, "strategy_gating": "halt_all" }
}
```

`risk_multiplier` scales the base position size from `risk-engine.md`.
`strategy_gating` selects the gating mode: `matrix` consults the
compatibility matrix below; `halt_all` blocks every strategy
regardless of matrix.

## Strategy-to-regime compatibility matrix

Each `strategy_versions` row carries a `regime_compatibility`
JSONB field — an allow-list of regimes the strategy may run in:

```json
{ "compatible_regimes": ["low_vol_trend", "high_vol_trend"] }
```

Gating rule per cycle, evaluated deterministically after the
classifier emits the current `regime_id`:

```
if regime_id NOT IN strategy.regime_compatibility.compatible_regimes:
    BLOCK strategy for this cycle
    journal event: strategy_blocked_by_regime
        { strategy_id, regime_id, regime_version_id, cycle_ts, reason }
```

A strategy not explicitly listed as compatible is blocked. No default-
allow. This is fail-closed per principle #10.

The block is a journal event, not a silent skip. The scheduler records
it so the Review worker can detect strategies that never fire and
prompt a CIO decision (retire the strategy or expand its matrix).

## Regime transitions are journal events

When the classifier emits a `regime_id` that differs from the
previous cycle's `regime_id`, a `regime_transition` journal event is
written:

```
{ from_regime, to_regime, regime_version_id, cycle_ts, classifier_features_snapshot }
```

Transitions are not gating themselves — the gate is the
compatibility matrix applied to the new regime — but they are auditable
signals for the Review worker and CIO.

## Lineage pins

`lineage_records` gains two pins (additive columns, no break to
existing schema):

| Column | Type | Notes |
|--------|------|-------|
| `regime_version_id` | UUID | FK to `regime_versions.id`; the classifier version that produced this decision's regime |
| `regime_id` | regime_bucket | The resolved bucket for this decision |

Both are immutable at insert. A decision cannot exist without a
pinned regime — if the classifier fails, the cycle fails safe
(`FAILED_SAFE`), never defaults to a guessed regime.

## LLM may propose, classifier decides

The RiskValidator LLM (per `risk-engine.md`) receives the classifier's
`regime_id` as an input and may PROPOSE a different regime in its
`risk_notes`. That proposal is reasoning data only — it does not
change the pinned `regime_id` and does not relax the compatibility
gate. If an operator believes the classifier is wrong, the fix is a
new `regime_versions` row promoted through the human CIO gate, not a
runtime override.

## Crisis regime — halt pending CIO override

When the classifier emits `crisis`:

1. All trading halts immediately for the cycle (gating =
   `halt_all`).
2. Open positions are NOT auto-closed by the regime gate alone —
   the kill switch (`policy_versions` scope `kill_switch`) governs
   position-level liquidation. Crisis blocks new entries; it does
   not force exits.
3. A `crisis_halt` journal event is written.
4. Trading resumes only after an explicit CIO override (human gate,
   principle #7) — recorded as a status transition. The override does
   not delete the crisis event; it unblocks the next cycle.

This ties the regime model to the kill-switch hierarchy in
`governance-and-cross-department.md`: crisis is a regime-level halt,
the kill switch is the operator-level halt, and both must be cleared
explicitly.

## What this document does NOT define

- Classifier algorithm internals (rule thresholds, model weights) —
  those live in the `regime_versions.params` JSONB and are promoted
  through the registry, not hardcoded here.
- Risk math beyond the `risk_multiplier` scaling hook — that stays in
  `risk-engine.md` (Phase 8).
- Kill-switch tiers and position-liquidation rules — `risk-engine.md`
  and `policy_versions` scope `kill_switch`.
- Scheduler internals for cycle triggering — Phase 7.

## Phase boundary

This document amends `risk-engine.md` (Phase 8) by making the regime
input a pinned, deterministic artifact instead of free LLM text. It
amends the policy registry (Phase 3) by adding `scope='regime'` and
the `regime_versions` table. It does not define classifier code
(Phase 14+), risk formulas beyond the multiplier hook, or UI exposure
of regime state (Phase 9/10).
