# Supply Chain Security

## Overview

Dependency and artifact security per D12-5. Automated vulnerability
scanning in CI, Dependabot for continuous monitoring, container image
hardening, and artifact integrity via SHA-pinned images.

## Dependency scanning pipeline

```
CI pipeline: security-scan job
  │
  ├─ pip-audit
  │     Scan Python dependencies (requirements.txt / pyproject.toml)
  │     Output: list of known CVEs with severity
  │
  ├─ npm audit
  │     Scan frontend dependencies (package.json / package-lock.json)
  │     Output: list of known CVEs with severity
  │
  ├─ docker scout quickview
  │     Scan built container image for OS and library CVEs
  │     Output: CVE list by layer
  │
  └─ Gate: critical or high severity → BLOCK
        Warning/low → pass with annotation
```

### Gate policy

| Severity | Action |
|----------|--------|
| Critical | Block merge. Must be resolved or suppressed with documented reason. |
| High | Block merge. Must be resolved or suppressed with documented reason. |
| Moderate | Allow merge. Annotation in PR. |
| Low | Allow merge. No annotation. |

Suppression requires a comment in the suppression file explaining:
- Why the vulnerability does not apply to Lumine's usage
- When to re-evaluate
- Who approved the suppression

This prevents "suppress and forget" accumulation.

## Dependabot configuration

### Python (pip)

```yaml
# .github/dependabot.yml (Phase 14+)
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "security"
```

### Docker

```yaml
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "docker"
```

### GitHub Actions

```yaml
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "ci"
```

## Container image hardening

### Base image

`python:3.12-slim` — provides glibc (needed by some quant libraries)
while keeping the image significantly smaller than `python:3.12`.
Alpine deliberately rejected due to musl compatibility issues.

### Dockerfile principles (Phase 14+)

```
# Multi-stage build
FROM python:3.12-slim AS builder
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
# Non-root user
RUN useradd --create-home --shell /bin/bash lumine
USER lumine
COPY --from=builder --chown=lumine:lumine /root/.local /home/lumine/.local
COPY --chown=lumine:lumine src/ /app/
```

- No root user in any container.
- `COPY --chown=lumine:lumine` ensures file ownership.
- Multi-stage build keeps build dependencies out of the runtime image.
- `--no-cache-dir` reduces image size.
- Dev dependencies (pytest, linters) excluded from production image.

### Service-specific users

| Container | User |
|-----------|------|
| lumine-trade-core | `lumine` |
| lumine-mt5-bridge | `lumine` |
| lumine-llm-gateway | `lumine` |
| lumine-research-worker | `lumine` |
| lumine-review-worker | `lumine` |
| lumine-sandbox-worker | `lumine` |
| lumine-scheduler | `lumine` |
| lumine-news-adapter | `lumine` |

All application containers share the same `lumine` user. Infrastructure
containers (Caddy, Prometheus, Grafana, Loki, Tempo, PostgreSQL, Redis)
use their own documented non-root users as defined by their official
images.

## Artifact integrity

### Image tagging

```
# Build output (from D11-3)
ghcr.io/lumine/lumine-trade-core:<git-sha>   # immutable
ghcr.io/lumine/lumine-trade-core:latest      # moving pointer
```

### Production compose

```
# compose.yaml (Phase 14+)
services:
  lumine-trade-core:
    image: ghcr.io/lumine/lumine-trade-core:abc1234  # pinned SHA
```

Production compose files always pin the SHA tag. `latest` is used only
during development. Rollback means changing the SHA tag in compose and
running `docker compose up -d`.

## What this document does NOT define

- Concrete Dependabot YAML, Dockerfiles, CI workflow YAML (Phase 14+).
- SBOM generation (SPDX/CycloneDX) — deferred to V2.
- Container signing (Cosign/Notary) — deferred to V2.
- Private package registry / PyPI mirror — not needed for V1.

## Phase boundary

Supply chain security architecture and policies are fixed here.
Configuration files and CI implementation belong to Phase 14+.