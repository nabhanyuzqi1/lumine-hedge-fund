# Database Standards

- **Status:** active
- **Owner:** data-engineers / architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180
- **Source:** promoted from `docs/05-data/`

## Naming
- Tables: `snake_case`, plural (e.g. `lineage_records`, `fills`).
- Columns: `snake_case`. Timestamps end in `_ts` (`decision_ts`, `created_at`).
- Booleans: `is_`/`has_` prefix.
- Foreign keys: `<table_singular>_id` (e.g. `strategy_id`).

## Migrations
- Alembic; `make migrations-new m="..."`.
- One logical change per migration; must be reversible (`downgrade`).
- Append-only tables (lineage, journal, fills, reasoning_traces) get no
  `downgrade` that destroys data — mark irreversible explicitly.

## Partitioning
- Time-series, append-only tables partitioned by time (`decision_ts` monthly,
  `ts` daily for ticks). See `docs/05-data/lineage-scale-and-partitioning.md`.
- Pre-create partitions 3 months ahead; detach cold partitions to S3/Parquet
  after the retention horizon.

## Indexes
- B-tree for equality/range; BRIN for append-ordered time series; GIN for
  JSONB only when a measured query needs it (default: no GIN on JSONB).
- Low-cardinality labels only in metric indexes (observability).

## Retention / archival
- Per `docs/05-data/physical-erd.md`: ticks 7d, bars_1m/5m 90d, bars_1h+ permanent.
- `lineage_records`, `fills`, `reasoning_traces`, `journal`: permanent (audit core).
- Cold archival to S3 Object Lock (WORM) for tamper-evidence (ADR-0017).

## Access control
- App role: INSERT-only on append-only tables (ADR-0017). UPDATE/DELETE revoked.
- `audit_writer` role for the journal; no other role writes it.
- Migrations run as a privileged role separate from the app role.

## Determinism
- `decision_ts` sourced from Postgres `now()` (ADR-0035) — DB is the clock
  authority on the critical path.
