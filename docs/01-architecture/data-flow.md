# Data Flow

## Overview

This document defines the main decision-cycle data flow, the safe-state
behavior on each failure mode, the data sourcing strategy, the news layer,
and the trade-management lifecycle. The flow embodies product-philosophy
principles #2 (deterministic controls over LLM promises), #4 (evidence
before capital), #6 (reproducibility before adaptation), and #10 (safe
state by default).

## Decision cycle (happy path)

```
1. TRIGGER
   scheduler (cron bar-close OR price.events OR news.events)
        ↓ scheduler.events stream
   trade-core picks up trigger (synchronous)

2. FEATURE COMPUTATION (deterministic)
   FeatureProvider computes indicators (ATR / EMA / RSI / OHLC) from
   PostgreSQL time-series + Redis tick cache
        ↓ features (in-proc)

3. LLM REASONING (proposer)
   trade-core calls LLMGateway → AutoGen committee
   (Technical / Macro / News / SMC → IC → CIO proposer)
   with model / prompt versions pinned from registry
        ↓ decision.proposals (JSON schema-validated)

4. RISK VALIDATION (deterministic, veto)
   Risk validator checks proposal against:
   - current exposure (from PostgreSQL positions)
   - risk policy / envelope (from registry policy_versions)
   - kill-switch flag (synchronous read)
   - strategy book limits
        ↓ APPROVE / REJECT / MODIFY + reason

5. PORTFOLIO SIZING (deterministic)
   if APPROVE: size calculation per book (intraday / swing)
   attribution tag attached
        ↓ sized order

6. LINEAGE WRITE (synchronous, blocking, ACID)
   lineage record written to PostgreSQL BEFORE dispatch:
   trigger, features, proposal, risk decision, size,
   model / prompt / strategy / policy versions, timestamp
        ↓ if write fails → safe state, no dispatch

7. EXECUTION DISPATCH
   Execution Router publishes to mt5.commands stream
        ↓ Redis stream

8. MT5 BRIDGE (isolated process)
   bridge consumes command, calls MT5 API,
   emits fill / position events
        ↓ mt5.fills + mt5.positions streams

9. FILL RECONCILIATION (deterministic)
   trade-core listener consumes fill, updates position in PostgreSQL,
   computes slippage, compares vs expected
        ↓ reconciliation drift check (target: zero)

10. REVIEW FEED (async)
    decision.outcomes stream → review worker (async)
    review worker post-trade attribution, drift detection
    (off the critical path; never blocks trading)
```

## Safe-state behavior

Every failure drives the system toward reduced exposure, not expanded risk.

| Failure | Behavior |
|---------|----------|
| Lineage write fails | No dispatch; halt new entries |
| MT5 bridge crash | Trade-core detects stream timeout; cancel open orders; flatten / reduce per policy |
| Risk validator error | REJECT by default (fail safe) |
| LLM gateway timeout | Skip cycle; retry on next trigger; no order |
| Kill switch ON | Cancel open orders; flatten / reduce per policy; halt new entries; restart only by CIO |
| PostgreSQL unavailable | Halt all new decisions (lineage cannot be written) |
| Redis unavailable | Halt new decisions (cannot dispatch to bridge); broker-side SL/TP remains active |
| News adapter down | Trade continues on price + feature triggers; news trigger paused |
| Feature computation error | Skip cycle; no order |

## Reproducibility invariant

Each decision cycle produces exactly one lineage record containing a
snapshot of all artifact versions in use. Replaying a decision = re-running
with the same trigger, features, and versions. For LLM non-determinism, the
lineage stores the actual LLM output (since temperature / sampling config
can be pinned but output may still vary). This satisfies principle #6:
without reproducibility, adaptation is indistinguishable from drift.

## Data sourcing strategy

**Organic / broker-native first.** The system does not depend on paid
third-party data APIs in its default configuration.

### Market data (organic, broker-native, free)

```
MT5 Bridge (Python, isolated process)
├─ Pull real-time ticks + bars from MT5 (broker-native)
├─ Pull historical OHLCV from MT5 on demand
├─ Emit to Redis stream (mt5.marketdata)
├─ Write time-series to PostgreSQL (partitioned per instrument / timeframe)
└─ Cache latest tick in Redis (for feature engine)
```

