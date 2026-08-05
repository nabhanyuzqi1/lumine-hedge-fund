# Package Management

## Overview

Dependency management strategy for both Python and TypeScript workspaces.
Lockfiles committed, `--frozen` in CI, Dependabot for automated updates,
SHA-pinned Docker base images.

## Python: `uv`

### Why `uv`

- Single Rust binary replacing pip, venv, pip-tools, and pipx.
- PubGrub-based resolver — faster and more deterministic than pip's
  backtracking resolver.
- `uv.lock` — cross-platform lockfile with content hash verification,
  analogous to `Cargo.lock` or `pnpm-lock.yaml`.
- Global package cache — repeated installs in CI are near-instant.
- Built-in `uv pip audit` for vulnerability scanning.

### Workflow

```bash
# Add a production dependency
uv add fastapi
# → Updates pyproject.toml + uv.lock

# Add a dev dependency
uv add --group dev pytest ruff mypy

# Add a test dependency
uv add --group test testcontainers httpx pytest-asyncio

# Install from lockfile (CI, fresh clone)
uv sync --frozen
# → Exact versions, hash-verified, no network resolution

# Install with dev + test dependencies
uv sync --frozen --group dev --group test

# Update all dependencies
uv lock --upgrade
# → New lockfile, review diff, commit

# Audit for vulnerabilities
uv pip audit
```

### Dependency groups

```toml
# backend/pyproject.toml

[project]
name = "lumine"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "redis[hiredis]>=5.0",
    "autogen-agentchat>=0.5",
    "autogen-ext[openai]>=0.5",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
    "httpx>=0.28",
    "python-jose[cryptography]>=3.3",
    "jsonschema>=4.0",
    "alembic>=1.14",
    "psycopg2-binary>=2.9",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=6.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.9",
    "mypy>=1.14",
    "pre-commit>=4.0",
]

test = [
    "testcontainers>=4.0",
    "httpx>=0.28",
]
```

### CI verification

```yaml
# ci.yml
- name: Verify Python lockfile integrity
  run: |
    uv sync --frozen --group dev --group test
    uv pip audit
```

### Policy

| Policy | Detail |
|--------|--------|
| Lockfile committed | `uv.lock` in version control |
| `--frozen` in CI | Detects lockfile drift — developer forgot to commit |
| Lower-bound pins | `>=` in `pyproject.toml`, exact in `uv.lock` |
| Weekly Dependabot | Grouped PR for all Python dependencies |
| No transitive overrides | Trust resolver; override only for CVE with no upstream fix |

## TypeScript: `pnpm`

### Why `pnpm`

- Content-addressable store — one copy of each package version on disk,
  hard-linked into `node_modules`.
- Strict by default — packages can only import declared dependencies
  (no phantom dependencies from hoisting).
- `pnpm-lock.yaml` — deterministic, cross-platform lockfile.
- Faster than npm for installs and updates.
- Built-in `pnpm audit` for vulnerability scanning.

### Workflow

```bash
# Add a production dependency
pnpm add react react-dom

# Add a dev dependency
pnpm add -D vitest @testing-library/react

# Install from lockfile (CI)
pnpm install --frozen-lockfile

# Update all dependencies
pnpm update --latest
# → New lockfile, review diff, commit

# Audit for vulnerabilities
pnpm audit
```

### `package.json` structure

```json
{
  "name": "lumine-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "biome ci .",
    "format": "biome format --write .",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^19.0",
    "react-dom": "^19.0",
    "react-router-dom": "^7.0",
    "@tanstack/react-query": "^5.0",
    "zustand": "^5.0",
    "lightweight-charts": "^5.0",
    "echarts": "^5.0",
    "echarts-for-react": "^3.0"
  },
  "devDependencies": {
    "@biomejs/biome": "^1.9",
    "typescript": "^5.7",
    "vitest": "^3.0",
    "@testing-library/react": "^16.0",
    "@testing-library/jest-dom": "^6.0",
    "jsdom": "^26.0",
    "vite": "^6.0",
    "@vitejs/plugin-react": "^4.0"
  }
}
```

### CI verification

```yaml
# ci-frontend.yml
- name: Verify frontend lockfile integrity
  run: |
    cd frontend
    pnpm install --frozen-lockfile
    pnpm audit
```

### Policy

| Policy | Detail |
|--------|--------|
| Lockfile committed | `pnpm-lock.yaml` in version control |
| `--frozen-lockfile` in CI | Detects lockfile drift |
| Caret ranges | `^` in `package.json`, exact in lockfile |
| Weekly Dependabot | Grouped PR for all frontend dependencies |
| `node_modules` gitignored | Never committed |

## Docker images

### Base images

| Image | Purpose | Pin method |
|-------|---------|------------|
| `python:3.12-slim` | Backend runtime | SHA256 digest in `FROM` |
| `postgres:16-alpine` | Database | SHA256 digest in compose |
| `redis:7-alpine` | Cache + queue | SHA256 digest in compose |
| `caddy:2-alpine` | Reverse proxy | SHA256 digest in compose |

```dockerfile
# SHA-pinned base image (Phase 12 D12-5)
FROM python:3.12-slim@sha256:abc123... AS builder
```

### Policy

| Policy | Detail |
|--------|--------|
| SHA-pinned | Prevents tag mutation attacks (D12-5) |
| No `latest` tag | In production compose files |
| Weekly Dependabot | Auto-PR for Docker base image updates |
| Trivy scan in CI | Critical/high CVEs block merge |

## Dependabot configuration

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Jakarta"
    groups:
      python-deps:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
    open-pull-requests-limit: 3

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Jakarta"
    groups:
      frontend-deps:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
    open-pull-requests-limit: 3

  - package-ecosystem: "docker"
    directory: "/backend"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Jakarta"
    open-pull-requests-limit: 2

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Jakarta"
    open-pull-requests-limit: 2
```

### Dependabot policy

| Policy | Detail |
|--------|--------|
| Weekly schedule | Monday morning — operator reviews before the week's work |
| Grouped PRs | All minor/patch updates in one PR per ecosystem |
| Limit 3 open PRs | Prevents PR flood |
| Major updates | Not auto-PRed — manual upgrade decision |
| Security updates | Immediate, not grouped, not limited |

## Dependency update workflow

```
1. Dependabot opens PR (Monday)
2. CI runs on the PR — all tests must pass
3. Operator reviews changelog diff
4. If tests pass + no breaking changes → merge
5. If breaking changes → operator creates manual upgrade task
```

## What this document does NOT define

- Concrete dependency versions in `uv.lock` or `pnpm-lock.yaml` (Phase 15).
- `pyproject.toml` lower-bound pins for every dependency (Phase 15).
- Dependabot ignore rules for specific packages (Phase 15 — configured
  as needed).

## Phase boundary

Package managers, lockfile policy, Dependabot configuration, and Docker
image pinning strategy are fixed here. Lockfiles and concrete versions
are created in Phase 15 Sprint 1.