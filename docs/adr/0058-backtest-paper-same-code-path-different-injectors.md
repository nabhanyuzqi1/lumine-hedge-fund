# ADR-0058 — Backtest and paper-trading: same code path, different injectors

- **Status:** Accepted
- **Phase:** 13-testing
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

The only valid backtest is one that runs the same code as live. If backtest
skips risk validation, uses a different sizing formula, or bypasses lineage
writes, the results are meaningless — they test a different system than the
one trading real capital. LLM calls are non-deterministic and would make
backtest unreproducible.

## Decision

Backtest, paper-trading, and live trading run the same
`execute_decision_cycle()` function. The only difference is injected
dependencies: `LLMGateway` (mock vs real), `ExecutionRouter` (simulated fills
vs paper MT5 vs live MT5). No `if MODE == "backtest"` branches anywhere in
the decision engine. Backtest replays historical OHLCV from PostgreSQL,
injects mock LLM responses from fixture files, simulates fills with a
pessimistic slippage model. Paper trading uses live market data from MT5
paper account, real LLM calls, real MT5 order execution (paper account). Both
produce lineage records structurally identical to live.

## Rationale

- The only valid backtest is one that runs the same code as live. If backtest
  skips risk validation, uses a different sizing formula, or bypasses lineage
  writes, the results are meaningless.
- Dependency injection makes the same-path guarantee implementable without
  conditional branches. The decision engine receives its dependencies at
  construction; it does not inspect them.
- Mock LLM in backtest is necessary because LLM calls are non-deterministic
  and real-time LLM calls would make backtest unreproducible. The mock uses
  recorded or hand-crafted fixtures that represent realistic committee
  outputs.
- Separate backtest engine rejected: any divergence from the live code path
  invalidates the backtest results. Maintaining two parallel code paths is
  also a maintenance burden.
- Real LLM in backtest rejected: non-deterministic output makes backtest
  unreproducible; cost of LLM calls for 90 days of bar-close triggers is
  significant; latency makes backtest impractically slow.

## Consequences

- Positive: backtest results are a faithful simulation of the live system.
- Positive: no mode-branch code to maintain or audit.
- Negative: backtest fixture quality determines backtest fidelity — fixtures
  must be realistic.
- Reversibility: the DI architecture allows adding new injectors (e.g.,
  alternative fill models) without changing the decision engine.

## Cross-references

- Related ADRs: ADR-0019, ADR-0020
- Implements principle(s): #4, #6
- Affects phases: 13, 07
- Source document: `../13-testing/decisions.md` (D13-4)
