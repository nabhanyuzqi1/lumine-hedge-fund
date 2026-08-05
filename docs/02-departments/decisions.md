# Phase 2 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Adaptive parallel committee topology** | Default: 4 analysts run parallel, IC consolidates, CIO Proposer decides. Fallback: 1 bounded debate round when IC confidence < threshold or inter-analyst disagreement > threshold. Efficient by default, thorough when needed. Escalation trigger is deterministic (registry thresholds), not LLM judgment. |
| 2 | **IC Forum + CIO Proposer as separate authority** | IC is a committee discussion forum (consolidate, resolve conflict). CIO Proposer is final authority, may override IC. Mirrors real hedge fund: IC debates, CIO decides. |
| 3 | **Deterministic departments as sub-modules with boundaries** | RiskValidator / PortfolioSizer / ExecutionRouter are separate sub-modules in trade-core with stable input/output contracts. In-proc sync, testable per module, replaceable per-stage. |
| 4 | **Hybrid split by function for async workers** | Research = LLM-driven (generate). Review = hybrid (deterministic attribution + LLM narrative). Sandbox = deterministic only (backtest). LLM only in generative / interpretive roles; deterministic in verification / execution. |
| 5 | **Tiered kill switch: global + book + strategy** | CIO global kill (flatten all) + per-book suspend (intraday / swing) + per-strategy suspend. Granular isolation without halting the entire system. |
| 6 | **Closed learning loop via streams** | Trade → Review → Research → Sandbox → CIO gate → Production. Feedback via streams, not in-proc calls. Promotion never auto — always CIO human gate (principle #7). |
| 7 | **Per-role model version allocation** | Each LLM sub-role (Technical / Macro / News / SMC / IC / CIO Proposer / Research / Review) has its own entry in `model_versions` registry. Different roles may use different providers / models. Cost-optimized + specialization. Resolved via registry, never hardcoded. |

## Principles honored

- **#2 Deterministic over LLM**: risk veto absolute; LLM is proposer only.
- **#4 Evidence before capital**: Sandbox out-of-sample test before promotion.
- **#5 Books separately attributable**: attribution tags mandatory; books never blend.
- **#6 Reproducibility before adaptation**: per-role model versions pinned per decision; debate escalation trigger deterministic.
- **#7 Self-modification as research**: promotion is CIO human gate, never automated.
- **#9 Replaceability**: per-role model versions via registry; sub-modules with stable boundaries.
- **#10 Safe state by default**: validator fail-safe = REJECT; tiered kill switch.

## Phase boundary respected

Phase 2 fixes department architecture and interaction only. It does NOT
define: prompt text (Phase 4), AutoGen implementation (Phase 4), payload
field definitions (Phase 3), database schema (Phase 3), risk math
(Phase 7), MT5 protocol (Phase 8), backtest engine (Phase 9), or code
(Phase 14+).
