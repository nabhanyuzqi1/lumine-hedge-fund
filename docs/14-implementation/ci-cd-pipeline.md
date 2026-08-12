# CI/CD Pipeline

## Scope

The repository uses five GitHub Actions workflows:

| Workflow | Trigger scope | Purpose |
|---|---|---|
| [`ci.yml`](../../.github/workflows/ci.yml) | Backend path changes, pushes to `main`, pull requests to `main` | Backend quality, tests, API drift, security, container scan |
| [`ci-frontend.yml`](../../.github/workflows/ci-frontend.yml) | Frontend path changes, pushes to `main`, pull requests to `main` | Frontend lint, typecheck, tests, build, Lighthouse |
| [`docs.yml`](../../.github/workflows/docs.yml) | Docs/infrastructure/README changes | Link, ADR index, and freshness checks |
| [`supply-chain.yml`](../../.github/workflows/supply-chain.yml) | Lockfile/manifest changes, pull requests, daily schedule | Dependency audit, SBOM, OSV, secrets scan |
| [`deploy.yml`](../../.github/workflows/deploy.yml) | Pushes to `main` | Build GHCR image, staging deploy, production approval/deploy |

All workflows use least-privilege `contents: read` where they do not need to publish artifacts or deploy.

## Backend CI

`ci.yml` uses Python 3.12 and `uv sync --frozen --group dev`.

Jobs:

1. `lint`: `ruff check src/ tests/` and `ruff format --check src/ tests/`.
2. `type-check`: `mypy src/`.
3. `security`: Bandit, Semgrep, Gitleaks, and pip-audit.
4. `unit-tests`: PostgreSQL 16 and Redis 7 services, unit tests, coverage gate at 80%.
5. `integration-tests`: PostgreSQL/Redis services and real integration tests.
6. `contract-tests`: API and OpenAPI contract tests.
7. `openapi-diff`: regenerates `docs/09-api/openapi.yaml` and fails on drift.
8. `system-tests`: full decision-cycle tests after unit and integration jobs.
9. `container-scan`: backend image build and Trivy scan for `CRITICAL,HIGH` findings.

Backend service credentials are test-only values:

```text
DATABASE_URL=postgresql+asyncpg://lumine:lumine@localhost:5432/lumine_test
REDIS_URL=redis://localhost:6379/0
```

These values must never be reused for production.

## Frontend CI

`ci-frontend.yml` uses Node.js 22 and `npm ci` against the committed lockfile.

Jobs:

- `guard`: skips cleanly only when `frontend/package.json` does not exist.
- `lint`: frontend lint command.
- `typecheck`: TypeScript check.
- `test`: Vitest suite.
- `build`: Vite production build and artifact upload.
- `lighthouse`: downloads the build artifact and runs the configured Lighthouse CI command.

## Documentation and Supply Chain

`docs.yml` runs:

- Lychee link checking for root docs, `docs/**/*.md`, and infrastructure docs.
- ADR index validation.
- Documentation freshness as a warning-only check.

`supply-chain.yml` runs:

- `pip-audit` against backend dependencies.
- CycloneDX SBOM generation and artifact upload.
- OSV scanning for Python and frontend lockfiles.
- Gitleaks over repository history.

Supply-chain warnings are currently non-blocking where the workflow explicitly sets `continue-on-error` or `|| true`; this is deliberate baseline policy and must be tightened before production certification.

## Deployment

`deploy.yml` builds the backend image and publishes it to GHCR. The staging job connects to the VPS over SSH, pulls the image, runs Compose with `--wait`, checks health, audits Caddy/UFW/Docker configuration, and runs an SSE smoke test. Production deployment is protected by the GitHub `production` environment approval gate.

Required repository or environment configuration:

- `GITHUB_TOKEN` for GHCR publication and action integrations.
- `STAGING_HOST`, `STAGING_USER`, and `STAGING_SSH_KEY` for staging.
- `PRODUCTION_HOST`, `PRODUCTION_USER`, and `PRODUCTION_SSH_KEY` for production.
- GitHub `staging` and `production` environments with reviewers and deployment secrets.
- VPS checkout, Docker Compose, Caddy, UFW, and application secret provisioning.

The exact secret names and remote commands must stay aligned with [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) and the infrastructure runbooks.

## Local Parity

Run the same blocking gates locally:

```bash
make lint
make typecheck
make test
make coverage
make security
make verify-chain
```

For integration tests, start Docker Desktop first:

```bash
make docker-up
make test-integration
make docker-down
```

For migration validation, configure a local PostgreSQL role/database matching `DATABASE_URL` and run:

```bash
make migrate
cd backend && uv run alembic check
```

## Failure Policy

- Lint, typecheck, tests, OpenAPI drift, and blocking security findings fail CI.
- Integration and system tests must run against disposable service instances.
- Deployment does not proceed past staging health checks.
- Production requires an explicit environment approval.
- A skipped job caused by path filters is different from a passed quality gate; branch protection must require the relevant workflow checks for the changed surface.
- Any environment-blocked local gate must be recorded in the sprint evidence package rather than replaced with fabricated output.

## Current Audit Note

The latest local audit passed unit/contract tests, coverage, Ruff, and mypy. Docker-backed integration tests and local Alembic checks were environment-blocked. Full WORM anchor reconciliation remains open. See [`docs/15-implementation/sprint-evidence/sprint-7-audit-hardening.md`](../15-implementation/sprint-evidence/sprint-7-audit-hardening.md).
