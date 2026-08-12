# Phase 11 — Infrastructure

## Overview

Phase 11 defines runtime delivery: hosting topology, build/deploy pipeline,
observability, backup/DR, and secrets injection for the Lumine platform. It
operationalizes the Phase 1 `deployment-topology.md` contract without
changing it, and serves the Phase 9 API contracts (REST + SSE) and the
Phase 10 frontend (React SPA).

Phase 11 does NOT define: security policy details (Phase 12), test strategy
(Phase 13), implementation code/manifests (Phase 14+), or any service
contract (Phases 1–9).

## Documents

| Document | Purpose |
|----------|---------|
| `decisions.md` | Locked decisions D11-1 .. D11-6 with rationale |
| `topology.md` | Runtime layout: containers, networks, egress, sizing |
| `build-deploy.md` | CI/CD pipeline: GitHub Actions + GHCR + Vercel |
| `observability.md` | Metrics, logs, traces, dashboards, alert rules |
| `backup-dr.md` | Backup schedule, restore verification, DR runbook, secrets injection |

Runtime deployment specs (ground truth of what runs on the VPS today):

| Spec | Purpose |
|------|---------|
| `../01-architecture/` + `backend/docker-compose.prod.yml` | Lumine stack: postgres, redis, api, mt5, headroom, 9router (root `/opt/lumine/backend/`) |
| `../11-infrastructure/` + `infrastructure/control-plane/` | Control plane: caddy, authelia, homepage, uptime-kuma, landing, dozzle (root `/srv/control-plane/`) |
| `../11-infrastructure/` + `infrastructure/hermes/` | Hermes agent (upstream NousResearch clone, root `/opt/hermes/hermes-agent/`) |

## Decisions at a glance

| # | Decision | Choice |
|---|----------|--------|
| D11-1 | Hosting V1 | Frontend Vercel (production domain) + backend Docker Compose on single VPS; CORS allowlists Vercel production origin |
| D11-2 | Reverse proxy & TLS | Caddy (automatic Let's Encrypt TLS) |
| D11-3 | CI/CD | GitHub Actions → GHCR → SSH deploy (backend); Vercel Git integration (frontend) |
| D11-4 | Observability | Prometheus + Grafana + Loki + Tempo/OTel collector, all self-hosted |
| D11-5 | Backup/DR | `pg_dump` daily + WAL archiving + Redis AOF → rclone (encrypted) to B2/S3 |
| D11-6 | Secrets injection | SOPS + age (`secrets.env` in repo), env-var injection at deploy time |

## What this phase does NOT define

- Security policy: SSH hardening, access audit, key rotation policy,
  network ACL policy (Phase 12).
- Quality gates and test levels executed inside CI (Phase 13).
- Concrete compose files, Dockerfiles, Terraform, CI YAML (Phase 14+).
- Rate-limit values, payload schemas, API behavior (Phases 4/7/8/9).
- Frontend bundle internals (Phase 10 / 14+).

## Phase boundary

This phase fixes hosting, delivery, observability, backup, and secrets
injection architecture. Concrete manifests and code belong to Phase 14+.
