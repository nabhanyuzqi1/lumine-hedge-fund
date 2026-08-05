# Stream Payloads

## Overview

Event payloads crossing process boundaries are validated against JSON
Schema files (Decision 4). Wire format V1 is JSON text (Decision 5) for
debuggability; an upgrade path to MessagePack is fixed via the
port/adapter boundary — only the transport adapter changes, payloads
stay schema-validated. This document defines the validation contract,
the wire format, the common envelope, and the nine payload shapes. It
does not define the schema registry service, MessagePack migration
timeline, or code.

## Wire format (Decision 5)

**V1: JSON text.** Debuggable, universal, no binary decoding friction
during build-out.

**Upgrade path:** MessagePack via the port/adapter boundary (Phase 1
replaceability). The transport adapter serializes/deserializes; the
schema files and the validation contract stay unchanged. Migration
timeline is Phase 14+ — only the *path* is fixed here.

## Schema files (Decision 4)

```
schemas/streams/
├── mt5.commands.json
├── mt5.fills.json
├── mt5.positions.json
├── mt5.marketdata.json
├── news.events.json
├── price.events.json
├── decision.outcomes.json
├── scheduler.events.json
└── decision.proposals.json      (logical payload — see note)
```

One `.json` per stream, versioned alongside code.

## Validation contract

Producer validates before publish; consumer validates after read, before
processing. Both sides reject invalid payloads. No component trusts an
unvalidated payload — defense in depth (principle #10: safe state by
default).

```
producer:  load schema -> validate(payload) -> if valid: publish
consumer:  read -> validate(payload) -> if valid: process; if invalid: drop/flag
```

Invalid payloads never cross the process boundary silently. A producer
that cannot validate must not publish; a consumer that cannot validate
must not act.

## Common envelope

Every event carries this envelope:

```json
{
  "event_id":      "uuid",
  "ts":            "2026-07-31T14:22:01.123Z",
  "schema_version":"1.0.0",
  "book":          "intraday | swing",
  "strategy_id":   "uuid",
  "lineage_id":    "uuid (where applicable)",
  "payload":       { ...stream-specific... }
}
```

- `book` + `strategy_id` on every event = attribution is mandatory
  (principle #5: books never blend).
- `lineage_id` threads the audit trail across streams.
- `schema_version` lets payloads evolve without breaking consumers.

## Stream catalog (8 streams + 1 logical)

| Stream | Payload (stream-specific) | Producer -> Consumer |
|--------|---------------------------|----------------------|
| `mt5.commands` | symbol, side, size, sl, tp, order_type | ExecutionRouter -> Bridge |
| `mt5.fills` | fill_id, lineage_id, price, size, commission, slippage | Bridge -> Listener |
| `mt5.positions` | symbol, side, size, sl, tp (broker-side state) | Bridge -> Listener |
| `mt5.marketdata` | ts, symbol, ohlcv | Bridge -> feature engine |
| `news.events` | ts, headline, sentiment, relevance, source | News ingest -> News Analyst |
| `price.events` | ts, symbol, feature snapshot (ATR/EMA/RSI) | Feature engine -> trade-core |
| `decision.outcomes` | lineage_id, fill, slippage, drift_flag | trade-core -> Review |
| `scheduler.events` | trigger_type, ts, target | Scheduler -> trade-core |
| `decision.proposals` | proposal, confidence, sub_roles, versions | (logical — see note) |

### Note on `decision.proposals`

Phase 1 resolution: `decision.proposals` is **not** a Redis stream.
trade-core calls the LLM gateway (cross-process synchronous RPC),
receives the proposal, and passes it in-proc to RiskValidator. The
schema file still exists — it validates the logical payload at the
gateway boundary. The proposal is persisted to
`lineage_records.proposal` JSONB; it is not re-published on a stream.
This resolves the Phase 1 ambiguity (data-flow depicted it as a step;
the catalog listed it as a stream) in favor of the sync in-proc
interpretation.

## Separation guarantees

- **Producer + consumer both validate.** No trust across process
  boundaries.
- **Attribution mandatory.** `book` + `strategy_id` on every event.
- **Schema-versioned.** Payloads can evolve without breaking consumers.
- **`decision.proposals` is logical.** Validated at the gateway
  boundary, persisted to lineage, not streamed.

## What this document does NOT define

- Schema registry service / API (Phase 14+).
- MessagePack migration timeline (Phase 14+ — only the path is fixed).
- LLM proposal field internals (Phase 4 — prompt design).
- MT5 field mapping / protocol (Phase 8).
- Code (Phase 14+).

## Phase boundary

This document fixes the validation contract, wire format V1, the common
envelope, and the nine payload shapes. It does not define the schema
registry service (Phase 14+), prompt internals (Phase 4), the MT5
protocol (Phase 8), or code (Phase 14+).
