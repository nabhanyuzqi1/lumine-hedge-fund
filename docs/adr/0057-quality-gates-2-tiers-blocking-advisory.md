# ADR-0057 — Quality gates: 2 tiers (blocking + advisory)

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

CI gates must catch deterministic regressions, contract breaks, and security
vulnerabilities at commit time. Backtest and paper-trading take minutes to
weeks and cannot run per-commit. Coverage as a blocking gate creates perverse
incentives. A two-tier system separates per-commit enforcement from
pre-launch acceptance.

## Decision

Two gate tiers. Blocking: unit tests, integration tests, contract tests,
system tests, SAST, secret scanning, dependency audit, container scan, lint,
and type-check. Advisory: coverage report, backtest (90-day), paper trading
(2-week), penetration test, kill-switch test, backup restore test. Advisory
gates become blocking at pre-launch acceptance.

## Rationale

- Blocking gates run on every push and complete in < 10 minutes total
  (parallel stages). They catch deterministic regressions, contract breaks,
  and security vulnerabilities at commit time.
- Advisory gates are too slow or require external resources (MT5 paper
  account, manual pentest) to run per-commit. They are enforced at the
  pre-launch acceptance gate — all must pass before live capital is deployed.
- Coverage threshold is advisory, not blocking: a coverage drop is a signal
  to review, not a deployment blocker. Making coverage blocking incentivizes
  low-quality tests that hit lines without asserting behavior.
- All gates blocking rejected: backtest and paper-trading take minutes to
  weeks; blocking CI on them would make development impossible.
- Coverage as blocking gate rejected: creates perverse incentives (tests
  written to satisfy the metric, not to verify behavior).

## Consequences

- Positive: per-commit CI is fast (< 10 min) and catches real regressions.
- Positive: pre-launch acceptance enforces slow gates before live capital.
- Negative: advisory gates can be skipped by convention (mitigated: pre-launch
  acceptance is a hard checkpoint).
- Reversibility: move a gate from advisory to blocking by changing CI policy.

## Cross-references

- Related ADRs: ADR-0055, ADR-0056, ADR-0060
- Implements principle(s): #4, #7
- Affects phases: 13, 14
- Source document: `../13-testing/decisions.md` (D13-3)
