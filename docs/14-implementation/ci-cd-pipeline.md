# CI/CD Pipeline

## Overview

Three GitHub Actions workflows: backend CI (`ci.yml`), frontend CI
(`ci-frontend.yml`), and deploy (`deploy.yml`). Backend and frontend
pipelines run in parallel on every push. Deploy pipeline runs on push
to main with a manual approval gate for production.

## Pipeline architecture

```
GitHub Actions
├── ci.yml (backend)              ── every push to any branch ──
│   ├── lint (ruff)
│   ├── type-check (mypy)
│   ├── unit tests (pytest)
│   ├── integration tests (pytest + testcontainers)
│   ├── contract tests (pytest + httpx + pytest-asyncio)
│   ├── system tests (pytest + Docker Compose, mock LLM/MT5)
│   ├── security scans (bandit, semgrep, gitleaks, pip-audit)
│   └── container build + scan (docker build + trivy)
│
├── ci-frontend.yml               ── every push to any branch ──
│   ├── lint (biome)
│   ├── type-check (tsc --noEmit)
│   ├── unit tests (vitest)
│   └── build (vite build)
│
└── deploy.yml                    ── on push to main ──
    ├── build-and-push (Docker build → GHCR)
    ├── deploy-staging (SSH → VPS staging)
    │   ├── docker compose pull && up -d --wait
    │   ├── healthcheck verify
    │   ├── config audit (Caddy, UFW, Docker)
    │   └── SSE smoke test (curl)
    └── deploy-production (manual approval → SSH → VPS production)
        ├── docker compose pull && up -d --wait
        └── healthcheck verify
```

## Backend CI (`ci.yml`)

### Triggers

```yaml
on:
  push:
    paths:
      - 'backend/**'
      - '.github/workflows/ci.yml'
  pull_request:
    paths:
      - 'backend/**'
      - '.github/workflows/ci.yml'
```

### Jobs

#### lint

```yaml
lint:
  name: "Lint (ruff)"
  runs-on: ubuntu-latest
  timeout-minutes: 2
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev
    - run: uv run ruff check src/ tests/
    - run: uv run ruff format --check src/ tests/
```

#### type-check

```yaml
type-check:
  name: "Type check (mypy)"
  runs-on: ubuntu-latest
  timeout-minutes: 2
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev
    - run: uv run mypy src/ --strict
```

#### unit-tests

```yaml
unit-tests:
  name: "Unit tests (pytest)"
  needs: [lint, type-check]
  runs-on: ubuntu-latest
  timeout-minutes: 3
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev
    - run: uv run pytest tests/unit/ -v --cov=src/ --cov-report=term --cov-report=xml
    - uses: actions/upload-artifact@v4
      with:
        name: coverage-report
        path: coverage.xml
```

#### integration-tests

```yaml
integration-tests:
  name: "Integration tests"
  needs: [lint, type-check]
  runs-on: ubuntu-latest
  timeout-minutes: 5
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev --group test
    - run: uv run pytest tests/integration/ -v
```

#### contract-tests

```yaml
contract-tests:
  name: "Contract tests"
  needs: [lint, type-check]
  runs-on: ubuntu-latest
  timeout-minutes: 5
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev --group test
    - run: uv run pytest tests/contract/ -v
```

#### system-tests

```yaml
system-tests:
  name: "System tests"
  needs: [unit-tests, integration-tests]
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev --group test
    - run: docker compose -f backend/docker-compose.yml up -d --wait
    - run: uv run pytest tests/system/ -v
    - run: docker compose -f backend/docker-compose.yml down --volumes
      if: always()
```

#### security

```yaml
security:
  name: "Security scans"
  needs: [lint]
  runs-on: ubuntu-latest
  timeout-minutes: 5
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0  # Gitleaks needs full history
    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - run: uv sync --frozen --group dev

    # SAST — Python
    - run: uv run bandit -r src/ -ll

    # SAST — multi-language (Semgrep OWASP Top 10)
    - uses: semgrep/semgrep-action@v1
      with:
        config: p/default
      # Blocking per D13-3 — SAST is a required quality gate

    # Secret scanning
    - uses: gitleaks/gitleaks-action@v2

    # Dependency audit
    - run: uv pip audit
```

#### container-scan

```yaml
container-scan:
  name: "Container scan (Trivy)"
  runs-on: ubuntu-latest
  timeout-minutes: 5
  steps:
    - uses: actions/checkout@v4
    - run: docker build -t lumine:${{ github.sha }} backend/
    - uses: aquasecurity/trivy-action@master
      with:
        image-ref: lumine:${{ github.sha }}
        format: sarif
        output: trivy.sarif
        severity: CRITICAL,HIGH
        exit-code: 1
```

