# ADR-0008 — Failure taxonomy determines recovery, not per-call judgment

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Ad-hoc retry logic per call site is non-deterministic, unauditable, and
produces inconsistent recovery behavior. A stage that fails for a transient
provider timeout should not be treated the same as a schema-invalid output
or a kill-switch activation. Recovery must be driven by a fixed taxonomy so
the matrix is deterministic and auditable.

## Decision

All stage failures are classified into a fixed taxonomy:
`TRANSIENT_PROVIDER`, `SCHEMA_INVALID`, `CHECKPOINT_UNAVAILABLE`,
`CONTEXT_STALE`, `VERSION_MISMATCH`, `DEADLINE_EXCEEDED`,
`KILL_SWITCH_ACTIVE`, `OPERATOR_CANCELLED`, `INTERNAL_INVARIANT`. The
taxonomy drives the recovery matrix deterministically — no ad-hoc retry
logic per call site.

## Rationale

- Deterministic recovery is auditable and replayable (principle #6).
- A fixed taxonomy makes the recovery matrix testable and CI-checkable.
- Per-call judgment would produce inconsistent behavior across stages and
  providers.
- The taxonomy covers the full failure space without overlap.

## Consequences

- Positive: recovery behavior is uniform, predictable, and testable.
- Positive: new failure modes require a taxonomy extension (explicit, not
  silent).
- Negative: a novel failure that does not fit the taxonomy defaults to
  `INTERNAL_INVARIANT` (conservative).
- Reversibility: taxonomy is extensible; existing codes are stable.

## Cross-references

- Related ADRs: ADR-0006, ADR-0010, ADR-0011, ADR-0033
- Implements principle(s): #6, #10
- Affects phases: 07
- Source document: `../07-autogen/decisions.md` (D7-7)
