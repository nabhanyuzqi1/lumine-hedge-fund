# ADR-0020 — Versioned, point-in-time feature store

- **Status:** Accepted
- **Phase:** 03-agents-and-contracts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Features are currently an unversioned JSONB blob in
`lineage_records.features`. That blob is a snapshot at decision time, but
the feature definition (which indicators, which parameters, which code) is
not pinned. Two runs with the "same" `features` JSONB can have been
computed by different feature code. This violates reproducibility
(principle #6): replaying a decision cannot guarantee the same feature
vector because the code that produced the features is not identified.

## Decision

Features are versioned, registry-pinned, point-in-time correct, and
compute-once. A new `feature_versions` registry table pins the definition
(name, version, params, `code_hash`, `warmup_required`). A `feature_values`
table stores computed values with `as_of_ts` (point-in-time marker) and
`computed_ts`, partitioned by `as_of_ts`, PK enforcing compute-once (no
overwrite). `lineage_records.features` gains a `feature_versions` array —
the fifth version pin alongside model, prompt, policy, strategy. Lookahead
(`as_of_ts > T`) is a hard error at read time.

## Rationale

- Same `feature_version_id` + same `as_of_ts` + same symbol = identical
  feature vector, forever (PK immutable, `code_hash` + `params` immutable).
- The fifth pin closes the last replay-divergence vector.
- Point-in-time correctness makes features safe for backtest: the store
  refuses to serve the future.
- Compute-once prevents silent re-computation divergence.

## Consequences

- Positive: replay reconstructs the exact feature vector without
  recomputation.
- Positive: backtest parity (ADR-0019) depends on and is enabled by this
  contract.
- Negative: a feature definition change requires a new registry row (no
  in-place edits).
- Reversibility: the registry follows the standard supersession model.

## Cross-references

- Related ADRs: ADR-0014, ADR-0019, ADR-0016
- Implements principle(s): #6
- Affects phases: 03, 05, 13
- Source document: `../03-agents-and-contracts/feature-store-contract.md` (S11)
