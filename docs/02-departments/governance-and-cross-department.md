# Governance & Cross-Department Interaction

## Overview

Governance is the human CIO authority, which sits outside the system. This
document defines the authority hierarchy, the cross-department interaction
matrix, the separation of authority, and the governance reporting path.

## Authority hierarchy

```
HUMAN CIO (outside system)
  - kill switch (global + book + strategy)
  - restart authorization
  - promotion gate (strategy → production)
  - mandate definition
        ↓
LLM PROPOSER (Zone 4)
  Market Reasoning (Technical/Macro/News/SMC) → IC Forum → CIO Proposer
        ↓ proposed action (data, not command)
RISK VALIDATOR (Zone 1, deterministic) ── FINAL VETO
        ↓ if APPROVE
PORTFOLIO SIZER (Zone 1, deterministic)
        ↓ sized order + attribution
EXECUTION ROUTER (Zone 1, deterministic) → MT5 Bridge (Zone 2)
        ↓ fill
LINEAGE STORE (PostgreSQL, blocking ACID before dispatch)
        ↓
REVIEW (Zone 3, async) → RESEARCH → SANDBOX → CIO gate → PRODUCTION
```

No LLM agent sits above the risk validator. No async worker sits on this
path. The CIO kill switch sits above the entire path and is read on every
cycle.

## Cross-department interaction matrix

| From | To | Channel | Mode |
|------|-----|---------|------|
| Scheduler | Trade-core | trigger | sync (in-proc) |
| Market Reasoning | Risk validator | proposal | sync (in-proc, via trade-core) |
| Risk validator | Portfolio sizer | APPROVE | sync (in-proc) |
| Portfolio sizer | Execution router | sized order | sync (in-proc) |
| Execution router | MT5 Bridge | command | async (`mt5.commands` stream) |
| MT5 Bridge | Trade-core listener | fill / position | async (`mt5.fills` / `mt5.positions`) |
| Trade-core | Review worker | outcomes | async (`decision.outcomes`) |
| Review worker | Research worker | drift / hypothesis | async (stream) |
| Research worker | Sandbox worker | candidate | async (stream) |
| Sandbox worker | Review worker | backtest result | async (stream) |
| Review worker | CIO (human) | promotion recommendation | report (outside system) |
| CIO (human) | System | kill / restart / promote | flag / report (outside system) |

The matrix is the stable interaction contract. Sync (in-proc) for the
critical path; async (Redis streams) for cross-process dispatch and the
learning loop; reports (outside system) for human governance.

### Note on `decision.proposals`

Phase 1 stream catalog lists `decision.proposals` (LLM committee → Risk
validator). Phase 2 clarifies the transport: trade-core calls the LLM
gateway (cross-process, synchronous RPC) and receives the proposal; the
proposal then passes to the risk validator in-proc within trade-core. The
`decision.proposals` contract is the logical payload (schema-validated),
not a Redis stream. The proposal is also persisted to the lineage store as
part of the decision record. This resolves the Phase 1 ambiguity (data-flow
depicts it as a data-flow step; the catalog listed it as a stream) in favor
of the sync in-proc interpretation.

## Separation of authority

- **LLM never executes.** LLM output is data, not command.
- **Async workers never trade.** Research / Review / Sandbox consume streams;
  they cannot publish to `mt5.commands`.
- **Risk veto is absolute.** No component may override a REJECT.
- **Books never blend.** Attribution tags are mandatory on every order, fill,
  and lineage record (principle #5).
- **CIO authority is external.** The system cannot promote, restart, or
  bypass CIO gates (principle #7).

## Closed learning loop (reaffirmed)

```
live trade → review → research → sandbox → CIO gate → production
     ↑                                                    ↓
     └────────────── new version pinned ─────────────────┘
```

- Promotion is a human gate (principle #7: self-modification as research,
  not production authority).
- Old versions stay pinned in lineage (reproducibility, principle #6).

## Governance reporting (outside system, to CIO)

The system presents information to the CIO; the CIO decides. The system
cannot decide on its own beyond its defined authority.

- Performance dashboard per book / strategy (from Review worker).
- Drift alerts + recommended actions.
- Promotion recommendations (from Review, CIO decides).
- Lineage audit trail (from PostgreSQL).

## What Phase 2 guarantees

- **Clear authority hierarchy** across all departments.
- **Clean separation** between LLM (proposer), deterministic (veto / size /
  execute), and async (research / review / sandbox) roles.
- **Closed learning loop** with a human gate at promotion.
- **No phase leakage**: no prompt text, no AutoGen implementation, no payload
  field definitions, no code. Only department architecture and interaction.

## Phase boundary

This document fixes the authority hierarchy and interaction matrix. It does
not define:

- Governance dashboard implementation (Phase 12 — Observability).
- Reporting payload schemas (Phase 3).
- CIO interface tooling (outside system scope).
- Code (Phase 14+).
