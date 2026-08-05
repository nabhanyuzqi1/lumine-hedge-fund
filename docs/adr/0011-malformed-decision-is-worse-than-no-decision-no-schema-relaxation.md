# ADR-0011 — Malformed decision is worse than no decision (no schema relaxation)

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

When an LLM returns JSON that fails the Phase 4 schema, the temptation is
to relax the schema and retry to "get a decision through." But a coerced
decision is a fabricated decision — it does not represent what the model
actually concluded. A malformed decision propagates garbage into the
lineage and the execution path. Provider-level retries and fallbacks stay
in Phase 6; the workflow layer must not loosen schemas.

## Decision

Invalid structured output fails safe — schema is never relaxed to coerce a
pass. Analyst JSON failing the schema produces `FAILED_SAFE`. Debate output
invalid → debate discarded, IC proceeds on pre-debate analyst outputs.
IC or CIO output invalid → run `FAILED_SAFE`. A malformed decision is
worse than no decision.

## Rationale

- Safe state by default (principle #10): a lost run is better than a
  garbage decision.
- Schema relaxation would fabricate decision lineage — violating
  reproducibility (#6) and auditability (#4).
- Provider-level retries and fallbacks belong to Phase 6, not the workflow
  layer.
- Debate failure is non-fatal (debate is optional); IC/CIO failure is
  fatal (no proposal without them).

## Consequences

- Positive: no garbage decision ever reaches execution.
- Positive: schema failures are visible and auditable.
- Negative: a transient schema failure loses the entire run (token cost).
- Reversibility: schema is versioned via registry; relaxation would
  require a new schema version, not a runtime coercion.

## Cross-references

- Related ADRs: ADR-0008, ADR-0028
- Implements principle(s): #6, #10
- Affects phases: 07, 04
- Source document: `../07-autogen/decisions.md` (D7-4)
