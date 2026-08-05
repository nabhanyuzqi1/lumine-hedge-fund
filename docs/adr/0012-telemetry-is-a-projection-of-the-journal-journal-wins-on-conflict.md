# ADR-0012 — Telemetry is a projection of the journal; journal wins on conflict

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Structured logs, metrics, and traces are essential for operations, but if
they become a parallel source of truth, they diverge from the actual
decision record. When telemetry and the journal disagree, the system must
have a deterministic resolution rule — otherwise operators investigate
phantom issues or miss real ones.

## Decision

Observability (structured logs, metrics, traces) is a projection of the
durable journal plus `llm_usage`, not a parallel source of truth. If
telemetry and the journal disagree, the journal wins. Alert channels and
dashboards are Phase 11/10 consumers of this projection.

## Rationale

- The journal is append-only and ACID-durable; telemetry pipelines may
  drop, sample, or reorder events.
- A single source of truth prevents phantom alerts and false
  all-clears.
- Telemetry-as-projection keeps the observability stack replaceable
  without affecting the audit record.
- Principle #6 (reproducibility) binds: the journal is the replayable
  record; telemetry is not.

## Consequences

- Positive: no ambiguity about which record is authoritative.
- Positive: telemetry infrastructure can be replaced without touching the
  audit record.
- Negative: a journal write failure means telemetry also loses that event
  (acceptable — safe state).
- Reversibility: telemetry tooling is replaceable; the journal-wins rule
  is structural.

## Cross-references

- Related ADRs: ADR-0005, ADR-0013
- Implements principle(s): #6, #10
- Affects phases: 07, 11
- Source document: `../07-autogen/decisions.md` (D7-10)
