# ADR-0043 — Phased development: no skipping, no mixing

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

CLAUDE.md rule 2 states: "Never skip phases. Never mix phases. Review and
finalize each phase before proceeding." The platform has 16 phases (0-15),
each producing specific deliverables in `docs/NN-phase-name/`. Skipping a
phase leaves architectural gaps that surface as rework or defects later.
Mixing phases in one document or task blurs ownership boundaries and makes
review impossible — a document that mixes Phase 5 (data) and Phase 9 (API)
cannot be cleanly reviewed by either owner.

## Decision

Phases must be executed in order. No phase is skipped. No phases are mixed
in one document or task. Each phase is reviewed and finalized before the
next phase begins. Phase ownership boundaries (defined in CLAUDE.md) are
respected: Phase 5 owns data persistence, Phase 9 owns interface contracts,
Phase 10 owns UX/frontend architecture, Phase 11 owns runtime delivery,
Phase 13 owns cross-system test strategy, Phase 14 owns implementation
sequencing.

## Rationale

- Skipping a phase leaves architectural gaps that become expensive rework.
- Mixing phases in one document blurs ownership and blocks clean review.
- Phase ownership boundaries prevent cross-phase contamination (e.g.,
  Phase 10 redefining Phase 5 data models).
- Review and finalize before proceeding ensures each phase's deliverables
  are complete and approved before the next builds on them.

## Consequences

- Positive: each phase's deliverables are complete and reviewable.
- Positive: ownership boundaries are clear — no phase redefines another's
  scope.
- Negative: phase discipline may slow initial progress (intentional).
- Reversibility: the rule is a process gate; phase order is fixed.

## Cross-references

- Related ADRs: ADR-0041, ADR-0042
- Implements principle(s): #4
- Affects phases: 00-15
- Source document: `../../CLAUDE.md` (rule 2)
