# ADR-0039 — Deadline propagation from stage to LLM call

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`workflow-lifecycle.md` fixes that each progress state has a per-run
deadline and that exceeding it fires `DEADLINE_EXCEEDED`. It does NOT
define how that deadline reaches the individual LLM call inside the stage.
Per-call timeouts set in isolation (a flat 30s on every gateway call)
either waste budget on cheap calls or blow the stage deadline on expensive
ones.

## Decision

Each LLM call within a stage receives a derived timeout:
`call_timeout = remaining_budget - reserve`, where `remaining_budget` is
measured from the stage deadline (monotonic clock) and `reserve` is the
MEASURED time the stage needs post-call to validate output and write the
journal/checkpoint (per-stage reserve table, stored in `policy_versions`).
Multi-call stages use a budget manager allocating per-call budgets summing
to the stage budget. Resumed runs recompute from CURRENT remaining budget.
If `remaining_budget - reserve <= 0`, the call fails fast
(`DEADLINE_EXCEEDED`) without starting. The failure record carries
`exhausted_by` identifying which call or stage exhausted the budget.

## Rationale

- Flat per-call timeouts waste budget on cheap calls and blow deadlines on
  expensive ones.
- Measured reserve (not guessed) ensures the stage can complete its
  post-call validation and journal write.
- Fail-fast on zero-remaining avoids wasting gateway cost on a call that
  cannot finish within the deadline.
- `exhausted_by` lets the recovery matrix distinguish "ran out of budget
  on call 2 of 3" from "stage never started."

## Consequences

- Positive: no LLM call blows the stage deadline.
- Positive: zero-remaining calls fail fast, saving gateway cost.
- Positive: resumed runs get proportionally reduced budgets (no stale
  timeout).
- Negative: reserve values must be measured and tuned in Phase 14.
- Reversibility: reserve values are policy (`policy_versions`), tunable
  without code change.

## Cross-references

- Related ADRs: ADR-0035, ADR-0008
- Implements principle(s): #6, #10
- Affects phases: 07, 06
- Source document: `../07-autogen/deadline-propagation.md` (S24)