### Parallelism strategy

```
lint ───────────────────┬── unit-tests ──┬── system-tests ──┐
type-check ─────────────┤                │                  ├── (done)
lint ── security ───────┘                │                  │
                        integration-tests ┘                  │
                        contract-tests ────┘                 │
                                                             │
                        container-scan ──────────────────────┘

Total wall-clock:
  ≈ max(lint+type-check, lint+security) + max(unit, integration, contract) + max(system, container)
  ≈ 30s + 2m + 5m
  ≈ 7m 30s (under D13-3 budget of < 10m for blocking gates)
```

### Gate enforcement

Per D13-3:

| Job | Severity to block | Type |
|-----|-------------------|------|
| lint | Any error | Blocking |
| type-check | Any error | Blocking |
| unit-tests | Any failure | Blocking |
| integration-tests | Any failure | Blocking |
| contract-tests | Any failure | Blocking |
| system-tests | Any failure | Blocking |
| bandit | High | Blocking |
| semgrep | Error | Blocking |
| gitleaks | Any finding | Blocking |
| pip-audit | Critical, High | Blocking |
| trivy | Critical, High | Blocking |

## Frontend CI (`ci-frontend.yml`)

### Triggers

```yaml
on:
  push:
    paths:
      - 'frontend/**'
      - '.github/workflows/ci-frontend.yml'
  pull_request:
    paths:
      - 'frontend/**'
      - '.github/workflows/ci-frontend.yml'
```

### Jobs

```yaml
jobs:
  lint:
    name: "Lint (biome)"
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: cd frontend && pnpm install --frozen-lockfile
      - run: cd frontend && pnpm biome ci .

  type-check:
    name: "Type check (tsc)"
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: cd frontend && pnpm install --frozen-lockfile
      - run: cd frontend && pnpm tsc --noEmit

  test:
    name: "Unit tests (vitest)"
    needs: [lint, type-check]
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: cd frontend && pnpm install --frozen-lockfile
      - run: cd frontend && pnpm vitest run --coverage

  build:
    name: "Build (vite)"
    needs: [test]
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: cd frontend && pnpm install --frozen-lockfile
      - run: cd frontend && pnpm vite build
```

### Gate enforcement

| Job | Severity to block | Type |
|-----|-------------------|------|
| lint | Any error | Blocking |
| type-check | Any error | Blocking |
| test | Any failure | Blocking |
| build | Any failure | Blocking |

## Deploy pipeline (`deploy.yml`)

### Triggers

```yaml
on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - '.github/workflows/deploy.yml'
```

### Jobs

#### build-and-push

```yaml
build-and-push:
  name: "Build and push Docker image"
  runs-on: ubuntu-latest
  outputs:
    image_tag: ${{ steps.meta.outputs.tags }}
  steps:
    - uses: actions/checkout@v4
    - uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - id: meta
      uses: docker/metadata-action@v5
      with:
        images: ghcr.io/${{ github.repository }}/lumine
        tags: |
          type=sha,format=long
          type=ref,event=branch
    - uses: docker/build-push-action@v6
      with:
        context: backend/
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```

#### deploy-staging

```yaml
deploy-staging:
  name: "Deploy to staging"
  needs: [build-and-push]
  runs-on: ubuntu-latest
  environment:
    name: staging
    url: https://staging.lumine.internal
  steps:
    - uses: actions/checkout@v4
    - uses: webfactory/ssh-agent@v0.9
      with:
        ssh-private-key: ${{ secrets.SSH_DEPLOY_KEY }}
    - name: Deploy
      run: |
        ssh -o StrictHostKeyChecking=accept-new ${{ vars.VPS_HOST }} << 'DEPLOY'
          set -e
          cd /srv/lumine-staging

          # Pull images (SHA-pinned by compose file)
          docker compose pull

          # Rolling update
          docker compose up -d --wait

          # Healthcheck
          docker compose exec -T trade-core python -c "
          import httpx; r = httpx.get('http://localhost:8000/health');
          assert r.status_code == 200, f'Healthcheck failed: {r.status_code}'
          " || exit 1

          echo "Staging deploy complete."
        DEPLOY
    - name: SSE smoke test
      run: |
        curl -N -sS \
          -H "Authorization: ${{ secrets.STAGING_API_KEY }}" \
          https://staging.lumine.internal/api/v1/streams/market_data \
          --max-time 10 || true
    - name: Config audit
      run: |
        ssh -o StrictHostKeyChecking=accept-new ${{ vars.VPS_HOST }} << 'AUDIT'
          # Caddy config syntax
          caddy validate --config /srv/lumine-staging/Caddyfile || exit 1

          # Docker daemon iptables
          docker info --format '{{.DockerRootDir}}' | grep -q . || exit 1

          echo "Config audit passed."
        AUDIT
```

