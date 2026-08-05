# Backtest & Paper Trading

## Overview

Backtest and paper-trading architecture per D13-4. Both run the same
`execute_decision_cycle()` function as live trading. The only difference
is injected dependencies. No `if MODE == "backtest"` branches exist
anywhere in the decision engine.

## The same-path guarantee

```
┌─────────────────────────────────────────────────┐
│  trade_core/decision_engine.py                    │
│                                                   │
│  def execute_decision_cycle(trigger):             │
│      features = FeatureProvider.compute(trigger)  │
│      proposal = llm_gateway.committee(features)   │
│      risk = RiskValidator.check(proposal)         │
│      size = SizingCalculator.calculate(proposal)  │
│      lineage = LineageWriter.write(...)           │
│      execution = ExecutionRouter.dispatch(...)    │
│      return lineage                               │
│                                                   │
│  # Same function called by:                       │
│  # - Live: scheduler → real LLM → real MT5        │
│  # - Backtest: harness → mock LLM → simulated fill│
│  # - Paper: scheduler → real LLM → paper MT5      │
│  # NO if/else branch for mode detection           │
└─────────────────────────────────────────────────┘
```

### Dependency injection strategy

```python
# Production
engine = DecisionEngine(
    llm_gateway=RealLLMGateway(),
    execution_router=Mt5ExecutionRouter(account="live"),
)

# Backtest
engine = DecisionEngine(
    llm_gateway=MockLLMGateway(fixtures="backtest_fixtures.json"),
    execution_router=SimulatedExecutionRouter(slippage_model=slippage_config),
)

# Paper
engine = DecisionEngine(
    llm_gateway=RealLLMGateway(),
    execution_router=Mt5ExecutionRouter(account="paper"),
)
```

The `DecisionEngine` class does not inspect which implementation it
received. It calls `llm_gateway.committee()` and `execution_router.
dispatch()` through the same interface regardless of mode.

### What this guarantees

1. Risk validation runs the same code in backtest, paper, and live.
2. Position sizing runs the same code in all three modes.
3. Lineage records are structurally identical in all three modes.
4. The decision cycle orchestration (trigger → feature → proposal →
   risk → size → lineage → dispatch) is identical.
5. A bug in risk validation will be caught by backtest before it
   reaches live capital.

## Backtest architecture

### Harness

```
Backtest Harness (Python, separate process)
  │
  ├─ 1. Load historical OHLCV from PostgreSQL (90 days)
  │     Partitioned by instrument/timeframe
  │
  ├─ 2. For each bar close (time-travel simulation):
  │     ├─ Inject current bar into FeatureProvider
  │     │     (same FeatureProvider used by live trade-core)
  │     ├─ Trigger decision cycle
  │     │     └─ Same code path: feature → LLM committee → risk → sizing → lineage
  │     ├─ LLM Gateway: MOCKED
  │     │     └─ Returns canned responses from fixture file
  │     │     └─ Fixture: recorded real LLM outputs OR hand-crafted
  │     ├─ Risk validation: REAL (same deterministic code)
  │     ├─ Sizing: REAL (same deterministic code)
  │     ├─ Lineage write: REAL (to staging DB)
  │     └─ Execution: SIMULATED
  │           └─ SimulatedFillEngine: apply slippage, latency, partial fill
  │
  ├─ 3. SimulatedFillEngine:
  │     ├─ Slippage model: bid/ask spread + 0.1–0.5 pip random
  │     ├─ Latency model: 50–200ms random delay
  │     ├─ Partial fill: 5% probability, 50–90% fill ratio
  │     └─ Rejection: 2% probability (simulate MT5 errors)
  │
  └─ 4. Output:
        ├─ Performance metrics (Sharpe, max DD, win rate, profit factor)
        ├─ Lineage records (same schema as live)
        └─ Trade-by-trade log with timestamps
```

### LLM mock fixtures

Fixtures are JSON files containing canned AutoGen committee outputs.
Each fixture represents a complete committee response for a given
market condition.

```
backtest_fixtures/
├─ strong_buy.json       # All 4 analysts bullish, IC consensus BUY, CIO approves
├─ strong_sell.json      # All 4 analysts bearish, IC consensus SELL, CIO approves
├─ split_committee.json  # 2 bullish, 2 bearish, IC no consensus, CIO decides
├─ cio_override.json     # IC says BUY, CIO overrides to HOLD
├─ debate_triggered.json # Low IC confidence, debate round invoked
├─ neutral.json          # All analysts neutral, no action
└─ error_cases/
    ├─ invalid_schema.json    # Malformed output → schema validation fail
    ├─ extreme_confidence.json # Confidence = 0.0 or 1.0
    └─ missing_fields.json    # Required fields absent
```

Fixtures are versioned and stored in the repository. They are
authored by the operator based on real LLM outputs or hand-crafted
to represent specific scenarios.

