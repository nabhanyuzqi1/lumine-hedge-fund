# Sprint Plan

## Overview

Five sprints, 10 weeks total. Each sprint delivers a working vertical
slice. Backend-first ordering respects the dependency graph: foundation
→ data → engine → API → dashboard → hardening.

## Sprint dependency graph

```
Sprint 1 (Foundation, 2 weeks)
  └── Sprint 2 (Data Pipeline, 2 weeks)
        └── Sprint 3 (Decision Engine, 3 weeks)
              ├── Sprint 4 (API & Frontend, 2 weeks)
              └── Sprint 5 (Hardening, 1 week)
```

Sprint 4 and Sprint 5 can overlap — frontend can begin once the first
API router is available, and hardening can begin once the decision
engine is stable.

## Sprint 1 — Foundation (2 weeks)

**Goal:** Repository exists, CI runs, database migrates, containers start.
`make dev` starts the full stack. `make test` runs all Level 1 tests.

### Deliverables

| Day | Deliverable | Detail |
|-----|-------------|--------|
| 1-2 | Repo scaffolding | `backend/` + `frontend/` skeleton, `pyproject.toml` with dependencies, `package.json`, `biome.json`, `tsconfig.json`, `.gitignore`, `.pre-commit-config.yaml` |
| 3-4 | Database migrations | Alembic init, all Phase 3/5 tables: `time_series_*` (partitioned), `lineage_records`, `fills`, `positions`, `model_versions`, `prompt_versions`, `strategy_versions`, `policy_versions`, `llm_usage`, `security_events`, `processed_commands`, `workflow_journal` |
| 5-6 | Docker Compose | Dev compose: `trade-core`, `postgres`, `redis`, `caddy`; named volumes for PG data and Redis AOF; health checks on all services; volume mounts for live code reload |
| 7-8 | CI pipeline | `ci.yml`: lint (ruff) → type-check (mypy) → unit tests (pytest) → integration tests (testcontainers) → security scans (bandit, semgrep, gitleaks, pip-audit) → container build + scan (trivy). `ci-frontend.yml`: lint (biome) → type-check (tsc) → test (vitest) → build (vite). All parallel where possible. |
| 9-10 | Data layer | SQLAlchemy ORM models for all tables, async session factory, Redis client with connection pool, `pydantic-settings` config class, `structlog` setup with JSON renderer, `shared/errors.py` exception hierarchy |

### Exit criteria

- [ ] `make dev` starts PostgreSQL, Redis, and trade-core containers
- [ ] `make test` runs all Level 1 unit tests (passing)
- [ ] `make migrate` creates all tables with correct schema
- [ ] CI pipeline passes on push to main (all gates green)
- [ ] `make lint` and `make type-check` pass with zero errors

### Dependencies

- Phase 3: `registry-schema.md`, `lineage-schema.md`, `time-series-schema.md`
- Phase 5: `physical-erd.md`, `migrations.md`, `redis-roles.md`
- Phase 11: `topology.md`, `build-deploy.md`
- Phase 12: `supply-chain.md`
- Phase 13: `test-levels.md`, `test-environments.md`

## Sprint 2 — Data Pipeline (2 weeks)

**Goal:** MT5 bridge streams live data, feature engineering computes
indicators, Redis caches features and ticks. Integration tests verify
database and Redis interactions.

### Deliverables

| Day | Deliverable | Detail |
|-----|-------------|--------|
| 1-3 | MT5 bridge | Redis command queue (`mt5:commands`), result pub/sub (`mt5:results`), `protocol.py` with command/response Pydantic schemas, MT5 EA integration (Python-side bridge, EA reads from Redis) |
| 4-6 | Data collection | `data/collector.py`: tick → Redis stream, OHLCV aggregation → PostgreSQL time-series tables (partitioned), `FeatureProvider` with ATR, EMA, RSI, pivot points, volume profile |
| 7-8 | Redis cache | Feature cache (TTL 60s), tick cache (circular buffer, last 1000 ticks), snapshot cache (TTL 5s), `volatile-lru` eviction policy |
| 9-10 | Integration tests | Level 2 tests: `FeatureProvider` reads from real PostgreSQL + Redis (testcontainers), `LineageWriter` writes and reads back, `ExecutionRouter` publishes to Redis, MT5 bridge mock |

### Exit criteria

- [ ] MT5 bridge receives ticks and publishes to Redis
- [ ] FeatureProvider computes ATR, EMA, RSI, pivot points from live data
- [ ] OHLCV bars are written to PostgreSQL partitioned tables
- [ ] All Level 2 integration tests pass
- [ ] No data loss on Redis restart (AOF recovery)

### Dependencies

- Phase 8: `mt5-integration.md`, `execution-engine.md`
- Phase 5: `physical-erd.md`, `redis-roles.md`
- Phase 3: `time-series-schema.md`, `stream-payloads.md`
- Sprint 1: PostgreSQL, Redis, data layer

## Sprint 3 — Decision Engine (3 weeks)

**Goal:** AutoGen pipeline produces valid proposals, risk engine validates,
lineage records written, execution dispatched. This is the core sprint.
Paper trading begins in staging on day 13.

