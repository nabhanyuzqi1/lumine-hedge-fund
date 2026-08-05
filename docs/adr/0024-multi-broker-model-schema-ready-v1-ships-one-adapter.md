# ADR-0024 — Multi-broker model: schema-ready, V1 ships one adapter

- **Status:** Accepted
- **Phase:** 08-trading
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

The system is single-broker by deployment but the CLAUDE.md goal is
multi-broker. `risk-engine.md` and the Phase 5 ERD assume a single MT5
broker — hardcoded symbol semantics, pip values, margin rules, and session
calendars. Adding multi-broker support later as a schema migration is
expensive and error-prone: every position/fill row needs re-attribution.
A single-broker schema is hard to reverse.

## Decision

The system is single-broker by deployment but multi-broker by schema.
`brokers` and `accounts` registry tables are added. `positions.account_id`
and `fills.account_id` are NOT NULL. A `BrokerRiskAdapter` interface
parameterizes symbol/margin/session semantics by adapter, not hardcoded.
Risk engine formulas call adapter methods. Exposure limits are enforced
per-account AND consolidated — both must hold. V1 ships with one broker
row, one account row, one adapter (`MT5RiskAdapter`).

## Rationale

- Single-broker schema is hard to reverse; multi-broker schema is cheap to
  ship with one row.
- `BrokerRiskAdapter` interface means adding a broker = insert a row +
  implement the adapter, no risk-engine code change (principle #9).
- Dual per-account/consolidated exposure limits prevent concentration risk
  across accounts.
- The migration (backfill `account_id`) is run once, before any
  multi-broker rows exist.

## Consequences

- Positive: adding a broker requires no schema migration.
- Positive: consolidated exposure is enforced from day one.
- Negative: V1 carries one extra indirection (adapter resolution) for a
  single-broker deployment.
- Reversibility: the schema is multi-broker-ready; the deployment is not.

## Cross-references

- Related ADRs: ADR-0021, ADR-0040, ADR-0037
- Implements principle(s): #9
- Affects phases: 08, 05
- Source document: `../08-trading/multi-broker-model.md` (S14)
