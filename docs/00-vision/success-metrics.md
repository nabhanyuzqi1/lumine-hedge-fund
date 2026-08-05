# Success Metrics

## Primary business KPIs

| KPI | Definition | Target direction |
|-----|------------|------------------|
| Absolute net return | P&L after all costs (spread, commission, swap, slippage, infrastructure) | Positive and growing |
| Return / max drawdown | Annualized return divided by maximum peak-to-trough drawdown | Higher is better |

These two are co-primary. Absolute return ranks candidate systems; return /
max drawdown penalizes paths that achieve return through unacceptable
equity impairment.

## Secondary KPIs

| KPI | Purpose |
|-----|---------|
| Win rate | Trade-level signal quality (contextual, not standalone) |
| Profit factor | Gross profit / gross loss |
| Sharpe ratio | Return per unit total volatility |
| Sortino ratio | Return per unit downside volatility |
| Average win / average loss | Reward asymmetry |
| Trade frequency | Activity level vs. mandate |
| Cost ratio | Total cost as % of capital |
| Strategy attribution | P&L decomposed by book, strategy, regime |

## Risk and operational KPIs

| KPI | Purpose |
|-----|---------|
| Max drawdown | Capital impairment depth |
| Drawdown duration | Recovery burden |
| Risk-policy breaches | Count of violations (target: zero) |
| Kill-switch invocations | Count and cause |
| Unplanned downtime | Operational availability |
| Time-to-safe-state | Latency from fault detection to safe state |
| Decision lineage completeness | % of decisions with full audit trail (target: 100%) |
| Reconciliation drift | Broker vs. internal record divergence (target: zero) |

## Validation gates

Progression to autonomous live trading requires passing each gate in order.

1. **Research gate** — Strategy demonstrates out-of-sample edge after
   realistic costs in backtest.
2. **Paper gate** — Strategy demonstrates forward edge in paper trading
   over a sufficient window with production-equivalent data and decision
   latency.
3. **Limited-live gate** — Strategy operates small live capital within
   mandate with no policy breaches and acceptable risk-adjusted returns.
4. **Scale gate** — CIO approves capital scaling after reviewing limited-live
   evidence.

## Non-goal metrics (explicitly excluded from success criteria)

- Trade count maximization
- Agent activity volume
- Model token spend in isolation (cost efficiency matters; raw spend does not)
- Guaranteed capital preservation (see `scope-and-non-goals.md`)