MT5 is the sole real-time market-data source for V1. Data comes from the
broker itself, which is the most accurate feed for execution (no external
feed drift). The `MarketDataProvider` Port remains available so that future
adapters (LMAX, Interactive Brokers, etc.) can be added without rewrite;
paid third-party aggregators are optional adapters, never the default.

### Fallback policy

- Tick stream timeout → trade-core safe state (no trading on stale data).
- No automatic fallback to paid third-party APIs in V1 (organic-first
  principle).
- Reconnect is isolated inside the bridge; trade-core remains safe.

## News layer (organic multi-source, "Bloomberg Terminal class, free version")

The news adapter is a separate process that aggregates information from
free / organic sources, processed by AI for relevance and sentiment. The
target is institutional-grade information awareness without paid terminal
subscriptions.

```
News Adapter (separate process, organic multi-source)
├─ Sources:
│  ├─ Government / official (central bank statements, Fed, ECB, Treasury)
│  ├─ Forexfactory economic calendar (free)
│  ├─ Yahoo Finance search (scrape / search)
│  ├─ Google search (AI-driven retrieval)
│  ├─ Social media (X / Twitter, Reddit financial subs)
│  └─ RSS feeds (Reuters, Bloomberg public, major outlets)
├─ Retrieval:
│  - Scheduled polling per source (cron)
│  - Event-triggered (breaking keyword alert)
│  - AI-driven search query (LLM generates query → fetch → filter)
├─ Processing:
│  - Dedup, source trust scoring (gov > major outlet > social)
│  - LLM extract sentiment + relevance + impact
│  - Anti-injection: news content cannot prompt-inject the LLM
│  - Emit news.events stream → scheduler / trade-core
└─ No paid news API (Bloomberg Terminal / Refinitiv) in default config;
   optional adapter via NewsProvider Port
```

Technical details of scraping resilience, rate limiting, robots.txt / ToS
compliance, and AI query generation are implementation concerns for a later
phase. Phase 1 fixes only the sourcing strategy, the organic-first
principle, and the stream contract.

## Trade management lifecycle

Trade management is hybrid: the LLM proposes a complete management plan at
entry and may re-evaluate on periodic triggers; deterministic engine
executes real-time per tick. SL/TP is hard-set on the broker side as a
final safety net.

```
Entry moment (LLM proposer):
  proposal = {
    entry, SL, TP, breakeven_trigger, trailing_rule,
    management_rules, exit_conditions, confidence
  }
        ↓ deterministic validator (risk checks SL/TP vs envelope)
        ↓ approve → MT5 (SL/TP hard-set on broker side as safety net)

Real-time management (deterministic engine):
  - per tick / bar: check management_rules
  - breakeven: move SL to entry when condition met (deterministic)
  - trailing: move SL per ATR rule (deterministic)
  - SL / TP hit: broker side; engine confirms fill
  - LLM NOT called per tick (latency + cost + non-determinism)

AI re-evaluation (on periodic triggers, not per tick):
  - bar close (5m / 1h / 4h): AI may re-assess, propose modify
    (move TP, partial close, add)
  - news event: AI may re-assess, propose flatten / hedge
  - always via proposer → validator → lineage flow; never bypass
```

### Why LLM does not manage trades in real time

- **Principle #2**: deterministic controls over LLM. SL/TP are risk
  controls and must be deterministic.
- **Latency**: LLM calls take 500ms–3s; MT5 ticks arrive at ms scale. SL/TP
  must react instantly.
- **Non-determinism**: an LLM may change its mind on every call, causing SL
  to jump erratically — dangerous.
- **Cost**: per-tick LLM calls cause massive token spend with no value.

### Broker-side SL/TP as safety net

- SL/TP are submitted to MT5 at entry. If the engine or bridge crashes, the
  broker still honors SL/TP, capping loss.
- Engine-side management (breakeven, trailing) optimizes outcomes but is
  not safety-critical; broker-side SL/TP is.

## Summary

The data flow guarantees: every decision is reproducible (lineage +
versioned artifacts), every failure degrades to safe state, market data is
organic/broker-native, news is organic multi-source, and trade management
keeps deterministic control of risk while allowing AI to reason at trigger
granularity — never per tick.
