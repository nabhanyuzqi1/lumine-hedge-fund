# Build & Deploy Pipeline

## Overview

Delivery architecture for frontend (Vercel) and backend (GitHub Actions +
GHCR + SSH deploy), per D11-3. Quality gates executed inside the pipeline
are owned by Phase 13; this document fixes the delivery mechanics only.

## Frontend pipeline (Vercel Git integration)

- Push to the repository triggers Vercel build (`vite build`, Phase 10
  D10-1) and deploy to the production domain.
- Preview deployments exist for review, but the Caddy CORS allowlist
  contains only the production origin (D11-1) — previews cannot reach the
  API by design.
- Frontend environment (API base URL) is configured via Vercel project env
  vars; no secrets exist in the frontend bundle (HMAC key/secret are entered
  by the operator in the settings screen and held locally, per Phase 10).

## Backend pipeline (GitHub Actions)

```
push/merge → main
  │
  ├─ job: test
  │     lint + unit tests — blocking gate (gate content = Phase 13)
  │
  ├─ job: build
  │     docker build per service → push to GHCR
  │     tags: <git-sha> (immutable) + latest (pointer)
  │
  ├─ job: deploy
  │     SSH to VPS (dedicated non-root deploy key):
  │       1. sops -d secrets.env → /srv/lumine/.env   (decrypted on-target,
  │          never stored on the runner)
  │       2. docker compose pull
  │       3. docker compose run --rm migrate       (DB migration =
  │          explicit step; failure aborts deploy)
  │       4. docker compose up -d --remove-orphans
  │
  └─ job: verify
        healthcheck endpoint + SSE smoke check
        failure → alert to operator (see observability.md)
```

## Binding rules

1. **Immutable images.** Every build is tagged with the git SHA; `latest`
   is a moving pointer only. Rollback = compose pinned to a previous SHA.
2. **Migrations are forward-only (expand–contract).** A failed migration
   aborts the deploy before containers are replaced. Rollback never
   auto-reverses migrations.
3. **Deploy gating.** Deploys happen only from `main` (branch protection;
   branch/review policy details = Phase 14). No manual production deploys
   outside the pipeline except documented DR (`backup-dr.md`).
4. **Trade-safe restarts.** Rolling per-service restarts via compose are
   safe by construction: open orders always carry broker-side SL/TP
   (Phase 1), trade-core resumes from PostgreSQL, and SSE clients reconnect
   automatically with `Last-Event-ID` (Phase 9 sse-api.md). Brief
   per-service downtime during restart is accepted.
5. **Failed deploy ≠ broken system.** If `verify` fails, compose remains on
   the last good state and the operator is alerted; nothing silently
   half-deploys.
6. **Secrets flow.** The age key exists only as a GitHub Actions secret;
   `.env` plaintext exists only on the VPS filesystem. No secret passes
   through logs, image layers, or the runner workspace.

## What this document does NOT define

- Concrete workflow YAML, Dockerfiles, compose files (Phase 14+).
- Test gate content and thresholds (Phase 13).
- Branch protection and review policy (Phase 14).

## Phase boundary

Delivery mechanics are fixed here. Manifests and CI code belong to
Phase 14+.