### Deliverables

| Day | Deliverable | Detail |
|-----|-------------|--------|
| 1-2 | LLM Gateway | 9router HTTP client, model registry lookup (Phase 6 D6-3), static tier routing (D6-1), daily budget check + circuit breaker (D6-4), `llm_usage` append-only writer (D6-7), per-tier fallback chain (D6-6) |
| 3-4 | Analyst agents | 4 analyst AutoGen agents: `technical_analyst.py`, `macro_analyst.py`, `news_analyst.py`, `smc_analyst.py`. Each: loads prompt from `.prompt` file, calls LLM via gateway, validates output against Phase 4 JSON schema, returns structured result |
| 5-6 | IC Forum + CIO | `ic_forum.py`: receives 4 analyst outputs, deliberates, produces weighted recommendation with dissent. `debate.py`: deterministic trigger (D4-5), bounded 1-round debate. `cio_proposer.py`: receives IC output + all raw analyst inputs, produces final proposal with override flag |
| 7-8 | Risk engine | `risk_validator.py` (deterministic): exposure check (max 2% per trade), position limit check, kill-switch enforcement, strategy book limit check. `sizing_calculator.py`: ATR-based stop-loss, 1% risk per trade, lot size calculation. `risk_assessor.py` (LLM-assisted, per Phase 8 D8-8): qualitative risk assessment that can adjust volume or veto; final decision remains deterministic |
| 9-10 | Lineage + execution | `lineage_writer.py`: append-only write to `lineage_records` (ACID), contains full proposal, risk verdict, and policy pins. `execution_router.py`: publishes to Redis `mt5:commands`, idempotency via `processed_commands` (D3-7) for lineage-level dedup and `order_id:attempt_N` (D8-9) for order-level dedup. Reconciliation: fill vs expected comparison |
| 11-12 | System tests | Level 4 tests: full decision cycle with mock LLM (fixture files) and mock MT5 (simulated fills). Scenarios: strong buy, strong sell, neutral, split committee, CIO override, debate triggered, lineage write failure → halt, safe-state on component failure |
| 13-15 | Paper trading | Deploy to staging environment, configure MT5 paper account, start 2-week continuous paper trading. Real LLM calls, real MT5 paper execution. Lineage records written to staging DB. Weekly paper trading review |

### Exit criteria

- [ ] Full decision cycle runs end-to-end (trigger → fill → reconciliation)
- [ ] All 4 analyst agents produce schema-valid JSON
- [ ] IC Forum handles consensus, split, and no-consensus scenarios
- [ ] CIO Proposer can override IC with documented reason
- [ ] Risk validator rejects over-exposure, oversized, and kill-switched proposals
- [ ] Lineage records written before execution dispatch (write-before-dispatch)
- [ ] All Level 4 system tests pass
- [ ] Paper trading running continuously in staging with zero order errors

### Dependencies

- Phase 4: `proposal-schema.md`, `prompt-storage.md`, `prompt-versioning.md`, `inter-agent-message-versioning.md`
- Phase 6: `llm-gateway.md`, `model-routing.md`, `cost-control.md`, `memory-policy.md`, `memory-architecture.md`, `gateway-admission-control.md`, `confidence-calibration.md`, `context-budget-policy.md`
- Phase 7: `orchestration.md`, `workflow-lifecycle.md`, `recovery-and-termination.md`, `checkpoint-and-replay.md`, `reasoning-trace-storage.md`, `comparative-replay-isolation.md`, `concurrency-budget.md`, `deadline-propagation.md`
- Phase 8: `risk-engine.md`, `order-lifecycle.md`, `execution-engine.md`
- Phase 3: `lineage-schema.md`, `registry-schema.md`
- Sprint 2: FeatureProvider, MT5 bridge, data collection

## Sprint 4 — API & Frontend (2 weeks)

**Goal:** REST API serves all endpoints, SSE streams deliver realtime data,
React dashboard renders live streams with charts.

### Deliverables

| Day | Deliverable | Detail |
|-----|-------------|--------|
| 1-2 | FastAPI routers | Domain routers per D9-3: `portfolio.py`, `orders.py`, `workflows.py`, `lineage.py`, `market.py`, `journal.py`, `streams.py`, `admin.py`, `rpc.py`. HMAC auth middleware (`auth.py`), rate limit middleware, `trace_id` injection. Common envelope (`common.py`). Error responses per `error-contract.md` |
| 3-4 | SSE endpoints + Frontend foundation | SSE: 6 streams (`market_data`, `analyst_outputs`, `ic_decisions`, `cio_proposals`, `risk_assessments`, `execution_orders`), heartbeat (30s), `Last-Event-ID` reconnect, gap detection. Frontend: Vite + React, Zustand stores per SSE stream, TanStack Query for REST, SSE client with HMAC signing, reconnect logic, ActivityLog |
| 5-6 | Dashboard pages | `Terminal.tsx`: multi-pane workspace with 6 panes (D10-2). `OrderDetail.tsx`, `LineageDetail.tsx`, `Portfolio.tsx`, `Risk.tsx`, `Admin.tsx`. Dark theme tokens from `tokens.css`. Keyboard shortcuts (`useKeyboard.ts`) |
| 7-8 | Charts | `lightweight-charts` for candlestick + volume (D10-4). `ECharts` for equity curve, drawdown, exposure treemap, correlation heatmap. Realtime tick → chart update at 60fps. Crosshair sync between price and volume |
| 9-10 | Contract tests | Level 3 tests: REST response codes (200, 400, 401, 403, 404, 409, 429), auth headers (missing, invalid, expired, wrong scope), pagination, idempotency key, SSE reconnect with `Last-Event-ID`, heartbeat delivery, schema validation |

