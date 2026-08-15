# Lumine

AI-native quantitative hedge fund platform. Lumine starts with XAUUSD and is designed for auditable, risk-controlled, multi-portfolio execution.

> **Status**: Sprint 1 Foundation in progress. Architecture and design phases 0-14 are documented and approved. Production trading is not enabled by this repository state.

## Product Surface

- FastAPI backend for market data, decisions, risk, execution, journal, audit, and SSE streams.
- React/Vite frontend with institutional dashboard and terminal.
- PostgreSQL for durable state and audit records.
- Redis for realtime buffers, idempotency, and bridge transport.
- MetaTrader 5 Expert Advisor bridge for execution.
- AutoGen-based agent hierarchy with deterministic risk and sizing controls.
- 9router-compatible LLM gateway with versioned prompts, model pins, budgets, and usage records.

## Repository Map

| Area | Location |
|---|---|
| Backend | [`backend/`](backend/) |
| Frontend | [`frontend/`](frontend/) |
| Architecture and phase docs | [`docs/`](docs/) |
| Infrastructure | [`infrastructure/`](infrastructure/) |
| Deployment scripts | [`scripts/deploy/`](scripts/deploy/) |
| Project commands | [`Makefile`](Makefile) |

Phase index:

- [Vision](docs/00-vision/README.md)
- [Architecture](docs/01-architecture/README.md)
- [Departments](docs/02-departments/README.md)
- [Agents and contracts](docs/03-agents-and-contracts/README.md)
- [Communication and prompts](docs/04-communication-and-prompts/README.md)
- [Data](docs/05-data/README.md)
- [AI](docs/06-ai/README.md)
- [AutoGen](docs/07-autogen/README.md)
- [Trading](docs/08-trading/README.md)
- [API](docs/09-api/README.md)
- [Frontend](docs/10-frontend/README.md)
- [Infrastructure](docs/11-infrastructure/README.md)
- [Security](docs/12-security/README.md)
- [Testing](docs/13-testing/README.md)
- [Implementation planning](docs/14-implementation/README.md)
- [Implementation status](docs/15-implementation/README.md)
- [Governance and operations](docs/90-governance-and-operations/README.md)

## Local Setup

Prerequisites:

- macOS or Linux
- Python 3.12
- `uv`
- Node.js 22 and npm for the frontend
- Docker Desktop for PostgreSQL/Redis integration tests
- PostgreSQL and Redis for local runtime, or the project Docker Compose setup

Install dependencies:

```bash
make install
```

Run the backend:

```bash
make run-backend
```

Run the frontend in a second terminal:

```bash
make run-frontend
```

Open `http://localhost:5173/` for the portal and `http://localhost:5173/terminal` for the terminal when Vite is running.

## Canonical Quality Gates

```bash
make lint
make typecheck
make test
make coverage
make security
make verify-chain
```

Focused backend commands:

```bash
cd backend
uv run pytest tests/unit tests/contract
uv run pytest tests/integration
uv run alembic upgrade head
uv run python scripts/verify_chain.py
```

The project virtual environment must be used when the system `uv` environment is not provisioned correctly:

```bash
backend/.venv/bin/pytest backend/tests/unit backend/tests/contract
```

## Canonical Quality Gates

```bash
make lint
make typecheck
make test
make coverage
make security
make verify-chain
```

Focused backend commands:

```bash
cd backend
uv run pytest tests/unit tests/contract
uv run pytest tests/integration
uv run alembic upgrade head
uv run python scripts/verify_chain.py
```

The project virtual environment must be used when the system `uv` environment is not provisioned correctly:

```bash
backend/.venv/bin/pytest backend/tests/unit backend/tests/contract
```

## Current Implementation Status

Sprint 1 Foundation in progress. Deliverables: repository scaffolding, dependency management with `uv`, TypeScript setup with Biome, Docker Compose dev environment, and Alembic migrations.

See [docs/15-implementation/sprint-plan.md](docs/15-implementation/sprint-plan.md) for detailed sprint breakdown and exit criteria.

## Security Rules

- Do not commit `.env`, `secrets.env`, private keys, tokens, or broker credentials.
- Use SOPS/age-based secret handling documented in [`docs/adr/0050-secrets-injection-sops-age-env-var.md`](docs/adr/0050-secrets-injection-sops-age-env-var.md).
- Keep live trading disabled until database, broker, risk, audit, and WORM verification gates pass.
- Every decision and execution must remain replayable and attributable to versioned inputs.

## Development Rules

- Work on one documented phase at a time.
- Update architecture and contracts before changing implementation behavior.
- Keep deterministic risk, sizing, validation, and persistence outside LLM reasoning.
- Add focused tests for every behavioral change.
- Do not commit secrets or bypass failing quality gates without documenting the reason.

## License

Proprietary. Copyright (c) 2026 Lumine.
