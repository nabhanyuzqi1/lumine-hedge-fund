# ADR-0034 — Deterministic regime classifier as first-class concept

- **Status:** Accepted
- **Phase:** 03-agents-and-contracts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`risk-engine.md` lists "volatility regime (low/medium/high)" as an LLM
input but treats regime as a free-text flavor the model interprets. That
is unsafe: a strategy tuned for trending markets can silently run inside a
range regime, and the only thing stopping it is LLM judgment. Phase 8 risk
engine consumes regime; Phase 3 must own the contract so regime is
first-class, versioned, deterministic, and pinned to lineage. Regime was
an LLM input; strategies ran in the wrong regime.

## Decision

The source of truth for the current regime is a deterministic classifier
— rule-based or model-based, but always versioned, hash-pinned, and
replayable. A `regime_versions` registry table pins the classifier
definition (`classifier_code_hash`, `params`, `regime_buckets`). Five V1
buckets: `low_vol_trend`, `low_vol_range`, `high_vol_trend`,
`high_vol_range`, `crisis`. Each `strategy_versions` row carries
`regime_compatibility` — an allow-list of compatible regimes; a strategy
not explicitly compatible is blocked (fail-closed). `lineage_records` gains
`regime_version_id` and `regime_id` pins. The LLM may propose a regime
label as reasoning input; the classifier output is what gates execution.
Crisis regime halts all trading pending CIO override.

## Rationale

- Reproducibility (#6): a regime label that depends on LLM judgment cannot
  be replayed; a pinned classifier with hash-pinned params can.
- Safe state (#10): strategy gating fails closed — a strategy not
  explicitly compatible with the current regime is blocked, not allowed.
- Auditability (#4): `regime_version_id` and `regime_id` are pinned to
  every lineage record.
- LLMs reason, deterministic code decides: regime classification gates
  capital; such decisions stay deterministic.

## Consequences

- Positive: no strategy runs in a regime it is not tested for.
- Positive: regime context of any past decision is recoverable forever.
- Positive: crisis regime halts trading automatically (principle #10).
- Negative: a classifier change requires a new registry row and CIO gate.
- Reversibility: the classifier follows the standard supersession model.

## Cross-references

- Related ADRs: ADR-0016, ADR-0031
- Implements principle(s): #6, #7, #10
- Affects phases: 03, 08
- Source document: `../03-agents-and-contracts/regime-model.md` (S12)
