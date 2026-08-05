# ADR-0010 — Kill switch: no autonomous restart

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

A kill switch that halts the system but then autonomously restarts defeats
its purpose: the operator engaged it because something is wrong, and an
auto-restart silently resumes trading on a system the operator does not
trust. Restart authority must rest with the CIO/human (Phase 2 authority),
not the orchestrator.

## Decision

Kill-switch activation moves any active run to `TERMINATED_KILL` at the
next safe checkpoint boundary (or immediately between LLM calls). No
autonomous cycle restart from a kill state; restart requires explicit
CIO/human action. Graceful shutdown stops new cycles and lets active
stages reach their next checkpoint or deadline.

## Rationale

- Safe state by default (principle #10): the system stays stopped until a
  human clears it.
- Autonomous restart would mask the condition that triggered the kill.
- CIO/human authority over restart is consistent with the agent hierarchy
  (principle #7).
- Graceful shutdown lets in-flight stages reach a checkpoint, preserving
  their journal entries.

## Consequences

- Positive: operator confidence that a kill actually stops the system.
- Positive: in-flight stages reach a safe checkpoint before termination.
- Negative: recovery requires manual intervention (intentional).
- Reversibility: kill switch is a policy-governed control; the no-restart
  rule is structural.

## Cross-references

- Related ADRs: ADR-0006, ADR-0008
- Implements principle(s): #7, #10
- Affects phases: 07
- Source document: `../07-autogen/decisions.md` (D7-9)
