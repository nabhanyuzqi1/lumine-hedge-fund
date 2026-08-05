# Risk Engine Determinism Contract

## Overview

This document fixes Finding S1: the current `risk-engine.md` lets the
RiskValidator LLM return a continuous `risk_adjustment` multiplier
(`-0.5` to `+0.5`) on base volume. That multiplier is a
non-deterministic LLM sample on the position-sizing critical path. It
violates reproducibility (principle #6): replaying the same decision
with the same pins does not reproduce the same size, because the LLM
re-samples the multiplier.

This document supersedes the LLM risk-assessment section of
`risk-engine.md`. The deterministic base formula and exposure limits in
that document remain in force; only the LLM's role and the
sizing path change.

Decision **D8-7**: LLM risk output is **advisory only**. The continuous
multiplier is removed. Sizing uses a deterministic lookup keyed by a
qualitative `regime_bucket` the LLM proposes. The bucket-to-multiplier
map is code/registry, not an LLM sample. The resolved scalar multiplier
is pinned in lineage so replay reproduces the exact size.

## Decision: LLM risk role is advisory only (D8-7)

### Problem with the current contract

```
adjusted_volume = base_volume * (1 + llm.risk_adjustment)   # NON-DETERMINISTIC
```

`llm.risk_adjustment` is a float sampled by the model. The same
`prompt_version_id` + `model_version_id` + inputs does not guarantee
the same float. Two replays of one decision can produce different
sizes. That breaks the lineage gate's replay guarantee
(`lineage-schema.md`) and principle #6.

### New LLM risk contract

The RiskValidator LLM receives the same inputs as before but outputs a
qualitative, enumerable, bounded shape — never a continuous sizing
scalar.

Inputs (unchanged from `risk-engine.md`):
- the proposal (action, symbol, confidence)
- current portfolio exposure
- recent news sentiment (structured, see `prompt-injection-defense.md`)
- volatility regime (low / medium / high)
- correlation with existing positions

Outputs:

| Field | Type | Deterministic? | Role |
|-------|------|----------------|------|
| `risk_notes` | string | no (advisory prose) | Human/Review narrative only; never an input to sizing |
| `veto` | boolean | yes (hard boolean) | `true` → order REJECTED |
| `regime_bucket` | enum | yes (bounded set) | Selects a row in the deterministic lookup table |

The `risk_adjustment` float field is **deprecated**. It MUST NOT be
read by any sizing code. Migration note below.

`veto=true` is a hard, reproducible boolean: the LLM may flip it, but
a veto is a rejection, not a sizing input. Replaying a vetoed decision
reproduces REJECTED regardless of the LLM's prose. This is the one
piece of LLM output permitted on the critical path because its binary
surface is small and its consequence is conservative (reject, never
enlarge).

### Deterministic sizing lookup

The `regime_bucket` the LLM proposes is resolved to a multiplier
through a versioned registry table — not by the LLM. The map lives in
`policy_versions.risk_adjustments` (JSONB), pinned via the existing
`policy_version_id` FK in `lineage_records`.

Lookup shape:

```jsonc
// policy_versions.risk_adjustments (JSONB)
{
  "buckets": {
    "low-vol":  { "band1": 1.0, "band2": 1.0, "band3": 1.0 },
    "med-vol":  { "band1": 1.0, "band2": 0.9, "band3": 0.8 },
    "high-vol": { "band1": 0.9, "band2": 0.8, "band3": 0.7 }
  },
  "volatility_bands": {
    "band1": [0.0,  0.005],
    "band2": [0.005, 0.015],
    "band3": [0.015, null]
  },
  "default_multiplier": 0.7
}
```

- `regime_bucket` is one of `low-vol`, `med-vol`, `high-vol` (enum
  fixed by policy; LLM may only pick from this set).
- `volatility_band` is computed deterministically from the
  feature-store ATR/realized-vol feature at decision time
  (`feature-store-contract.md`). The LLM does not pick the band.
- The multiplier is the cell at `(regime_bucket, volatility_band)`.
- Any miss (unknown bucket, unknown band, missing cell) falls back to
  `default_multiplier` and is flagged as a risk-context anomaly.

### Final calculation (replaces the one in `risk-engine.md`)

```
if llm.veto:
    verdict = REJECT
    size    = NULL
else:
    bucket  = llm.regime_bucket          # enum, validated against policy
    band    = classify_volatility(atr)   # deterministic, from feature store
    mult    = policy.risk_adjustments.buckets[bucket][band]   # registry lookup
    adjusted_volume = base_volume * mult
    final_volume    = max(0.01, min(adjusted_volume, max_volume))
    verdict = APPROVE
```

The LLM never produces a float that reaches `final_volume`. The only
LLM influence on size is the choice of `regime_bucket`, which selects
a discrete cell from a versioned, hash-audited policy table.

## Lineage pinning

`lineage_records.risk_context` (JSONB, already defined in
`lineage-schema.md`) gains a required scalar field so replay
reproduces the exact size without re-consulting the LLM:

```jsonc
// lineage_records.risk_context (additions; rest unchanged)
{
  "veto": false,
  "regime_bucket": "high-vol",
  "volatility_band": "band3",
  "risk_adjustment_multiplier": 0.7,     // SCALAR — the resolved multiplier
  "policy_version_id": "<uuid>",         // already a top-level pin; repeated for convenience
  "risk_notes": "..."                    // advisory prose, not an input to sizing
}
```

`risk_adjustment_multiplier` is a scalar frozen at the blocking ACID
write (`lineage-schema.md` step 4b). Replay reads the scalar directly;
it does not re-invoke the LLM and does not re-resolve the lookup. This
restores the invariant: same `lineage_id` → same size, forever.

The blocking ACID gate already pins `policy_version_id`; the lookup
table is therefore reproducible from the pinned policy row. Pinning
the resolved scalar is belt-and-suspenders: it also covers the case
where the policy row is later retired but the decision must still
replay to the same number.

## Migration (deprecation of the old field)

- `risk_adjustment` (float, `-0.5..+0.5`) is **deprecated**. Sizing
  code MUST NOT read it.
- The LLM output schema (Phase 4) is updated to emit
  `{risk_notes, veto, regime_bucket}` and MUST NOT emit
  `risk_adjustment`.
- Existing `lineage_records` rows written under the old contract are
  not rewritten (D7-8: replay never mutates). They keep their original
  `risk_context`. A replay of a pre-migration row reads its already-pinned
  size and does not re-route through the new lookup.
- New rows (post-migration) MUST carry `risk_adjustment_multiplier` as
  a scalar. A row missing the field post-migration fails the lineage
  write gate.

## Interaction with existing decisions

- **D6-5 (stateless V1):** unchanged. The LLM is still stateless; the
  bucket is proposed per-cycle from the cycle's deterministic context.
  No inter-cycle memory is introduced.
- **D6-1 (static tier routing):** unchanged. RiskValidator still runs
  at `context-rich` with escalation to `strongest` per the routing
  table.
- **D7-5 (journal is truth):** the journal records the resolved scalar
  and the bucket. The journal remains the source of truth.
- **D7-8 (replay never mutates):** replay reads the pinned scalar; it
  never overwrites the original row and never re-samples the LLM.
- **Lineage gate (`lineage-schema.md`):** the blocking ACID write now
  includes the resolved scalar. A write that omits it fails the gate
  → safe state, no dispatch (principle #10).

## Rationale

| Concern | Answer |
|---------|--------|
| Reproducibility (#6) | Size is a function of `(base_volume, regime_bucket, volatility_band, policy_version_id)` — all pinned and deterministic. |
| Auditability (#4) | The bucket, band, and resolved multiplier are in `lineage_records.risk_context`. |
| LLM value-add | The LLM still encodes qualitative judgment (which regime, whether to veto) without producing a continuous sizing scalar. |
| Conservatism | Misses default to `default_multiplier` (the most conservative cell), not to 1.0. |

## Alternatives rejected

- **Deterministic multiplier from the LLM with temperature 0:** rejected.
  Temperature 0 does not guarantee determinism across providers, model
  versions, or batch size; and it still puts a float on the critical path.
- **Drop the LLM from risk entirely:** rejected. The LLM's qualitative
  regime read and veto are useful advisory inputs; removing them loses
  signal without fixing the sizing-determinism problem.
- **Pin the LLM-sampled float in lineage and read it back on replay:**
  rejected. That makes *replay* deterministic but makes *live* sizing
  non-deterministic run-to-run. The contract must be deterministic at
  decision time, not only at replay time.

## What this document does NOT define

- Prompt wording for the RiskValidator (Phase 4).
- The numeric cells of `risk_adjustments` (Phase 5 registry data; this
  doc fixes only the shape).
- ATR/volatility computation code (Phase 14+, feature-store-contract).
- Exposure limit enforcement (already in `risk-engine.md`).

## Phase boundary

This document fixes the LLM risk output contract (advisory, enum,
boolean), the deterministic lookup shape, the lineage scalar pin, and
the deprecation of `risk_adjustment`. It does not define prompt text
(Phase 4), physical table DDL beyond the JSONB shape (Phase 5), or
code (Phase 14+).
