# Lumine

**AI-Native Quantitative Hedge Fund Platform**

[![Backend CI](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/ci.yml/badge.svg)](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/ci.yml)
[![Frontend CI](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/ci-frontend.yml)
[![Supply Chain](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/supply-chain.yml/badge.svg)](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/supply-chain.yml)
[![Docs](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/docs.yml/badge.svg)](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/docs.yml)
[![Deploy](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/deploy.yml/badge.svg)](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/deploy.yml)

Lumine is an institutional-grade, AI-driven quantitative investment system. Autonomous AI agents collaborate inside a strict hierarchy to make investment decisions, manage risk, and execute trades — starting with **XAUUSD**, scaling to Forex, Indices, Commodities, Crypto, Stocks, and Futures.

This is **not** a retail trading bot, EA, or signal provider. Lumine is designed like a real hedge fund: an auditable, observable, replaceable, fault-tolerant platform where **LLMs only reason** and **deterministic Python owns the money and the safety**.

---

## Status

| Service | Endpoint |
|---------|----------|
| Landing page | [lumine-terminal.com](https://lumine-terminal.com) |
| Backend API | `https://<vps>/backend/` |
| Control plane portal | `https://<vps>/portal/` |
| Health dashboard | `https://<vps>/dashboard/` |

System uptime is monitored internally via [Uptime Kuma](https://github.com/louislam/uptime-kuma) on the control plane. Dashboard accessible at `/dashboard/` behind Authelia SSO.

---

## The Core Idea

```text
LLM agents reason about markets --- deterministic Python enforces risk, sizing, execution
```

Every trade decision travels one critical path. Reasoning happens above the risk line; money moves only below it.

```text
Scheduler --- trade-core
  |
  v
LLM committee (4 analysts --- optional debate --- IC --- CIO Proposer)   [reasoning]
  |
  v
RiskValidator --- FINAL VETO                                             [deterministic]
  |  APPROVE
  v
PortfolioSizer                                                          [deterministic]
  |
  v
ExecutionRouter
  +-- BEGIN TX
  +-- INSERT lineage_records   <-- blocking ACID gate (safe state by default)
  +-- COMMIT  --- must succeed before dispatch
  +-- publish mt5.commands stream
  |
  v
MT5 Bridge --- fill --- listener --- UPDATE positions / INSERT fills
```

No LLM sits above `RiskValidator`. No async worker sits on the critical path. The CIO kill switch is read every cycle and sits above the entire path.

---

## Five Invariants

1. **Reproducibility** --- every decision pins `model_version_id`, `prompt_version_id`, and `policy_version_id`. Decisions are replayable.
2. **Auditability** --- every trade decision carries an evidence chain. Lineage is written before capital moves.
3. **Safe state by default** --- failures stop the pipeline, they never hide it.
4. **LLMs only reason** --- deterministic code handles risk, sizing, and execution.
5. **Evidence before capital** --- no proposal reaches the bridge without a signed, versioned record.

---

## Agent Hierarchy

```text
CEO
  +-- CIO
        +-- Investment Committee (IC)
              +-- Technical Analyst
              +-- Macro Analyst
              +-- News Analyst
              +-- SMC Analyst
        +-- Risk Officer
        +-- Portfolio Manager
              +-- Execution Controller
                    +-- Trade Journal
                          +-- Performance Reviewer
```

Each agent defines: purpose, responsibilities, inputs, outputs, KPIs, prompt philosophy, memory requirements, and failure modes. See [`docs/02-departments/`](docs/02-departments/) and [`docs/90-governance-and-operations/94-runbooks/agent-failure-matrix.md`](docs/90-governance-and-operations/94-runbooks/agent-failure-matrix.md).

---

## Development Status

| Phase | Name | Status |
|-------|------|--------|
| 0--14 | Vision through Implementation Planning | Done |
| 15 | Implementation | **In progress** --- Sprint 1–3 done, Sprint 4 API core done (G1–G5, G6, G7, G8 gate PASS), Sprint 5+ pending |

Phases are executed strictly in order; each produces documents in `docs/NN-phase-name/` before any code is written. See [`docs/phase-mapping.md`](docs/phase-mapping.md) and [`docs/INDEX.md`](docs/INDEX.md).

---

## Technology Stack

### Core Platform

| Layer | Choice | Link |
|-------|--------|------|
| Language | Python 3.12+ | [python.org](https://python.org) |
| API framework | FastAPI + Uvicorn | [github.com/fastapi/fastapi](https://github.com/fastapi/fastapi) |
| Database | PostgreSQL (asyncpg) | [github.com/postgres/postgres](https://github.com/postgres/postgres) |
| Cache | Redis (hiredis) | [github.com/redis/redis](https://github.com/redis/redis) |
| ORM | SQLAlchemy 2.0 (async) | [github.com/sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) |
| Migrations | Alembic | [github.com/sqlalchemy/alembic](https://github.com/sqlalchemy/alembic) |
| AI orchestration | Microsoft AutoGen | [github.com/microsoft/autogen](https://github.com/microsoft/autogen) |
| LLM gateway | 9router | GPT-5.5/5.6, DeepSeek V4, Kimi K3, Qwen 3.7, GLM 5.2 |
| Trading | MetaTrader 5 + EA bridge | [metatrader5.com](https://metatrader5.com) |
| Logging | structlog | [github.com/hynek/structlog](https://github.com/hynek/structlog) |

### Frontend (Phase 10 --- locked)

| Choice | Link |
|--------|------|
| React 19 | [github.com/facebook/react](https://github.com/facebook/react) |
| Vite | [github.com/vitejs/vite](https://github.com/vitejs/vite) |
| Tailwind CSS | [github.com/tailwindlabs/tailwindcss](https://github.com/tailwindlabs/tailwindcss) |
| Motion (Framer) | [github.com/motiondivision/motion](https://github.com/motiondivision/motion) |
| shadcn/ui | [github.com/shadcn-ui/ui](https://github.com/shadcn-ui/ui) |
| TanStack Query | [github.com/tanstack/query](https://github.com/tanstack/query) |
| Zustand | [github.com/pmndrs/zustand](https://github.com/pmndrs/zustand) |
| lightweight-charts | [github.com/tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts) |
| ECharts | [github.com/apache/echarts](https://github.com/apache/echarts) |

### Infrastructure & Control Plane

| Component | Role | Link |
|-----------|------|------|
| Docker | Container runtime | [github.com/docker](https://github.com/docker) |
| Caddy | Reverse proxy + TLS | [github.com/caddyserver/caddy](https://github.com/caddyserver/caddy) |
| Authelia | SSO + TOTP auth gate | [github.com/authelia/authelia](https://github.com/authelia/authelia) |
| Homepage | Service dashboard hub | [github.com/gethomepage/homepage](https://github.com/gethomepage/homepage) |
| Uptime Kuma | Health monitoring | [github.com/louislam/uptime-kuma](https://github.com/louislam/uptime-kuma) |
| noVNC | Remote MT5 desktop | [github.com/novnc/noVNC](https://github.com/novnc/noVNC) |
| Prometheus | Metrics collection | [github.com/prometheus/prometheus](https://github.com/prometheus/prometheus) |
| Grafana | Observability dashboards | [github.com/grafana/grafana](https://github.com/grafana/grafana) |
| Loki + Promtail | Log aggregation | [github.com/grafana/loki](https://github.com/grafana/loki) |
| Tempo | Distributed tracing | [github.com/grafana/tempo](https://github.com/grafana/tempo) |

### Dev Tooling

| Tool | Link |
|------|------|
| uv (Python package manager) | [github.com/astral-sh/uv](https://github.com/astral-sh/uv) |
| Ruff (linter + formatter) | [github.com/astral-sh/ruff](https://github.com/astral-sh/ruff) |
| MyPy (type checker) | [github.com/python/mypy](https://github.com/python/mypy) |
| GitHub Actions (CI/CD) | [github.com/features/actions](https://github.com/features/actions) |
| SOPS + age (secrets) | [github.com/getsops/sops](https://github.com/getsops/sops) |

---

## Control Plane Architecture

The VPS runs a single `control-plane` Docker Compose stack that fronts all services:

```text
Internet :80/:443  (only public ports)
  |
  +-- Caddy (host network, TLS)
       |
       +-- /                --- landing page (public, nginx container :8080)
       +-- /auth*           --- Authelia SSO (login + TOTP, :9091)
       +-- /portal*         --- Homepage hub (auth required, :3000)
       +-- /dashboard*      --- Uptime Kuma (auth required, :3001)
       +-- /hermes*         --- Hermes messaging dashboard (auth, :9119)
       +-- /mt5/*           --- noVNC remote desktop (auth, :6901)
       +-- /backend*        --- Lumine API (auth, :8000)
       +-- /logout*         --- Session destroy --- redirect to Authelia logout
```

**All upstream services bind `127.0.0.1`** --- Caddy is the single entrypoint. The only exception is `9router` on `:20128` (external AI agent access, compensating controls pending). See [D11-7](docs/11-infrastructure/decisions.md#d11-7--control-plane-caddy--authelia--homepage--uptime-kuma) for the full decision record.

**Access:** `https://166.88.227.177/` with self-signed TLS (domain pending). Login once at `/auth/` with TOTP; all protected routes share the session. Logout at `/logout/` or via the Homepage header button.

---

## Repository Layout

```text
lumine-hedge-fund/
+-- docs/                              # Knowledge base (Phases 0--15 + governance tier)
|   +-- INDEX.md                       # Topic x phase knowledge map
|   +-- phase-mapping.md               # Master-prompt --- folder mapping
|   +-- adr/                           # Architectural Decision Records (single registry)
|   +-- 00-vision/ ... 15-implementation/  # Design phases
|   +-- 90-governance-and-operations/  # Permanent operating standards, runbooks
+-- backend/                           # Python workspace (FastAPI, AutoGen, MT5 bridge)
|   +-- src/lumine/                    # api, autogen_pipeline, backtest, bridge, features,
|                                      # llm_gateway, monitoring, security, trade_core, ...
+-- frontend/                          # Landing page + future Phase 10 trading dashboard
+-- infrastructure/                    # Control plane configs (Caddy, Authelia, Homepage, Uptime Kuma)
+-- scripts/                           # Deploy & ops scripts (deploy-site, deploy-stack, watchdog)
+-- Makefile                           # Canonical entry commands (CI parity)
+-- .github/workflows/                 # CI, frontend CI, supply-chain, docs, deploy
```

---

## Getting Started

### Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (frontend)
- Docker (services: PostgreSQL, Redis, Temporal)
- MetaTrader 5 terminal (trading only; not required for development)

### Backend

```bash
make install-backend        # uv sync --all-extras
make migrate                # alembic upgrade head
make run-backend            # uvicorn lumine.api:app --reload --port 8000
make test                   # full test suite (unit, integration, contract, backtest, system)
```

### Frontend (`frontend/`)

```bash
cd frontend
npm install
npm run dev                 # local dev server
npm run build               # static build to frontend/dist
npm run preview             # serve the production build locally
```

The site builds with a relative base (`base: './'`), compatible with VPS root deployment through Caddy's `control-landing` nginx container.

### Makefile Commands

| Target | Purpose |
|--------|---------|
| `make install` | Install backend + frontend dependencies |
| `make migrate` | Apply database migrations (dev) |
| `make migrations-new m="msg"` | Autogenerate a new migration |
| `make run-backend` / `run-frontend` | Dev servers |
| `make lint` / `typecheck` | Ruff, MyPy and formatting gates |
| `make test` | Unit, integration, contract, backtest, and system suites |
| `make coverage` | Coverage report |
| `make eval` | LLM eval suite |
| `make backtest` | Backtesting harness |
| `make security-scan` | Supply-chain SBOM, pip-audit, bandit, secret scan |
| `make docs-lint` | Docs links, ADR registry, freshness checks |
| `make docker-build` / `docker-up` / `docker-down` | Containerized runtime |

`make help` lists all targets. CI invokes these targets only, guaranteeing local/CI parity.

---

## Documentation Map

| If you are... | Read this first |
|---------------|-----------------|
| New to the project | [`docs/00-vision/`](docs/00-vision/) --- [`ARCHITECTURE.md`](ARCHITECTURE.md) --- [`docs/90-governance-and-operations/92-onboarding/`](docs/90-governance-and-operations/92-onboarding/) |
| Looking for a decision | [`docs/adr/INDEX.md`](docs/adr/INDEX.md) |
| Looking for a topic (not a phase) | [`docs/INDEX.md`](docs/INDEX.md) |
| On-call | [`docs/90-governance-and-operations/94-runbooks/`](docs/90-governance-and-operations/94-runbooks/) |
| Implementing | [`docs/14-implementation/`](docs/14-implementation/) --- [`docs/15-implementation/`](docs/15-implementation/) |
| Reporting a vulnerability | [`SECURITY.md`](SECURITY.md) |

---

## Architecture

- [`ARCHITECTURE.md`](ARCHITECTURE.md) --- canonical one-page overview (hierarchy, critical path, invariants)
- [`docs/01-architecture/`](docs/01-architecture/) --- system architecture: layers, decisions, tradeoffs, risks
- [`docs/05-data/`](docs/05-data/) --- physical storage, ERD, caching, retention
- [`docs/08-trading/`](docs/08-trading/) --- MT5 integration, execution engine, risk engine
- [`docs/09-api/`](docs/09-api/) --- API contracts, event envelopes, transports
- [`docs/11-infrastructure/`](docs/11-infrastructure/) --- containers, observability, CI/CD, topology
- [`docs/12-security/`](docs/12-security/) --- security architecture and controls

---

## Testing & Quality Gates

`docs/13-testing/` defines the cross-system strategy: unit, integration, contract, backtest, and system levels across dev, CI, and production environments. Quality gates run in CI:

- Lint and type checks (`make lint`, `make typecheck`)
- Full test suites (`make test`)
- LLM eval suite (`make eval`)
- Supply-chain scans: `osv-scanner`, Trivy (non-blocking), `pip-audit`, bandit, secret scanning (`make security-scan`)
- Docs integrity checks (`make docs-lint`)

---

## Deploy

### Landing Page (active)

The marketing site (`frontend/`) deploys automatically to the production VPS via GitHub Actions on push to `main`, or manually via [`workflow_dispatch`](https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions/workflows/deploy.yml).

**Pipeline:**

1. Build site: `npm ci && npm run build` --- `frontend/dist`
2. Send `dist/` to VPS via SCP (`/tmp/lumine-dist/`)
3. Install into `/var/www/lumine` (in-place copy, preserves bind-mount inode)
4. Health check: `curl http://127.0.0.1:8080/` via the `control-landing` nginx container

**Required GitHub secrets:**

| Secret | Purpose |
|--------|---------|
| `DEPLOY_HOST` | VPS hostname or IP |
| `DEPLOY_USER` | SSH user on the VPS |
| `DEPLOY_SSH_KEY` | ED25519 private key (public key in `authorized_keys`) |
| `DEPLOY_DB_PASSWORD` | Database password *(future full-stack)* |
| `DEPLOY_HMAC_SECRET_KEY` | HMAC signing key *(future full-stack)* |
| `DEPLOY_LLM_GATEWAY_API_KEY` | 9router API key *(future full-stack)* |
| `DEPLOY_VNC_PASSWORD` | noVNC password *(future full-stack)* |

Secrets: **Settings --- Secrets and variables --- Actions --- New repository secret**.

**SSH key setup (one-time):**

```bash
ssh-keygen -t ed25519 -f lumine_deploy -C "lumine-ci-deploy"
ssh-copy-id -i lumine_deploy.pub root@<vps-host>
# Add lumine_deploy (private key) as DEPLOY_SSH_KEY secret
```

**Local deploy:**

```bash
cp scripts/deploy/.env.sample scripts/deploy/.env
$EDITOR scripts/deploy/.env
./scripts/deploy/deploy-site.sh
```

### Full Stack (pending)

Backend services (Docker Compose) will deploy via `deploy-stack.sh` when V1 services are ready. The pipeline builds an immutable image per SHA, pushes to GHCR, and SSHs to the VPS for `docker compose pull && up -d`. See [D11-3](docs/11-infrastructure/decisions.md#d11-3--cicd-github-actions--ghcr--ssh-deploy-vercel-git-integration).

---

## Operations

- [`scripts/`](scripts/) --- deployment scripts: `deploy-site.sh` (landing page --- container nginx :8080), `deploy-stack.sh` (full stack, pending), MT5 watchdog, noVNC
- [`docs/90-governance-and-operations/`](docs/90-governance-and-operations/) --- permanent operating standards: onboarding, incident response, runbooks, agent failure matrix
- Container runtime via `make docker-up` (PostgreSQL, Redis, Temporal, worker, API)
- Uptime Kuma monitors all 7 endpoints from inside the VPS; dashboard at `/dashboard/` behind Authelia

---

## Security

See [`SECURITY.md`](SECURITY.md) for the vulnerability reporting policy. Security architecture is documented in [`docs/12-security/`](docs/12-security/). Do not commit secrets; `.env*`, `*.key`, and `*.enc` files are gitignored --- use encrypted credentials (`credentials.yml.enc`).

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CODEOWNERS`](CODEOWNERS). Phases are not mixed: every change belongs to exactly one phase and updates its documentation first.

---

## Roadmap

1. **Phase 15 --- Implementation**: Sprints 1–3 done (foundation, data pipeline, risk & execution); Sprint 4 API core done (HMAC auth, envelope, SSE 6 channels, idempotency, rate limiting, logging/tracing — G1–G5, G7 of `sprint-4-completion-plan.md`); Sprint 5 hardening and frontend F-Sprints pending.
2. **XAUUSD live**: paper trading --- MT5 bridge --- production.
3. **Multi-asset**: Forex, indices, commodities, crypto, equities.
4. **Multi-account**: multiple portfolios, brokers, and trading accounts.

---

## License

See the repository metadata and [`SECURITY.md`](SECURITY.md) for policy details. All prompts and schemas are versioned, hashed, and auditable by design.
