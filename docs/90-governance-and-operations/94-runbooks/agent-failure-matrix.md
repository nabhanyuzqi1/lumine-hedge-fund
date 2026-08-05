# Agent Failure Matrix — Binding (agent, failure_code) to Runbooks

## Overview

Decision **D-OPS-1**: every (agent, failure_code) pair relevant to an
agent has a binding entry — expected cause, runbook reference,
severity, and whether auto-recovery is allowed. The CLAUDE.md
requirement that "each agent must define Failure Modes" is no longer
decorative: it is a generated, CI-checked matrix.

`recovery-and-termination.md` (Phase 7) defines the failure taxonomy
and the recovery matrix at the *stage* level (analyst stage, debate
stage, IC/CIO stage). This document binds the taxonomy to *agents*
and to *runbooks* — the operational artifact an on-call engineer
reaches for when a specific agent fails with a specific code.

## Decision: the matrix

### Agents (rows)

From the agent hierarchy (CLAUDE.md):

- CIO Proposer
- IC Forum
- Technical Analyst
- Macro Analyst
- News Analyst
- SMC Analyst
- Risk Officer
- Portfolio Manager
- Execution Controller
- Trade Journal
- Performance Reviewer

### Failure codes (columns)

From `recovery-and-termination.md` (D7-7 taxonomy):

- `TRANSIENT_PROVIDER`
- `SCHEMA_INVALID`
- `CHECKPOINT_UNAVAILABLE`
- `CONTEXT_STALE`
- `VERSION_MISMATCH`
- `DEADLINE_EXCEEDED`
- `KILL_SWITCH_ACTIVE`
- `OPERATOR_CANCELLED`
- `INTERNAL_INVARIANT`

### Cell contract

Each populated cell records:

| Field | Content |
|-------|---------|
| `expected_cause` | The typical root cause for this (agent, code) pair |
| `runbook_ref` | Path to the runbook (e.g. `runbooks/cio-schema-invalid.md`) |
| `severity` | `page` / `warn` / `info` — per `observability.md` alert triggers |
| `auto_recovery_allowed` | bool — may the orchestrator apply the recovery action without human intervention |

A cell is **empty** only when the failure code cannot apply to the
agent (e.g. `KILL_SWITCH_ACTIVE` is uniform across all agents and has
a single shared entry, not per-agent variations). Emptiness is
deliberate and CI-verified, not accidental.

## Matrix

Severity legend: `page` = immediate human attention, `warn` = review
queue, `info` = logged only. Auto-recovery: `Y` = orchestrator may
apply the Phase 7 recovery action autonomously, `N` = run goes
FAILED_SAFE and waits for human/action.

### CIO Proposer

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `TRANSIENT_PROVIDER` | LLM gateway timeout on context-rich/strongest tier | `runbooks/llm-transient.md` | warn | Y |
| `SCHEMA_INVALID` | LLM returned malformed proposal JSON | `runbooks/cio-schema-invalid.md` | page | N |
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable at CIO stage | `runbooks/checkpoint-unavailable.md` | page | N |
| `CONTEXT_STALE` | Market context stale at CIO resume | `runbooks/context-stale.md` | warn | N |
| `VERSION_MISMATCH` | Pinned model/prompt/policy retired between stages | `runbooks/version-mismatch.md` | page | N |
| `DEADLINE_EXCEEDED` | CIO stage exceeded its per-state deadline | `runbooks/cio-deadline.md` | warn | N |
| `INTERNAL_INVARIANT` | Orchestrator detected impossible state in CIO | `runbooks/internal-invariant.md` | page | N |

`KILL_SWITCH_ACTIVE` and `OPERATOR_CANCELLED` are uniform across all
agents (see shared entries below).

### IC Forum

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `TRANSIENT_PROVIDER` | LLM gateway timeout on context-rich tier | `runbooks/llm-transient.md` | warn | Y |
| `SCHEMA_INVALID` | IC Forum output failed schema validation | `runbooks/ic-schema-invalid.md` | page | N |
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable at IC stage | `runbooks/checkpoint-unavailable.md` | page | N |
| `CONTEXT_STALE` | Analyst inputs stale at IC resume | `runbooks/context-stale.md` | warn | N |
| `VERSION_MISMATCH` | Pinned versions retired between analyst and IC stages | `runbooks/version-mismatch.md` | page | N |
| `DEADLINE_EXCEEDED` | IC Forum exceeded its deadline | `runbooks/ic-deadline.md` | warn | N |
| `INTERNAL_INVARIANT` | Impossible state in IC deliberation | `runbooks/internal-invariant.md` | page | N |

