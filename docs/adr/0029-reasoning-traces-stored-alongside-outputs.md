# ADR-0029 — Reasoning traces stored alongside outputs

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`lineage_records.proposal` (Phase 3) pins the committee output — the
synthesized action. It does not store the reasoning. An auditor asking
"why did the committee decide this?" cannot answer it from the proposal
alone: the proposal is the action, not the chain of argument that produced
it. Lineage stored "what", not "why"; audit and LP due-diligence need
"why".

## Decision

Every LLM stage call writes a full reasoning trace to a new
`reasoning_traces` table, and `lineage_records.proposal` references the
trace IDs via a `reasoning_trace_ids` array. Each trace row stores the
full post-templating prompt (`prompt_sent`), the full model response
(`response_raw`), the schema-validated parsed output, and SHA-256 hashes
of both prompt and response. The trace write is synchronous with the
stage's completion — if it fails, the stage does not advance. Retention
is permanent; the table is append-only (no UPDATE, no DELETE).

## Rationale

- Closes the "why" audit gap without violating reproducibility (#6) or
  the stateless policy (D6-5).
- `prompt_hash` proves the model saw exactly what the record says it saw
  — the load-bearing hash for replay integrity.
- `response_hash` is a fingerprint for change detection, not a replay
  equality assertion (LLM nondeterminism is expected).
- Where reasoning tokens are not exposed by the provider, the gap is
  flagged (`_reasoning_gap: true`) rather than silent.

## Consequences

- Positive: the full reasoning chain (every analyst, IC, CIO) is
  reconstructable for any decision.
- Positive: prompt drift is detectable on replay (hash mismatch).
- Negative: ~600 rows/day at 100 cycles/day; permanent storage cost (text
  compresses well).
- Reversibility: the table is append-only; the linkage is additive to
  the proposal JSONB.

## Cross-references

- Related ADRs: ADR-0005, ADR-0014, ADR-0036
- Implements principle(s): #4, #6, #10
- Affects phases: 07, 03, 12
- Source document: `../07-autogen/reasoning-trace-storage.md` (S9)
