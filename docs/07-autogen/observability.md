# Observability — Logs, Metrics, Traces, Audit Events

## Overview

Decision **D7-10**: the durable journal and `llm_usage` are the
source of truth; logs, metrics, and traces are **projections** of
them. If telemetry and the journal disagree, the journal wins. This
phase fixes *what* is emitted and *what it means*; where it is
shipped is Phase 11.

## Signals

### Structured logs

One log line per journal event, same fields
(checkpoint-and-replay.md), plus `service` and `host`. Logs exist
for operators; they carry no information the journal lacks. Log
level mapping:

| Journal event | Level |
|---------------|-------|
| Normal transition | INFO |
| `recovery_action` = degraded-continued / debate-discarded | WARN |
| Any terminal state | ERROR (FAILED_SAFE), WARN (ABORTED_STALE, CANCELLED_OPERATOR), CRITICAL (TERMINATED_KILL, INTERNAL_INVARIANT) |

### Metrics (counters/histograms, labels fixed)

| Metric | Labels | Meaning |
|--------|--------|---------|
| `workflow_runs_total` | `book`, `strategy`, `terminal_state` | Run outcomes |
| `workflow_stage_duration` (histogram) | `stage` (analysts/debate/ic/cio) | Stage latency, feeds Phase 14 deadline tuning |
| `workflow_run_duration` (histogram) | `book`, `strategy` | End-to-end cycle latency |
| `workflow_failures_total` | `failure_code` | Taxonomy distribution |
| `workflow_resumes_total` | `outcome` (resumed/aborted) | Gate behavior |
| `workflow_degrades_total` | `kind` (escalation-skipped/debate-skipped/…) | Phase 6 breaker interaction |

Labels are deliberately low-cardinality: no symbol, no run IDs in
metric labels — identity belongs in logs/traces/journal, not in the
metrics store.

### Traces

One trace per `workflow_run_id`; spans per `stage_run_id`; child
spans per `logical_call_id` carrying the gateway idempotency key,
`tier`, and `model_version_id` actually used (post-fallback). Trace
status mirrors the stage outcome; the trace is reconstructable from
the journal alone.

### Durable audit events

The journal itself **is** the audit event stream. No separate audit
log is maintained for workflow behavior — a second store would
create a second truth. Audit questions (who/what/when/why) are
answered by journal queries, and by Phase 3 `lineage_records` once a
proposal exists.

## What observers must be able to answer

From these projections alone, without touching code:

1. Current state of any run, and all runs for a `(book, strategy,
   symbol)` key.
2. Why a run ended: terminal state + failure code + the stage that
   produced it.
3. Which model/prompt/policy versions produced any validated output.
4. Whether a decision ran degraded (cost breaker, discarded debate)
   and why.
5. Cycle latency distribution per stage, to tune deadlines in
   Phase 14.

## Alert triggers (content only — routing is Phase 11)

| Condition | Severity |
|-----------|----------|
| `TERMINATED_KILL` any run | page |
| `INTERNAL_INVARIANT` any run | page |
| `FAILED_SAFE` rate above policy threshold | page |
| `ABORTED_STALE` cluster (repeated gate failures) | warn |
| Any degrade event sustained over N cycles | warn |
| Kill switch engaged (regardless of runs) | page |

Thresholds and channels are Phase 11/14; the *conditions* are fixed
here because they define what "healthy" means for the pipeline.

## What this document does NOT define

- Metrics/log/trace backends, retention, dashboards, paging
  (Phase 11; dashboard UI Phase 10).
- Cost dashboards (Phase 6 accounting + Phase 10 UI).
- API exposure of run status (Phase 9).

## Phase boundary

This document fixes the observability contract: signals, labels,
levels, alert conditions, and the projection-over-journal rule. It
does not define the telemetry stack or its delivery.
