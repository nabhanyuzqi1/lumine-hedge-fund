# Lumine — AI-Native Quantitative Hedge Fund Platform

Lumine is an institutional-grade, AI-driven quantitative investment system. Autonomous AI agents collaborate inside a strict hierarchy to make investment decisions, manage risk, and execute trades — starting with **XAUUSD**, scaling to Forex, Indices, Commodities, Crypto, Stocks, and Futures.

This is **not** a retail trading bot, EA, or signal provider. Lumine is designed like a real hedge fund: an auditable, observable, replaceable, fault-tolerant platform where **LLMs only reason** and **deterministic Python owns the money and the safety**.

## The core idea

```
LLM agents reason about markets ──► deterministic Python enforces risk, sizing, execution
```

Every trade decision travels one critical path. Reasoning happens above the risk line; money moves only below it.

```
Scheduler ──► trade-core
  │
  ▼
LLM committee (4 analysts ──► optional debate ──► IC ──► CIO Proposer)   [reasoning]
  │
  ▼
RiskValidator ── FINAL VETO                                             [deterministic]
  │  APPROVE
  ▼
PortfolioSizer                                                          [deterministic]
  │
  ▼
ExecutionRouter
  ├── BEGIN TX
  ├── INSERT lineage_records   ◄── blocking ACID gate (safe state by default)
  ├── COMMIT  ── must succeed before dispatch
  └── publish mt5.commands stream
  │
  ▼
MT5 Bridge ──► fill ──► listener ──► UPDATE positions / INSERT fills
```

No LLM sits above `RiskValidator`. No async worker sits on the critical path. The CIO kill switch is read every cycle and sits above the entire path.

## Five invariants

1. **Reproducibility** — every decision pins `model_version_id`, `prompt_version_id`, and `policy_version_id`. Decisions are replayable.
2. **Auditability** — every trade decision carries an evidence chain. Lineage is written before capital moves.
3. **Safe state by default** — failures stop the pipeline, they never hide it.
4. **LLMs only reason** — deterministic code handles risk, sizing, and execution.
5. **Evidence before capital** — no proposal reaches the bridge without a signed, versioned record.

## Agent hierarchy

```
CEO
  └── CIO
        └── Investment Committee (IC)
              ├── Technical Analyst
              ├── Macro Analyst
              ├── News Analyst
              └── SMC Analyst
        └── Risk Officer
        └── Portfolio Manager
              └── Execution Controller
                    └── Trade Journal
                          └── Performance Reviewer
```

Each agent defines: purpose, responsibilities, inputs, outputs, KPIs, prompt philosophy, memory requirements, and failure modes. See [`docs/02-departments/`](docs/02-departments/) and [`docs/90-governance-and-operations/94-runbooks/agent-failure-matrix.md`](docs/90-governance-and-operations/94-runbooks/agent-failure-matrix.md).

## Development status

| Phase | Name | Status |
|-------|------|--------|
| 0–14 | Vision → Implementation Planning | Done |
| 15 | Implementation | **In progress** — Sprint 1 partial, Sprint 2 pending |

Phases are executed strictly in order; each produces documents in `docs/NN-phase-name/` before any code is written. See [`docs/phase-mapping.md`](docs/phase-mapping.md) and [`docs/INDEX.md`](docs/INDEX.md).

## Repository layout

```
lumine-hedge-fund/
├── docs/                              # Knowledge base (Phases 0–15 + governance tier)
│   ├── INDEX.md                       # Topic × phase knowledge map
│   ├── phase-mapping.md               # Master-prompt → folder mapping
│   ├── adr/                           # Architectural Decision Records (single registry)
│   ├── 00-vision/ … 15-implementation/# Design phases
│   └── 90-governance-and-operations/  # Permanent operating standards, runbooks
├── backend/                           # Python workspace (FastAPI, AutoGen, MT5 bridge)
│   └── src/lumine/                    # api, autogen_pipeline, backtest, bridge, features,
│                                      # llm_gateway, monitoring, security, trade_core, …
├── frontend/                          # TypeScript/React workspace (Phase 10 stack, pending)
├── site/                              # Marketing / landing page (Vite + React + Tailwind)
│                                      # builds to static dist/ for GitHub Pages or VPS
├── scripts/                           # Deployment & ops scripts (deploy-stack, watchdog)
├── Makefile                           # Canonical entry commands (CI parity)
└── .github/workflows/                 # CI, supply-chain, docs, deploy, pages
```

