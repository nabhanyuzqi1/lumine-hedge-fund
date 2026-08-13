# Phase Mapping — Master Prompt vs Repository

## Purpose

The master prompt defines 16 phases (`PHASE 0` through `PHASE 15`). Each phase
maps 1:1 to a repository folder under `docs/`. This document is the canonical
mapping and the single place where the phase→folder contract is stated.

If a phase folder is renamed, this file is updated in the same commit.

## Mapping Table

| Master Prompt Phase | Repo Folder | Status | Notes |
|---------------------|-------------|--------|-------|
| Phase 0 — Vision & Product Strategy | `docs/00-vision/` | Done | Vision, mission, goals, personas, scope |
| Phase 1 — System Architecture | `docs/01-architecture/` | Done | High-level architecture, data flow, critical path |
| Phase 2 — Department Design | `docs/02-departments/` | Done | Hedge fund department structure, agent hierarchy |
| Phase 3 — Agent Architecture + Data Contracts | `docs/03-agents-and-contracts/` | Done | Agent registry, agent specs, lineage enforcement, stream payloads, positions/fills, time-series, data lifecycle |
| Phase 4 — Communication Architecture + AI/AutoGen Strategy | `docs/04-communication-and-prompts/` | Done | Agent messaging, JSON schemas, prompt versioning, proposal schema, locked decisions |
| Phase 5 — Data Architecture | `docs/05-data/` | Done | Physical ERD, PostgreSQL/Redis, migrations, indexing, partitioning, retention, archival, backup, DR, query-performance design |
| Phase 6 — AI & LLM Strategy | `docs/06-ai/` | Done | Model routing, LLM gateway, cost control, memory policy, model registry |
| Phase 7 — AutoGen Architecture | `docs/07-autogen/` | Done | Orchestration, workflow lifecycle, recovery, termination, checkpoint, replay, observability |
| Phase 8 — Trading Architecture | `docs/08-trading/` | Done | MT5 integration, execution engine, risk engine, order lifecycle, reconciliation |
| Phase 9 — API Design | `docs/09-api/` | Done | FastAPI, REST, SSE, auth, error contracts, API versioning |
| Phase 10 — Institutional UI/UX Design System & Frontend Architecture | `docs/10-frontend/` | Done | Institutional experience, information architecture, tokens, components, financial charts, realtime client state, motion, accessibility, performance budgets, wireframes |
| Phase 11 — Infrastructure | `docs/11-infrastructure/` | Done | Docker, VPS, CI/CD, monitoring, backup/DR, observability schema, deployment topology |
| Phase 12 — Security | `docs/12-security/` | Done | Threat model, encryption, SSH, firewall, supply chain, audit log, secrets management |
| Phase 13 — Testing Strategy | `docs/13-testing/` | Done | 7 test levels, environments, quality gates, backtest, paper trading, security, AI testing |
| Phase 14 — Implementation Planning | `docs/14-implementation/` | Done | Repository structure, sprint plan, package management, coding standards |
| Phase 15 — Implementation | `docs/15-implementation/` + `backend/` + `frontend/` | In Progress | Sprint 1 foundation partial; Sprint 2 pending |

## Phase Boundary Clarifications

- **Phase 3 vs Phase 4:** Phase 3 owns *what an agent is* (registry, spec, I/O contracts, lineage enforcement). Phase 4 owns *how agents talk* (message envelopes, prompt storage, proposal schema, AutoGen orchestration entry). Orchestration internals live in Phase 7 (`docs/07-autogen/orchestration.md`).
- **Phase 3 vs Phase 5:** Phase 3 owns logical data contracts (schemas, stream payloads). Phase 5 owns physical persistence (tables, indexes, partitioning, retention).
- **Phase 5 owns physical persistence.** Database requirements must not be copied into Phase 10.
- **Phase 9 owns backend API and streaming transport contracts.** Phase 10 consumes those contracts; it does not redefine them.
- **Phase 10 owns user experience and frontend architecture** — design system, information architecture, tokens, components, charts, realtime client state, accessibility, performance budgets, wireframes.
- **Phase 11 owns runtime delivery** — hosting, containers, CI/CD, observability infrastructure, deployment topology.
- **Phase 13 owns cross-system test strategy** — test levels, environments, quality gates, acceptance policy. Phase 10 still defines component-specific UX budgets.
- **Phase 14 owns implementation sequencing** — final package selection, repo structure, work breakdown, coding standards, delivery order.

## Additional Tiers (Not Phases)

These cross-cut the phases and live outside the numbered phase sequence:

| Tier | Folder | Purpose |
|------|--------|---------|
| Architecture Decision Records | `docs/adr/` | All reversible+irreversible decisions, indexed in `INDEX.md` |
| Governance & Operations | `docs/90-governance-and-operations/` | Glossary, anti-scope, onboarding, standards, runbooks, FinOps, AI governance, change management, FAQ |
| Diagram Sources | `docs/_diagrams/` | Mermaid sources rendered in phase docs |
| CI Scripts | `docs/_ci/` | Docs linting, ADR index check, freshness check |
| Knowledge Map | `docs/INDEX.md` | Topic × Phase matrix for navigation |

## Rule

Folder names are fixed after Phase 14 approval. Any rename requires:

1. An ADR recording the rename and rationale.
2. A single commit renaming the folder and updating every reference.
3. An update to this mapping table in the same commit.

## Current Phase

All ideation phases (0-14) are complete. **Phase 15 — Implementation** is in progress.
Sprint 1 (Foundation) is partially complete. Sprint 2 (Data Pipeline) is pending.
See `docs/15-implementation/README.md` for live status and `docs/15-implementation/spec-reconciliation.md` for the spec↔code gap tracker.
\n|| Phase 16 — Production Deployment & Operations | `docs/16-implementation/` | Pending | Deployment, automation, compliance certification |