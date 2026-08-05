# Deadline Propagation — Stage to LLM Call

## Overview

`workflow-lifecycle.md` fixes that each progress state has a per-run
deadline and that exceeding it fires `DEADLINE_EXCEEDED`. It does
NOT define how that deadline reaches the individual LLM call inside
the stage. Per-call timeouts set in isolation (a flat 30s on every
gateway call) either waste budget on cheap calls or blow the stage
deadline on expensive ones. This document fixes how a stage computes
its remaining budget, how each LLM call within the stage receives a
derived timeout, the reserve table, multi-call budget management,
fail-fast on zero-remaining, and the observability metrics.

It amends `workflow-lifecycle.md` (Phase 7) and the gateway contract
(Phase 6).

## Decision: D7-4 — Deadline-derived per-call timeout, measured reserve

### Stage computes `deadline_ts` at start

When a stage enters a `*_RUNNING` state, the lifecycle clock provides
`deadline_ts` (from `workflow-lifecycle.md` per-state deadline). The
stage records `stage_start_ts` and computes:

```
remaining_budget = deadline_ts - stage_start_ts
```

This is measured with the monotonic clock (per
`clock-and-time-contract.md`) as a duration, not a wall-clock
subtraction.

### Per-call timeout = remaining - reserve

Each LLM call within the stage receives:

```
call_timeout = remaining_budget - reserve
```

where `reserve` is the MEASURED time the stage needs after the LLM
call returns to validate output and write the journal/checkpoint.
Reserve is per-stage, measured in Phase 14 tuning, not guessed.

### Reserve table per stage

V1 reserve values (milliseconds), tuned from measured stage latency
in Phase 14:

| Stage | Reserve (ms) | Covers |
|-------|-------------|--------|
| technical_analyst | 500 | schema validation, journal write |
| macro_analyst | 500 | schema validation, journal write |
| news_analyst | 500 | schema validation, journal write |
| smc_analyst | 500 | schema validation, journal write |
| ic_forum | 800 | schema validation, weights check, journal write |
| cio_proposer | 1000 | proposal schema validation, lineage gate check, journal write |
| risk_validator | 500 | verdict validation, journal write |

Reserve values are policy — stored in `policy_versions` scope
`deadline_reserve` — not hardcoded. They are re-measured when stage
implementation changes.

### Multi-call stages use a budget manager

A stage with multiple LLM calls (e.g. a debate round with N turns, or
IC forum with sequential calls) uses a budget manager that allocates
per-call budgets summing to the stage budget:

```
total_stage_budget = remaining_budget - reserve
per_call_budget[i] = allocation[i]  where sum(allocation) <= total_stage_budget
```

Allocation is policy (equal split, or weighted by expected call
cost). The budget manager tracks elapsed time across calls and
reduces subsequent calls' budgets by actual elapsed — never exceeds
remaining.

### Resumed runs proportionally reduce

A resumed run (from a checkpoint, per `checkpoint-and-replay.md`)
has less remaining budget because time has elapsed. Per-call timeout
is recomputed from the CURRENT remaining budget at resume time:

```
call_timeout = current_remaining_budget - reserve
```

A resumed call NEVER gets the original full timeout. If the resume
happens with insufficient budget, the next call fails fast (see
below).

### Fail fast on zero-remaining

At each LLM call start:

```
if remaining_budget - reserve <= 0:
    fail fast: DEADLINE_EXCEEDED
        exhausted_by: { stage, call_id, attempted_at }
    do NOT start the call
```

Starting a call that cannot finish within the deadline wastes gateway
cost and still fails. Fail fast, record `exhausted_by`, route through
the recovery matrix.

### `DEADLINE_EXCEEDED` carries `exhausted_by`

The failure record extends to identify which call or stage exhausted
the budget:

```json
{
  "failure_code": "DEADLINE_EXCEEDED",
  "exhausted_by": {
    "stage": "ic_forum",
    "call_id": "ic_call_2_of_3",
    "remaining_at_attempt_ms": 120,
    "reserve_ms": 800
  }
}
```

This lets the recovery matrix and the Review worker distinguish "ran
out of budget on call 2 of 3" from "stage never started" — different
diagnoses, different fixes.

### Observability

| Metric | Type | Meaning |
|--------|------|---------|
| `stage_deadline_remaining` | gauge | remaining budget at stage start, per stage |
| `call_timeout_set` | histogram | timeout value assigned to each LLM call |
| `call_elapsed_vs_timeout` | histogram | actual call elapsed / set timeout ratio |
| `deadline_fail_fast_count` | counter | calls that failed fast (zero-remaining) |
| `reserve_consumed` | histogram | actual post-call time consumed vs reserved |

These feed Phase 7 observability (`observability.md`) and Phase 13
testing quality gates. A stage consistently consuming >80% of its
deadline on a single call is a tuning signal for Phase 14.

## What this document does NOT define

- Exact deadline durations per state (those are Phase 14 tuning from
  measured latency; `workflow-lifecycle.md` fixes only that they
  exist).
- Gateway-side timeout enforcement mechanism (Phase 6
  `llm-gateway.md`).
- Recovery actions on `DEADLINE_EXCEEDED` (`recovery-and-termination.md`).
- Budget allocation weights for multi-call stages (policy, tuned in
  Phase 14).

## Phase boundary

This document amends `workflow-lifecycle.md` (Phase 7) by defining
how per-state deadlines propagate to individual LLM calls. It amends
the gateway contract (Phase 6) by requiring the gateway to honor a
caller-supplied timeout. It does not define deadline durations,
recovery policy, or gateway implementation.
