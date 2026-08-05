# Concurrency Budget

## Overview

Decision **D7-9**: the orchestrator enforces a resource concurrency
budget that bounds how many workflow runs may execute simultaneously,
independent of the logical concurrency rule (D7-2).

D7-2 (workflow-lifecycle.md) fixes **logical** concurrency: one active
run per `(book, strategy, symbol)`. This document fixes **resource**
concurrency: how many runs share CPU, memory, gateway slots, and DB
write capacity at the same time. The two are orthogonal — a system
with 100 active logical runs cannot execute all 100 simultaneously
without exhausting resources.

This document pairs with `gateway-admission-control.md` (Phase 6),
which fixes the gateway-side admission contract this budget consumes.

## Decision(s)

- **D7-9a** — Global max concurrent runs (system-wide bound).
- **D7-9b** — Per-book max concurrent runs (isolation).
- **D7-9c** — Research runs capped separately and preempted by
  production.
- **D7-9d** — When budget is exhausted, new triggers QUEUE (bounded)
  or are REJECTED with `ADMISSION_REJECTED`.
- **D7-9e** — Deadlock prevention via ordered budget acquisition.

## (a) Logical vs. resource concurrency

D7-2 says: a second trigger for the same `(book, strategy, symbol)`
while a run is in-flight is either deduplicated or supersedes the old
run. This is a correctness rule — it prevents two runs from making
conflicting decisions on the same book/strategy/symbol.

Resource concurrency is different: it asks "how many runs across
DIFFERENT book/strategy/symbol keys may execute in parallel?" Without
a bound, the system spawns unbounded parallelism, exhausting gateway
slots, DB connections, and memory. This document fixes that bound.

## (b) Global max concurrent runs

```sql
-- policy_versions.orchestration (JSONB)
{
  "concurrency": {
    "global_max_runs": 32,
    "per_book_max_runs": 8,
    "research_max_runs": 4,
    "queue_depth": 64
  }
}
```

`global_max_runs` (default 32, tunable) is the hard system-wide
ceiling. No more than 32 workflow runs may be in any `*_RUNNING`
state simultaneously. This bound is informed by:

- gateway tier semaphores (D6-8a): 32 runs × ~6 LLM calls = 192
  concurrent calls worst case, but staggered stages mean actual
  concurrent gateway load is lower;
- DB connection pool size (Phase 5);
- memory per run (context snapshots, feature windows).

The bound is conservative by default. Raising it requires measured
evidence that gateway, DB, and memory headroom exist (Phase 14 tuning).

## (c) Per-book max concurrent runs

`per_book_max_runs` (default 8) isolates books from each other. A
single book with many strategies cannot monopolize the global budget
and starve other books.

If `intraday` has 8 active runs and `swing` has a pending trigger,
`swing` gets the next global slot even if `intraday` has more pending
triggers. This enforces principle #5 (books never blend) at the
resource level.

The per-book cap is <= `global_max_runs`. A book cannot have a higher
cap than the system.

## (d) Research runs capped separately

`research_max_runs` (default 4) bounds comparative re-execution runs
(D7-8) to a separate sub-budget. Research runs:

- draw from a research-specific gateway budget (separate provider key
  OR reserved token-bucket partition — see
  `comparative-replay-isolation.md`);
- are preempted by production runs: if global budget is full and a
  `production_live` trigger arrives, a research run is paused at its
  next checkpoint boundary and its slot is yielded.

Preemption is checkpoint-safe: a research run pauses only at a
checkpoint state (`ANALYSTS_VALIDATED`, `DEBATE_VALIDATED`,
`IC_VALIDATED`, `PROPOSAL_VALIDATED`), never mid-stage. This preserves
the D7-3 resume guarantee.

Research runs cannot acquire `strongest`-tier gateway budget (protects
cost ceiling — see `comparative-replay-isolation.md`).

## (e) Queue or reject when budget exhausted

