# Positions & Fills Schema

## Overview

Execution output is split into two tables (Decision 8): `positions`
holds the derived current state (mutated on each fill); `fills` is the
append-only ledger (immutable truth). This is the event-sourcing
pattern: the log is truth, the snapshot is convenience. This document
defines both tables, the reconciliation contract, and the
`processed_commands` idempotency table. It does not define remediation
policy, MT5 field mapping, or code.

## Table: `fills` (append-only ledger)

```sql
CREATE TABLE fills (
  fill_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lineage_id     UUID NOT NULL REFERENCES lineage_records(lineage_id),
  ts             TIMESTAMPTZ NOT NULL,
  symbol         TEXT NOT NULL,
  side           TEXT NOT NULL,            -- 'BUY' | 'SELL'
  size           NUMERIC(20,4) NOT NULL,
  price          NUMERIC(20,5) NOT NULL,
  commission     NUMERIC(20,4) NOT NULL,
  slippage       NUMERIC(20,5) NOT NULL,  -- fill_price - expected_price
  book           TEXT NOT NULL,
  strategy_id    UUID NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_fills_lineage ON fills (lineage_id);
CREATE INDEX idx_fills_ts      ON fills (ts);
```

`fills` is immutable. One row per fill event. INSERT only — no UPDATE,
no DELETE. If `positions` ever drifts from `fills`, the position can be
rebuilt by replaying the ledger.

## Table: `positions` (current state, mutated)

```sql
CREATE TABLE positions (
  position_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol         TEXT NOT NULL,
  book           TEXT NOT NULL,
  strategy_id    UUID NOT NULL,
  side           TEXT NOT NULL,            -- 'BUY' | 'SELL'
  size           NUMERIC(20,4) NOT NULL,
  avg_entry      NUMERIC(20,5) NOT NULL,
  sl             NUMERIC(20,5),
  tp             NUMERIC(20,5),
  opened_at      TIMESTAMPTZ NOT NULL,
  opened_lineage UUID NOT NULL REFERENCES lineage_records(lineage_id),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  status         TEXT NOT NULL DEFAULT 'open'  -- 'open' | 'closed'
);
CREATE UNIQUE INDEX idx_positions_open ON positions (symbol, book, strategy_id)
  WHERE status = 'open';
```

`positions` is the derived current view. Mutated on each fill
(size grows/shrinks, `avg_entry` recomputed, `updated_at` refreshed).
When size reaches zero, `status` flips to `closed` (row kept for
audit; the partial unique index allows a new position for the same
key to open).

## Why split

- **`fills` = truth.** Append-only, immutable, auditable forever.
- **`positions` = convenience.** Fast read of current exposure without
  replaying the ledger.
- **Rebuildable.** `positions` can be reconstructed from `fills` +
  `lineage_records` if drift is detected.

This mirrors the lineage invariant: the immutable log is the source of
truth; derived state is a cache.

## Reconciliation contract (Phase 1, target: zero drift)

```
bridge emits mt5.positions -> listener reconciles vs PostgreSQL positions
  |
  v
if mismatch:
  - log drift detail (expected vs actual)
  - drift flag -> decision.outcomes -> review worker (async)
  - safe state per policy (no silent acceptance — principles #4, #10)
  - DO NOT auto-correct PostgreSQL to match broker silently
```

Reconciliation never silently overwrites. Drift is flagged, surfaced to
Review, and resolved per policy. Auto-correcting the database to match
the broker would destroy the audit trail and mask bridge bugs
(principle #10: safe state by default; principle #4: evidence before
capital).

## Idempotency table: `processed_commands` (Decision 7)

```sql
CREATE TABLE processed_commands (
  lineage_id    UUID PRIMARY KEY REFERENCES lineage_records(lineage_id),
  processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  result        TEXT NOT NULL,             -- 'dispatched' | 'duplicate_ignored'
  replay_count  INT NOT NULL DEFAULT 0,
  last_replay_at TIMESTAMPTZ
);
-- Insert pattern:
--   INSERT ... VALUES (...) ON CONFLICT (lineage_id) DO UPDATE
--     SET replay_count = processed_commands.replay_count + 1,
--         last_replay_at = now(),
--         result = 'duplicate_ignored';
```

If the bridge replays a command (stream offset rewind, crash recovery),
the second insert conflicts on `lineage_id`. The row is not re-created
(primary key holds); instead `replay_count` is bumped, `last_replay_at`
is stamped, and `result` is flipped to `duplicate_ignored`. The bridge
inspects the conflict outcome: first insert (`result='dispatched'`)
submits to MT5; subsequent attempts (`duplicate_ignored`) skip the
MT5 call. No duplicate order, and the replay is recorded in the audit
trail. This is the idempotency gate Phase 1 requires.

## Critical path interaction

```
1. ExecutionRouter writes lineage_records (blocking ACID) — see lineage-schema.md
2. ExecutionRouter publishes to mt5.commands
3. Bridge consumes command, checks processed_commands:
   - INSERT ... ON CONFLICT (lineage_id) DO UPDATE
   - if inserted (result='dispatched')  -> submit to MT5, emit fill
   - if conflict  (result='duplicate_ignored') -> bump replay_count, skip MT5 call
4. Listener consumes fill:
   - match fill.lineage_id -> lineage_records
   - INSERT INTO fills (append-only)
   - UPDATE positions (mutate current state)
5. Bridge emits mt5.positions -> listener reconciles vs positions
```

Step 3 is the idempotency gate. Step 4 is the ledger + snapshot write.
Step 5 is the reconciliation check. All ACID; drift flagged not masked.

## Separation guarantees

- **`fills` is append-only.** INSERT only; the ledger is immutable.
- **`positions` is derived.** Mutated, but rebuildable from `fills`.
- **No silent auto-correction.** Drift flagged, never masked.
- **Idempotency enforced.** `processed_commands` prevents duplicate
  orders on replay.

## What this schema does NOT define

- Reconciliation remediation policy (Phase 7 — Risk Policy).
- MT5 field mapping / protocol (Phase 8).
- Position sizing math (Phase 7 / PortfolioSizer internals).
- Code (Phase 14+).

## Phase boundary

This document fixes the `positions` / `fills` / `processed_commands`
schemas, the reconciliation contract, and the idempotency gate. It does
not define remediation policy (Phase 7), the MT5 protocol (Phase 8), or
code (Phase 14+).
