# Level-1 Test Inventory — module ↔ test mapping

- **Status:** active
- **Owner:** backend
- **Created:** 2026-08-11 (Sprint 5, H4)
- **Levels:** per `docs/13-testing/test-levels.md` — L1 unit (no I/O),
  L2 integration (real PG/Redis), L3 contract (API shape), L4 system
  (full cycle, mocked externals), L5 backtest, L6 E2E (frontend), L7 audit.

Every module in `backend/src/lumine/**` is mapped below. Modules with no
test file are marked **orphan** and must be covered before they ship logic.

## api/

| Module | Test file | Level |
|--------|-----------|-------|
| `api/app.py` | `tests/contract/test_api_contract.py`, `tests/contract/test_openapi_contract.py` | L3 |
| `api/middleware/auth.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/middleware/envelope.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/middleware/idempotency.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/middleware/logging.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/middleware/rate_limit.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/admin.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/journal.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/lineage.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/market.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/orders.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/portfolio.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/rpc.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/streams.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/routers/workflows.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/schemas/api.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/schemas/common.py` | `tests/contract/test_api_contract.py` | L3 |
| `api/sse/__init__.py` | (import surface only) | — |

## autogen_pipeline/

| Module | Test file | Level |
|--------|-----------|-------|
| `autogen_pipeline/_base.py` | `tests/unit/test_analysts.py` | L1 |
| `autogen_pipeline/agents/_base.py` | `tests/unit/test_analysts.py` | L1 |
| `autogen_pipeline/agents/macro_analyst.py` | `tests/unit/test_analysts.py` | L1 |
| `autogen_pipeline/agents/news_analyst.py` | `tests/unit/test_analysts.py` | L1 |
| `autogen_pipeline/agents/smc_analyst.py` | `tests/unit/test_analysts.py` | L1 |
| `autogen_pipeline/agents/technical_analyst.py` | `tests/unit/test_analysts.py` | L1 |
| `autogen_pipeline/cio_proposer.py` | `tests/unit/test_ic_forum_debate_cio.py` | L1 |
| `autogen_pipeline/debate.py` | `tests/unit/test_ic_forum_debate_cio.py` | L1 |
| `autogen_pipeline/ic_forum.py` | `tests/unit/test_ic_forum_debate_cio.py` | L1 |
| `autogen_pipeline/journal.py` | `tests/integration/test_reasoning_traces.py` | L2 |
| `autogen_pipeline/orchestrator.py` | `tests/unit/test_orchestrator.py`, `tests/system/test_decision_cycle.py` | L1+L4 |
| `autogen_pipeline/risk_assessor.py` | `tests/unit/test_risk_assessor.py` | L1 |
| `autogen_pipeline/traces.py` | `tests/integration/test_reasoning_traces.py` | L2 |

## bridge/

| Module | Test file | Level |
|--------|-----------|-------|
| `bridge/client.py` | `tests/unit/test_bridge_client.py`, `tests/integration/test_bridge.py` | L1+L2 |
| `bridge/types.py` | `tests/unit/test_bridge_types.py` | L1 |

## data/

| Module | Test file | Level |
|--------|-----------|-------|
| `data/collector.py` | `tests/unit/test_collector.py`, `tests/integration/test_collector_persistence.py` | L1+L2 |
| `data/lineage.py` | `tests/integration/test_lineage.py` | L2 |
| `data/models.py` | `tests/unit/test_models.py` | L1 |
| `data/partitions.py` | `tests/unit/test_partitions.py`, `tests/integration/test_partitions.py` | L1+L2 |
| `data/persistence.py` | `tests/integration/test_collector_persistence.py` | L2 |
| `data/redis_client.py` | `tests/integration/test_infra_smoke.py` | L2 |
| `data/session.py` | `tests/integration/test_infra_smoke.py` | L2 |

## features/

| Module | Test file | Level |
|--------|-----------|-------|
| `features/indicators.py` | `tests/unit/test_indicators.py` | L1 |
| `features/provider.py` | `tests/unit/test_feature_provider.py`, `tests/integration/test_feature_provider.py` | L1+L2 |
| `features/types.py` | `tests/unit/test_feature_provider.py` | L1 |

## llm_gateway/

| Module | Test file | Level |
|--------|-----------|-------|
| `llm_gateway/budget.py` | `tests/unit/test_llm_budget.py` | L1 |
| `llm_gateway/client.py` | `tests/unit/test_llm_client.py` | L1 |
| `llm_gateway/fallback.py` | `tests/unit/test_llm_fallback.py` | L1 |
| `llm_gateway/gateway.py` | `tests/unit/test_llm_gateway.py` | L1 |
| `llm_gateway/registry.py` | `tests/unit/test_llm_routing.py` | L1 |
| `llm_gateway/router.py` | `tests/unit/test_llm_routing.py` | L1 |
| `llm_gateway/types.py` | `tests/unit/test_llm_routing.py` | L1 |
| `llm_gateway/usage.py` | `tests/unit/test_llm_usage.py`, `tests/integration/test_llm_usage.py` | L1+L2 |

## prompts/

| Module | Test file | Level |
|--------|-----------|-------|
| `prompts/registry.py` | `tests/unit/test_prompt_registry.py` | L1 |

## schemas/

| Module | Test file | Level |
|--------|-----------|-------|
| `schemas/validation.py` | (covered indirectly by unit suite) | L1 |

## shared/

| Module | Test file | Level |
|--------|-----------|-------|
| `shared/config.py` | `tests/unit/test_config.py` | L1 |
| `shared/errors.py` | `tests/unit/test_errors.py` | L1 |
| `shared/logging.py` | `tests/unit/test_logging.py` | L1 |
| `shared/types.py` | `tests/unit/test_types.py` | L1 |

## trade_core/

| Module | Test file | Level |
|--------|-----------|-------|
| `trade_core/execution_router.py` | `tests/integration/test_execution_router.py` | L2 |
| `trade_core/reconciliation.py` | `tests/unit/test_reconciliation.py` | L1 |
| `trade_core/risk_validator.py` | `tests/unit/test_risk_validator.py` | L1 |
| `trade_core/sizing_calculator.py` | `tests/unit/test_sizing_calculator.py` | L1 |

## Orphan modules (no dedicated test file)

| Module | Note |
|--------|------|
| `api/sse/__init__.py` | Import surface only — covered via contract streams tests |
| `monitoring/__init__.py` | Empty package (Sprint 5 out of scope) |
| `registry/__init__.py` | Empty package (spec gap, separate plan) |
| `security/__init__.py` | Empty package |
| `schemas/agents/__init__.py` | Empty package |
| `schemas/streams/__init__.py` | Empty package |
| `prompts/evals/__init__.py` | Eval scaffolding |

## Gap policy

- Empty `__init__.py` packages are not "orphans" in the risk sense — they
  hold no logic. Tracked here so they cannot silently gain code without a
  test.
- New logic added to any module listed above must land with a test at the
  appropriate level in the same PR (docs-first rule, CLAUDE.md).
- Re-audit at the end of every sprint (spec-reconciliation cadence).
