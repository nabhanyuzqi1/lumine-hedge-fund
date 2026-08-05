# ADR-0065 — 5 sprints, 10 weeks total

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Implementation must be sequenced into sprints that deliver working, testable
increments. The backend depends on the API contracts (Phase 9), which depend
on the decision engine (Phase 4/7/8), which depends on data (Phase 5), which
depends on the MT5 bridge (Phase 8), which depends on the foundation. Sprint
3 (decision engine) is the most complex and critical. Horizontal layer
sprints produce no working system until the final sprint.

## Decision

Five sprints delivering vertical slices in sequence: Sprint 1 — Foundation (2
weeks), Sprint 2 — Data Pipeline (2 weeks), Sprint 3 — Decision Engine (3
weeks), Sprint 4 — API and Frontend (2 weeks), Sprint 5 — Hardening (1 week).

## Rationale

- Vertical slices mean each sprint delivers a working, testable increment.
  Sprint 1 delivers a running stack. Sprint 2 delivers live data. Sprint 3
  delivers the decision engine. Sprint 4 delivers the dashboard. Sprint 5
  delivers production readiness.
- Backend-first ordering: the frontend depends on API contracts (Phase 9).
  The API depends on the decision engine (Phase 4/7/8). The decision engine
  depends on data (Phase 5). Data depends on the MT5 bridge (Phase 8). The
  MT5 bridge depends on the foundation (Sprint 1).
- Sprint 3 is the longest (3 weeks) — it is the core of the system. The
  AutoGen pipeline, LLM gateway, risk engine, and lineage writer are the most
  complex components and the most critical to get right.
- Sprint 5 is the shortest (1 week) — it is hardening and acceptance, not new
  feature development.
- Horizontal layers rejected: no working system until the final sprint.
  Integration bugs between layers are discovered late. No opportunity for
  early paper trading.
- More sprints (8-10) rejected: finer granularity but more ceremony. 5
  sprints matches the natural architectural boundaries.
- Fewer sprints (3) rejected: each sprint is too large to review and too
  risky — a problem in Sprint 2 blocks the entire delivery.

## Consequences

- Positive: each sprint produces a testable increment.
- Positive: backend-first respects the dependency graph.
- Negative: Sprint 3 is a 3-week critical path — slippage delays Sprint 4.
- Reversibility: sprint boundaries are planning, not architecture; adjustable
  by re-planning.

## Cross-references

- Related ADRs: ADR-0066, ADR-0067
- Implements principle(s): #2, #4
- Affects phases: 14, 15
- Source document: `../14-implementation/decisions.md` (D14-5)
