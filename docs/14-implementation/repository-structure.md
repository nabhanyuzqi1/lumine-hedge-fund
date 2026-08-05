# Repository Structure

## Overview

Monorepo with two language workspaces: `backend/` (Python) and
`frontend/` (TypeScript/React). `docs/` and `.github/` at the root
serve both workspaces. Each workspace is independently buildable,
testable, and deployable.

## Directory tree

```
lumine-hedge-fund/
├── docs/                           # All phase documents (Phases 0-14)
│   ├── phase-mapping.md
│   ├── 00-vision/
│   ├── 01-architecture/
│   ├── 02-departments/
│   ├── 03-agents-and-contracts/
│   ├── 04-communication-and-prompts/
│   ├── 05-data/
│   ├── 06-ai/
│   ├── 07-autogen/
│   ├── 08-trading/
│   ├── 09-api/
│   ├── 10-frontend/
│   ├── 11-infrastructure/
│   ├── 12-security/
│   ├── 13-testing/
│   └── 14-implementation/
│
├── backend/                        # Python workspace root
│   ├── pyproject.toml              # Project metadata, dependencies, tool config
│   ├── uv.lock                     # Locked Python dependencies
│   ├── docker-compose.yml          # Development compose
│   ├── docker-compose.prod.yml     # Production compose (Phase 11)
│   ├── Dockerfile                  # Multi-stage, non-root user
│   ├── alembic/                    # Database migrations
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   ├── src/
│   │   ├── lumine/                     # Python package root (namespace)
│   │   │   ├── __init__.py
│   │   │   ├── trade_core/             # Critical-path monolith (Phase 1)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── decision_engine.py  # execute_decision_cycle()
│   │   │   │   ├── feature_provider.py
│   │   │   │   ├── risk_validator.py
│   │   │   │   ├── sizing_calculator.py
│   │   │   │   ├── lineage_writer.py
│   │   │   │   └── execution_router.py
│   │   │   │
│   │   │   ├── autogen_pipeline/       # Phase 4/7: AutoGen orchestration
│   │   │   │   ├── __init__.py
│   │   │   │   ├── orchestrator.py     # Workflow lifecycle state machine
│   │   │   │   ├── agents/             # One file per agent role
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── technical_analyst.py
│   │   │   │   │   ├── macro_analyst.py
│   │   │   │   │   ├── news_analyst.py
│   │   │   │   │   └── smc_analyst.py
│   │   │   │   ├── debate.py
│   │   │   │   ├── ic_forum.py
│   │   │   │   └── cio_proposer.py
│   │   │   │
│   │   │   ├── llm_gateway/            # Phase 6: 9router client + routing
│   │   │   │   ├── __init__.py
│   │   │   │   ├── gateway.py          # 9router HTTP client
│   │   │   │   ├── router.py           # Static tier routing + escalation
│   │   │   │   ├── budget.py           # Daily budget check + circuit breaker
│   │   │   │   └── cost_tracker.py     # llm_usage table writer
│   │   │   │
│   │   │   ├── mt5_bridge/             # Phase 8: Redis-based MT5 bridge
│   │   │   │   ├── __init__.py
│   │   │   │   ├── command_queue.py    # Redis command publisher
│   │   │   │   ├── result_subscriber.py # Redis pub/sub listener
│   │   │   │   └── protocol.py         # MT5 command/response schemas
│   │   │   │
│   │   │   ├── api/                    # Phase 9: FastAPI application
│   │   │   │   ├── __init__.py
│   │   │   │   ├── app.py              # FastAPI application factory
│   │   │   │   ├── routers/            # One router per domain (D9-3)
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── portfolio.py
│   │   │   │   │   ├── orders.py
│   │   │   │   │   ├── workflows.py
│   │   │   │   │   ├── lineage.py
│   │   │   │   │   ├── market.py
│   │   │   │   │   ├── journal.py
│   │   │   │   │   ├── streams.py
│   │   │   │   │   ├── admin.py
│   │   │   │   │   └── rpc.py
│   │   │   │   ├── middleware/         # Auth, rate limit, trace_id
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── auth.py         # HMAC-SHA256 verification
│   │   │   │   │   ├── rate_limit.py
│   │   │   │   │   └── tracing.py      # trace_id injection
│   │   │   │   ├── schemas/            # Pydantic request/response models
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── common.py       # Envelope, pagination, error
│   │   │   │   │   ├── portfolio.py
│   │   │   │   │   ├── orders.py
│   │   │   │   │   └── ...
│   │   │   │   └── sse/                # SSE endpoint handlers
│   │   │   │       ├── __init__.py
│   │   │   │       ├── market_data.py
│   │   │   │       ├── analyst_outputs.py
│   │   │   │       ├── ic_decisions.py
│   │   │   │       ├── cio_proposals.py
│   │   │   │       ├── risk_assessments.py
│   │   │   │       └── execution_orders.py
│   │   │   │
│   │   │   ├── data/                   # Phase 5: Database access layer
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models.py           # SQLAlchemy ORM models
│   │   │   │   ├── queries.py          # Raw SQL for performance-critical paths
│   │   │   │   └── redis.py            # Redis client + connection pool
│   │   │   │
│   │   │   ├── registry/               # Phase 3: Version registry
│   │   │   │   ├── __init__.py
│   │   │   │   ├── model_registry.py
│   │   │   │   ├── prompt_registry.py
│   │   │   │   ├── strategy_registry.py
│   │   │   │   └── policy_registry.py
│   │   │   │
│   │   │   ├── schemas/                # Phase 3/4: JSON Schema files
│   │   │   │   ├── streams/            # Stream payload schemas
│   │   │   │   │   ├── market_data.json
│   │   │   │   │   ├── analyst_output.json
│   │   │   │   │   └── ...
│   │   │   │   └── agents/             # Agent output schemas (Phase 4)
│   │   │   │       ├── technical_analyst_output.json
│   │   │   │       ├── macro_analyst_output.json
│   │   │   │       ├── news_analyst_output.json
│   │   │   │       ├── smc_analyst_output.json
│   │   │   │       ├── ic_forum_output.json
│   │   │   │       └── cio_proposal_output.json
│   │   │   │
│   │   │   ├── prompts/                # Phase 4: Prompt files + eval datasets
│   │   │   │   ├── technical_analyst@v1.prompt
│   │   │   │   ├── macro_analyst@v1.prompt
│   │   │   │   ├── news_analyst@v1.prompt
│   │   │   │   ├── smc_analyst@v1.prompt
│   │   │   │   ├── ic_forum@v1.prompt
│   │   │   │   ├── cio_proposer@v1.prompt
│   │   │   │   └── evals/              # Phase 13: Eval datasets (YAML)
│   │   │   │       ├── technical_analyst/
│   │   │   │       │   └── datasets/
│   │   │   │       ├── macro_analyst/
│   │   │   │       ├── news_analyst/
│   │   │   │       └── smc_analyst/
│   │   │   │
│   │   │   ├── security/               # Phase 12: Auth + audit
│   │   │   │   ├── __init__.py
│   │   │   │   ├── hmac.py             # HMAC-SHA256 sign/verify
│   │   │   │   ├── scope_checker.py    # Scope-based authorization
│   │   │   │   └── audit.py            # security_events writer
│   │   │   │
│   │   │   ├── backtest/               # Phase 13: Backtest harness
│   │   │   │   ├── __init__.py
│   │   │   │   ├── harness.py          # Backtest orchestrator
│   │   │   │   ├── slippage_model.py   # Pessimistic slippage simulation
│   │   │   │   └── fixtures/           # LLM mock fixture files (JSON)
│   │   │   │
│   │   │   ├── monitoring/             # Phase 11: Health + metrics
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py           # Healthcheck endpoints
│   │   │   │   └── metrics.py          # Prometheus metrics
│   │   │   │
│   │   │   └── shared/                 # Cross-module utilities
│   │   │       ├── __init__.py
│   │   │       ├── config.py           # pydantic-settings, env-var loading
│   │   │       ├── logging.py          # structlog configuration
│   │   │       ├── types.py            # Shared type aliases, enums
│   │   │       └── errors.py           # Custom exception hierarchy
│   │
│   └── tests/                      # Mirrors src/ structure
│       ├── __init__.py
│       ├── conftest.py             # Shared fixtures
│       ├── unit/
│       │   ├── test_risk_validator.py
│       │   ├── test_sizing_calculator.py
│       │   ├── test_feature_provider.py
│       │   ├── test_lineage_serializer.py
│       │   ├── test_hmac.py
│       │   └── ...
│       ├── integration/
│       │   ├── test_lineage_writer.py
│       │   ├── test_feature_provider_db.py
│       │   ├── test_execution_router_redis.py
│       │   └── ...
│       ├── contract/
│       │   ├── test_rest_api.py
│       │   ├── test_sse_reconnect.py
│       │   ├── test_agent_schemas.py
│       │   └── ...
│       ├── system/
│       │   ├── test_decision_cycle.py
│       │   ├── test_safe_state.py
│       │   └── ...
│       └── backtest/
│           ├── test_harness.py
│           └── test_slippage_model.py
│
├── frontend/                       # TypeScript workspace root
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── biome.json
│   ├── index.html
│   └── src/
│       ├── main.tsx                # React entry point
│       ├── App.tsx                 # Root layout + routing
│       ├── api/                    # API client layer (Phase 9)
│       │   ├── client.ts           # HMAC-signed HTTP client
│       │   ├── rest/               # TanStack Query hooks per domain
│       │   │   ├── usePortfolio.ts
│       │   │   ├── useOrders.ts
│       │   │   ├── useLineage.ts
│       │   │   └── ...
│       │   └── sse/                # SSE connection managers
│       │       ├── useMarketStream.ts
│       │       ├── useCommitteeStream.ts
│       │       ├── useRiskStream.ts
│       │       └── useExecutionStream.ts
│       ├── stores/                 # Zustand stores (Phase 10 D10-3)
│       │   ├── marketStore.ts
│       │   ├── orderStore.ts
│       │   ├── committeeStore.ts
│       │   └── riskStore.ts
│       ├── components/             # Atomic Design hierarchy
│       │   ├── atoms/              # Button, Input, Badge, Spinner...
│       │   ├── molecules/          # PriceCard, OrderRow, AgentVote...
│       │   ├── organisms/          # PriceChart, OrderBook, CommitteePanel...
│       │   └── templates/          # WorkspaceLayout, DetailLayout...
│       ├── pages/                  # Top-level pages
│       │   ├── Terminal.tsx        # Multi-pane workspace (D10-2)
│       │   ├── OrderDetail.tsx
│       │   ├── LineageDetail.tsx
│       │   ├── Portfolio.tsx
│       │   ├── Risk.tsx
│       │   └── Admin.tsx
│       ├── hooks/                  # Shared hooks
│       │   ├── useStream.ts        # Generic SSE hook
│       │   ├── useKeyboard.ts      # Keyboard shortcuts
│       │   └── useTheme.ts
│       ├── lib/                    # Utilities, formatters, types
│       │   ├── types.ts            # Shared TypeScript types
│       │   ├── format.ts           # Number, date, currency formatters
│       │   ├── hmac.ts             # Client-side HMAC signing
│       │   └── constants.ts
│       ├── styles/                 # Design tokens, global styles
│       │   ├── tokens.css          # CSS custom properties
│       │   ├── global.css          # Reset, base styles
│       │   └── utilities.css       # Utility classes
│       └── test/                   # Component + hook tests
│           ├── setup.ts            # Vitest setup
│           └── components/
│
└── .github/
    ├── workflows/
    │   ├── ci.yml                  # Backend CI
    │   ├── ci-frontend.yml         # Frontend CI
    │   └── deploy.yml              # Deploy to staging + production
    └── dependabot.yml
```

