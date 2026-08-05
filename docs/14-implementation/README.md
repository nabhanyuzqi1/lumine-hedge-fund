# Phase 14 — Implementation Planning

## Overview

Phase 14 is the bridge between 13 phases of architecture and Phase 15
implementation. It defines how code will be organized, written, reviewed,
built, tested, deployed, and sequenced — without writing a single line
of implementation code.

This phase answers: "We know what to build. How do we start building it?"

## Documents

| Document | Purpose |
|----------|---------|
| `decisions.md` | 7 locked decisions with full rationale |
| `repository-structure.md` | Monorepo layout, module boundaries, naming conventions |
| `coding-standards.md` | Python + TypeScript standards, linting, formatting, type-checking |
| `sprint-plan.md` | 5-sprint breakdown with deliverables, dependencies, and gates |
| `package-management.md` | Dependency tools, lockfiles, audit policy, Dependabot config |
| `ci-cd-pipeline.md` | CI/CD design, stages, gates, deploy workflow, parallelism |

## Decisions at-a-glance

| # | Decision | Summary |
|---|----------|---------|
| D14-1 | Monorepo | Python `backend/` + TypeScript `frontend/`, single repository |
| D14-2 | Package pinning | `uv` + `pnpm`, lockfiles committed, `--frozen` in CI |
| D14-3 | Python standards | `ruff` + `mypy` strict + `pytest` |
| D14-4 | TypeScript standards | `biome` + TypeScript strict + `vitest` |
| D14-5 | 5 sprints, 10 weeks | Foundation → Data Pipeline → Decision Engine → API & Frontend → Hardening |
| D14-6 | Vertical slices | Each sprint delivers a working vertical slice; backend-first, frontend depends on API contracts |
| D14-7 | Trunk-based git | Conventional commits, feature flags, squash merge, PR required for all changes |

## Implementation principles

1. **Phase 14 is the contract.** Sprint 1 starts with Phase 14 as the
   reference — folder structure, standards, and sequence are fixed.
2. **No code before Phase 15.** Phase 14 produces documents only. Zero
   `.py`, `.tsx`, `.yml`, or configuration files are created.
3. **Backward traceability.** Every implementation decision must trace
   to a specific Phase 1-13 decision. If a new decision is needed, it
   is documented as a Phase 14 amendment.
4. **Feature flags for incomplete work.** Code merged to main must not
   break the working system. Incomplete features are gated behind
   `LUMINE_FEATURE_<NAME>` environment variables.
5. **No speculative implementation.** Only build what the sprint plan
   specifies. Future sprints may change approach based on learnings
   from the current sprint.
6. **Sprint review gates.** Each sprint ends with: all tests pass, CI
   green, paper trading (from Sprint 3 onward) shows zero errors, and
   code review is complete.

## What this phase does NOT define

- Actual code, tests, migrations, or configuration files (Phase 15)
- Specific package versions beyond what lockfiles will contain (Phase 15)
- Test data, fixtures, or seed data content (Phase 15)
- Grafana dashboard JSON, Prometheus rules, or Alertmanager config (Phase 15)
- Docker Compose environment variables and secrets (Phase 15, using SOPS from Phase 12)
- Production deployment schedule or go-live date (operator decision)

## Phase boundary

Implementation planning is fixed here. No code is written. Phase 15
(Sprint 1-5) begins only after Phase 14 is approved and all documents
are verified for consistency with Phases 1-13.