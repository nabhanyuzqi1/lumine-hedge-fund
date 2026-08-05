# ADR-0050 — Secrets injection: SOPS + age, env-var injection

- **Status:** Accepted
- **Phase:** 11-infrastructure
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

Secrets must be versioned and auditable in Git without ever being plaintext.
The project is single-operator; a stateful secrets cluster is disproportionate
to V1 needs. Many libraries read env vars only and would need shims for
alternative injection mechanisms.

## Decision

One encrypted `.env.enc` (SOPS + age) in the private repo. CI decrypts at
deploy time and writes `/srv/lumine/.env` over SSH; containers receive values
as environment variables at `compose up`. The age private key lives in a
GitHub Actions secret (deploy) and the operator's password manager (local).

## Rationale

- Secrets are versioned and auditable in Git without ever being plaintext; no
  additional service to run.
- Docker secrets (`/run/secrets`) rejected: marginally safer against `/proc`
  inspection, but many libraries read env vars only and would need shims.
- Self-hosted Vault rejected: a stateful cluster plus operational burden far
  beyond V1 needs.
- Rotation = edit, commit, deploy.
- Access policy details (who may hold the age key, audit) belong to Phase 12.

## Consequences

- Positive: secrets are Git-versioned, auditable, never plaintext at rest in
  repo.
- Positive: rotation is a simple edit-commit-deploy cycle.
- Negative: env-var injection is slightly less secure than file-based secrets
  (mitigated: containers are non-root, no `/proc` access between services).
- Reversibility: migrate to Vault or Docker secrets by changing the injection
  layer.

## Cross-references

- Related ADRs: ADR-0047, ADR-0049
- Implements principle(s): #5
- Affects phases: 11, 12
- Source document: `../11-infrastructure/decisions.md` (D11-6)
