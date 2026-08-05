# ADR-0055 — Test levels: 7 levels, no E2E browser test

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The system needs a test level taxonomy that covers deterministic logic,
database/Redis interactions, API/schema compliance, the full decision cycle,
backtest, paper trading, and security. Each level tests a distinct concern at
a distinct speed. The dashboard is a read-only consumer of SSE streams; all
API behavior is covered by contract tests; all deterministic logic is covered
by unit tests.

## Decision

Seven test levels — unit, integration, contract, system, backtest,
paper-trading, and security. No end-to-end browser test in V1. Levels 1-4
(unit through system) are blocking CI gates; levels 5-6 (backtest, paper) are
advisory pre-launch gates; level 7 (security) is mixed — automated scans are
blocking, penetration test is advisory.

## Rationale

- Each level tests a distinct concern at a distinct speed. Unit tests verify
  deterministic logic (< 30s). Integration tests verify database and Redis
  interactions (< 2m). Contract tests verify API and schema compliance (< 3m).
  System tests verify the full decision cycle with mocks (< 5m). This is fast
  enough for per-commit CI.
- Backtest and paper-trading take minutes to weeks — they cannot be
  per-commit gates. They are pre-launch acceptance gates instead.
- E2E browser tests (Playwright/Selenium) are rejected for V1: the dashboard
  is a read-only consumer of SSE streams; all API behavior is covered by
  contract tests; all deterministic logic is covered by unit tests. Browser
  tests add maintenance burden and CI flakiness without testing new behavior.
  Phase 10 frontend component tests and visual regression tests still apply at
  the component level.
- Combining integration and contract into one level rejected: different
  concerns (database vs API), different tools (testcontainers vs httpx),
  different failure modes.

## Consequences

- Positive: each level isolates a distinct concern and failure mode.
- Positive: no CI flakiness from browser tests.
- Negative: no automated browser-level regression (mitigated: component-level
  tests cover UI behavior).
- Reversibility: add E2E browser tests as an 8th level if the dashboard
  becomes interactive beyond read-only.

## Cross-references

- Related ADRs: ADR-0056, ADR-0057, ADR-0019
- Implements principle(s): #4, #6
- Affects phases: 13, 14
- Source document: `../13-testing/decisions.md` (D13-1)
