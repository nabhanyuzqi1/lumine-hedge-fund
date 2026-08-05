# Phase 5 — Data Architecture (Physical Storage)

## Overview

Phase 5 defines the physical storage layer: how the logical schemas from
Phase 3 are deployed, sized, cached, backed up, and recovered. Phase 3
fixed *what the data looks like*; Phase 5 fixes *how it is physically
stored and protected* at multi-million-record scale.

Phase 5 does NOT define: API design (Phase 9), dashboard (Phase 10),
infrastructure/CI (Phase 11), security (Phase 12), or code (Phase 14+).

## Relationship to Phase 3

Phase 3 locked the logical schemas (tables, columns, payload envelopes,
partition strategy, retention tiers). Those decisions are inherited
unchanged. Phase 5 adds only what Phase 3 explicitly deferred to the
physical layer:

- physical ERD and growth estimates,
- Redis physical roles (cache / queue / pub-sub),
- PostgreSQL availability and backup/DR,
- schema migration standard,
- object storage role.

Nothing in Phase 5 re-opens a locked Phase 3 decision.

## Documents

| Document | Purpose |
|----------|---------|
| `physical-erd.md` | Full physical ERD, relationships, per-table growth, retention, indexes, expected queries |
| `redis-roles.md` | Redis physical roles: cache, MT5 command queue, results pub/sub, persistence, keyspace |
| `availability-backup.md` | PostgreSQL topology, PITR backup, RPO/RTO, disaster recovery runbook outline |
| `migrations.md` | Alembic migration standard, naming, hash audit, rollback policy |
| `object-storage.md` | S3-compatible object storage role (backup only), bucket layout, lifecycle |
| `decisions.md` | Locked decisions for Phase 5 |

## Phase Boundary

This phase fixes the physical storage, caching, availability, backup,
and migration rules. It does not define aggregation logic, scheduling
infrastructure, security controls, or production code.
