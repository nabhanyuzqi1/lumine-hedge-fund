# ADR-0005 — Durable workflow journal is the source of truth

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Every decision cycle is a durable run moving through named lifecycle
states. Failed runs must be auditable without fabricating decision
lineage. A journal that records state transitions, validated stage outputs
(references, not re-embedded payloads), failure taxonomy codes, and
recovery actions — in order, per run — is the minimum that makes the Phase
4 topology recoverable and auditable.

## Decision

A durable append-only workflow journal is the source of truth for workflow
state. It records state transitions, validated stage output references,
failure taxonomy codes, and recovery actions per run. This phase fixes the
logical fields only; physical DDL, indexes, retention, and partitioning
belong to Phase 5.

## Rationale

- Named states make failures locatable, replayable, and auditable
  (principles #6, #10).
- An append-only journal prevents history mutation — replay never alters
  the record (principle #6).
- Storing references (not re-embedded payloads) avoids data duplication and
  keeps the journal compact.
- A journal is the minimum viable recovery substrate; no saga framework or
  generic workflow engine needed (YAGNI).

## Consequences

- Positive: every run is fully auditable from the journal alone.
- Positive: failed runs leave a complete trace for post-mortem.
- Negative: the journal adds one write per state transition on the critical
  path.
- Reversibility: physical storage is Phase 5; logical contract is stable.

## Cross-references

- Related ADRs: ADR-0006, ADR-0007, ADR-0012, ADR-0013, ADR-0017
- Implements principle(s): #6, #10
- Affects phases: 07, 05
- Source document: `../07-autogen/decisions.md` (D7-5)