### Slippage model

The slippage model is deliberately pessimistic. A backtest that
generates profit with a pessimistic slippage model is more likely
to be profitable in live trading than one with an optimistic model.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Base spread cost | Current bid/ask spread | Real cost of crossing the spread |
| Random slippage | 0.1–0.5 pip (uniform) | Additional variance beyond spread |
| Latency | 50–200ms (uniform) | Time between decision and fill |
| Partial fill probability | 5% | Occasional liquidity gaps |
| Partial fill ratio | 50–90% (uniform) | How much of the order fills |
| Rejection probability | 2% | MT5 errors, requotes, disconnections |

### Backtest metrics & thresholds

| Metric | Threshold | Type |
|--------|-----------|------|
| Sharpe ratio | > 0 | Sanity check — strategy must not lose money |
| Max drawdown | < 20% | Sanity check — strategy must not blow up |
| Profit factor | > 1.0 | Sanity check — gross profit > gross loss |
| Win rate | No threshold | Informational only |
| Total trades | > 0 | Must have generated at least one trade |
| Lineage gaps | 0 | Every trade must have a lineage record |

Thresholds are sanity checks, not performance targets. A strategy
that fails these thresholds is likely broken — not just unprofitable.

### Backtest execution

Backtest runs can be triggered in two ways:

1. **CI (advisory):** Runs on every push to main, 90 days of 1-hour
   bars. Results are reported but do not block merge. Runtime < 10
   minutes.
2. **Staging (manual):** Runs on demand with configurable date range
   and timeframe. Can run longer backtests (1 year, 5-minute bars)
   for strategy research. Runtime depends on data volume.

## Paper trading architecture

### Environment

Paper trading runs in the staging environment (see `test-environments.md`).
It is a full deployment of the Lumine stack with one difference: MT5
is connected to a paper/demo account instead of a live account.

```
Staging Environment (same VPS, different ports)
  │
  ├─ docker-compose.staging.yml
  │     Same images as production (SHA-pinned)
  │     Different env vars: MT5_CONNECT_MODE=paper, DB=staging
  │
  ├─ MT5 Bridge → MT5 Demo Account
  │     Live market data, simulated execution
  │     Broker fills are simulated (MT5 paper account)
  │
  ├─ LLM Gateway → REAL LLM calls
  │     Same models, same prompts, same routing
  │     Separate cost tracking (staging vs production)
  │
  └─ Monitoring:
        Same Prometheus/Grafana dashboards
        Separate data sources (staging DB)
        Alert on staging anomalies (but not critical-pager)
```

### Paper trading requirements

| Requirement | Criteria | Measurement |
|-------------|----------|-------------|
| Duration | Minimum 2 weeks continuous | Clock |
| Order errors | Zero | Execution log |
| Lineage completeness | Every decision has a lineage record | Lineage record count vs trade count |
| Kill-switch | Engage disables trading, disengage resumes | Kill-switch test |
| MT5 recovery | Bridge disconnect → reconnect recovers | Bridge failover test |
| LLM cost | Within expected budget | LLM cost dashboard |

### Paper trading acceptance criteria

Paper trading is the final rehearsal before live capital. It must
demonstrate:

1. The system can run continuously for 2 weeks without intervention.
2. All 6 SSE streams are healthy and deliver data without gaps.
3. The decision engine produces valid proposals at every trigger.
4. Risk validation never incorrectly approves a proposal.
5. Lineage records are written for every decision.
6. MT5 orders are executed correctly (entry, SL, TP, modifications).
7. Kill-switch engages and disengages correctly.
8. The system recovers from MT5 bridge disconnection.
9. LLM costs are within the expected budget.
10. No unexpected errors, crashes, or data corruption.

## Comparison: backtest vs paper vs live

| Dimension | Backtest | Paper Trading | Live Trading |
|-----------|----------|---------------|--------------|
| Market data | Historical (stale) | Live (real-time) | Live (real-time) |
| LLM | Mocked (fixtures) | Real | Real |
| Execution | Simulated (slippage model) | MT5 paper account | MT5 live account |
| Capital at risk | None | None | Real |
| Lineage records | Yes (staging DB) | Yes (staging DB) | Yes (production DB) |
| Decision engine | Same code | Same code | Same code |
| Purpose | Strategy validation | System validation | Capital deployment |

## What this document does NOT define

- Backtest harness implementation code (Phase 14+).
- Slippage model calibration data and methodology (Phase 14+).
- LLM mock fixture authoring process (Phase 14+).
- Paper trading monitoring dashboard JSON (Phase 14+).
- Concrete Docker Compose staging configuration (Phase 14+).

## Phase boundary

Backtest and paper-trading architecture, same-path guarantee, slippage
model parameters, and acceptance criteria are fixed here. Implementation
code and configuration belong to Phase 14+.