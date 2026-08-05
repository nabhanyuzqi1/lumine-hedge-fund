# Phase 13 — Locked Decisions

## D13-1 — Test levels: 7 levels, no E2E browser test

> **ADR:** [ADR-0055](../../adr/INDEX.md#adr-0055) — Test levels: 7 levels, no E2E browser test

**Choice:** Seven test levels — unit, integration, contract, system,
backtest, paper-trading, and security. No end-to-end browser test in V1.
Levels 1–4 (unit through system) are blocking CI gates; levels 5–6
(backtest, paper) are advisory pre-launch gates; level 7 (security) is
mixed — automated scans are blocking, penetration test is advisory.

**Rationale:**
- Each level tests a distinct concern at a distinct speed. Unit tests
  verify deterministic logic (< 30s). Integration tests verify database
  and Redis interactions (< 2m). Contract tests verify API and schema
  compliance (< 3m). System tests verify the full decision cycle with
  mocks (< 5m). This is fast enough for per-commit CI.
- Backtest and paper-trading take minutes to weeks — they cannot be
  per-commit gates. They are pre-launch acceptance gates instead.
- E2E browser tests (Playwright/Selenium) are rejected for V1: the
  dashboard is a read-only consumer of SSE streams; all API behavior
  is covered by contract tests; all deterministic logic is covered by
  unit tests. Browser tests add maintenance burden and CI flakiness
  without testing new behavior. Phase 10 frontend component tests and
  visual regression tests still apply at the component level.

**Alternatives rejected:**
- E2E browser tests: high maintenance, flaky, slow, and low signal for
  a read-only dashboard. Phase 10 component-level tests (vitest +
  testing-library) cover UI behavior more reliably.
- Combining integration and contract into one level: different concerns
  (database vs API), different tools (testcontainers vs httpx), different
  failure modes. Keeping them separate isolates failures clearly.

## D13-2 — Test environments: 3 environments, no dedicated staging server

> **ADR:** [ADR-0056](../../adr/INDEX.md#adr-0056) — Test environments: 3 environments, no dedicated staging server

**Choice:** Three environments — CI (ephemeral GitHub Actions runner with
testcontainers), staging (same VPS as production, separate DB/Redis/ports,
MT5 paper account), and production (same VPS, live account). No dedicated
staging server.

**Rationale:**
- A single VPS is the Phase 1 constraint. Staging runs on the same node
  as production, completely isolated at the database, Redis, network, and
  port level. This is safe because staging has no public access — it is
  reachable only via internal IP allowlist.
- Dedicated staging server rejected: doubles VPS cost for no security
  benefit at V1 scale. The isolation is at the data layer, not the
  hardware layer.
- CI environment is ephemeral — testcontainers provide fresh PostgreSQL
  and Redis per run. No shared state, no cross-run contamination.

**Alternatives rejected:**
- Dedicated staging VPS: doubles cost, adds operational burden of
  managing a second server. Isolation at DB/network level is sufficient.
- Local-only testing (no shared staging): paper trading requires a live
  MT5 connection and continuous uptime; a developer laptop cannot
  provide this.

## D13-3 — Quality gates: 2 tiers (blocking + advisory)

> **ADR:** [ADR-0057](../../adr/INDEX.md#adr-0057) — Quality gates: 2 tiers (blocking + advisory)

**Choice:** Two gate tiers. Blocking: unit tests, integration tests,
contract tests, system tests, SAST, secret scanning, dependency audit,
container scan, lint, and type-check. Advisory: coverage report, backtest
(90-day), paper trading (2-week), penetration test, kill-switch test,
backup restore test. Advisory gates become blocking at pre-launch
acceptance.

**Rationale:**
- Blocking gates run on every push and complete in < 10 minutes total
  (parallel stages). They catch deterministic regressions, contract
  breaks, and security vulnerabilities at commit time.
- Advisory gates are too slow or require external resources (MT5 paper
  account, manual pentest) to run per-commit. They are enforced at the
  pre-launch acceptance gate — all must pass before live capital is
  deployed.
- Coverage threshold is advisory, not blocking: a coverage drop is a
  signal to review, not a deployment blocker. Making coverage blocking
  incentivizes low-quality tests that hit lines without asserting behavior.

**Alternatives rejected:**
- All gates blocking: backtest and paper-trading take minutes to weeks;
  blocking CI on them would make development impossible.
- Coverage as blocking gate: creates perverse incentives (tests written
  to satisfy the metric, not to verify behavior). Coverage is a tool
  for the developer, not a deployment gate.

## D13-4 — Backtest & paper-trading: same code path, different injectors

> **ADR:** [ADR-0058](../../adr/INDEX.md#adr-0058) — Backtest and paper-trading: same code path, different injectors

**Choice:** Backtest, paper-trading, and live trading run the same
`execute_decision_cycle()` function. The only difference is injected
dependencies: `LLMGateway` (mock vs real), `ExecutionRouter` (simulated
fills vs paper MT5 vs live MT5). No `if MODE == "backtest"` branches
anywhere in the decision engine.

Backtest: replays historical OHLCV data from PostgreSQL, injects mock LLM
responses from fixture files, simulates fills with a pessimistic slippage
model. Paper trading: live market data from MT5 paper account, real LLM
calls, real MT5 order execution (paper account). Both produce lineage
records structurally identical to live.

**Rationale:**
- The only valid backtest is one that runs the same code as live. If
  backtest skips risk validation, uses a different sizing formula, or
  bypasses lineage writes, the results are meaningless — they test a
  different system than the one trading real capital.
- Dependency injection makes the same-path guarantee implementable
  without conditional branches. The decision engine receives its
  dependencies at construction; it does not inspect them.
- Mock LLM in backtest is necessary because LLM calls are non-deterministic
  and real-time LLM calls would make backtest unreproducible. The mock
  uses recorded or hand-crafted fixtures that represent realistic
  committee outputs.

**Alternatives rejected:**
- Separate backtest engine: any divergence from the live code path
  invalidates the backtest results. Maintaining two parallel code paths
  is also a maintenance burden.
- Real LLM in backtest: non-deterministic output makes backtest
  unreproducible; cost of LLM calls for 90 days of bar-close triggers
  is significant; latency makes backtest impractically slow.

## D13-5 — Security testing: automated CI + manual pentest

> **ADR:** [ADR-0059](../../adr/INDEX.md#adr-0059) — Security testing: automated CI + manual pentest

**Choice:** Three security testing layers. Automated CI (every push):
Bandit (Python SAST), Semgrep (multi-language patterns), Gitleaks
(secret scanning), pip-audit + npm audit (dependency audit, D12-5),
Trivy (container scan). Config audit (staging deploy + monthly cron):
Caddy config validation, UFW rules audit, Docker daemon config check,
backup encryption verify. Manual penetration test (pre-launch +
quarterly): grey-box methodology, 3-day engagement, OWASP-based scope.

**Rationale:**
- Automated tools catch the majority of security issues at zero
  marginal cost per commit. SAST, secrets, and dependency scanning
  are standard practice for any production system.
- Config audit is mostly automated but requires a running environment
  (staging) to validate — it cannot run in ephemeral CI.
- Manual pentest catches logic flaws that automated tools cannot:
  auth bypass, scope escalation, replay attack resistance, rate
  limiting effectiveness. Quarterly repetition ensures new code
  surfaces are tested.
- Grey-box methodology is chosen over black-box (tester has API docs
  but not source code): realistic attacker profile for a system with
  published API contracts.

**Alternatives rejected:**
- White-box pentest (full source code access): more thorough but
  more expensive and less realistic for external threats.
- Bug bounty program: V1 attack surface is too small to justify the
  operational overhead of triaging and rewarding external reports.
  Deferred to V2+.
- Automated DAST (dynamic scanning): high false-positive rate for
  HMAC-authenticated APIs; manual pentest is more efficient at V1 scale.

## D13-6 — SLO & acceptance: 0.1% error budget, 8 pre-launch gates

> **ADR:** [ADR-0060](../../adr/INDEX.md#adr-0060) — SLO and acceptance: 0.1% error budget, 8 pre-launch gates

**Choice:** Service level objective: 99.9% API availability. Error budget:
0.1% = 43 minutes 50 seconds per month. Burn rate alerts: critical (2%
burned in 1 hour), warning (5% burned in 6 hours). Pre-launch acceptance:
8 gates must pass before live capital is deployed — all 4 blocking CI
gates, backtest (Sharpe > 0, max drawdown < 20%), paper trading (2 weeks
with zero order errors and zero lineage gaps), kill-switch test, backup
restore test, MT5 bridge failover test, security pentest (no critical/high
open), and deploy verify.

**Rationale:**
- 99.9% is achievable for a single-node deployment with no external
  dependencies in the critical path (MT5 and LLM are the only external
  calls, and both have graceful degradation — broker-side SL/TP and
  cycle-skip respectively).
- 8 pre-launch gates are the minimum viable confidence threshold before
  live capital. Each gate tests a distinct failure mode. Skipping any
  gate means accepting an untested risk.
- Backtest thresholds (Sharpe > 0, max drawdown < 20%) are deliberately
  low — they are sanity checks, not performance targets. A strategy that
  fails these thresholds is likely broken, not just unprofitable.

**Alternatives rejected:**
- 99.99% availability (52 minutes/year): requires redundant infrastructure
  (hot standby, load balancer, multi-AZ) that V1 does not have.
- No error budget: without an explicit budget, every alert becomes
  noise and every outage becomes a subjective judgment call. The budget
  makes the trade-off explicit.
- Backtest as performance gate (Sharpe > 1.0): performance targets
  belong to strategy research, not system acceptance. The acceptance
  gate verifies the system works correctly; performance is a strategy
  concern.

## Principles honored

- Phase 1 minimal-egress: no new egress added — all testing is local or
  uses the same MT5/LLM connections already approved.
- Phase 1 safe state by default: every test level verifies the system
  degrades toward reduced exposure, not expanded risk.
- Evidence before capital: backtest and paper-trading produce auditable
  lineage records; no live capital until all 8 acceptance gates pass.
- Reproducibility before adaptation: deterministic tests are versioned
  in the repo; backtest fixtures are pinned; prompt eval datasets are
  versioned.
- Fail visible: gate failures are explicit and blocking; suppression
  requires documented reason.

## Phase boundary

Decisions D13-1..D13-6 are locked. Concrete test code, CI YAML, eval
datasets, backtest harness, and pentest runbook belong to Phase 14+.