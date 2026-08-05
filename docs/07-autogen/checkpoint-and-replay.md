# Checkpoint & Replay

## Overview

Decision **D7-3**: resume happens only from validated checkpoints and
only through deterministic gates. Decision **D7-5**: a durable
append-only journal makes every run — including failed ones —
auditable. Decision **D7-8**: replay never mutates history.

## Durable workflow journal (D7-5) — logical definition

One journal entry per state transition or notable event, append-only,
totally ordered per run. Logical fields:

| Field | Content |
|-------|---------|
| `workflow_run_id` | Run identity; pre-lineage correlation root (D7-6) |
| `seq` | Monotonic sequence within the run |
| `ts` | UTC timestamp of the transition |
| `from_state`, `to_state` | Lifecycle states (workflow-lifecycle.md) |
| `stage_run_id` | Stage identity for stage-level events |
| `failure_code` | Taxonomy code when `to_state` is terminal (recovery-and-termination.md) |
| `checkpoint_ref` | Reference to the validated stage output stored at checkpoint states (Phase 3/5 storage), not a re-embedded payload |
| `pins` | `policy_version_id`, `model_version_id`s, `prompt_version_id`s frozen at CONTEXT_PINNED |
| `context_ref` | Reference to the pinned market/context snapshot + its freshness marker |
| `recovery_action` | What recovery did (resumed / aborted / debate-discarded / degraded-continued), when applicable |
| `actor` | `system`, `operator`, or `kill-switch` |

Physical realization — DDL, indexes, retention, partitioning — is
Phase 5. The journal is written synchronously at transitions; a run
that cannot journal itself fails safe (`CHECKPOINT_UNAVAILABLE`).

## Checkpoint contents

At each checkpoint state (`ANALYSTS_VALIDATED`, `DEBATE_VALIDATED`,
`IC_VALIDATED`, `PROPOSAL_VALIDATED`) the run durably records:

1. the **validated stage outputs** (or a storage reference to them),
   exactly as they passed the Phase 4 schema;
2. the **pins** already frozen at CONTEXT_PINNED;
3. the **context reference** and its freshness marker.

Resume re-executes nothing before the checkpoint: analysts'
validated outputs are reused verbatim; no LLM call is repeated.

## Resume gates (all must pass)

1. **Freshness**: the pinned context is still within the freshness
   bound for the cycle's trading horizon. Stale → `ABORTED_STALE`.
2. **Version match**: pinned `model_version_id`s /
   `prompt_version_id`s / `policy_version_id` still resolve to the
   same registry rows (not retired/superseded). Mismatch →
   `ABORTED_STALE`.
3. **Kill switch clear**: switch active → `TERMINATED_KILL` (not
   resumable at all).
4. **No supersession**: no newer trigger has superseded this run
   (D7-2). Superseded → `ABORTED_STALE`.

Gate outcomes are journal entries (`recovery_action`). Resuming a
run on stale inputs or swapped models would silently change the
decision basis — that is why these are hard aborts, not warnings.

## Replay modes (D7-8)

### Audit replay (authoritative)

Read the stored actual outputs from the journal + checkpoint
references and re-present them. Nothing is re-executed; no LLM call
is made. This is the mode used for post-mortems, regulator evidence,
and "why did the committee decide this" questions. The stored record
is the truth; telemetry is only a projection (D7-10).

### Comparative re-execution

A **new run** (new `workflow_run_id`, fresh or specified pins) that
re-executes the pipeline to compare behavior — e.g., a candidate
prompt or model in the Research sandbox (Phase 2/6 lifecycle).
Rules:

- never writes to the original run's journal or lineage;
- never routable to the live decision path unless its pins are
  `production` and it goes through the normal trigger path;
- its results are comparison artifacts, not decisions.

### What replay never does

- Mutate, overwrite, or "correct" a historical run.
- Re-execute in place and swap outputs under the same
  `workflow_run_id`.
- Fabricate lineage for a run that failed before PROPOSAL_VALIDATED.

## Correlation hierarchy (D7-6)

```
workflow_run_id
  └── stage_run_id            (analyst-1..4, debate, ic, cio)
        └── logical_call_id / idempotency_key   (per gateway call, Phase 6)
```

- `lineage_id` (Phase 3) exists only after the proposal passes the
  lineage gate; journal and `llm_usage` rows before that point
  correlate by `workflow_run_id`, and `llm_usage.lineage_id` is
  backfilled once lineage exists.
- This closes the pre-lineage gap: LLM calls happen before
  `lineage_records` is written, yet every token remains attributable
  to exactly one run.

## What this document does NOT define

- Physical journal schema, retention, archival (Phase 5).
- Freshness bound numeric values (Phase 14, from cycle latency).
- Replay tooling/UI (Phase 10; sandbox mechanics Phase 2/6).
- Comparative-run API surface (Phase 9).

## Phase boundary

This document fixes journal logical content, checkpoint contents,
resume gates, replay modes, and correlation identity. It does not
define storage physics, tooling, or interfaces.
