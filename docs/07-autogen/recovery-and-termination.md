# Recovery & Termination

## Overview

Decision **D7-7**: every failure is classified into a controlled
taxonomy, and the taxonomy — not per-call-site judgment — determines
the recovery action. Decision **D7-4**: a malformed decision is worse
than no decision; the system never relaxes a schema to coerce a pass.

## Failure taxonomy (D7-7)

| Code | Meaning | Typical source |
|------|---------|----------------|
| `TRANSIENT_PROVIDER` | Provider timeout, 5xx, rate-limit after Phase 6 retry/fallback exhausted | LLM gateway |
| `SCHEMA_INVALID` | Stage output failed Phase 4 JSON schema validation | Orchestrator validator |
| `CHECKPOINT_UNAVAILABLE` | Durable checkpoint could not be read/written | Journal store |
| `CONTEXT_STALE` | Pinned market/context inputs no longer fresh at resume | Freshness gate |
| `VERSION_MISMATCH` | Pinned model/prompt/policy version no longer matches registry at resume | Version gate |
| `DEADLINE_EXCEEDED` | Stage exceeded its per-state deadline | Lifecycle clock |
| `KILL_SWITCH_ACTIVE` | Kill switch engaged before or during the run | Risk/ops lane |
| `OPERATOR_CANCELLED` | Human cancelled the run | Ops action |
| `INTERNAL_INVARIANT` | Orchestrator detected an impossible state (bug) | Runtime assertion |

## Recovery matrix

| Failure | Where | Action |
|---------|-------|--------|
| `TRANSIENT_PROVIDER` | Any LLM stage | Phase 6 retry/fallback already applied inside the gateway; if still failing → stage fails → run `FAILED_SAFE`. Resume from last checkpoint allowed (gates apply). |
| `SCHEMA_INVALID` | Analyst stage | Analyst stage fails → run `FAILED_SAFE`. No auto-retry with a relaxed prompt (D7-4). |
| `SCHEMA_INVALID` | Debate stage | Debate discarded; run continues to IC on pre-debate analyst outputs; `debate_held=false` with reason recorded (Phase 4 rule). |
| `SCHEMA_INVALID` | Debate-trigger evaluator | Evaluator error → treated as "no debate"; flag recorded for audit. |
| `SCHEMA_INVALID` | IC or CIO stage | Run `FAILED_SAFE`. No partial proposal reaches Phase 8. |
| `CHECKPOINT_UNAVAILABLE` | Any | Run `FAILED_SAFE` — a run that cannot record itself cannot be audited, so it must not proceed. |
| `CONTEXT_STALE` / `VERSION_MISMATCH` | Resume gate | Run `ABORTED_STALE`; a fresh run may start immediately. |
| `DEADLINE_EXCEEDED` | Any stage | Stage fails; run follows the failed stage's rule above (analyst/IC/CIO → `FAILED_SAFE`; debate → discard). |
| `KILL_SWITCH_ACTIVE` | Any | Run `TERMINATED_KILL` (see below). |
| `OPERATOR_CANCELLED` | Any | Run `CANCELLED_OPERATOR`; in-flight LLM calls allowed to finish or be cancelled at the next call boundary; result discarded. |
| `INTERNAL_INVARIANT` | Any | Run `FAILED_SAFE`; alert emitted — this class indicates a code defect, not an operational condition. |

## Kill switch (D7-9)

- Activation terminates any active run at the **next LLM call
  boundary** (no mid-call abort needed; calls are short JSON
  completions): in-flight calls complete and are discarded, the run
  transitions to `TERMINATED_KILL` with the kill-switch context
  recorded.
- **No autonomous restart.** A run in `TERMINATED_KILL` never resumes.
  New cycles remain blocked until the kill switch is cleared by the
  CIO/human authority defined in Phase 2. Nothing in the orchestrator
  may auto-clear it.
- Kill-switch state itself lives on the fast lane (Phase 1); Phase 7
  only consumes it.

## Graceful shutdown

Deploys and restarts must not strand runs:

1. Stop accepting new triggers (new triggers rejected with a clear
   "draining" signal or queued per Phase 9 contract).
2. Active runs continue to their **next checkpoint** or their state
   deadline, whichever comes first.
3. Runs parked at a checkpoint are resumable after restart (subject
   to the resume gates — a long deploy may legitimately turn them
   `ABORTED_STALE`).
4. Runs parked in non-checkpoint states re-execute that stage after
   restart.

## Degraded-cost interaction

When the Phase 6 circuit breaker degrades a stage (skipped
escalation, skipped debate, dropped journal job), that is **not** a
failure: the run continues, and the degrade fact is recorded in the
run journal and `llm_usage.degraded` (Phase 6). Recovery policy here
applies only to genuine failures. A run may therefore complete
degraded-but-valid; its lineage says so.

## What this document does NOT define

- Resume gate mechanics and journal fields (checkpoint-and-replay.md).
- Alert delivery (Phase 11).
- Deadlines' numeric values (Phase 14).
- Kill-switch enforcement inside MT5/execution (Phase 8).

## Phase boundary

This document fixes the failure taxonomy, per-class recovery actions,
kill-switch semantics, and shutdown behavior. It does not define
checkpoint contents, alert plumbing, or execution-side risk handling.
