# Lineage Scale & Partitioning

## Overview

Decision **D5-9**: the blocking ACID lineage write is a single-table
hotspot. `physical-erd.md` states "no partitioning needed" for
`lineage_records` — that claim is V1-scoped (single symbol, ~100K
rows/year) and must be corrected for multi-asset scale. This document
amends `physical-erd.md` (Phase 5) and `lineage-schema.md` (Phase 3)
to introduce preemptive monthly partitioning and a write-aside pattern
that preserves the blocking-gate safety contract without making the
analytical hot table a write bottleneck.

## Decision(s)

- **D5-9a** — Re-estimate `lineage_records` growth for multi-asset
  target: ~10,000+ decisions/day, ~2.6M rows/year, unbounded
  (permanent table). The V1 estimate (~100K/yr) is explicitly
  V1-only.
- **D5-9b** — Partition `lineage_records` by `decision_ts` MONTHLY,
  preemptively.
- **D5-9c** — Partition maintenance via pg_partman (or equivalent):
  pre-create 3 months ahead, detach oldest into cold storage (S3/
  Parquet) after 2 years.
- **D5-9d** — Write-aside pattern: the blocking ACID gate writes to
  `lineage_pending` (small, hot, monthly-partitioned); async
  promotion to `lineage_records` (analytical) within 5s.
- **D5-9e** — Local indexes per partition; existing scalar indexes
  retained.
- **D5-9f** — Blocking-gate latency budget: p99 < 10ms on
  `lineage_pending`.

## (a) Growth re-estimate

`physical-erd.md` estimates `lineage_records` at ~100K rows/year,
based on V1 single-symbol scope (10-500 decisions/day). This is
correct for V1 but explicitly flagged as V1-only.

Multi-asset target estimate:

| Dimension | V1 | Multi-asset target |
|-----------|----|--------------------|
| Asset classes | 1 (XAUUSD) | 10 (Forex, Indices, Commodities, Crypto, Stocks, Futures) |
| Strategies per book per symbol | 1-2 | 3-8 |
| Books | 2 (intraday, swing) | 4-6 |
| Symbols per asset class | 1 | 5-20 |
| Decisions/day per strategy | 10-500 | 10-500 |
| Total decisions/day | ~10-500 | ~10,000+ |
| Rows/year | ~100K | ~2.6M+ |

The table is permanent (append-only, never deleted — principle #6
reproducibility). At 2.6M rows/year, the table reaches 26M rows in 10
years. While PostgreSQL can handle this in a single table, write
contention on the hot tail and vacuum pressure on the append-only
insert path become measurable problems well before that.

The decision rate is the driver, not tick rate. But 10,000+ decisions/
day means ~7 decisions/minute during market hours — and those are
clustered (multiple strategies fire on the same bar), creating bursty
write contention on a single unpartitioned table.

## (b) Partition by decision_ts MONTHLY

```sql
-- Partitioned parent (amends lineage-schema.md)
CREATE TABLE lineage_records (
  lineage_id          UUID NOT NULL DEFAULT gen_random_uuid(),
  decision_ts         TIMESTAMPTZ NOT NULL,
  book                TEXT NOT NULL,
  strategy_id         UUID NOT NULL,
  symbol              TEXT NOT NULL,
  side                TEXT NOT NULL,
  verdict             TEXT NOT NULL,
  size                NUMERIC(20,4),
  fill_price          NUMERIC(20,5),
  model_version_id    UUID NOT NULL,
  prompt_version_id   UUID NOT NULL,
  policy_version_id   UUID NOT NULL,
  strategy_version_id UUID NOT NULL,
  trigger             JSONB NOT NULL,
  features            JSONB,
  proposal            JSONB NOT NULL,
  risk_context        JSONB NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (lineage_id, decision_ts)   -- decision_ts required in PK for partitioned table
) PARTITION BY RANGE (decision_ts);

-- Example monthly partition
CREATE TABLE lineage_records_2026_08 PARTITION OF lineage_records
  FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
```

