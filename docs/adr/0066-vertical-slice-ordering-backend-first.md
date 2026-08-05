# ADR-0066 — Vertical slice ordering, backend-first

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Each sprint must deliver a complete vertical slice that can be tested
end-to-end. The frontend depends on API contracts that evolve during backend
development. Early paper trading (exceeding the minimum 2-week requirement
from D13-6) requires the decision engine to be functional by Sprint 3.
Cross-cutting concerns (logging, metrics, error handling) must not be
afterthoughts.

## Decision

Each sprint delivers a complete vertical slice. Backend services are built
first; frontend depends on API contracts. Critical path: MT5 bridge -> data
pipeline -> decision engine -> execution -> API -> dashboard. Paper trading
begins as soon as the decision engine is functional (Sprint 3+).

## Rationale

- Vertical slices provide continuous integration feedback. Every sprint
  produces something that can be tested end-to-end.
- Backend-first respects the dependency graph: the frontend cannot render
  data that the API cannot serve, and the API cannot serve decisions that the
  engine cannot produce.
- Early paper trading (Sprint 3+) means the system runs against live market
  data for 4+ weeks before go-live — far exceeding the minimum 2-week
  requirement (D13-6).
- Cross-cutting concerns (logging, metrics, error handling) are built in
  Sprint 1 and used by every subsequent sprint — they are not an
  afterthought.
- Frontend-first (mock API) rejected: produces a polished dashboard with no
  backend to connect to. The mock-to-real transition is a source of bugs and
  rework.
- Parallel backend + frontend rejected: requires the API contract to be
  stable before any implementation. In practice, the contract evolves during
  backend development, causing frontend rework.

## Consequences

- Positive: continuous integration feedback every sprint.
- Positive: 4+ weeks of paper trading before go-live.
- Negative: frontend work is concentrated in Sprint 4 (mitigated: component
  tests and design system from Phase 10 reduce implementation risk).
- Reversibility: sprint ordering is planning, not architecture.

## Cross-references

- Related ADRs: ADR-0065, ADR-0060
- Implements principle(s): #2, #4, #7
- Affects phases: 14, 15
- Source document: `../14-implementation/decisions.md` (D14-6)