### Analysts (Technical / Macro / News / SMC)

Analysts share the same failure profile; the matrix is identical
across the four. Per-agent runbooks differ only in the prompt/schema
details referenced.

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `TRANSIENT_PROVIDER` | LLM gateway timeout on cost-efficient tier | `runbooks/llm-transient.md` | warn | Y |
| `SCHEMA_INVALID` | Analyst output failed schema validation | `runbooks/analyst-schema-invalid.md` | warn | N |
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable at analyst stage | `runbooks/checkpoint-unavailable.md` | page | N |
| `CONTEXT_STALE` | Market features stale at analyst resume | `runbooks/context-stale.md` | warn | N |
| `VERSION_MISMATCH` | Pinned prompt/model retired mid-cycle | `runbooks/version-mismatch.md` | page | N |
| `DEADLINE_EXCEEDED` | Analyst stage exceeded deadline (parallel pass) | `runbooks/analyst-deadline.md` | info | Y |
| `INTERNAL_INVARIANT` | Impossible state in analyst invocation | `runbooks/internal-invariant.md` | page | N |

Note: `SCHEMA_INVALID` on an analyst is `warn` (not `page`) because
Phase 7's recovery matrix already routes analyst-stage schema failure
to run FAILED_SAFE without partial proposal — the run is lost but the
system is safe. CIO/IC schema failures are `page` because they
indicate the decision-critical stages cannot produce valid output.

### Risk Officer

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `SCHEMA_INVALID` | Risk context snapshot malformed | `runbooks/risk-schema-invalid.md` | page | N |
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable at risk validation | `runbooks/checkpoint-unavailable.md` | page | N |
| `CONTEXT_STALE` | Position/exposure snapshot stale at risk validation | `runbooks/risk-context-stale.md` | page | N |
| `VERSION_MISMATCH` | Pinned policy_version (risk envelope) retired | `runbooks/version-mismatch.md` | page | N |
| `DEADLINE_EXCEEDED` | Risk validation exceeded deadline | `runbooks/risk-deadline.md` | page | N |
| `INTERNAL_INVARIANT` | Risk engine internal inconsistency | `runbooks/internal-invariant.md` | page | N |

The Risk Officer is deterministic (no LLM call), so
`TRANSIENT_PROVIDER` does not apply. Risk failures are `page` across
the board: a risk layer that cannot validate is a hard stop.

### Portfolio Manager (Sizer)

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `SCHEMA_INVALID` | Sized order malformed | `runbooks/sizer-schema-invalid.md` | page | N |
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable at sizing | `runbooks/checkpoint-unavailable.md` | page | N |
| `CONTEXT_STALE` | Fill/exposure snapshot stale at sizing | `runbooks/sizer-context-stale.md` | page | N |
| `VERSION_MISMATCH` | Pinned policy_version (sizing) retired | `runbooks/version-mismatch.md` | page | N |
| `DEADLINE_EXCEEDED` | Sizing exceeded deadline | `runbooks/sizer-deadline.md` | warn | N |
| `INTERNAL_INVARIANT` | Sizer internal inconsistency | `runbooks/internal-invariant.md` | page | N |

Deterministic; `TRANSIENT_PROVIDER` does not apply.

### Execution Controller

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable at dispatch | `runbooks/checkpoint-unavailable.md` | page | N |
| `CONTEXT_STALE` | Fill/position snapshot stale at dispatch | `runbooks/exec-context-stale.md` | page | N |
| `VERSION_MISMATCH` | Pinned strategy_version retired at dispatch | `runbooks/version-mismatch.md` | page | N |
| `DEADLINE_EXCEEDED` | Dispatch exceeded deadline | `runbooks/exec-deadline.md` | page | N |
| `INTERNAL_INVARIANT` | Execution router internal inconsistency | `runbooks/internal-invariant.md` | page | N |

Deterministic. `SCHEMA_INVALID` does not apply (the router consumes
already-validated lineage records). Kill-switch handling is a shared
entry (below).

