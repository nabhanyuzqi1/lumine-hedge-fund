# Test Environments

## Overview

Three environments serve distinct testing purposes, per D13-2. Staging
and production share the same VPS with complete data-layer isolation.

## Environment architecture

```
Single VPS
├─ /srv/lumine-staging/       (port 8080, DB lumine_staging, MT5 paper)
│  ├─ docker-compose.staging.yml
│  ├─ .env.staging
│  └─ Caddy: staging.lumine.internal → :8080 (IP allowlist only)
│
├─ /srv/lumine-production/    (port 80/443, DB lumine_production, MT5 live)
│  ├─ docker-compose.production.yml
│  ├─ .env
│  └─ Caddy: lumine.vercel.app → :443 (production origin only)
│
└─ Shared: PostgreSQL (separate databases), Redis (separate DB numbers)
```

## CI environment

**Location:** GitHub Actions runner (ephemeral)

**Lifecycle:** Created at job start, destroyed at job end. No shared state
between runs.

**Services:**
- PostgreSQL and Redis via `testcontainers` (Python library). Ephemeral
  containers — no pre-provisioned infrastructure.
- All application services run in-process or as Docker containers within
  the CI job.
- LLM gateway and MT5 bridge are always mocked in CI (no external network
  access required for tests).

**Data:**
- Test fixtures: static JSON/YAML files in the repository.
- Seed data: SQL files in the repository, applied at test start.
- No access to production or staging data.

## Staging environment

**Location:** Same VPS as production, `/srv/lumine-staging/`

**Access:** Internal only. Caddy listens on port 8080 with IP allowlist
(operator IP ranges only). No public DNS, no Vercel connection.

**Data isolation:**

| Concern | Production | Staging |
|---------|-----------|---------|
| PostgreSQL database | `lumine_production` | `lumine_staging` |
| Redis DB number | 0 | 1 |
| Docker network | `lumine-net` | `lumine-staging-net` |
| Docker Compose project | `lumine-production` | `lumine-staging` |
| Caddy ports | 80, 443 | 8080 (internal) |
| MT5 account | Live account | Paper/demo account |
| API keys | Production scope sets | Staging scope sets |
| LLM cost tracking | Production budget | Separate staging budget |
| Prometheus metrics | Production scrape target | Separate scrape target |

**Purpose:**
- Paper trading: minimum 2 weeks continuous operation before live launch.
- Config audit: Caddy, UFW, Docker daemon validation.
- Backup restore test: monthly automated restore verification.
- Kill-switch test: engage → verify cancel + halt → disengage → verify
  resume.
- MT5 bridge failover test: disconnect → verify SL/TP active → reconnect
  → verify recovery.
- Pre-launch acceptance checklist execution.

**Deployment:**
- Deployed from the same CI pipeline as production, with a different
  target (`deploy-staging` job or `environment` parameter).
- Images are the same SHA-pinned images as production.
- Environment variables differ: `MT5_CONNECT_MODE=paper`, `DB_NAME=
  lumine_staging`, `REDIS_DB=1`.

## Production environment

**Location:** Same VPS, `/srv/lumine-production/`

**Access:** Public ports 80, 443 via Caddy. CORS allowlist: Vercel
production origin only. SSH port 22 (ed25519 only).

**Purpose:** Live trading with real capital. Not a test environment,
but the final validation target for all pre-launch acceptance gates.

## Test data strategy

| Data type | Source | Refresh | Used by |
|-----------|--------|---------|---------|
| Unit test fixtures | Static JSON/YAML in repo | On schema change | Level 1 |
| Integration seed data | SQL files in repo | On schema change | Level 2 |
| Contract test fixtures | Static JSON matching Phase 9 schemas | On contract change | Level 3 |
| System test fixtures | Canned LLM responses + market data | On schema change | Level 4 |
| Backtest historical data | 90 days OHLCV from MT5 → PostgreSQL dump | Monthly | Level 5 |
| Paper trading data | Live market (real-time from MT5 paper) | Continuous | Level 6 |

### Historical data pipeline for backtest

```
1. MT5 Bridge (production) continuously writes OHLCV to PostgreSQL
2. Monthly: pg_dump of 90 days OHLCV → staging database
3. Backtest harness reads from staging database
4. Data is NOT synthetic — it is real broker data from production
```

## SLO & Error Budget

### Service level objective

| Metric | Target | Measurement |
|--------|--------|-------------|
| Tick latency (MT5 → decision engine) | p99 < 500ms | Prometheus histogram |
| Decision cycle latency (trigger → proposal) | p99 < 30s | Trace span duration |
| SSE heartbeat delivery | p99 < 2s | Prometheus gauge |
| API availability | 99.9% | Prometheus `up` metric |
| Error budget | 0.1% = 43m 50s/month | Alertmanager burn rate |

### Error budget burn rate alerts

| Severity | Condition | Action |
|----------|-----------|--------|
| Critical | 2% of budget burned in 1 hour | Page operator |
| Warning | 5% of budget burned in 6 hours | Notify operator |

Burn rate is calculated from the `up` metric for the trade-core service.
The error budget is consumed whenever the service is not healthy (failing
healthchecks, not reachable, or returning 5xx above threshold).

### Rationale for 99.9%

- A single-node deployment with no redundant infrastructure cannot
  realistically achieve 99.99% (52 minutes/year of downtime).
- 99.9% (43 minutes/month) allows for one brief outage per month — a
  failed deploy rollback, a restart, or a transient MT5 disconnection.
- The critical path has graceful degradation: broker-side SL/TP remains
  active during any backend outage, capping financial risk.
- As the system scales to multi-node (V2+), the SLO can be tightened.

## Pre-launch acceptance checklist

Before live capital is deployed, all 8 gates must pass:

| # | Gate | Level | Criteria |
|---|------|-------|-----------|
| 1 | CI blocking gates | 1–4 | All unit, integration, contract, and system tests pass in CI |
| 2 | Backtest (90-day) | 5 | Sharpe > 0, max drawdown < 20%, profit factor > 1.0 |
| 3 | Paper trading (2-week) | 6 | Zero order errors, zero lineage gaps |
| 4 | Kill-switch test | Staging | Engage → cancel open orders + halt → disengage → resume |
| 5 | Backup restore test | Staging | Restore from latest backup, verify data integrity (D11-5) |
| 6 | MT5 bridge failover | Staging | Disconnect → SL/TP active → reconnect → recovery |
| 7 | Security pentest | Manual | No critical or high findings open |
| 8 | Deploy verify | Staging | Healthcheck + SSE smoke check pass (D11-3) |

All 8 gates must pass. A gate failure means the system is not ready for
live capital. The operator makes the final go/no-go decision, but the
gates provide the objective evidence.

## What this document does NOT define

- Concrete Docker Compose staging/production files (Phase 14+).
- CI environment provisioning (GitHub Actions workflow YAML, Phase 14+).
- Testcontainers configuration code (Phase 14+).
- SLO dashboard JSON and Prometheus recording rules (Phase 14+).
- Acceptance checklist automation (Phase 14+).

## Phase boundary

Test environments, isolation strategy, SLO, error budget, and pre-launch
acceptance criteria are fixed here. Environment provisioning and
configuration belong to Phase 14+.