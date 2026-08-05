# Phase 13 — Testing Strategy

## Overview

Phase 13 defines the cross-system testing strategy for Lumine V1: test
levels, environments, quality gates, backtest and paper-trading
validation, security testing, AI/LLM testing, and SLO/acceptance
criteria. It builds on Phase 11 CI/CD pipeline, Phase 12 security
architecture, Phase 9 API contracts, Phase 4 prompt schemas, and
Phase 10 performance budgets.

Phase 13 does NOT define: test code, fixtures, CI YAML, eval datasets
(Phase 14+), or any service contract (Phases 1–9).

## Documents

| Document | Purpose |
|----------|---------|
| `decisions.md` | Locked decisions D13-1 .. D13-6 with rationale |
| `test-levels.md` | 7 test levels: scope, tools, runtime, gate policy |
| `test-environments.md` | 3 environments, data isolation, SLO, acceptance checklist |
| `backtest-paper.md` | Backtest harness, paper trading architecture, same-path guarantee |
| `security-testing.md` | SAST, secrets, deps, container, pentest, pre-commit hooks |
| `ai-testing.md` | Schema contract, prompt eval, drift detection, prompt immutability |

## Decisions at a glance

| # | Decision | Choice |
|---|----------|--------|
| D13-1 | Test levels | 7 levels: unit, integration, contract, system, backtest, paper-trading, security. No E2E browser test in V1. |
| D13-2 | Test environments | 3 environments: CI (ephemeral), staging (VPS, paper account), production (VPS, live account). No dedicated staging server. |
| D13-3 | Quality gates | 2 tiers: blocking (unit, integration, contract, system, SAST, secrets, deps, container) + advisory (coverage, backtest, paper, pentest). |
| D13-4 | Backtest & paper-trading | Same code path as live via dependency injection. Backtest = historical data + mock LLM + simulated fills. Paper = live data + real LLM + paper MT5. |
| D13-5 | Security testing | 3 layers: SAST/secret/deps/container (CI automated), config audit (staging + cron), penetration test (manual, pre-launch + quarterly). |
| D13-6 | SLO & acceptance | 0.1% error budget. Pre-launch checklist: 8 gates must pass before live capital. |

## Testing principles

1. **Deterministic first, AI second.** Majority code path (risk, sizing,
   features, lineage, reconciliation, trade management) must have ≥ 80%
   unit test coverage. AI reasoning tested via contract schema + backtest
   and paper-trading outcome, not mocked LLM assertions.
2. **Same path, different safety.** Backtest, paper, and live run the same
   `execute_decision_cycle()` function. Only injected dependencies differ.
   No `if MODE == "backtest"` shortcuts.
3. **Evidence before capital.** Every backtest and paper-trading decision
   produces a lineage record structurally identical to live. Audit trail
   is continuous from simulation to production.
4. **Fail visible.** Gate failures are explicit and blocking. Suppression
   requires documented reason (Phase 12 D12-5 pattern). No silent warning
   accumulation.
5. **Security is continuous.** SAST, secrets, deps, and container scans
   run on every push. Pentest is manual but repeated quarterly. Security
   is not a pre-launch checkbox.

## What this phase does NOT define

- Test code, fixtures, CI workflow YAML, pre-commit config, eval datasets
  (Phase 14+).
- Coverage tooling configuration, thresholds per module (Phase 14+).
- Backtest harness implementation, slippage model calibration (Phase 14+).
- Penetration test execution details, specific tools/commands (Phase 14+
  operations runbook).
- AutoGen agent implementation code (Phase 14+).
- Testcontainers orchestration, Docker Compose test profiles (Phase 14+).
- Frontend component testing, visual regression, accessibility, and
  performance profiling (Phase 10 owns component-level test obligations;
  Phase 13 owns the cross-system framework they fit into).
- Prompt authoring workflow, eval harness implementation (Phase 14+).

## Phase boundary

Testing strategy, levels, environments, gates, SLO, and acceptance
criteria are fixed here. Test code, CI configuration, fixtures, eval
datasets, and harness implementation belong to Phase 14+.