#### deploy-production

```yaml
deploy-production:
  name: "Deploy to production"
  needs: [deploy-staging]
  runs-on: ubuntu-latest
  environment:
    name: production
    url: https://lumine.vercel.app
  steps:
    - uses: actions/checkout@v4
    - uses: webfactory/ssh-agent@v0.9
      with:
        ssh-private-key: ${{ secrets.SSH_DEPLOY_KEY }}
    - name: Deploy
      run: |
        ssh -o StrictHostKeyChecking=accept-new ${{ vars.VPS_HOST }} << 'DEPLOY'
          set -e
          cd /srv/lumine-production
          docker compose pull
          docker compose up -d --wait
          docker compose exec -T trade-core python -c "
          import httpx; r = httpx.get('http://localhost:8000/health');
          assert r.status_code == 200, f'Healthcheck failed: {r.status_code}'
          " || exit 1
          echo "Production deploy complete."
        DEPLOY
```

The production deployment requires **manual approval** in the GitHub
Actions UI. The `environment: production` block with no auto-approval
rule means the operator must click "Review deployments" → "Approve"
before the job runs.

## GitHub Environments

### `staging` environment

| Setting | Value |
|---------|-------|
| Deployment target | `https://staging.lumine.internal` |
| Auto-approve | Yes (no manual gate for staging) |
| Required reviewers | None |

### `production` environment

| Setting | Value |
|---------|-------|
| Deployment target | `https://lumine.vercel.app` |
| Auto-approve | No — manual approval required |
| Required reviewers | Operator (repository admin) |
| Wait timer | None |

## Secrets & Variables

### GitHub Actions secrets

| Secret | Scope | Purpose |
|--------|-------|---------|
| `SSH_DEPLOY_KEY` | Repository | ed25519 private key, scoped to `/srv/lumine/` via `command=` restriction (D12-2) |
| `GITHUB_TOKEN` | Automatic | Docker push to GHCR (auto-provided by GitHub) |
| `STAGING_API_KEY` | Environment (staging) | HMAC key for SSE smoke test |
| `AGE_PRIVATE_KEY` | Environment (staging, production) | SOPS decrypt for `secrets.env` (D11-6) |

### GitHub Actions variables

| Variable | Scope | Purpose |
|----------|-------|---------|
| `VPS_HOST` | Repository | VPS IP address or hostname |

## Frontend deployment (Vercel)

Frontend deployment is handled by Vercel Git integration, not the
GitHub Actions deploy pipeline:

- **Production:** Auto-deploy on push to `main` (frontend/ changes).
- **Preview:** Auto-deploy on PR branches.
- **CORS:** Vercel production origin is CORS-allowlisted in Caddy
  (D11-1). Preview deployments are not allowlisted.

## Rollback procedure

```bash
# 1. Identify the last known-good SHA
git log --oneline -5

# 2. Revert the deploy to the previous image
ssh $VPS_HOST "cd /srv/lumine-production && \
  docker compose pull && \
  docker compose up -d --wait"

# 3. Verify health
ssh $VPS_HOST "docker compose -f /srv/lumine-production/docker-compose.yml exec -T trade-core \
  python -c 'import httpx; print(httpx.get(\"http://localhost:8000/health\").json())'"

# 4. If the rollback is to a specific commit, checkout the tag/SHA
# and re-run the deploy workflow
```

Since images are SHA-pinned in `docker-compose.prod.yml`, rolling back
is a matter of reverting the compose file to the previous SHA and
re-running the deploy workflow.

## What this document does NOT define

- Concrete CI YAML files (Phase 15 — the workflow files themselves).
- `docker-compose.yml` and `docker-compose.prod.yml` content (Phase 15).
- Caddyfile content (Phase 15).
- Vercel project configuration (Phase 15).
- Rate limit and retry configuration for CI jobs (Phase 15).

## Phase boundary

CI/CD pipeline architecture, job dependencies, parallelism strategy,
gate enforcement, and deploy workflow are fixed here. Workflow YAML
files and deployment configuration are created in Phase 15 Sprint 1.