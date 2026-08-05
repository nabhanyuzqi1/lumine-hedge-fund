# ADR-0016 — LLM risk role is advisory only; sizing multiplier is a deterministic registry lookup

- **Status:** Accepted
- **Phase:** 08-trading
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The original `risk-engine.md` lets the RiskValidator LLM return a
continuous `risk_adjustment` multiplier (-0.5 to +0.5) on base volume. That
multiplier is a non-deterministic LLM sample on the position-sizing
critical path. Replaying the same decision with the same pins does not
reproduce the same size because the LLM re-samples the multiplier. This
violates reproducibility (principle #6) and breaks the lineage gate's
replay guarantee.

## Decision

LLM risk output is advisory only. The continuous multiplier is removed.
Sizing uses a deterministic lookup keyed by a qualitative `regime_bucket`
the LLM proposes. The bucket-to-multiplier map lives in
`policy_versions.risk_adjustments` (versioned, hash-audited registry), not
in an LLM sample. The resolved scalar multiplier is pinned in
`lineage_records.risk_context` so replay reproduces the exact size. The
LLM may still emit a hard `veto` boolean (conservative: reject, never
enlarge).

## Rationale

- Reproducibility (#6): size is a function of `(base_volume, regime_bucket,
  volatility_band, policy_version_id)` — all pinned and deterministic.
- Auditability (#4): bucket, band, and resolved multiplier are in lineage.
- LLM value-add preserved: qualitative regime read and veto remain.
- Conservatism: misses default to `default_multiplier` (most conservative
  cell), not 1.0.
- Temperature-0 deterministic float rejected: does not guarantee
  determinism across providers and still puts a float on the critical path.

## Consequences

- Positive: same `lineage_id` → same size, forever.
- Positive: LLM influence on size is a discrete enum, not a continuous
  sample.
- Negative: the sizing granularity is coarser (buckets, not a continuous
  range).
- Reversibility: the lookup table is policy; the advisory-only contract is
  structural.

## Cross-references

- Related ADRs: ADR-0014, ADR-0034
- Implements principle(s): #6, #10
- Affects phases: 08, 03
- Source document: `../08-trading/risk-engine-determinism.md` (S1)
