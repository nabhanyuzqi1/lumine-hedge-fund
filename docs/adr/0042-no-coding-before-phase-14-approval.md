# ADR-0042 — No coding before Phase 14 approval

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

CLAUDE.md rule 3 states: "Never start coding unless Phase 14 has been
approved." The platform's design philosophy (rule 5) is "architecture
before code." Phases 0 through 13 produce architecture and design
documentation; Phase 14 produces the implementation plan; Phase 15 is
implementation. Allowing coding before Phase 14 approval risks building on
an unapproved plan, producing rework, inconsistency, and untraceable
decisions.

## Decision

No implementation code is written until Phase 14 (Implementation Planning)
has been approved. Phases 0-13 produce documentation only. Phase 14
produces the implementation plan (package selection, repository structure,
work breakdown, coding standards, delivery order). Phase 15 is the only
phase that produces code. Documentation and CI/tooling scripts are not
"code" in this sense — the rule binds to implementation code.

## Rationale

- Architecture before code (rule 5): building on an unapproved plan
  produces rework.
- Phased development (rule 2): each phase is reviewed and finalized before
  the next begins; coding before Phase 14 violates phase ordering.
- An approved Phase 14 plan ensures package selection, repository structure,
  and coding standards are settled before the first line of implementation.
- Evidence before capital: untraceable code produced outside the plan
  violates the auditability principle (#4).

## Consequences

- Positive: implementation starts from a settled, approved plan.
- Positive: no rework from building on an unapproved architecture.
- Negative: documentation phases may feel slow before code appears
  (intentional discipline).
- Reversibility: the rule is a process gate; Phase 14 approval is the
  trigger.

## Cross-references

- Related ADRs: ADR-0041, ADR-0043
- Implements principle(s): #4
- Affects phases: 14, 15
- Source document: `../../CLAUDE.md` (rule 3)
