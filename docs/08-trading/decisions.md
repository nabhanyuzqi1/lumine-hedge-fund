# Phase 8 — Locked Decisions

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Order lifecycle = global linear states** | One state machine for all orders: PROPOSED → RISK_CHECK → PENDING → PARTIAL_FILL → FILLED → CLOSED → SETTLED → ARCHIVED, plus terminal REJECTED/CANCELLED/FAILED. Simpler to audit and reason about than per-order or hierarchical models. |
| 2 | **6 main states + 2 post-close states** | PROPOSED, RISK_CHECK, PENDING, PARTIAL_FILL, FILLED, CLOSED as main; SETTLED and ARCHIVED as post-close. Explicit partial fill and settlement states improve auditability without overcomplicating the active path. |
| 3 | **Strict per-role transitions** | Each state transition is owned by exactly one role: CIO Proposer, RiskValidator, Execution Controller, Position Manager, Journal Writer. No shared authority. Audit trail always shows who changed what. |
| 4 | **5 roles, each owns transitions** | CIO Proposer creates; RiskValidator approves/rejects; Execution Controller fills/cancels/fails; Position Manager closes; Journal Writer settles/archives. Clear separation of concerns. |
| 5 | **Full audit payload per transition** | Every transition records: transition_id, order_id, previous_state, new_state, actor_role, actor_id, reason, decision_ts, lineage_record_id, mt5_ticket, metadata. Complete audit trail for compliance and debugging. |
| 6 | **Manual retry only** | FAILED orders do not auto-retry. Retry creates a new order with `retry_of` reference. Prevents hidden systemic failures and keeps audit trail explicit. |
| 7 | **MT5 integration = Redis Pub/Sub + Queue bridge** | Python backend communicates with MT5 EA via Redis. Commands go to `mt5:commands` queue; results publish to `mt5:results` channel. Async, decoupled, cross-platform. |
| 8 | **Risk engine = LLM-assisted reasoning** | Deterministic base formula (1% risk, ATR-based SL) + LLM qualitative assessment. LLM can adjust volume or veto; final decision remains deterministic. |
| 9 | **Execution engine = idempotency key + Redis dedup** | Every attempt gets `order_id:attempt_N` key. Redis dedup prevents duplicate execution. No auto-retry; manual retry creates new order. |

## Principles Honored

- **#4 Evidence before capital**: every transition carries lineage and reason.
- **#6 Reproducibility before adaptation**: state machine is deterministic and replayable.
- **#9 Replaceability**: roles are interchangeable as long as transition authority is respected.
- **#10 Safe state by default**: manual retry prevents automated cascade failures.

## Phase Boundary Respected

Phase 8 fixes the order lifecycle and transition rules. It does NOT define:
risk math (Phase 8 next document), MT5 protocol (Phase 8 next document),
API design (Phase 9), or production code (Phase 14+).