## Module boundaries

### `trade_core/` vs `autogen_pipeline/`

`trade_core/` is the deterministic critical path. It contains no LLM
calls, no AutoGen imports, no network I/O beyond database and Redis.
It is tested at Level 1 (unit) with zero external dependencies.

`autogen_pipeline/` is the LLM orchestration layer. It depends on
`trade_core/` (calls `feature_provider`, receives `risk_validator`
results) but `trade_core/` never depends on `autogen_pipeline/`.

This separation is intentional:
- `trade_core/` can be tested in isolation with deterministic inputs.
- `autogen_pipeline/` can be tested with mock LLM responses.
- The dependency direction enforces the LLM-as-proposer,
  deterministic-as-validator architecture (Phase 1 Decision #2).

### `api/` vs everything else

`api/` is the HTTP boundary. It depends on `trade_core/`,
`autogen_pipeline/`, `data/`, and `security/`. No other module depends
on `api/`. This is the Port/Adapter pattern from Phase 1 — the API is
an adapter that exposes internal capabilities over HTTP.

### `data/` as the persistence boundary

`data/` is the only module that imports SQLAlchemy and Redis clients.
All other modules access data through `data/` interfaces. This means:
- Changing the database library requires changes to `data/` only.
- Modules are testable with mock data layer implementations.
- SQL is never scattered across the codebase.

### `shared/` constraints

`shared/` contains only cross-cutting utilities: config, logging,
types, errors. It must not contain business logic, database access,
or external API calls. It is a leaf dependency — it depends on
nothing within `src/` except standard library and third-party packages.

## Naming conventions

| Type | Convention | Example |
|------|------------|---------|
| Python modules | `snake_case` | `risk_validator.py` |
| Python packages | `snake_case` | `trade_core/` |
| Python classes | `PascalCase` | `RiskValidator` |
| Python functions | `snake_case` | `check_exposure()` |
| Python constants | `UPPER_CASE` | `MAX_EXPOSURE_PCT` |
| TypeScript modules | `camelCase` | `useMarketStream.ts` |
| TypeScript components | `PascalCase` | `PriceChart.tsx` |
| TypeScript hooks | `use` prefix, camelCase | `useStream.ts` |
| TypeScript stores | `Store` suffix, camelCase | `marketStore.ts` |
| Test files | `test_` prefix (Python), `.test` suffix (TS) | `test_risk_validator.py`, `Button.test.tsx` |

## What this document does NOT define

- Concrete file contents (Phase 15).
- Import paths and dependency graphs (emerge during implementation).
- Package versions in `pyproject.toml` or `package.json` (Phase 15).

## Phase boundary

Repository structure is fixed. Module boundaries, naming conventions,
and the directory tree are the contract for Sprint 1 (Foundation).
Files are created in Phase 15.