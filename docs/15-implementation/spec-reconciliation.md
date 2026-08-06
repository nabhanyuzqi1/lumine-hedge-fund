# Spec Reconciliation — Phase 14 claim ↔ Phase 15 reality

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-06
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
| `alembic/versions/` migrations | `repository-structure.md` | `0001_initial_schema.py` and `0002_add_registry_tables_and_lineage_pins.py` exist | Partial | 0002 adds feature_versions, regime_versions, calendar_versions; expands lineage to 7 version pins. Still missing: reasoning_traces, brokers, accounts, tca_records, journal_hash_chain | ADR-0020, ADR-0029, ADR-0024, ADR-0040, ADR-0017 |
| `lineage_records` version pins | `ARCHITECTURE.md` Invariant #1 | 7 pins declared; 7 now implemented (model_version_ids JSONB, prompt_version_ids JSONB, policy, strategy, feature, regime, calendar) | Done | 0002 migration implements the full pin set. feature/regime/calendar FKs are nullable until registry tables are populated | ADR-0020, ADR-0034, ADR-0037 |
| Debate trigger functions | `orchestration.md` | `ic_confidence_predicted` and `disagreement_score` now defined with explicit formulas | Done | Definitions added to orchestration.md — deterministic, pure, reproducible | — |
| SSE browser auth | `auth.md` | Session-based JWT cookie path added alongside HMAC for dashboard operator | Done | Browser EventSource can now authenticate via httpOnly cookie | — |
| `risk-engine.md` / `risk-engine-determinism.md` conflict | `docs/08-trading/` | Deprecation notice added to risk-engine.md pointing to authoritative contract | Done | risk-engine-determinism.md (ADR-0016) is the authoritative sizing contract | ADR-0016 |
| `frontend/` scaffold | `repository-structure.md` | `frontend/src/` empty | Critical | Scaffold per `frontend-sprint-plan.md` in Sprint 6 | — |
| Test levels (7) | `docs/13-testing/test-levels.md` | Empty `__init__.py` per level | Critical | Add ≥1 real test per level + coverage gate in CI (F10) | — |
| OpenAPI generated | `docs/09-api/api-versioning.md` | Not yet | High | Generate `openapi.yaml` from FastAPI in Sprint 5 | ADR-0041* |
| Prompt registry module | `prompt-storage.md` + ADR-0015 | `prompts/__init__.py` only | High | Implement `prompts/registry.py` + `registry.yaml` in Sprint 2 | ADR-0015, ADR-0028 |
| Agent registry | `agent-failure-matrix` (90) | `autogen_pipeline/agents/__init__.py` only | High | Implement typed `AgentSpec` registry in Sprint 4 | ADR-0033 |
| Monitoring module | `docs/11-infrastructure/observability.md` | `monitoring/__init__.py` only | High | Implement logging/metrics/tracing in Sprint 4 | — |
| LLM gateway | `docs/06-ai/llm-gateway.md` | `llm_gateway/__init__.py` only | High | Implement with admission control in Sprint 4 | ADR-0022 |

> ADR-0041* is a placeholder id; assign on creation.

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
