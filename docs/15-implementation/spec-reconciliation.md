# Spec Reconciliation — Phase 14 claim ↔ Phase 15 reality

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-11
- **Review-cadence:** 30

This document is the integrity check between what `docs/14-implementation/`
specifies and what the code actually contains. Drift here is the most
dangerous documentation failure mode: docs that lie destroy trust in the
whole KB.

## Reconciliation table

| Phase 14 spec claim | File:line (approx) | Code reality | Gap | Action | ADR |
|---------------------|--------------------|--------------|-----|--------|-----|
| `trade_core/decision_engine.py` — `execute_decision_cycle()` | `repository-structure.md` | Implemented as `autogen_pipeline/orchestrator.py` `DecisionOrchestrator.execute` (10-stage cycle). Spec named `trade_core/decision_engine.py`; code lives in `autogen_pipeline/` — see deviation-log `D-004` | Done | Path deviation recorded; substance matches spec. Sprint 3 | ADR-0016 |
| `trade_core/feature_provider.py` | `repository-structure.md` | Does not exist | Critical | Implement in Sprint 2 against feature-store-contract | ADR-0020 |
| `trade_core/risk_validator.py` | `repository-structure.md` | Implemented at `backend/src/lumine/trade_core/risk_validator.py` (`assess_proposal`, 6 deterministic checks) | Done | Advisory-only LLM role per ADR-0016; deterministic validator. Sprint 3 | ADR-0016 |
| `trade_core/sizing_calculator.py` | `repository-structure.md` | Implemented at `backend/src/lumine/trade_core/sizing_calculator.py` (`calculate_size`, ATR-based, floor-rounded) | Done | Deterministic multiplier lookup via `risk_adjustment_multiplier` policy pin. Sprint 3 | ADR-0016 |
|| `alembic/versions/` migrations | `repository-structure.md` | `0001_initial_schema.py`, `0002_add_registry_tables_and_lineage_pins.py`, `0003_add_default_partitions.py`, `0004_rename_model_versions_config_to_params.py`, `0005_align_llm_usage_to_spec.py`, `0006_add_reasoning_traces_and_message_schemas.py`, `0007_add_audit_hardening.py`, `0008_add_anchor_state.py`, `0009_add_tca_and_accounts.py` exist | Partial | 0009 adds TCA records, brokers, accounts tables with indexes. Still missing: full historical data population | ADR-0040, ADR-0024 |
| `lineage_records` version pins | `ARCHITECTURE.md` Invariant #1 | 7 pins declared; 7 now implemented (model_version_ids JSONB, prompt_version_ids JSONB, policy, strategy, feature, regime, calendar) | Done | 0002 migration implements the full pin set. feature/regime/calendar FKs are nullable until registry tables are populated | ADR-0020, ADR-0034, ADR-0037 |
| Debate trigger functions | `orchestration.md` | `ic_confidence_predicted` and `disagreement_score` now defined with explicit formulas | Done | Definitions added to orchestration.md — deterministic, pure, reproducible | — |
| SSE browser auth | `auth.md` | Session-based JWT cookie path added alongside HMAC for dashboard operator | Done | Browser EventSource can now authenticate via httpOnly cookie | — |
| `risk-engine.md` / `risk-engine-determinism.md` conflict | `docs/08-trading/` | Deprecation notice added to risk-engine.md pointing to authoritative contract | Done | risk-engine-determinism.md (ADR-0016) is the authoritative sizing contract | ADR-0016 |
| `frontend/` scaffold | `repository-structure.md` | `frontend/src/` scaffolded; F-Sprint 1–6 Done (scaffold, design system, realtime layer, charts, surfaces, accessibility & performance); evidence `sprint-evidence/f-sprint-6-a11y-perf.md` | Done | Align with commit `83749bd` | — |
| Test levels (7) | `docs/13-testing/test-levels.md` | Level 3 contract suite: `tests/contract/test_api_contract.py` 30 tests (auth codes, envelope, idempotency, rate limit, pagination, SSE frames); unit 448 tests | Partial | Coverage gate in CI (F10) still open; integration suite blocked by Docker (G9) | — |
| OpenAPI generated | `docs/09-api/api-versioning.md` | `docs/09-api/openapi.yaml` generated from `app.openapi()` (`scripts/generate_openapi.py`); CI `openapi-diff` job fails on drift; contract test pins shape | Done | Sprint 5 (H1, H2) — commit `ea4c003` | ADR-0070 |
|| `prompts/registry.py` | `prompt-storage.md` + ADR-0015 | `prompts/registry.py` implemented with SHA-256 validation, caching, variable extraction | Done | Prompt registry complete. Sprint 7 | ADR-0015, ADR-0028 |
| TCA calculation & persistence | `tca-and-execution-quality.md`, ADR-0040 | `trade_core/tca.py` (193 lines), `execution_router.py` integration (`persist_tca()`) | Done | Full TCA pipeline: calculation, benchmark resolution, atomic persistence with Fill. Sprint 7 | ADR-0040 |
| Migration 0009 (TCA, brokers, accounts) | `repository-structure.md` | `alembic/versions/0009_add_tca_and_accounts.py` with indexes | Done | Tables created: `tca_records`, `brokers`, `accounts`. Sprint 7 | ADR-0040, ADR-0024 |
|| Agent registry spec | `agent-failure-matrix` (90) | `autogen_pipeline/agents/__init__.py` only | High | Implement typed `AgentSpec` registry in future sprint | ADR-0033 |
| Monitoring module | `docs/11-infrastructure/observability.md` | `api/middleware/logging.py` — `RequestLoggingMiddleware` (structlog access logs, `trace_id` contextvars, `X-Request-ID` echo) wired outermost in `app.py` | Done | Logging + request tracing complete (G7, Sprint 4); metrics (Prometheus) and distributed tracing deferred to Sprint 5 | — |
| LLM gateway | `docs/06-ai/llm-gateway.md` | `llm_gateway/__init__.py` only | High | Implement with admission control in Sprint 4 | ADR-0022 |

> ADR-0041* resolved as ADR-0070 (OpenAPI contract generation).

## Reconciliation cadence

- Updated at the end of every sprint.
- CI gate (planned): `spec-reconciliation` table must not contain
  `Critical` gaps for areas tagged as "Done" in `README.md` status.

## Drift policy

- If code exists without spec → add spec or ADR, then reconcile.
- If spec exists without code → mark `Not started`/`Partial`, never claim
  `Done`.
- If spec and code disagree → an ADR records which wins; the loser is
  updated in the same PR.
