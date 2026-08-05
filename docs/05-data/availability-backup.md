# Availability, Backup & Disaster Recovery

## Overview

Decision **D5-1** (single instance + PITR) and **D5-4** (WAL + base
backup to S3). PostgreSQL is the system of record and holds the
financial ledger (`fills`, `lineage_records`); its backup posture is
held to an institutional standard even though deployment starts on one
VPS.

## Topology (V1)

```
Single PostgreSQL instance (Linux VPS)
   |-- WAL archiving (continuous) ----> S3-compatible bucket
   |-- pgBackRest base backup --------> S3-compatible bucket
            full: weekly
            incremental: daily
```

No streaming standby in V1 (YAGNI; adds a second VPS and operational
complexity before load justifies it). The WAL archive is what bounds
data loss, not a replica.

## Recovery objectives

| Objective | Target | Mechanism |
|-----------|--------|-----------|
| **RPO** (max data loss) | ~5 minutes | continuous WAL archiving |
| **RTO** (time to restore) | ~1 hour | restore base backup + replay WAL to a fresh VPS (manual) |

RPO ~5 min assumes WAL segment shipping cadence; tighten by lowering the
archive timeout if the business requires nearer-zero loss.

## Backup schedule

| Backup | Cadence | Retention in S3 |
|--------|---------|-----------------|
| WAL segments | continuous | per archive retention window |
| Full base backup | weekly | 4 weeks |
| Incremental | daily | 4 weeks |

Retention of backups is independent of data-table retention: backups of
permanent tables (`lineage_records`, `fills`, registry) must be kept
long enough to satisfy audit/replay needs — those tables are never
deleted at the source, so their backups follow the same "keep forever"
intent within the S3 lifecycle window chosen.

## Restore & DR runbook (outline)

1. Provision fresh VPS, install matching PostgreSQL major version.
2. `pgBackRest restore` latest full + incremental chain.
3. Replay archived WAL to target time (PITR) or to latest.
4. Verify: row counts on `fills`/`lineage_records`, open `positions`
   reconcile vs broker.
5. Repoint application, resume.

**Restore drills are mandatory.** A backup that has never been restored
is not a backup. A restore to a scratch instance is performed on a
scheduled cadence (e.g. monthly) and the result recorded. Scheduling
infrastructure is Phase 11; the requirement is fixed here.

## What survives what

| Failure | Data impact |
|---------|-------------|
| Instance crash, disk intact | none — restart, replay local WAL |
| Disk loss | up to ~5 min (WAL archive gap) |
| VPS destroyed | restore from S3, RTO ~1 hour |

## What this document does NOT define

- Backup tooling install/config code (Phase 14+).
- Scheduling/orchestration (Phase 11).
- Encryption/credentials for S3 (Phase 12 — Security).
- Standby/HA topology (deferred; re-open only when load justifies).

## Phase Boundary

This document fixes the topology, RPO/RTO, backup schedule, and DR
requirements. It does not define automation, security, or code.