### Exit criteria

- [ ] All 9 domain routers functional with auth
- [ ] All 6 SSE streams deliver data with correct envelope
- [ ] Dashboard renders live market data from SSE
- [ ] Charts update in realtime without frame drops
- [ ] All Level 3 contract tests pass
- [ ] Frontend builds with zero TypeScript errors

### Dependencies

- Phase 9: `rest-api.md`, `sse-api.md`, `auth.md`, `error-contract.md`
- Phase 10: `architecture.md`, `components.md`, `design-tokens.md`, `wireframes.md`, `performance.md`
- Phase 13: `test-levels.md` (Level 3)
- Sprint 3: Decision engine, lineage writer, execution router

## Sprint 5 — Hardening (1 week)

**Goal:** Security, monitoring, backup, and acceptance checklist complete.
System ready for live capital deployment.

### Deliverables

| Day | Deliverable | Detail |
|-----|-------------|--------|
| 1-2 | Security hardening | UFW rules (80, 443, 22 only, D12-4), SSH config (ed25519 only, no password, D12-2), Caddy TLS + CORS, container non-root user, SOPS + age for `.env.enc` (D11-6), Grafana IP allowlist |
| 3-4 | Monitoring | Prometheus metrics (`health.py`, `metrics.py`), Loki + Promtail for structured logs, Grafana dashboards (system health, trade activity, LLM cost, error budget), Alertmanager rules (SLO burn rate, D13-6), dead man's switch |
| 5-6 | Backup | Daily `pg_dump` (custom format) + continuous WAL archiving, `rclone` with `crypt` remote to S3-compatible storage (D11-5), Redis AOF backup, monthly automated restore test |
| 7 | Acceptance checklist | All 8 pre-launch gates verified (D13-6): CI blocking gates, backtest (Sharpe > 0, max DD < 20%, profit factor > 1.0), paper trading (2 weeks, zero errors, zero lineage gaps), kill-switch test, backup restore test, MT5 bridge failover, security pentest (no critical/high open), deploy verify |

### Exit criteria

- [ ] UFW allows only 80, 443, 22
- [ ] SSH accepts only ed25519 keys
- [ ] Caddy enforces TLS ≥ 1.2, CORS allowlist exact
- [ ] All containers run as non-root
- [ ] Prometheus scraping all targets, Grafana dashboards populated
- [ ] Alertmanager sends test alert to operator
- [ ] Backup runs successfully, restore test passes
- [ ] All 8 pre-launch acceptance gates pass

### Dependencies

- Phase 11: `topology.md`, `observability.md`, `backup-dr.md`, `build-deploy.md`
- Phase 12: `network-firewall.md`, `ssh-access.md`, `encryption.md`, `audit-log.md`, `threat-model.md`
- Phase 13: `test-environments.md`, `security-testing.md`
- Sprint 3: Paper trading data (2+ weeks of lineage records)
- Sprint 4: Dashboard, API

## Sprint review gates

Each sprint must pass these gates before the next sprint begins:

| Gate | Criteria |
|------|----------|
| Test pass | All tests for the current level and all previous levels pass |
| CI green | CI pipeline passes on the sprint branch |
| Paper trading | From Sprint 3 onward: paper trading shows zero order errors and zero lineage gaps |
| Code review | All PRs for the sprint reviewed and approved |
| Doc update | Any architecture deviations documented as Phase 14 amendments |

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MT5 bridge instability | Medium | High | Sprint 2 builds bridge first; paper trading starts Sprint 3 — 4+ weeks of live testing before go-live |
| LLM provider outage | Low | Medium | Per-tier fallback chain (D6-6); cycle-skip on total outage (broker-side SL/TP active) |
| AutoGen integration complexity | Medium | High | Sprint 3 is the longest sprint (3 weeks); dedicated system test phase with mock LLM before real LLM |
| Frontend chart performance | Low | Medium | lightweight-charts is Canvas-based, proven at tick frequency; performance budget enforced in Sprint 4 |
| Database migration failure | Low | High | Alembic with explicit up/down; all migrations tested in CI before deploy; backup before each migration |

## What this document does NOT define

- Daily task breakdown within each sprint (Phase 15 — managed by the
  operator during implementation).
- Specific test case names and coverage targets per module (Phase 15).
- Paper trading review schedule and criteria (Phase 15 operations
  runbook).
- Go-live date and production deployment schedule (operator decision).

## Phase boundary

Sprint plan, deliverables, dependencies, exit criteria, and risk
register are fixed here. Daily task management, test authoring, and
deployment scheduling belong to Phase 15.