Rationale for monthly partitioning:

- `lineage_records` is append-only and time-range queried — the ideal
  partition candidate.
- Monthly granularity balances partition count (~12/year, manageable)
  against per-partition size (~217K rows/month at target rate, fast
  scans).
- `decision_ts` is already the primary query axis
  (`idx_lineage_decision_ts` in the existing schema).

The PRIMARY KEY gains `decision_ts` because PostgreSQL requires all
partition key columns in the PK of a partitioned table. This does not
change the idempotency contract — `lineage_id` remains globally
unique (UUID), and lookups by `lineage_id` scan all partitions only
if `decision_ts` is unknown. The common path (audit replay) knows
`decision_ts` from the journal.

## (c) Partition maintenance

Managed by pg_partman (or equivalent automation):

| Action | Trigger | Detail |
|--------|---------|--------|
| Pre-create future partitions | scheduled, 3 months ahead | ensures writes never hit a missing partition |
| Detach oldest partition | after 2 years | `DETACH PARTITION` (non-blocking, instant) |
| Export to cold storage | after detach | S3/Parquet, queryable via foreign table (parquet_s3_fdw or equivalent) |
| Retain cold data | forever | reproducibility (principle #6) — cold data is never deleted |

Cold storage via foreign table means a `SELECT` against
`lineage_records` transparently spans hot (PostgreSQL) and cold
(S3/Parquet) partitions. Cold queries are slower (seconds, not
milliseconds) but correct — audit replay of a 3-year-old decision
works without a restore.

The 2-year hot retention window is a storage cost trade-off, tunable.
The safety/reproducibility contract requires the data to exist and be
queryable, not to be in the hot table.

## (d) Write-aside pattern for the blocking gate

The blocking ACID gate (lineage-schema.md, step 4b-4c) currently
writes directly to `lineage_records`. At multi-asset scale, this
makes the analytical hot table a write bottleneck on the critical
path.

Write-aside splits the write:

```sql
-- line 1: the blocking gate (hot, small, fast)
CREATE TABLE lineage_pending (
  lineage_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_ts         TIMESTAMPTZ NOT NULL,
  book                TEXT NOT NULL,
  strategy_id         UUID NOT NULL,
  symbol              TEXT NOT NULL,
  side                TEXT NOT NULL,
  verdict             TEXT NOT NULL,
  size                NUMERIC(20,4),
  fill_price          NUMERIC(20,5),
  model_version_id    UUID NOT NULL,
  prompt_version_id   UUID NOT NULL,
  policy_version_id   UUID NOT NULL,
  strategy_version_id UUID NOT NULL,
  trigger             JSONB NOT NULL,
  features            JSONB,
  proposal            JSONB NOT NULL,
  risk_context        JSONB NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  promoted_at         TIMESTAMPTZ
) PARTITION BY RANGE (decision_ts);

-- line 2: the analytical table (partitioned, line (b) above)
-- lineage_records (same columns, minus promoted_at)
```

The critical-path contract becomes:

```
4. ExecutionRouter:
   a. BEGIN TRANSACTION
   b. INSERT INTO lineage_pending (...)   <- blocking ACID write (p99 < 10ms)
   c. COMMIT                              <- must succeed
   d. if commit fails -> safe state, NO dispatch
   e. if commit succeeds -> publish to mt5.commands stream
   f. async worker: INSERT INTO lineage_records SELECT * FROM lineage_pending
      WHERE lineage_id = ? -> UPDATE lineage_pending SET promoted_at = now()
      (within 5s, retryable, NOT on the critical path)
```

The safety contract is: **a durable record exists before dispatch.**
It does NOT require that record to live in the analytical hot table.
`lineage_pending` is equally durable (same PostgreSQL, same WAL, same
backup). The async promotion to `lineage_records` is a storage-layout
optimization, not a safety concern.

If the async promotion fails (worker crash, transient DB error), the
record is still safe in `lineage_pending`. A reconciliation worker
scans for rows where `promoted_at IS NULL` and `created_at < now() -
10s` and re-promotes them. The analytical table may lag by seconds,
but it never loses data.

`lineage_pending` is also monthly-partitioned (same scheme as
`lineage_records`). Promoted rows are pruned from `lineage_pending`
after confirmation (a grace period of 1 hour, then `DELETE` —
`lineage_pending` is NOT permanent, unlike `lineage_records`).

## (e) Index strategy on partitioned table

Partitioned tables use **local indexes** (one index per partition),
not global indexes. The existing scalar indexes from
`lineage-schema.md` are retained, applied per-partition:

| Index | Per-partition | Serves |
|-------|---------------|--------|
| `(decision_ts)` | covered by partition pruning | time-range scans (pruning handles this) |
| `(book, decision_ts)` | local B-tree | P&L/audit per book within a month |
| `(strategy_id)` | local B-tree | strategy-specific queries within a month |
| `(verdict)` | local B-tree | verdict distribution within a month |
| `(lineage_id, decision_ts)` | partition PK | single-row lookup by lineage_id + ts |

Cross-partition queries (e.g., "all decisions for strategy X across
all time") scan all partitions. This is acceptable for analytical
queries (not on the critical path) and optimized by partition pruning
for time-bounded queries (the common case).

No global index is used. PostgreSQL does not support global indexes
on partitioned tables, and a cross-partition strategy lookup is rare
enough (analytical, not critical-path) that a seq-scan across
partitions is acceptable. If a measured need arises, a materialized
view can denormalize the hot query path.

## (f) Blocking-gate latency budget

The `lineage_pending` write must satisfy:

```
p99 INSERT latency < 10ms
```

This is achievable because:

- `lineage_pending` is monthly-partitioned (small per-partition size:
  ~217K rows/month, or ~7K rows/day at target rate).
- The write is a single-row INSERT with a UUID PK (no sequence
  contention).
- No secondary indexes to maintain beyond the PK and the local
  indexes (which are small per-partition).
- No foreign key enforcement on the write path (FKs are logical
  constraints, not enforced at insert — the registry rows are
  resolved before insert).

If p99 exceeds 10ms under load, the remediation is to increase
partition frequency (weekly) or move `lineage_pending` to a separate
tablespace. The 10ms budget is a hard SLO, monitored via
`lineage_pending_write_latency_seconds` (p99 histogram).

## (g) Correction to physical-erd.md

`physical-erd.md` states:

> `lineage_records`/`fills` grow forever but slowly (decision-rate,
> not tick-rate). No partitioning needed in V1; revisit only if
> decision rate grows by orders of magnitude after multi-symbol
> expansion.

This is corrected to:

> `lineage_records` is partitioned MONTHLY by `decision_ts`
> (D5-9b). The V1 "no partitioning" claim was V1-scoped and is
> superseded by D5-9. `fills` and `processed_commands` remain
> unpartitioned in V1 (lower write rate, revisit at multi-asset
> scale if measured contention appears).

## What this document does NOT define

- `fills` / `processed_commands` partitioning (unpartitioned for now;
  revisit if measured need).
- Cold storage query performance SLOs (slower is acceptable;
  correctness is the contract).
- pg_partman configuration specifics (Phase 14).
- Reconciliation worker implementation (Phase 14+).
- Backup/restore for partitioned tables (`availability-backup.md`).

## Phase boundary

This document amends `physical-erd.md` (Phase 5) and
`lineage-schema.md` (Phase 3) to introduce monthly partitioning of
`lineage_records`, the `lineage_pending` write-aside pattern, and the
p99 < 10ms blocking-gate latency budget. It does not define risk
math (Phase 8), recovery policy (Phase 7), or code (Phase 14+).