When a trigger arrives and the relevant budget (global or per-book) is
exhausted:

1. If the lane queue has capacity (< `queue_depth`): the trigger is
   QUEUED. The orchestrator records `TRIGGER_QUEUED` in telemetry. The
   trigger fires when a slot frees.
2. If the lane queue is full (>= `queue_depth`): the trigger is
   REJECTED with `ADMISSION_REJECTED` (the same code as
   gateway-admission-control D6-8d). The orchestrator records
   `TRIGGER_REJECTED`. The scheduler may retry on the next cycle.

`ADMISSION_REJECTED` at the scheduler level is handled the same as at
the gateway level: it is a capacity decision, not a transient error.
No fallback, no silent retry. The trigger is either queued or
dropped-for-this-cycle.

Priority for queue dispatch: `production_live` triggers dequeue first,
then `production_replay`, then `research` — same ordering as gateway
lanes (D6-8c).

## (f) Deadlock prevention: ordered budget acquisition

A run progresses through stages, each consuming resources
(analyst-stage gateway budget, IC-stage gateway budget, lineage write
slot). Naive acquisition can deadlock: run A holds analyst budget and
waits for IC budget; run B holds IC budget and waits for analyst
budget.

Rule: **budget acquisition is ordered.** A run acquires resources in
a fixed stage order:

```
1. orchestrator slot (global + per-book)   <- acquired at RECEIVED, held for run lifetime
2. analyst-stage gateway budget             <- acquired at ANALYSTS_RUNNING
3. IC-stage gateway budget                  <- acquired at IC_RUNNING
4. CIO-stage gateway budget                 <- acquired at CIO_RUNNING
5. lineage_pending write slot               <- acquired at PROPOSAL_VALIDATED
```

A run may NOT hold a later-stage resource while waiting for an
earlier-stage resource. If a run cannot acquire the next stage's
budget, it waits (at its current checkpoint) and releases nothing it
already holds — but it also cannot block another run that needs only
the stages it already passed.

This is the canonical deadlock prevention pattern: if all participants
acquire resources in the same order, circular wait is impossible.

If a run waits too long for a stage budget (exceeding the stage
deadline from workflow-lifecycle.md), it fires `DEADLINE_EXCEEDED` and
routes through the recovery matrix — it does NOT hold its slots
indefinitely.

## Interaction with gateway admission control

| Gateway (Phase 6) | Orchestrator (Phase 7, this doc) |
|-------------------|----------------------------------|
| Per-tier semaphore (concurrent calls) | Per-run slot (concurrent runs) |
| Per-provider token-bucket (rate) | Global/per-book/research caps (parallelism) |
| Priority lanes (preempt dispatch) | Priority queues (preempt dispatch) |
| `ADMISSION_REJECTED` (queue full) | `ADMISSION_REJECTED` (budget full) |
| Backpressure signal → scheduler | Backpressure consumer |

The two layers compose: the orchestrator bounds how many runs are
active; the gateway bounds how many calls those runs dispatch
concurrently. A spike in `gateway_backpressure_held_total` may cause
the orchestrator to stop triggering new runs (D6-8e), and a spike in
`TRIGGER_REJECTED` may prompt raising `global_max_runs` or adding
gateway capacity.

## What this document does NOT define

- Gateway admission internals (Phase 6 `gateway-admission-control.md`).
- Research isolation specifics (Phase 7
  `comparative-replay-isolation.md`).
- Numeric tuning of bounds (Phase 14, from measured load).
- Recovery actions per failure code (Phase 7
  `recovery-and-termination.md`).
- Physical storage of queue state (Phase 5).

## Phase boundary

This document fixes the resource concurrency budget: global cap,
per-book cap, research sub-budget, queue/reject semantics, and
deadlock-prevention ordering. It is consumed by the Phase 7
orchestrator and pairs with the Phase 6 gateway admission contract. It
does not define gateway internals, recovery policy, or code.
