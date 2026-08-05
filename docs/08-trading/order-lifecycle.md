# Order Lifecycle & State Machine

## Overview

This document defines the official order state machine for Lumine. Every order
that reaches the execution layer must follow this lifecycle. The state machine
is linear and global: one order, one path, no branching except terminal states.

## State Machine

```
PROPOSED → RISK_CHECK → PENDING → PARTIAL_FILL → FILLED → CLOSED → SETTLED → ARCHIVED
                ↓              ↓           ↓
             REJECTED      CANCELLED    FAILED
```

## State Definitions

| State | Description | Entered By | Exited By |
|-------|-------------|------------|-----------|
| PROPOSED | CIO Proposer has emitted a proposal; waiting for risk validation | CIO Proposer | RiskValidator |
| RISK_CHECK | RiskValidator is evaluating the proposal | RiskValidator | RiskValidator |
| PENDING | RiskValidator approved; order ready to send to MT5 | RiskValidator | Execution Controller |
| PARTIAL_FILL | Some volume filled; remainder still pending | Execution Controller | Execution Controller |
| FILLED | All volume filled; position is open | Execution Controller | Position Manager |
| CLOSED | Position closed (SL, TP, manual, or signal) | Position Manager | Journal Writer |
| SETTLED | Settlement complete; final PnL recorded | Journal Writer | Journal Writer |
| ARCHIVED | Record moved to cold storage; queryable but not active | Journal Writer | — |

## Terminal States

| State | Description | Triggered By |
|-------|-------------|--------------|
| REJECTED | RiskValidator rejected the proposal | RiskValidator |
| CANCELLED | Order cancelled before full fill | Execution Controller |
| FAILED | Order failed due to technical error | Execution Controller |

## Transition Authority

Strict per-role transitions. No role may transition outside its authority.

| Role | Allowed Transitions | From States |
|------|---------------------|-------------|
| CIO Proposer | → PROPOSED | — |
| RiskValidator | → RISK_CHECK | PROPOSED |
| RiskValidator | → PENDING, → REJECTED | RISK_CHECK |
| Execution Controller | → PARTIAL_FILL, → FILLED, → CANCELLED, → FAILED | PENDING, PARTIAL_FILL |
| Position Manager | → CLOSED | FILLED, PARTIAL_FILL |
| Journal Writer | → SETTLED, → ARCHIVED | CLOSED, SETTLED |

## Audit Payload

Every state transition must write a record with this payload:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| transition_id | UUID | Yes | Unique ID for this transition |
| order_id | UUID | Yes | The order being transitioned |
| previous_state | VARCHAR(20) | Yes | State before transition |
| new_state | VARCHAR(20) | Yes | State after transition |
| actor_role | VARCHAR(50) | Yes | Role that triggered the transition |
| actor_id | VARCHAR(100) | No | Specific agent instance ID |
| reason | TEXT | Conditional | Required for REJECTED, CANCELLED, FAILED |
| decision_ts | TIMESTAMPTZ | Yes | When the transition occurred |
| lineage_record_id | UUID | Yes | Link to the proposal lineage |
| mt5_ticket | BIGINT | No | MT5 order ticket (set after PENDING) |
| metadata | JSONB | No | Slippage, fill_price, volume, error_code, etc. |

## Failure Handling

- **Manual retry only.** A FAILED order does not auto-retry.
- To retry, create a **new order** with `retry_of` pointing to the failed order.
- The retry decision must be explicit (human or monitoring system) based on
  `reason` and `metadata.error_code`.
- This keeps the audit trail clean: one failure, one record; one retry, one
  new record.

## Database Schema (Conceptual)

```sql
CREATE TABLE order_state_transitions (
    transition_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    previous_state VARCHAR(20) NOT NULL,
    new_state VARCHAR(20) NOT NULL,
    actor_role VARCHAR(50) NOT NULL,
    actor_id VARCHAR(100),
    reason TEXT,
    decision_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lineage_record_id UUID NOT NULL,
    mt5_ticket BIGINT,
    metadata JSONB,
    CONSTRAINT valid_transition CHECK (previous_state != new_state),
    CONSTRAINT reason_required_for_terminal CHECK (
        new_state NOT IN ('REJECTED', 'CANCELLED', 'FAILED') OR reason IS NOT NULL
    )
);

CREATE INDEX idx_order_transitions_order_id ON order_state_transitions(order_id);
CREATE INDEX idx_order_transitions_lineage ON order_state_transitions(lineage_record_id);
CREATE INDEX idx_order_transitions_decision_ts ON order_state_transitions(decision_ts);
```

## Tradeoffs

| Decision | Rationale | Risk |
|----------|-----------|------|
| Linear global states | Simpler to reason about; sufficient for XAUUSD phase | May need extension for complex multi-leg orders later |
| Strict role authority | Clear audit trail; no ambiguous transitions | Requires disciplined orchestration code |
| Manual retry only | Prevents hidden systemic issues; explicit recovery | Slower incident response |
| Partial fill as state | Accurate representation of MT5 reality | Requires execution controller to handle split tickets |

## What This Document Does NOT Define

- MT5 Expert Advisor code or communication protocol (Phase 8 next document)
- Risk math formulas or position sizing rules (Phase 8 risk-engine document)
- Retry logic implementation details (Phase 14+)
- Database physical partitioning or indexing strategy (Phase 5/11)

## Phase Boundary

This document fixes the order state machine, transition authority, audit
payload, and failure handling policy. It does not define MT5 integration
details, risk formulas, or production code.
