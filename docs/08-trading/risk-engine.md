# Risk Engine

> **IMPORTANT — LLM risk role has been redefined.**
> This document's LLM Risk Assessment section (lines 35-57) describes a
> continuous `risk_adjustment` float multiplier that is **deprecated**.
> See [risk-engine-determinism.md](risk-engine-determinism.md) (ADR-0016)
> for the authoritative contract: LLM risk output is **advisory only**,
> the sizing multiplier is a deterministic registry lookup keyed by
> `regime_bucket`. The deterministic base formula and exposure limits
> below remain in force.

## Overview

This document defines how Lumine calculates position sizing, stop loss, and
validates whether a proposed trade may proceed. The Risk Engine sits between
the Investment Committee and Execution.

## Decision: LLM-Assisted Risk Reasoning

RiskValidator uses a hybrid approach:

1. **Deterministic formulas** compute the base position size and stop loss.
2. **LLM reasoning** evaluates qualitative factors (news sentiment, market
   regime, correlation with existing positions).
3. **Final decision** is deterministic: if LLM recommends adjustment, the
   formula is recalculated with adjusted parameters.

This keeps the system auditable while allowing nuanced risk assessment.

## Deterministic Base Formula

```
risk_per_trade = 0.01  # 1% of equity
account_equity = get_equity()
atr_14 = get_atr(14)
stop_loss_pips = atr_14 * 2
pip_value = get_pip_value(symbol)

base_volume = (account_equity * risk_per_trade) / (stop_loss_pips * pip_value)
max_volume = get_broker_max_volume(symbol)
volume = min(base_volume, max_volume)
```

## LLM Risk Assessment

The RiskValidator LLM receives:
- The proposal (action, symbol, confidence)
- Current portfolio exposure
- Recent news sentiment
- Volatility regime (low/medium/high)
- Correlation with existing positions

The LLM outputs:
- `risk_adjustment`: -0.5 to +0.5 (multiplier on base volume)
- `risk_notes`: explanation
- `veto`: true/false (if true, order is REJECTED)

## Final Calculation

```
if llm.veto:
    reject_order()
else:
    adjusted_volume = base_volume * (1 + llm.risk_adjustment)
    final_volume = max(0.01, min(adjusted_volume, max_volume))
```

## Exposure Limits

| Limit | Value | Action if Exceeded |
|-------|-------|-------------------|
| Max risk per trade | 1% of equity | Reject |
| Max total exposure | 5% of equity | Reject new orders |
| Max correlated exposure | 3% of equity | Reduce volume or reject |
| Max daily loss | 3% of equity | Halt all trading for the day |

## Validation Flow

```
CIO Proposal
    |
    v
RiskValidator
    |---> Check deterministic limits
    |---> Run LLM risk assessment
    |---> Calculate final volume
    |---> APPROVE → PENDING
    |---> REJECT → REJECTED
```

## What This Document Does NOT Define

- LLM prompt text (Phase 4/6)
- ATR calculation code (Phase 14+)
- Broker-specific margin rules (Phase 8 MT5 Integration)
- Real-time exposure monitoring (Phase 10/11)

## Phase Boundary

This document fixes the hybrid risk approach, base formula, LLM assessment
structure, and exposure limits. It does not define prompt wording, indicator
code, or production monitoring.
