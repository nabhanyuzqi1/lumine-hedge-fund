# Communication & Contracts

## Overview

Lumine uses a two-lane communication model: a synchronous in-proc lane for
the critical decision path (atomicity, low latency) and an asynchronous
Redis-streams lane for cross-process dispatch (decoupling, scalability,
fault isolation). Every cross-process handoff is a schema-validated event
persisted to PostgreSQL for lineage.

## Two-lane model

```
SYNC (in-proc, Zone 1 trade-core)         ASYNC (Redis streams, cross-process)
═════════════════════════════════         ═══════════════════════════════════════
Feature → Risk → Portfolio → Exec         scheduler.events → research.worker
        ↓                                          → review.worker
   lineage.write (blocking, ACID)                 → sandbox.worker
   ↓                                       mt5.commands  ← execution.router
PostgreSQL (source of truth)              mt5.fills     → trade-core.listener
                                          mt5.positions → trade-core.listener
                                          news.events   → scheduler
                                          price.events  → scheduler
```

## Stream catalog

All streams are append-only, schema-validated, and persisted to PostgreSQL
as part of the lineage store. Producers and consumers are isolated by
process boundary.

| Stream | Producer | Consumer | Payload (logical) |
|--------|----------|----------|-------------------|
| `scheduler.events` | Scheduler | research/review/sandbox workers | trigger type, timestamp, scope |
| `mt5.commands` | Execution Router (trade-core) | MT5 Bridge | order spec: symbol, side, size, type, SL/TP, management rules |
| `mt5.fills` | MT5 Bridge | Trade-core listener | fill confirmation, slippage, commission |
| `mt5.positions` | MT5 Bridge | Trade-core listener | position state sync |
| `mt5.marketdata` | MT5 Bridge | Feature engine, Redis cache | real-time tick / bar |
| `news.events` | News adapter | Scheduler, Trade-core | news item, sentiment hint, relevance, source trust |
| `price.events` | Feature engine | Scheduler | bar close, signal threshold cross |
| `decision.proposals` | LLM committee | Risk validator | proposed action + reasoning + confidence |
| `decision.outcomes` | Trade-core | Review worker | approved/rejected + lineage ID |

Payload schemas (exact field definitions) are defined in Phase 3 Data
Architecture. Phase 1 fixes only the logical contract and ownership.

## Port / adapter contracts

Every replaceable component sits behind a Port (abstract interface). Adapters
implement Ports. Replacing a component means implementing a new adapter and
registering it — no neighbor rewrite.

```
┌─────────────┐     Port: BrokerGateway      ┌─────────────┐
│ Trade-core  │ ◄───────────────────────────► │ MT5 Bridge  │
│             │     Port: LLMGateway          │             │
│             │ ◄───────────────────────────► │ 9router     │
│             │     Port: FeatureProvider     │             │
│             │ ◄───────────────────────────► │ Feature svc │
│             │     Port: MarketDataProvider  │             │
│             │ ◄───────────────────────────► │ MT5 Bridge  │
│             │     Port: NewsProvider         │             │
│             │ ◄───────────────────────────► │ News adapter│
│             │     Port: LineageStore        │             │
│             │ ◄───────────────────────────► │ PostgreSQL  │
│             │     Port: RiskPolicyProvider  │             │
│             │ ◄───────────────────────────► │ Registry    │
└─────────────┘                                └─────────────┘
```

Port interface names are stable; adapters are swappable (see
`replaceability.md`).

## Versioned registry

Versioned artifacts are stored in a registry and pinned per decision for
reproducibility.

| Registry table | Contents |
|----------------|----------|
| `model_versions` | model ID + provider + sampling config |
| `prompt_versions` | prompt template + variables |
| `strategy_versions` | strategy spec + parameters |
| `policy_versions` | risk policy + envelope |

Every decision lineage record stores a snapshot of all artifact versions in
use. Replaying a decision = re-running with the same versions. For LLM
non-determinism, lineage stores the *actual* LLM output (not only the input),
since temperature/sampling config can be pinned but output may still vary.

## Lineage write rule

- **Synchronous, blocking, ACID**, on the critical path — before order
  dispatch.
- If the lineage write fails, the order is NOT dispatched (safe state).
- No decision without lineage; no lineage without a decision.
- This is the single most important invariant in the system: it guarantees
  that no live trade can ever exist without a complete, reproducible audit
  trail.

## Kill switch path

The CIO kill switch is hard-wired and bypasses every zone.

```
CIO Kill Switch (independent process / file flag / hardware input)
        ↓
trade-core reads flag every tick (synchronous check, on critical path)
        ↓
if KILLED:
  - cancel open orders
  - flatten / reduce exposure per policy
  - halt new entries
        ↓
restart only by CIO (system cannot self-restart)
```

The kill-switch read is synchronous and on the critical path, ahead of any
order dispatch. No LLM, no async worker, no automated process can override
or delay it.

## Forbidden anti-patterns

- LLM agent directly publishing to `mt5.commands` (must go through risk
  validator).
- Async worker calling trade-core in-proc (must go through a stream).
- Trade-core calling the MT5 API directly (must go through the bridge via
  stream).
- Lineage write performed async or non-blocking (must be sync, blocking,
  ACID).
- Hardcoding model ID, broker detail, or prompt text in trade-core (must go
  through the registry / adapter).
- Batching lineage writes (one write per decision, before dispatch).
