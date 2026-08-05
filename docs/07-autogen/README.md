# Phase 7 — AutoGen Architecture (Workflow Lifecycle, Recovery, Observability)

## Overview

Phase 4 locked *how the committee talks*: dynamic AutoGen rounds
(4 isolated parallel analysts → optional bounded debate → IC Forum →
CIO Proposer), strict JSON schemas, and the `lineage_records.proposal`
contract. Phase 6 locked *which model each role uses and how cost is
bounded*. Phase 7 locks *what happens when a workflow run fails, is
interrupted, goes stale, or must be observed and replayed* — the parts
the phase-mapping marks as still incomplete.

Inputs: Phase 1 (two-lane communication model, kill-switch path),
Phase 3 (`lineage_records`, version pins), Phase 4 (orchestration
topology + schemas), Phase 6 (gateway, budget, fallback). This phase
adds the durable workflow journal concept (logical fields only), the
lifecycle state machine, recovery semantics, and the observability
contract.

Phase 7 ends at a validated CIO proposal handed to the deterministic
RiskValidator. Risk math, order state, and execution are Phase 8.

## Documents in this folder

| File | Purpose |
|------|---------|
| `decisions.md` | Locked Phase 7 decision log |
| `workflow-lifecycle.md` | Cycle state machine, terminal safe states, concurrency rules |
| `recovery-and-termination.md` | Failure taxonomy, recovery matrix, kill-switch and shutdown semantics |
| `checkpoint-and-replay.md` | Durable journal, freshness gates, replay modes |
| `observability.md` | Structured logs, metrics, traces, durable audit events |

## What Phase 7 does NOT define

- Prompt contents and output schemas (Phase 4).
- Model routing, budgets, gateway fallback (Phase 6).
- Physical DDL, indexes, retention, partitioning of the workflow
  journal (Phase 5).
- Risk math, order lifecycle, MT5 execution (Phase 8).
- API / WebSocket exposure of workflow status (Phase 9).
- Alert delivery channels and infra deployment (Phase 11).
- Exact timeout and deadline numbers (tuned in Phase 14).
- Code (Phase 14+).

## Phase boundary

Phase 7 fixes the lifecycle, recovery, checkpoint, replay, and
observability policy of the AutoGen decision pipeline. It does not
change prompts, routing, risk math, or execution protocol.
