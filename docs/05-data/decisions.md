# Phase 5 — Locked Decisions

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Single PostgreSQL instance + PITR** | One instance on the VPS, continuous WAL archiving + pgBackRest base backups. RPO ~5 min, RTO ~1 hour. YAGNI on a standby until load justifies a second VPS; WAL archive bounds data loss. |
| 2 | **Keep native PostgreSQL partitioning (no TimescaleDB)** | Phase 3 Decision #2 already locked native RANGE partitions + BRIN, retention via DROP PARTITION. Consistent with locked decisions, no extension dependency. TimescaleDB re-evaluated only if continuous aggregates become a measured need. |
| 3 | **One Redis instance, multi-role, AOF everysec** | Single Redis serves MT5 command queue, results pub/sub, and feature/snapshot cache. AOF everysec sets the durability floor (the queue drives it); cache/pub-sub tolerate it. `volatile-lru` evicts only TTL cache keys — never the queue. |
| 4 | **Backup = WAL + pgBackRest base to S3** | Continuous WAL + weekly full + daily incremental to S3-compatible storage. RPO ~5 min, RTO ~1 hour, monthly restore drills mandatory. Institutional standard for the financial ledger even on one VPS. |
| 5 | **Alembic linear migrations** | One revision per change, explicit up/down, reviewed like code, content-hashed. Append-only tables get additive-only migrations; retention is always DROP PARTITION, never a DELETE migration. |
| 6 | **S3 = backups only in V1** | No data lake / tick archive / backtest artifacts yet. Permanent bars live in PG; ticks age out by design. Deferred uses require their own justified decision when a real consumer exists. |

## Inherited from Phase 3 (unchanged)

- Native partitioned time-series tables, BRIN + B-tree indexes.
- Tiered retention 7d / 90d / permanent via DROP PARTITION.
- Append-only `lineage_records`, `fills`, registry tables.
- `processed_commands` idempotency gate.
- Positions snapshot + fills ledger (event-sourcing split).

## Principles Honored

- **#6 Reproducibility before adaptation**: never-deleted decision tables + PITR backups + hash-audited migrations = replayable state.
- **#9 Replaceability**: provider-agnostic S3 layout; no extension lock-in.
- **#10 Safe state by default**: backup-first posture, restore drills, no silent data loss, idempotent recovery.
- **YAGNI**: no standby, no TimescaleDB, no data lake until a measured need exists.

## Phase Boundary Respected

Phase 5 fixes physical storage, caching, availability, backup, and
migration rules. It does NOT define: logical schema (Phase 3), API
(Phase 9), dashboard (Phase 10), infrastructure/CI (Phase 11), security
(Phase 12), or code (Phase 14+).
