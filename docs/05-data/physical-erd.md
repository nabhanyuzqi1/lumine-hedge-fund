# Physical ERD & Growth Model

## Overview

This document maps every physical table, its relationships, estimated
growth, retention, indexes, and the queries it serves. It is the single
reference for capacity planning and for judging whether the storage
layout holds at multi-million-record scale.

Table definitions (columns, types) are inherited from Phase 3 unchanged.
This document adds the physical dimension only.

## Entity groups

```
REGISTRY (versioned, append-only, never deleted)
  model_versions ─┐
  prompt_versions ─┼── pinned by ──> lineage_records
  strategy_versions┤        (4 FK version pins)
  policy_versions ─┘

DECISION (append-only, forever)
  lineage_records ──< fills            (1 lineage -> N fills)
  lineage_records ──< processed_commands (1:1 idempotency)
  lineage_records ──< positions.opened_lineage

EXECUTION STATE
  fills (ledger, immutable)  -->  positions (snapshot, mutated, rebuildable)

MARKET DATA (append-only, partitioned)
  ticks (daily partitions, 7d)
  bars_1m / bars_5m (monthly partitions, 90d)
  bars_1h / bars_4h / bars_1d (unpartitioned, permanent)
```

## Relationship map

| Parent | Child | FK | Cardinality |
|--------|-------|----|-------------|
| `strategy_versions` | `lineage_records` | `strategy_id`, `strategy_version_id` | 1 → N |
| `model_versions` | `lineage_records` | `model_version_id` | 1 → N |
| `prompt_versions` | `lineage_records` | `prompt_version_id` | 1 → N |
| `policy_versions` | `lineage_records` | `policy_version_id` | 1 → N |
| `strategy_versions` | `strategy_versions` | `parent_id` (self) | 1 → N |
| `lineage_records` | `fills` | `lineage_id` | 1 → N |
| `lineage_records` | `processed_commands` | `lineage_id` | 1 → 1 |
| `lineage_records` | `positions` | `opened_lineage` | 1 → N |

Market-data tables have no foreign keys — they are ingested in bulk and
must stay free of referential overhead on the hot write path.

## Per-table physical profile

| Table | Write rate | Est. rows/yr (1 symbol) | Retention | Partitioned | Notes |
|-------|-----------|--------------------------|-----------|-------------|-------|
| `ticks` | ~2–10/s market hours (~23h/day, ~5d/wk) | ~43–216M ingested/yr | 7 days | daily | Largest churn; resident size bounded by 7d retention |
| `bars_1m` | 1/min | ~375K (dropped after 90d) | 90 days | monthly | |
| `bars_5m` | 1/5min | ~75K (dropped after 90d) | 90 days | monthly | |
| `bars_1h` | 1/hr | ~6.2K | permanent | no | |
| `bars_4h` | 1/4hr | ~1.6K | permanent | no | |
| `bars_1d` | 1/day | ~260 | permanent | no | |
| `lineage_records` | per decision (~10–500/day) | ~100K | permanent | no | Grows forever; the audit core |
| `fills` | per fill (~10–1000/day) | ~200K | permanent | no | Append-only ledger |
| `positions` | per open/close | low (open set small) | closed rows kept | no | Mutated snapshot |
| `processed_commands` | per command | ~ equals fills | permanent | no | Idempotency gate |
| 4 registry tables | rare (per promotion) | hundreds | permanent | no | Never deleted |

**Resident working set** (after retention): at ~2–10 ticks/s over ~23
market hours/day, one week of ticks is roughly **1–6M rows** rotating in
the 7 daily partitions — small, because retention drops everything
older. bars_1m/5m keep ~90 days, everything permanent is small. The only
tables that grow unbounded are `lineage_records`, `fills`, and
`processed_commands` — all low-rate decision tables, not tick tables.

> Tick math: ~2–10/s × ~83,000 market-sec/day ≈ 165K–830K rows/day, so
> ~1.2–5.8M rows resident over 7 days, and × ~260 market days/yr
> (~5d/wk) ≈ ~43–216M rows ingested per year before retention drops
> them.

## Index inventory

| Table | Index | Type | Serves |
|-------|-------|------|--------|
| `lineage_records` | `(decision_ts)` | B-tree | decisions in a time range |
| `lineage_records` | `(book, decision_ts)` | B-tree | P&L / audit per book over time |
| `lineage_records` | `(strategy_id)` | B-tree | all decisions of a strategy |
| `lineage_records` | `(verdict)` | B-tree | verdict distribution |
| `fills` | `(lineage_id)` | B-tree | fills for a decision |
| `fills` | `(ts)` | B-tree | fills in a time range |
| `positions` | `(symbol, book, strategy_id) WHERE status='open'` | partial unique | current exposure lookup |
| `bars_*` | `(ts)` | BRIN | time range scans (append-ordered) |
| `bars_*` | `(symbol, ts)` | B-tree | single-symbol feature queries |
| `processed_commands` | PK `(lineage_id)` | B-tree | idempotency check |

JSONB columns (`trigger`, `features`, `proposal`, `risk_context`) are
not GIN-indexed in V1 — they are the cold reproducibility payload, not a
query target. Add a GIN index later only if a measured query needs it.

## Expected query patterns

1. **Feature engineering** — read `bars_*` for one symbol over a window:
   served by `(symbol, ts)` B-tree + BRIN.
2. **Audit / replay** — fetch one `lineage_records` row by PK, resolve
   4 registry FKs, read its `fills`.
3. **Exposure check** — read open `positions` via the partial unique
   index (hot path, must stay fast).
4. **Reconciliation** — compare broker positions vs `positions` snapshot.
5. **Idempotency gate** — `INSERT ... ON CONFLICT` on
   `processed_commands` PK.

## Growth & capacity notes

- The tick table is the only high-volume writer; retention keeps its
  resident size bounded. Partition DROP is the retention mechanism
  (instant, non-blocking).
- `lineage_records`/`fills` grow forever but slowly (decision-rate, not
  tick-rate). No partitioning needed in V1; revisit only if decision
  rate grows by orders of magnitude after multi-symbol expansion.
- Multi-symbol expansion multiplies market-data tables linearly but does
  not change decision-table growth class. The layout scales by adding
  partitions, not by redesign.

## What this document does NOT define

- Column-level types (Phase 3 owns the logical schema).
- Backup/restore procedure (`availability-backup.md`).
- Redis keyspace (`redis-roles.md`).
- Code (Phase 14+).

## Phase Boundary

This document fixes the physical ERD, growth model, index inventory, and
query patterns. It does not redefine the logical schema (Phase 3) or
define code (Phase 14+).
