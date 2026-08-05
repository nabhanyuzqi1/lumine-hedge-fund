# Phase 3 — Data Architecture

## Status

- **Phase**: 3
- **Name**: Data Architecture
- **Prior phase**: Phase 2 — Department & Agent Architecture (approved)
- **Next phase**: Phase 4 — Prompt Engineering & AutoGen Configuration

## Scope

Phase 3 fixes the data architecture for the entire system: database
schemas, event payload schemas, registry schemas, the lineage store, and
data lifecycle. Phase 1 declared PostgreSQL as the system of record and
the lineage write as the single most important invariant. Phase 3 makes
that concrete by defining every table, every stream payload envelope,
and every lifecycle rule.

Phase 3 fixes the data layer; it does NOT define prompt text, AutoGen
configuration, risk math, broker protocol, backtest engine, or code.

## Documents

| Document | Contents |
|----------|----------|
| `lineage-schema.md` | `lineage_records` table — hybrid scalar + JSONB, immutability, version pins, blocking ACID gate on critical path |
| `registry-schema.md` | Four versioned registry tables (`model_versions`, `prompt_versions`, `strategy_versions`, `policy_versions`), status lifecycle, replaceability contract, promotion gate |
| `time-series-schema.md` | Partitioned market-data tables (ticks, bars by timeframe), BRIN indexes, monthly/daily partitions |
| `positions-fills-schema.md` | `positions` (mutated current state) + `fills` (append-only ledger), reconciliation contract, `processed_commands` idempotency table |
| `stream-payloads.md` | JSON Schema validation, wire format V1 (JSON), 8 stream envelopes + 1 logical payload, producer + consumer validation |
| `data-lifecycle.md` | Partition management, tiered retention (7d / 90d / permanent), registry archival, lifecycle invariants |
| `decisions.md` | Locked decisions for Phase 3 |

## Authority statement

Phase 3 documents are the authoritative data architecture reference.
Every table, column, payload, and lifecycle rule originates here. They
do NOT define:

- Prompt text (Phase 4 — Prompt Engineering).
- AutoGen agent configuration (Phase 4).
- Risk math formulas / envelope calculations (Phase 7 — Risk Policy).
- MT5 protocol / API surface (Phase 8 — Broker Integration).
- Backtest engine implementation (Phase 9 — Research & Backtesting).
- Code of any kind (Phase 14+).

Where Phase 1 or Phase 2 referenced data structures, Phase 3 is the
authoritative definition. Phase 1/2 described the *contract* (lineage
is blocking ACID; registry is versioned); Phase 3 defines the *schema*.

## Key principle

**#6 Reproducibility before adaptation.** Every decision is pinned to
exact versions of model, prompt, strategy, and policy. Old versions are
never deleted. Append-only tables (`lineage_records`, `fills`, registry
tables) accept INSERT only — no UPDATE, no DELETE. A decision recorded
last month can be replayed against the same registry versions and
surviving permanent market data.
