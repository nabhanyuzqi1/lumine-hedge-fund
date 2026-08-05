# Market Reasoning Department (LLM Committee)

## Overview

The Market Reasoning Department is the LLM proposer layer (Zone 4). It
interprets market conditions and proposes actions. It has no command path to
MT5. Output is data (proposed action + reasoning + confidence), not command.

This document defines the LLM committee topology, the adaptive escalation
mechanism, per-role model version allocation, and sub-role responsibilities.
It does not define prompt text or AutoGen implementation — those belong to
Phase 4.

## Committee topology: adaptive parallel

The committee uses an adaptive topology that escalates to a debate round only
when confidence is low. The default path is efficient (parallel, low token,
low latency); the debate path is thorough but only triggered when needed.

### Default mode (high confidence path)

```
┌─ Technical Analyst ──┐
│  Macro Analyst        │ → parallel, independent
│  News Analyst         │   each outputs: argument + confidence
└─ SMC Analyst ─────────┘
          ↓
   IC Forum (committee discussion)
     - consolidate 4 arguments
     - resolve conflict
     - output: recommendation + confidence
          ↓
   CIO Proposer (final authority)
     - take IC recommendation + portfolio context / mandate
     - may override IC
     - output: final proposal → trade-core
```

### Debate mode (fallback, low confidence path)

```
Parallel proposal (same as default)
          ↓
Debate round: analysts challenge each other's arguments
     - 1 round, bounded (no recursion)
          ↓
IC Forum (with refined arguments)
          ↓
CIO Proposer → final proposal
```

### Debate trigger

Debate mode is triggered when either condition holds:

- IC confidence < threshold (threshold stored in registry `policy_versions`,
  never hardcoded).
- Inter-analyst disagreement > threshold (e.g. 2 bullish, 2 bearish).

The trigger is deterministic (registry-defined thresholds), not an LLM
judgment call. This preserves principle #6 (reproducibility): the same inputs
produce the same escalation decision.

## Sub-roles

| Sub-role | Input | Output | Reasoning focus |
|----------|-------|--------|-----------------|
| Technical Analyst | features (ATR/EMA/RSI/OHLC) | argument + confidence | price action, indicator confluence |
| Macro Analyst | macro context (rates, DXY, yields) | argument + confidence | macro regime, intermarket |
| News Analyst | news.events stream (sentiment, relevance) | argument + confidence | news impact, sentiment shift |
| SMC Analyst | features (order blocks, liquidity) | argument + confidence | smart money footprint, liquidity sweep |
| IC Forum | 4 analyst arguments | recommendation + confidence | consolidate, resolve conflict |
| CIO Proposer | IC recommendation + portfolio context | final proposal | decide, override IC if needed |

Sub-roles are logical boundaries. Their implementation (AutoGen agent
configuration) is Phase 4. Phase 2 fixes only the responsibility split and
interaction topology.

## Per-role model version

Each sub-role has its own entry in the `model_versions` registry. Different
sub-roles may use different providers / models. Trade-core resolves model
version via registry, never hardcoded. Each version is pinned per decision in
the lineage store.

| Sub-role | Model tier rationale |
|----------|----------------------|
| Technical Analyst | cost-efficient, fast (high-frequency reasoning) |
| Macro Analyst | context-rich, regime understanding |
| News Analyst | sentiment + relevance extraction |
| SMC Analyst | specialized pattern reasoning |
| IC Forum | consolidation, conflict resolution |
| CIO Proposer | strongest model (final decision authority) |

Exact model IDs are resolved from the registry at decision time. They are
never named in code or docs as fixed values (principle #9: replaceability;
no hardcoding).

## Authority

- Market Reasoning is **proposer only**. No veto, no command path.
- CIO Proposer may override IC recommendation (mirrors real hedge fund: IC
  debates, CIO decides).
- Risk validator (Phase 1, deterministic) retains FINAL VETO downstream. No
  LLM may override a REJECT.

## What this department does NOT do

- Does not call MT5 API (Execution Department, via bridge).
- Does not size orders (Portfolio Department).
- Does not validate risk (Risk Department).
- Does not self-trigger (Scheduler triggers; principle: deterministic
  triggers over LLM self-triggering).
- Does not manage trades in real time per tick (deterministic engine; see
  `data-flow.md` Phase 1).

## Phase boundary

This document fixes the topology, sub-role responsibilities, and model
version allocation strategy. It does not define:

- Prompt text (Phase 4).
- AutoGen agent configuration (Phase 4).
- Confidence threshold values (registry `policy_versions`, Phase 3 schema).
- Payload field definitions (Phase 3).
