# ADR-0047 — CI/CD: GitHub Actions + GHCR + SSH deploy; Vercel Git integration

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The backend needs a CI/CD pipeline that builds immutable images, pushes them
to a registry, and deploys to a single static VPS. The frontend uses Vercel
Git integration. The project is single-operator; CI infrastructure overhead
must be minimal.

## Decision

Backend pipeline: GitHub Actions builds one immutable image per service per
SHA, pushes to GHCR, then SSHs to the VPS to `docker compose pull && up -d`.
Frontend: Vercel Git integration auto-deploys on push.

## Rationale

- Zero additional infrastructure — no self-hosted CI runner to maintain.
- GHCR is free for private repos and sits next to the code.
- SSH deploy to a single static VPS is the simplest correct mechanism at this
  scale.
- Docker Hub rejected over pull rate limits.
- Self-hosted CI rejected as an extra stateful service to operate.

## Consequences

- Positive: no CI infrastructure to operate; images are SHA-immutable.
- Positive: frontend deploys are automatic on push.
- Negative: SSH deploy is a single-channel mechanism — no canary or
  blue-green at V1 scale.
- Reversibility: migrate to a different registry or deploy mechanism by
  changing the workflow YAML.

## Cross-references

- Related ADRs: ADR-0045, ADR-0067
- Implements principle(s): #5
- Affects phases: 11, 14
- Source document: `../11-infrastructure/decisions.md` (D11-3)