## Technology stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12+ |
| API framework | FastAPI + Uvicorn |
| Data | PostgreSQL (asyncpg), Redis (hiredis), Alembic |
| ORM | SQLAlchemy 2.0 (async) |
| AI orchestration | Microsoft AutoGen |
| LLM gateway | 9router (GPT-5.x/5.6, DeepSeek V4, Kimi K3/K2.7, Qwen 3.7, GLM 5.2) |
| Trading | MetaTrader 5 + Expert Advisor bridge |
| Logging | structlog |
| Frontend (locked, Phase 10) | React, Vite, Tailwind CSS, Motion, shadcn/ui, TanStack Query, Zustand, lightweight-charts, ECharts, SSE |
| Infrastructure | Docker, Linux VPS |

The frontend stack was evaluated and locked during Phase 10. See [`docs/10-frontend/decisions.md`](docs/10-frontend/decisions.md).

## Getting started

### Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (site and frontend)
- Docker (services: PostgreSQL, Redis, Temporal)
- MetaTrader 5 terminal (trading only; not required for development)

### Backend

```bash
make install-backend        # uv sync --all-extras
make migrate                # alembic upgrade head
make run-backend            # uvicorn lumine.api:app --reload --port 8000
make test                   # full test suite (unit, integration, contract, backtest, system)
```

### Marketing site (`site/`)

```bash
cd site
npm install
npm run dev                 # local dev server
npm run build               # static build to site/dist
npm run preview             # serve the production build locally
```

The site builds with a relative base (`base: './'`), so `site/dist/` deploys unchanged to GitHub Pages (project subpath) or to a VPS root (nginx) without domain configuration.

### Makefile commands

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

## Documentation map

| If you are… | Read this first |
|-------------|-----------------|
| New to the project | [`docs/00-vision/`](docs/00-vision/) → [`ARCHITECTURE.md`](ARCHITECTURE.md) → [`docs/90-governance-and-operations/92-onboarding/`](docs/90-governance-and-operations/92-onboarding/) |
| Looking for a decision | [`docs/adr/INDEX.md`](docs/adr/INDEX.md) |
| Looking for a topic (not a phase) | [`docs/INDEX.md`](docs/INDEX.md) |
| On-call | [`docs/90-governance-and-operations/94-runbooks/`](docs/90-governance-and-operations/94-runbooks/) |
| Implementing | [`docs/14-implementation/`](docs/14-implementation/) → [`docs/15-implementation/`](docs/15-implementation/) |
| Reporting a vulnerability | [`SECURITY.md`](SECURITY.md) |

## Architecture

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — canonical one-page overview (hierarchy, critical path, invariants)
- [`docs/01-architecture/`](docs/01-architecture/) — system architecture: layers, decisions, tradeoffs, risks
- [`docs/05-data/`](docs/05-data/) — physical storage, ERD, caching, retention
- [`docs/08-trading/`](docs/08-trading/) — MT5 integration, execution engine, risk engine
- [`docs/09-api/`](docs/09-api/) — API contracts, event envelopes, transports
- [`docs/11-infrastructure/`](docs/11-infrastructure/) — containers, observability, CI/CD, topology
- [`docs/12-security/`](docs/12-security/) — security architecture and controls

## Testing & quality gates

`docs/13-testing/` defines the cross-system strategy: unit, integration, contract, backtest, and system levels across dev, CI, and production environments. Quality gates run in CI:

- Lint and type checks (`make lint`, `make typecheck`)
- Full test suites (`make test`)
- LLM eval suite (`make eval`)
- Supply-chain scans: `osv-scanner`, Trivy (non-blocking), `pip-audit`, bandit, secret scanning (`make security-scan`)
- Docs integrity checks (`make docs-lint`)

## Operations

- [`scripts/`](scripts/) — deployment scripts: SSH-based `deploy-stack.sh`, MT5 watchdog, noVNC
- [`docs/90-governance-and-operations/`](docs/90-governance-and-operations/) — permanent operating standards: onboarding, incident response, runbooks, agent failure matrix
- Container runtime via `make docker-up` (PostgreSQL, Redis, Temporal, worker, API)

## Security

See [`SECURITY.md`](SECURITY.md) for the vulnerability reporting policy. Security architecture is documented in [`docs/12-security/`](docs/12-security/). Do not commit secrets; `.env*`, `*.key`, and `*.enc` files are gitignored — use encrypted credentials (`credentials.yml.enc`).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CODEOWNERS`](CODEOWNERS). Phases are not mixed: every change belongs to exactly one phase and updates its documentation first.

## Roadmap

1. **Phase 15 — Implementation**: Sprint 1 partial (backend foundation: API middleware, routers, schema contracts), Sprint 2 pending.
2. **XAUUSD live**: paper trading → MT5 bridge → production.
3. **Multi-asset**: Forex, indices, commodities, crypto, equities.
4. **Multi-account**: multiple portfolios, brokers, and trading accounts.

## License

See the repository metadata and [`SECURITY.md`](SECURITY.md) for policy details. All prompts and schemas are versioned, hashed, and auditable by design.
