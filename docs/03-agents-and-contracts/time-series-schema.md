# Time-Series Schema

## Overview

Market data is stored in PostgreSQL native partitioned tables (Decision
2). One parent table per timeframe, partitioned by range on `timestamp`,
with BRIN indexes for time-ordered append-only data. This document
defines the table structure, partition strategy, indexing, and how
retention aligns with partitioning. It does not define aggregation
logic, ingest code, or the MT5 protocol.

## Partition strategy

Each timeframe is its own partitioned parent table. Partitioning by
range on `ts` keeps each partition small and makes retention
instantaneous (DROP PARTITION instead of slow DELETE).

```sql
-- Parent (template, no rows stored here)
CREATE TABLE bars_1m (
  ts        TIMESTAMPTZ NOT NULL,
  symbol    TEXT NOT NULL,            -- 'XAUUSD'
  open      NUMERIC(20,5) NOT NULL,
  high      NUMERIC(20,5) NOT NULL,
  low       NUMERIC(20,5) NOT NULL,
  close     NUMERIC(20,5) NOT NULL,
  volume    NUMERIC(20,2) NOT NULL,
  source    TEXT NOT NULL             -- 'mt5' | 'aggregator'
) PARTITION BY RANGE (ts);

-- Monthly partition (created by lifecycle job)
CREATE TABLE bars_1m_2026_07 PARTITION OF bars_1m
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```

## Per-timeframe tables

| Table | Granularity | Partition unit | Retention |
|-------|-------------|----------------|-----------|
| `ticks` | per-tick | daily | 7 days |
| `bars_1m` | 1 minute | monthly | 90 days |
| `bars_5m` | 5 minutes | monthly | 90 days |
| `bars_1h` | 1 hour | none (small) | permanent |
| `bars_4h` | 4 hours | none (small) | permanent |
| `bars_1d` | 1 day | none (small) | permanent |

Each timeframe table shares the OHLCV schema above. `ticks` has a
different shape (bid/ask/last) defined in Phase 14+ — Phase 3 fixes
only the bar schema and the partition pattern.

## Indexing

```sql
-- BRIN: block-range index, ideal for time-ordered append-only data
CREATE INDEX idx_bars_1m_ts_brin ON bars_1m USING BRIN (ts);

-- B-tree: targeted symbol + time lookups
CREATE INDEX idx_bars_1m_symbol_ts ON bars_1m (symbol, ts);
```

**Why BRIN over B-tree for `ts`:** time-series is append-only and
naturally ordered by `ts`. BRIN indexes are ~1000x smaller than B-tree
on append-only data and fast for range scans.

**Why B-tree on `(symbol, ts)`:** targeted lookups for a single symbol
in a time range (the common feature-engineering query) need a B-tree;
BRIN is not selective enough for a single symbol.

## Retention alignment (Decision 6)

Retention is enforced by DROP PARTITION, never by row-level DELETE.
This keeps retention instantaneous and non-blocking.

| Table | Action |
|-------|--------|
| `ticks` | DROP daily partition after 7 days |
| `bars_1m`, `bars_5m` | DROP monthly partition after 90 days |
| `bars_1h`, `bars_4h`, `bars_1d` | no action (permanent) |

Old lineage records still resolve their features from surviving
permanent tables (`bars_1h`/`bars_4h`/`bars_1d`). Tick-level detail
ages out per policy — reproducibility is preserved at the bar level
that strategies actually consume.

## Partition pre-creation

```
Daily:   create next day's ticks partition
Monthly: create next month's bars_1m/5m partition
```

Partitions are pre-created ahead of need so inserts never hit a
missing-partition error. Idempotent (`CREATE TABLE IF NOT EXISTS`).
See `data-lifecycle.md` for the job definition.

## Separation guarantees

- **Append-only.** Market data is INSERT only; no UPDATE or DELETE on
  historical rows.
- **Retention via DROP PARTITION.** No row-level DELETE sweeps.
- **Partitions pre-created.** No runtime partition-missing failures.
- **Permanent tables never aged.** `bars_1h`/`bars_4h`/`bars_1d`
  survive forever for reproducibility.

## What this schema does NOT define

- Bar aggregation logic / tick-to-bar rollup (Phase 14+, data-ingest
  worker).
- Tick table schema specifics (Phase 14+).
- Partition automation code (Phase 14+).
- MT5 field mapping / protocol (Phase 8).

## Phase boundary

This document fixes the partitioned table structure, indexing, and
retention alignment. It does not define aggregation logic (Phase 14+),
the MT5 protocol (Phase 8), or code (Phase 14+).
