# ADR-0006 — Resume only from validated checkpoints via deterministic gates

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

A crashed or interrupted workflow run must be resumable without
fabricating decision lineage. Resuming from partial or unvalidated stage
output risks building a decision on garbage. Four conditions must hold
before resume is safe: input freshness, pinned-version match, kill-switch
clear, and no superseding newer trigger. Any gate failure should start a
fresh run rather than gamble on stale state.

## Decision

Resume is allowed only from the last validated durable checkpoint, and
only after four deterministic gates pass: input freshness, pinned-version
match (model/prompt/policy), kill-switch clear, and no superseding newer
trigger. Any gate failure produces `ABORTED_STALE` and a new run starts
fresh. Never resumes on partial or unvalidated stage output.

## Rationale

- Balances token cost against decision integrity.
- Four gates cover the real resume-hazard space: stale data, retired
  versions, operator halt, and superseded triggers.
- `ABORTED_STALE` is a safe terminal state — the run is lost but the
  system is safe (principle #10).
- Resuming on unvalidated output would silently corrupt the decision
  chain.

## Consequences

- Positive: no decision is ever built on partial or unvalidated state.
- Positive: stale runs fail fast and visibly, not silently.
- Negative: resume aborts discard already-spent LLM calls (token cost).
- Reversibility: gate logic is policy; gate set is stable.

## Cross-references

- Related ADRs: ADR-0005, ADR-0008, ADR-0025
- Implements principle(s): #6, #10
- Affects phases: 07
- Source document: `../07-autogen/decisions.md` (D7-3)
