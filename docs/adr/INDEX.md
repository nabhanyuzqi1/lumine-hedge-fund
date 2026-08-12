# Architectural Decision Records — Index

This is the single authoritative registry of architectural decisions for Lumine.
Each ADR has a globally unique ID (`ADR-NNNN`), a status, and a source document.
Phase-level `decisions.md` files are **pointers** to ADRs — they are no longer
the source of truth.

## Status legend

| Status | Meaning |
|--------|---------|
| Proposed | Drafted, not yet ratified |
| Accepted | Ratified, in force |
| Deprecated | Superseded or no longer applicable |
| Superseded | Replaced by a later ADR (link in row) |

## ADR Registry

> Format: `ID | Title | Status | Phase | Source`
> Migration of historical phase decisions (D{phase}-{n}) into the ADR series is
> performed incrementally. The block below is the **seed migration**; new ADRs
> are appended.

| ID | Title | Status | Phase | Source |
|----|-------|--------|-------|--------|
| ADR-0001 | Threat model: realistic V1, not speculative | Accepted | 12 | `docs/12-security/decisions.md` D12-1 |
| ADR-0002 | SSH: 2-key ed25519-only, no password auth | Accepted | 12 | `docs/12-security/decisions.md` D12-2 |
| ADR-0003 | Stateless V1 memory policy | Accepted | 06 | `docs/06-ai/decisions.md` D6-5 |
| ADR-0004 | Static tier model routing + deterministic escalation | Accepted | 06 | `docs/06-ai/decisions.md` D6-1 |
| ADR-0005 | Durable workflow journal is the source of truth | Accepted | 07 | `docs/07-autogen/decisions.md` D7-5 |
| ADR-0006 | Resume only from validated checkpoints via deterministic gates | Accepted | 07 | `docs/07-autogen/decisions.md` D7-3 |
| ADR-0007 | Replay never mutates history | Accepted | 07 | `docs/07-autogen/decisions.md` D7-8 |
| ADR-0008 | Failure taxonomy determines recovery, not per-call judgment | Accepted | 07 | `docs/07-autogen/decisions.md` D7-7 |
| ADR-0009 | One active logical workflow per (book, strategy, symbol) | Accepted | 07 | `docs/07-autogen/decisions.md` D7-2 |
| ADR-0010 | Kill switch: no autonomous restart | Accepted | 07 | `docs/07-autogen/decisions.md` D7-9 |
| ADR-0011 | Malformed decision is worse than no decision (no schema relaxation) | Accepted | 07 | `docs/07-autogen/decisions.md` D7-4 |
| ADR-0012 | Telemetry is a projection of the journal; journal wins on conflict | Accepted | 07 | `docs/07-autogen/decisions.md` D7-10 |
| ADR-0013 | Correlation hierarchy: workflow_run → stage_run → logical_call | Accepted | 07 | `docs/07-autogen/decisions.md` D7-6 |
| ADR-0014 | Lineage blocking ACID gate before dispatch | Accepted | 03 | `docs/03-agents-and-contracts/lineage-schema.md` |
| ADR-0015 | Prompts as repo files with SHA-256 import-time hash | Accepted | 04 | `docs/04-communication-and-prompts/prompt-storage.md` |
| ADR-0016 | LLM risk role is advisory only; sizing multiplier is a deterministic registry lookup | Accepted | 08 | `docs/08-trading/risk-engine-determinism.md` (S1) |
| ADR-0017 | Hash-chained, WORM-anchored audit journal | Accepted | 12 | `docs/12-security/audit-tamper-evidence.md` (S2) |
| ADR-0018 | Prompt injection is an explicit V1 threat; defense-in-depth contract | Accepted | 12 | `docs/12-security/prompt-injection-defense.md` (S3) |
| ADR-0019 | Backtest parity contract: same pins as production | Accepted | 13 | `docs/13-testing/backtest-parity-contract.md` (S7) |
| ADR-0020 | Versioned, point-in-time feature store | Accepted | 03 | `docs/03-agents-and-contracts/feature-store-contract.md` (S11) |
| ADR-0021 | Daily broker reconciliation is a SETTLED gate | Accepted | 08 | `docs/08-trading/reconciliation.md` (S20) |
| ADR-0022 | LLM gateway admission control with priority lanes | Accepted | 06 | `docs/06-ai/gateway-admission-control.md` (S5) |
| ADR-0023 | Lineage partitioning + write-aside safety gate | Accepted | 05 | `docs/05-data/lineage-scale-and-partitioning.md` (S6) |
| ADR-0024 | Multi-broker model: schema-ready, V1 ships one adapter | Accepted | 08 | `docs/08-trading/multi-broker-model.md` (S14) |
| ADR-0025 | Registry supersession model with graded compatibility | Accepted | 03 | `docs/03-agents-and-contracts/registry-supersession-model.md` (S17) |
| ADR-0026 | Comparative replay resource isolation | Accepted | 07 | `docs/07-autogen/comparative-replay-isolation.md` (S18) |
| ADR-0027 | Four-tier memory architecture with governed deferral triggers | Accepted | 06 | `docs/06-ai/memory-architecture.md` (S4) |
| ADR-0028 | Machine-enforced eval gate on prompt promotion | Accepted | 13 | `docs/13-testing/ai-promotion-gates.md` (S8) |
| ADR-0029 | Reasoning traces stored alongside outputs | Accepted | 07 | `docs/07-autogen/reasoning-trace-storage.md` (S9) |
| ADR-0030 | Model risk management (SR 11-7 style) | Accepted | 90 | `docs/90-governance-and-operations/96-ai-governance/model-risk-management.md` (S13) |
| ADR-0031 | Strategy promotion / demotion policy with quantitative gates | Accepted | 90 | `docs/90-governance-and-operations/96-ai-governance/strategy-promotion-policy.md` (S16) |
| ADR-0032 | Confidence calibration gate on escalation | Accepted | 06 | `docs/06-ai/confidence-calibration.md` (S22) |
| ADR-0033 | Agent failure-mode matrix binding | Accepted | 90 | `docs/90-governance-and-operations/94-runbooks/agent-failure-matrix.md` (S10) |
| ADR-0034 | Deterministic regime classifier as first-class concept | Accepted | 03 | `docs/03-agents-and-contracts/regime-model.md` (S12) |
| ADR-0035 | Clock synchronization and temporal-ordering contract | Accepted | 11 | `docs/11-infrastructure/clock-and-time-contract.md` (S13) |
| ADR-0036 | Per-role, per-tier context-window budget with deterministic truncation | Accepted | 06 | `docs/06-ai/context-budget-policy.md` (S15) |
| ADR-0037 | Market calendar, holiday, and economic-event contract | Accepted | 03 | `docs/03-agents-and-contracts/market-calendar-contract.md` (S21) |
| ADR-0038 | Inter-agent message schema versioning | Accepted | 04 | `docs/04-communication-and-prompts/inter-agent-message-versioning.md` (S23) |
| ADR-0039 | Deadline propagation from stage to LLM call | Accepted | 07 | `docs/07-autogen/deadline-propagation.md` (S24) |
| ADR-0040 | TCA and execution-quality reporting | Accepted | 08 | `docs/08-trading/tca-and-execution-quality.md` (S19) |
| ADR-0041 | Inter-engine review preferred for verification | Accepted | 14 | `CLAUDE.md` rule 9 |
| ADR-0042 | No coding before Phase 14 approval | Accepted | 14 | `CLAUDE.md` rule 3 |
| ADR-0043 | Phased development: no skipping, no mixing | Accepted | 14 | `CLAUDE.md` rule 2 |
| ADR-0044 | Prompts and schemas versioned, hashed, auditable | Accepted | 14 | `CLAUDE.md` rule 10 |
| ADR-0045 | Hosting V1: Vercel frontend + VPS backend | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-1 |
| ADR-0046 | Reverse proxy and TLS: Caddy | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-2 |
| ADR-0047 | CI/CD: GitHub Actions + GHCR + SSH deploy; Vercel Git integration | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-3 |
| ADR-0048 | Observability: Prometheus + Grafana + Loki + Tempo, self-hosted | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-4 |
| ADR-0049 | Backup and DR: scheduled dumps to encrypted object storage | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-5 |
| ADR-0050 | Secrets injection: SOPS + age, env-var injection | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-6 |
| ADR-0051 | Encryption: three layers (disk, column, backup) | Accepted | 12 | `docs/12-security/decisions.md` D12-3 |
| ADR-0052 | Firewall: UFW, 3 ports only, Docker bridge | Accepted | 12 | `docs/12-security/decisions.md` D12-4 |
| ADR-0053 | Supply chain: Dependabot + pip-audit + CI gate | Accepted | 12 | `docs/12-security/decisions.md` D12-5 |
| ADR-0054 | Audit: security event log + Loki structured logs | Accepted | 12 | `docs/12-security/decisions.md` D12-6 |
| ADR-0055 | Test levels: 7 levels, no E2E browser test | Accepted | 13 | `docs/13-testing/decisions.md` D13-1 |
| ADR-0056 | Test environments: 3 environments, no dedicated staging server | Accepted | 13 | `docs/13-testing/decisions.md` D13-2 |
| ADR-0057 | Quality gates: 2 tiers (blocking + advisory) | Accepted | 13 | `docs/13-testing/decisions.md` D13-3 |
| ADR-0058 | Backtest and paper-trading: same code path, different injectors | Accepted | 13 | `docs/13-testing/decisions.md` D13-4 |
| ADR-0059 | Security testing: automated CI + manual pentest | Accepted | 13 | `docs/13-testing/decisions.md` D13-5 |
| ADR-0060 | SLO and acceptance: 0.1% error budget, 8 pre-launch gates | Accepted | 13 | `docs/13-testing/decisions.md` D13-6 |
| ADR-0061 | Monorepo: Python workspace + TypeScript workspace, single repository | Accepted | 14 | `docs/14-implementation/decisions.md` D14-1 |
| ADR-0062 | Package pinning: uv (Python) + pnpm (TypeScript), lockfiles committed | Accepted | 14 | `docs/14-implementation/decisions.md` D14-2 |
| ADR-0063 | Python standards: ruff + mypy strict + pytest | Accepted | 14 | `docs/14-implementation/decisions.md` D14-3 |
| ADR-0064 | TypeScript standards: biome + TypeScript strict + vitest | Accepted | 14 | `docs/14-implementation/decisions.md` D14-4 |
| ADR-0065 | 5 sprints, 10 weeks total | Accepted | 14 | `docs/14-implementation/decisions.md` D14-5 |
| ADR-0066 | Vertical slice ordering, backend-first | Accepted | 14 | `docs/14-implementation/decisions.md` D14-6 |
| ADR-0067 | Git: trunk-based, conventional commits, feature flags | Accepted | 14 | `docs/14-implementation/decisions.md` D14-7 |
| ADR-0068 | Orchestration: hand-written deterministic runner, not AutoGen | Accepted | 15 | `docs/15-implementation/deviation-log.md` (2026-08-06, A1) |
| ADR-0069 | Control plane: Caddy + Authelia + Homepage + Uptime Kuma, GUI services behind auth | Accepted | 11 | `docs/11-infrastructure/decisions.md` D11-7 |
| ADR-0070 | OpenAPI contract: generated from FastAPI, checked in, CI-diffed | Accepted | 15 | `docs/14-implementation/ci-cd-pipeline.md` |

## Maintenance rules

1. Every new architectural decision gets a new ADR appended here.
2. ADRs are append-only. To change a decision, write a new ADR that
   **supersedes** the old one; update the old row's status and
   `Superseded by` link.
3. Phase `decisions.md` files must be reduced to pointers (`see ADR-NNNN`)
   as ADRs are migrated. New decisions must not be recorded only in a
   phase `decisions.md`.
4. The index is regenerated by a CI check (`docs/_ci/adr-index-check.py`)
   that verifies every ADR file is listed and every phase `decisions.md`
   reference resolves.
