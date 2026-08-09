# Knowledge Index — Topic × Phase Map

This is the topic-level navigation map for the Lumine knowledge base. Use it
when you know the *topic* but not the *phase*. Phase-level navigation is
`docs/phase-mapping.md`; decision-level navigation is `docs/adr/INDEX.md`.

## How to read

Each row is a topic. Each cell points to the authoritative doc(s) for that
phase on that topic. `—` means not applicable. Where a governance doc
(`90-…`) exists, it is the permanent operating standard; phase docs are the
design source.

## Topic × Phase matrix

| Topic | 00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 90 |
|-------|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|
| **Risk** | — | `data-flow` | `risk-portfolio` | `lineage-schema` | — | — | `model-routing` | `recovery` | `risk-engine`, `risk-engine-determinism`, `reconciliation` | — | — | — | `threat-model`, `audit-tamper-evidence` | `backtest-paper` | — | `spec-reconciliation` | `94-runbooks`, `96-ai-governance/strategy-promotion` |
| **Execution** | — | `data-flow` | `execution-department` | `positions-fills-schema` | — | `physical-erd` | — | — | `execution-engine`, `order-lifecycle`, `mt5-integration`, `tca-and-execution-quality`, `multi-broker-model` | — | — | `clock-and-time` | — | — | — | `spec-reconciliation` | `94-runbooks/mt5-*` |
| **Data & features** | — | `data-flow` | — | `lineage-schema`, `registry-schema`, `feature-store-contract`, `regime-model`, `market-calendar-contract` | — | `physical-erd`, `lineage-scale-and-partitioning`, `migrations`, `redis-roles`, `object-storage` | — | — | — | — | — | — | — | — | `repository-structure` | `spec-reconciliation` | `93-standards/db-standards` |
| **Agents** | `user-personas` | `departments-and-books` | `*` | `registry-schema`, `agent-failure-matrix` (90) | `proposal-schema`, `inter-agent-message-versioning` | — | `memory-architecture`, `model-routing` | `workflow-lifecycle`, `orchestration` | — | — | — | — | — | `ai-testing` | — | `spec-reconciliation` | `94-runbooks/agent-failure-matrix` |
| **Prompts** | — | — | — | — | `prompt-storage`, `proposal-schema`, `inter-agent-message-versioning` | — | `model-routing` | — | `risk-engine-determinism` | — | — | — | `prompt-injection-defense` | `ai-promotion-gates`, `ai-testing` | `coding-standards` | `spec-reconciliation` | `93-standards/prompt-standards` |
| **LLM / models** | — | — | — | — | — | — | `model-routing`, `llm-gateway`, `cost-control`, `memory-policy`, `memory-architecture`, `model-registry`, `gateway-admission-control`, `confidence-calibration`, `context-budget-policy` | `observability`, `reasoning-trace-storage`, `deadline-propagation` | — | — | — | — | — | `ai-testing`, `ai-promotion-gates` | — | `spec-reconciliation` | `96-ai-governance/model-risk-management`, `95-finops` |
| **AutoGen runtime** | — | — | — | `lineage-schema` | `proposal-schema` | — | — | `workflow-lifecycle`, `recovery-and-termination`, `checkpoint-and-replay`, `observability`, `orchestration`, `concurrency-budget`, `comparative-replay-isolation`, `deadline-propagation` | — | — | — | — | — | — | — | `spec-reconciliation` | — |
| **Audit / lineage** | — | `replaceability` | `governance-and-cross-department` | `lineage-schema` | `prompt-storage` | `physical-erd` | — | `checkpoint-and-replay`, `observability`, `reasoning-trace-storage` | `order-lifecycle`, `reconciliation` | — | — | `audit-log`, `audit-tamper-evidence` | — | — | — | `spec-reconciliation` | `94-runbooks`, `97-change-management` |
| **Infrastructure / ops** | — | `deployment-topology` | — | — | — | `availability-backup` | — | — | — | — | — | `topology`, `observability`, `backup-dr`, `build-deploy`, `clock-and-time` | `network-firewall`, `ssh-access` | `test-environments` | `ci-cd-pipeline` | `spec-reconciliation` | `94-runbooks/*`, `95-finops` |
| **Security** | `scope-and-non-goals` | — | — | — | — | — | — | — | `mt5-integration` | `auth` | — | — | `*` | `security-testing` | — | `spec-reconciliation` | `94-runbooks`, `96-ai-governance` |
| **Testing** | — | — | `research-review-sandbox` | — | — | — | — | `checkpoint-and-replay` | `backtest-paper` (13) | — | `performance` | — | `security-testing` | `*` | — | `spec-reconciliation` | `93-standards` |
| **Frontend** | `product-philosophy` | — | — | — | — | — | — | — | — | `rest-api`, `sse-api` | `*` | — | — | — | `repository-structure` | `spec-reconciliation`, `frontend-sprint-plan` | — |
| **API** | — | `communication-and-contracts` | — | `stream-payloads` | `proposal-schema` | — | — | — | — | `*` | `architecture` | — | — | — | — | `spec-reconciliation` | `93-standards/api-standards` |
| **Governance / decisions** | `success-metrics` | `high-level-architecture` | `governance-and-cross-department` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | `decisions` | — | `adr/INDEX.md`, `97-change-management`, `91-anti-scope-register` |
| **Onboarding** | `vision-and-mission` | `README` | `README` | `README` | `README` | — | — | — | — | — | — | — | — | — | — | `README` | `92-onboarding/*`, `91-glossary` |

## Definitions of authority

| Layer | Purpose | Mutability |
|-------|---------|------------|
| Phase docs (`00-15`) | Design source for a phase | Versioned; updated via ADR on architectural change |
| ADR registry (`adr/`) | Permanent decision record | Append-only; supersession via new ADR |
| Governance tier (`90-…`) | Permanent operating standards | Versioned; reviewed per cadence (S25) |
| Code | Implementation | Per Phase 15 spec reconciliation |

When a phase doc and a governance doc disagree, the **governance doc is the
operating standard** and the phase doc must be reconciled (an ADR records
the change).
