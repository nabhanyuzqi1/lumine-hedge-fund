# Phase 7 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Explicit workflow lifecycle state machine** | Every decision cycle is a durable run moving through named states: RECEIVED, CONTEXT_PINNED, ANALYSTS_RUNNING, ANALYSTS_VALIDATED, DEBATE_EVALUATED, optional DEBATE_RUNNING / DEBATE_VALIDATED, IC_RUNNING, IC_VALIDATED, CIO_RUNNING, PROPOSAL_VALIDATED, COMPLETED. Terminal safe states: FAILED_SAFE, ABORTED_STALE, TERMINATED_KILL, CANCELLED_OPERATOR. Named states make failures locatable, replayable, and auditable (principle #6, #10). |
| 2 | **One active logical workflow per (book, strategy, symbol)** | At most one non-terminal run exists per trading key. Duplicate triggers are idempotent; a newer trigger may supersede a stale in-flight run. Books are isolated from each other. Prevents two committees deciding on the same market state concurrently. |
| 3 | **Checkpoint-resume with stale-abort (hybrid)** | Resume is allowed only from the last validated durable checkpoint, and only after four gates pass: input freshness, pinned-version match (model/prompt/policy), kill-switch clear, and no superseding newer trigger. Any gate failure → ABORTED_STALE (a new run starts fresh). Never resumes on partial or unvalidated stage output. Balances token cost against decision integrity. |
| 4 | **Invalid structured output fails safe — never relax to retry** | Analyst JSON failing the Phase 4 schema → stage FAILED_SAFE. Debate output invalid → debate discarded, IC proceeds on pre-debate analyst outputs (per Phase 4). Debate-trigger evaluator raises → no debate, flag recorded. IC or CIO output invalid → run FAILED_SAFE. Schema/prompt is never loosened to coerce a pass; a malformed decision is worse than no decision. Provider-level retries and fallbacks stay in Phase 6, not here. |
| 5 | **Durable append-only workflow journal (logical definition)** | A journal records state transitions, validated stage outputs (references, not re-embedded payloads), failure taxonomy codes, and recovery actions, in order, per run. This phase fixes the logical fields only; physical DDL, indexes, retention, and partitioning belong to Phase 5. Failed runs must be auditable without fabricating decision lineage. |
| 6 | **Correlation hierarchy with pre-lineage gap closed** | `workflow_run_id → stage_run_id → logical_call_id / idempotency_key`. `lineage_id` is attached only once decision lineage exists (Phase 3 gate). LLM calls happen before `lineage_records` is written, so pre-lineage usage correlates via `workflow_run_id`; `llm_usage.lineage_id` (Phase 6) is backfilled once lineage exists. Physical reconciliation is a Phase 5/6 concern. |
| 7 | **Controlled failure taxonomy** | All stage failures classified into: TRANSIENT_PROVIDER, SCHEMA_INVALID, CHECKPOINT_UNAVAILABLE, CONTEXT_STALE, VERSION_MISMATCH, DEADLINE_EXCEEDED, KILL_SWITCH_ACTIVE, OPERATOR_CANCELLED, INTERNAL_INVARIANT. Taxonomy drives the recovery matrix deterministically — no ad-hoc retry logic per call site. |
| 8 | **Two replay modes, never history mutation** | Audit replay = read stored actual outputs; it is the authoritative record and re-executes nothing. Comparative re-execution = a new, distinct run (new `workflow_run_id`, current registry pins) used to compare model/prompt behavior; it never mutates or overwrites the original run. Preserves reproducibility (principle #6). |
| 9 | **Kill switch terminates immediately; no autonomous restart** | Kill-switch activation moves any active run to TERMINATED_KILL at the next safe checkpoint boundary (or immediately between LLM calls). No autonomous cycle restart from a kill state; restart requires explicit CIO/human action (Phase 2 authority). Graceful shutdown stops new cycles and lets active stages reach their next checkpoint or deadline. |
| 10 | **Observability = telemetry projection over durable audit events** | Structured logs, metrics, and traces are projections of the durable journal + `llm_usage`, not a parallel source of truth. If telemetry and journal disagree, the journal wins. Alert channels and dashboards are Phase 11/10 consumers. |

## Principles honored

- **#6 Reproducibility before adaptation**: named states, durable
  journal, gated resume, replay-without-mutation.
- **#10 Safe state by default**: every failure lands in a named
  terminal safe state; kill switch halts; malformed output never
  coerced.
- **Evidence before capital**: a decision reaches Phase 8 only with a
  validated proposal and intact lineage; degraded or failed runs never
  fabricate one.
- **YAGNI**: no saga frameworks, no generic workflow engine; the
  lifecycle is the minimum that makes the Phase 4 topology recoverable.

## Phase boundary respected

Phase 7 fixes lifecycle, recovery, checkpoint, replay, and
observability policy for the AutoGen pipeline. It does NOT define:
prompts/schemas (Phase 4), routing/cost (Phase 6), physical storage
(Phase 5), risk and execution (Phase 8), APIs (Phase 9), alert infra
(Phase 11), timeout numbers or code (Phase 14+).
