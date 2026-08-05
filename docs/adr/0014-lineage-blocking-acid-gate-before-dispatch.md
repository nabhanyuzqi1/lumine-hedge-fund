# ADR-0014 — Lineage blocking ACID gate before dispatch

- **Status:** Accepted
- **Phase:** 03-agents-and-contracts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The `lineage_records` table is the single most important invariant in the
system (Phase 1). Every decision must write exactly one record,
synchronously, ACID, before dispatch. If the lineage write fails or is
batched, an order can leave the system with no durable record of the
decision that produced it — violating evidence-before-capital and safe
state by default.

## Decision

The ExecutionRouter writes a `lineage_records` row inside a blocking ACID
transaction before publishing the order command. No batching; one write
per decision. If the commit fails, the order never leaves the system (safe
state). The critical path is: compute proposal → risk verdict → size →
BEGIN TRANSACTION → INSERT lineage → COMMIT → if commit succeeds, publish
to MT5 commands stream.

## Rationale

- Safe state by default (principle #10): a commit failure means no
  dispatch, not a dispatch without a record.
- Evidence before capital (principle #4): the decision record exists
  before the order.
- Append-only, immutable: `lineage_records` has no UPDATE or DELETE —
  the same `lineage_id` always returns the same state, forever.
- Version pins (model, prompt, policy, strategy) frozen at insert make
  replay deterministic (principle #6).
- Idempotency: `lineage_id` is the PK, generated before dispatch; bridge
  replays match fills back to it.

## Consequences

- Positive: no order ever leaves the system without a durable decision
  record.
- Positive: replay resolves the four pinned versions and reproduces the
  exact context.
- Negative: one synchronous DB write on the critical path per decision
  (addressed by ADR-0023 write-aside at scale).
- Reversibility: the blocking-gate contract is structural; the physical
  table is Phase 5.

## Cross-references

- Related ADRs: ADR-0020, ADR-0023, ADR-0016, ADR-0017
- Implements principle(s): #4, #6, #10
- Affects phases: 03, 05, 08
- Source document: `../03-agents-and-contracts/lineage-schema.md`
