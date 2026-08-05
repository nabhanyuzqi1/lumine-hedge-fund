# High-Level Architecture

## Overview

Lumine is structured as five logical zones with clear process boundaries.
The critical decision path (feature → risk → portfolio → execution → lineage)
runs synchronously in a single process for atomicity and low latency.
Asynchronous reasoning, review, and sandbox work run in separate worker
processes. The MT5 bridge is the only component that touches the MT5 API.
LLM reasoning is strictly advisory (proposer); deterministic Python holds
final authority (validator + executor).

## Five logical zones

```
┌─────────────────────────────────────────────────────────────────┐
│  ZONE 1: DETERMINISTIC TRADE-CORE (1 process, critical path)    │
│  sync in-proc event bus, ACID lineage write per decision        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Features │→│ Risk     │→│ Portfolio│→│ Execution│           │
│  │ (Python) │ │ Validator│ │ Alloc    │ │ Router   │           │
│  └──────────┘ └──────────┘ └──────────┘ └─────┬────┘           │
│       ↑                                        │                │
│  ┌────┴───────────────────────────────────┐   │                │
│  │ Decision Lineage Writer (sync, blocking)│   │                │
│  │ → PostgreSQL (source of truth)          │   │                │
│  └────────────────────────────────────────┘   │                │
└───────────────────────────────────────────────┼────────────────┘
                                                │ Redis stream
┌───────────────────────────────────────────────▼────────────────┐
│  ZONE 2: MT5 BRIDGE (separate process, isolated)               │
│  - Consume command stream, emit fill/position/event stream     │
│  - Pull real-time ticks + historical bars from MT5 (organic)   │
│  - Reconnect/restart isolated; crash → trade-core safe state   │
│  - Sole component that holds the MT5 API                       │
└────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ZONE 3: ASYNC REASONING WORKERS (separate processes)           │
│  - Research worker  (backtest, OOS, candidate generation)       │
│  - Review worker    (post-trade attribution, drift detection)   │
│  - Sandbox worker   (shadow eval, self-mod candidates)          │
│  Trigger: Redis streams from scheduler; never touch MT5         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ZONE 4: LLM REASONING LAYER (AutoGen multi-agent)              │
│  - Committee: Technical/Macro/News/SMC Analysts → IC → CIO     │
│  - Called by trade-core as PROPOSER (JSON schema-validated)     │
│  - Output: proposed action + reasoning + confidence             │
│  - Never holds command path to MT5                              │
│  - Via 9router gateway (model pinned from registry per decision)│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ZONE 5: INFRASTRUCTURE & GOVERNANCE                            │
│  - PostgreSQL (lineage, orders, positions, P&L, config,         │
│    strategy registry, partitioned time-series)                  │
│  - Redis (tick/feature cache, locks, streams)                   │
│  - Scheduler (cron + event triggers; deterministic)             │
│  - News adapter (organic multi-source aggregator)               │
│  - CIO Kill Switch (independent, hard-wired, bypasses all zones)│
│  - Observability (logs, metrics, traces)                        │
└─────────────────────────────────────────────────────────────────┘
```

## Key principles

- **Critical path is synchronous in-proc.** Feature → risk → portfolio →
  execution → lineage runs in one process for atomicity and latency. A
  failure anywhere on this path rolls back to safe state before dispatch.
- **MT5 bridge is the sole MT5 API holder.** Trade-core never calls MT5
  directly. Bridge crash cannot take down trade-core; trade-core detects
  stream timeout and enters safe state.
- **LLM layer is proposer only.** LLM committee generates proposed actions;
  deterministic risk validator has final veto. LLM never publishes to the
  MT5 command stream.
- **Async workers are off the critical path.** Research, review, and sandbox
  workers cannot block trading or trigger orders. They consume streams and
  emit findings.
- **Kill switch is independent and hard-wired.** The CIO kill switch is read
  synchronously on every tick by trade-core. It cannot be bypassed by any
  zone, including the LLM layer. Restart is CIO-only; the system cannot
  self-restart.

## Process boundary invariants

1. Trade-core is the only writer to the decision lineage store.
2. MT5 bridge is the only reader/writer of the MT5 API.
3. LLM gateway is the only caller of 9router / external LLM providers.
4. News adapter is the only outbound fetcher of external news sources.
5. Scheduler is the only producer of scheduler.events triggers.
6. No async worker may call trade-core in-proc; communication is via stream.
7. No component may write to the MT5 command stream except the execution
   router inside trade-core, and only after risk validation + lineage write.

## What this zone model guarantees

- **Safety**: a single component failure degrades to safe state, not
  unbounded risk.
- **Reproducibility**: every decision is pinned to versioned artifacts and
  written to lineage before dispatch.
- **Replaceability**: each zone's internal implementation can be swapped via
  Port/adapter without rewriting neighbors (see `replaceability.md`).
- **Observability**: every cross-process handoff is a stream event, which is
  persisted and traceable.
- **Governance**: CIO authority is independent of all zones and cannot be
  bypassed.
