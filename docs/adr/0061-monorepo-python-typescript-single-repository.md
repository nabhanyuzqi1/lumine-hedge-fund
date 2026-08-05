# ADR-0061 — Monorepo: Python workspace + TypeScript workspace, single repository

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The project has two language workspaces (Python backend, TypeScript/React
frontend) plus shared architecture docs at the root. A single operator needs
the simplest cross-cutting-change workflow. Cross-cutting changes (API
contract + frontend consumer + test) must be capturable in one commit. CI
secrets and deployment should have a single pipeline definition.

## Decision

One repository with two language workspaces: `backend/` (Python) and
`frontend/` (TypeScript/React). Shared code lives in
`backend/src/lumine/shared/` and `frontend/src/lib/`. `docs/` and `.github/`
remain at the repository root. No micro-repo or poly-repo.

## Rationale

- Single source of truth for versioning: one commit captures a cross-cutting
  change (API contract + frontend consumer + test).
- Simplified CI: one pipeline definition, one set of secrets, one deployment
  workflow.
- `docs/` stays at the root — architecture documents are the cross-cutting
  reference for both workspaces.
- Micro-repo rejected: excessive coordination overhead for a single-operator
  project. Cross-cutting changes require multiple PRs across repos.
- Poly-repo with shared libraries rejected: adds dependency management
  complexity (versioning shared packages, publishing to internal registry).
  Premature at V1 scale.

## Consequences

- Positive: one commit captures cross-cutting changes end-to-end.
- Positive: one CI pipeline, one set of secrets.
- Negative: repository size grows with both workspaces (mitigated: both are
  modest at V1).
- Reversibility: split into poly-repo by extracting workspaces with their
  history.

## Cross-references

- Related ADRs: ADR-0062, ADR-0063, ADR-0064
- Implements principle(s): #5
- Affects phases: 14
- Source document: `../14-implementation/decisions.md` (D14-1)
