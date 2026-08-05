# Workflow Lifecycle — Cycle State Machine

## Overview

Decision **D7-1**: every decision cycle is a durable run with an
explicit lifecycle. The state machine below is the complete set of
states and legal transitions for the Phase 4 topology (4 parallel
analysts → optional debate → IC Forum → CIO Proposer). Phase 7 ends
at PROPOSAL_VALIDATED; what Phase 8 does with the proposal is out of
scope here.

## States

### Progress states

| State | Meaning |
|-------|---------|
| `RECEIVED` | Trigger accepted; run created; no work done yet. |
| `CONTEXT_PINNED` | Inputs and registry pins frozen for this run (market snapshot reference, `policy_version_id`, `model_version_id`s, `prompt_version_id`s). From here on, the run is reproducible in principle. |
| `ANALYSTS_RUNNING` | The 4 analysts executing in isolated parallel (Phase 4). |
| `ANALYSTS_VALIDATED` | All 4 analyst outputs passed the Phase 4 schema. First durable checkpoint. |
| `DEBATE_EVALUATED` | The deterministic debate trigger (Phase 4 formula) evaluated; outcome (hold debate or not) recorded. |
| `DEBATE_RUNNING` | Optional — the single bounded debate round executing. |
| `DEBATE_VALIDATED` | Optional — debate output validated, or debate invalid → discarded with pre-debate analysts retained (Phase 4 rule), either way recorded. Checkpoint. |
| `IC_RUNNING` | IC Forum call executing. |
| `IC_VALIDATED` | IC output passed schema. Checkpoint. |
| `CIO_RUNNING` | CIO Proposer call executing. |
| `PROPOSAL_VALIDATED` | CIO output passed the proposal-v1 schema; decision lineage gate (Phase 3) cleared. Final checkpoint — handoff to RiskValidator (Phase 8). |
| `COMPLETED` | Handoff accepted by the downstream deterministic layer. Run closed. |

### Terminal safe states

| State | Meaning |
|-------|---------|
| `FAILED_SAFE` | An unrecoverable stage failure occurred (see recovery matrix). No proposal produced. |
| `ABORTED_STALE` | A resume attempt failed a freshness, version, kill-switch, or supersession gate. Run discarded; a fresh run may start. |
| `TERMINATED_KILL` | Kill switch activated during the run. |
| `CANCELLED_OPERATOR` | Operator cancelled the run before completion. |

Terminal states are final — no transition out. Every terminal
transition writes a journal entry with the failure taxonomy code
(recovery-and-termination.md).

## Transition graph (logical)

```
RECEIVED → CONTEXT_PINNED → ANALYSTS_RUNNING → ANALYSTS_VALIDATED
  → DEBATE_EVALUATED ──(no debate)──────────────→ IC_RUNNING
                     └─(debate)→ DEBATE_RUNNING → DEBATE_VALIDATED → IC_RUNNING
IC_RUNNING → IC_VALIDATED → CIO_RUNNING → PROPOSAL_VALIDATED → COMPLETED

Any progress state → FAILED_SAFE | TERMINATED_KILL | CANCELLED_OPERATOR
Resume gate failure → ABORTED_STALE
```

Debate is the only conditional segment; all others are linear. This
mirrors the Phase 4 dynamic-round contract and adds nothing to it.

## Concurrency rules (D7-2)

- **One active logical workflow per `(book, strategy, symbol)`.** A
  second trigger for the same key while a run is in a progress state
  is handled idempotently:
  - identical trigger payload → deduplicated (returns existing run);
  - newer trigger with fresher context → may **supersede** the
    in-flight run: the old run is marked superseded (a terminal
    transition recorded in its journal) and a new run starts.
- **Books isolated.** Runs for different books never share mutable
  state; a failure or kill in one book does not block another's
  analysts (system-wide kill switch excepted).
- **Stages within a run are sequential except analysts**, which run
  in isolated parallel exactly as Phase 4 defines. Phase 7 adds no
  new parallelism.

## Checkpoints

A **checkpoint** is a state from which resume is permitted
(D7-3): `ANALYSTS_VALIDATED`, `DEBATE_VALIDATED`, `IC_VALIDATED`,
`PROPOSAL_VALIDATED`. Non-checkpoint states (any `*_RUNNING`,
`CONTEXT_PINNED`, `RECEIVED`, `DEBATE_EVALUATED`) are not resumable —
their work is re-executed on recovery. Checkpoint contents and resume
gates are defined in checkpoint-and-replay.md.

## Time bounds

Each progress state has a deadline; exceeding it fires
`DEADLINE_EXCEEDED` and routes through the recovery matrix. Exact
numbers are tuned in Phase 14 from measured stage latency — this
document fixes only that deadlines exist per state, are recorded per
run, and are deterministic given the `policy_versions` row.

## What this document does NOT define

- Recovery actions per failure (recovery-and-termination.md).
- Journal physical schema (Phase 5).
- What happens after PROPOSAL_VALIDATED (Phase 8).
- Status exposure to UI (Phase 9/10).

## Phase boundary

This document fixes the state set, legal transitions, concurrency,
and checkpoint positions. It does not define recovery policy,
storage, or execution.
