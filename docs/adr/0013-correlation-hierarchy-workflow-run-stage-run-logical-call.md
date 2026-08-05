# ADR-0013 — Correlation hierarchy: workflow_run → stage_run → logical_call

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Tracing a decision from the top-level workflow run down to an individual
LLM call requires a structured correlation hierarchy. `lineage_id` is
attached only once decision lineage exists (Phase 3 gate), but LLM calls
happen before `lineage_records` is written. A gap in the correlation
chain makes it impossible to attribute a cost or latency spike to a
specific stage or call.

## Decision

Correlation hierarchy is `workflow_run_id → stage_run_id → logical_call_id
/ idempotency_key`. `lineage_id` is attached only once decision lineage
exists (Phase 3 gate). LLM calls that happen before `lineage_records` is
written correlate via `workflow_run_id`; `llm_usage.lineage_id` (Phase 6)
is backfilled once lineage exists.

## Rationale

- A three-level hierarchy covers the full trace path: run, stage, call.
- Attaching `lineage_id` only after the Phase 3 gate avoids premature
  commitment to a decision that may fail safe.
- Backfilling `llm_usage.lineage_id` closes the pre-lineage correlation
  gap without blocking the LLM call.
- `idempotency_key` at the call level prevents duplicate charges on
  replay.

## Consequences

- Positive: every LLM call is traceable to its stage and run.
- Positive: cost attribution works even for runs that fail before
  lineage.
- Negative: the backfill step is an async reconciliation (eventual
  consistency on `llm_usage.lineage_id`).
- Reversibility: the hierarchy is structural; physical reconciliation is
  Phase 5/6.

## Cross-references

- Related ADRs: ADR-0005, ADR-0012
- Implements principle(s): #6, #10
- Affects phases: 07, 06, 05
- Source document: `../07-autogen/decisions.md` (D7-6)