### Trade Journal

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `TRANSIENT_PROVIDER` | LLM gateway timeout on journal summarization | `runbooks/llm-transient.md` | info | Y |
| `SCHEMA_INVALID` | Journal narrative failed schema validation | `runbooks/journal-schema-invalid.md` | info | N |
| `CHECKPOINT_UNAVAILABLE` | Journal store unreachable | `runbooks/checkpoint-unavailable.md` | warn | Y |
| `DEADLINE_EXCEEDED` | Journal job exceeded deadline | `runbooks/journal-deadline.md` | info | Y |
| `INTERNAL_INVARIANT` | Journal worker inconsistency | `runbooks/internal-invariant.md` | warn | N |

The Trade Journal is an async worker (Phase 2). Its failures are
`info`/`warn` because they do not block the critical path; a missed
journal entry is a gap in the narrative record, not a risk to capital.
`CONTEXT_STALE` and `VERSION_MISMATCH` do not apply (the journal
consumes completed lineage records, not live context).

### Performance Reviewer

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `TRANSIENT_PROVIDER` | LLM gateway timeout on review narrative | `runbooks/llm-transient.md` | info | Y |
| `SCHEMA_INVALID` | Review output failed schema validation | `runbooks/reviewer-schema-invalid.md` | warn | N |
| `CHECKPOINT_UNAVAILABLE` | Outcome store unreachable | `runbooks/checkpoint-unavailable.md` | warn | Y |
| `CONTEXT_STALE` | Outcome data stale at review | `runbooks/reviewer-context-stale.md` | warn | N |
| `VERSION_MISMATCH` | Pinned versions retired | `runbooks/version-mismatch.md` | warn | N |
| `DEADLINE_EXCEEDED` | Review job exceeded deadline | `runbooks/reviewer-deadline.md` | info | Y |
| `INTERNAL_INVARIANT` | Reviewer inconsistency | `runbooks/internal-invariant.md` | warn | N |

Async worker; `info`/`warn` severity. Does not block the critical
path.

### Shared entries (uniform across all agents)

| Code | Expected cause | Runbook | Severity | Auto |
|------|----------------|---------|----------|------|
| `KILL_SWITCH_ACTIVE` | Kill switch engaged (global / book / strategy) before or during run | `runbooks/kill-switch.md` | page | N (run → TERMINATED_KILL) |
| `OPERATOR_CANCELLED` | Human cancelled the run | `runbooks/operator-cancelled.md` | info | N (run → CANCELLED_OPERATOR) |

These are uniform because the Phase 7 recovery matrix defines them at
the run level, not the stage level: any active run hits the same
terminal state regardless of which agent was executing.

## Generation rule

The matrix is a **generated artifact**. The source of truth is the
agent registry (a separate spec that defines each agent's role,
inputs, outputs, KPIs, and applicable failure codes). This matrix is
generated from the agent registry + the Phase 7 taxonomy. When the
agent registry changes (new agent, new failure code, revised
applicability), the matrix is regenerated and the diff is reviewed.

The generation rule:

1. Read the agent registry → list of agents.
2. Read `recovery-and-termination.md` → failure taxonomy.
3. For each (agent, code) pair, check the agent registry's
   `applicable_failure_codes` field.
4. If applicable → emit a cell with `expected_cause`,
   `runbook_ref`, `severity`, `auto_recovery_allowed` from the
   registry.
5. If not applicable → emit an empty cell (deliberate).

## CI check

A CI check verifies:

1. **Every agent has ≥ 1 failure-mode entry** per relevant taxonomy
   code. An agent with zero entries for a code it is registered as
   applicable to is a CI failure.
2. **Every populated cell has a non-null `runbook_ref`** that
   resolves to an existing runbook file.
3. **Every populated cell has a `severity` in {page, warn, info}**
   and an `auto_recovery_allowed` in {true, false}.
4. **The matrix matches the generated output** from the agent
   registry (no hand-edited drift).

This makes "each agent defines Failure Modes" (CLAUDE.md) a
machine-checked invariant, not a documentation convention.

## What this document does NOT define

- Runbook content (each runbook is a separate file under
  `docs/90-governance-and-operations/94-runbooks/`).
- The agent registry schema (separate spec).
- Alert routing and paging targets (Phase 11).
- Deadline numeric values (Phase 14).
- The Phase 7 recovery matrix (this document binds to it; it does not
  redefine recovery actions).

## Phase boundary

This document is a governance artifact consumed by ops. It binds the
Phase 7 failure taxonomy to agents and runbooks. It does not modify
the taxonomy, the recovery actions, or the agent hierarchy. The
agent registry, runbook content, and CI check implementation belong
to their respective specs and Phase 14+ code.
