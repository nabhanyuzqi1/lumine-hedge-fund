# ADR-0007 — Replay never mutates history

- **Status:** Accepted
- **Phase:** 07-autogen
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

Replay has two legitimate purposes: audit (did the stored output match
what the system actually produced?) and comparison (what would a different
model/prompt have produced on the same context?). Both must preserve the
original run intact. Overwriting the original on replay destroys the
auditable record and breaks reproducibility.

## Decision

Two replay modes, never history mutation. Audit replay reads stored actual
outputs — it is the authoritative record and re-executes nothing.
Comparative re-execution is a new, distinct run (new `workflow_run_id`,
current registry pins) used to compare model/prompt behavior; it never
mutates or overwrites the original run.

## Rationale

- Preserves reproducibility (principle #6): the original record is
  immutable.
- Audit replay is read-only by definition — no re-execution risk.
- Comparative re-execution writes new rows with a `replay_of` reference;
  the chain only grows.
- A verified prefix stays verified because the chain is append-only.

## Consequences

- Positive: the original decision record is irrefutable.
- Positive: comparative runs extend the chain without polluting history.
- Negative: comparative runs consume additional LLM cost and storage.
- Reversibility: the append-only contract is irreversible by design.

## Cross-references

- Related ADRs: ADR-0005, ADR-0006, ADR-0017, ADR-0019, ADR-0026
- Implements principle(s): #6
- Affects phases: 07
- Source document: `../07-autogen/decisions.md` (D7-8)
