# Backup, Disaster Recovery & Secrets Injection

## Overview

Data-protection architecture per D11-5 and D11-6. A backup that has never
been restored is not a backup — restore verification is an alerting
obligation (observability.md), not an optional check.

## Backup schedule (backup-sidecar, cron container)

| Asset | Mechanism | Frequency | Retention |
|-------|-----------|-----------|-----------|
| PostgreSQL | `pg_dump` custom format + continuous WAL archiving | dump daily 02:00 UTC; WAL streaming | 30 daily + 12 monthly |
| Redis | AOF (everysec) + file copy | AOF continuous; copy daily | 7 days |
| Lineage archive & news cache volumes | `rclone sync` | daily | 30 days |
| Compose config + `.env.enc` | Git repository (already versioned) | per commit | permanent |

- Upload path: `rclone` with a **crypt remote** (client-side encrypted) to
  Backblaze B2 / S3. This is the only egress added by Phase 11, approved
  explicitly in D11-5.
- Backup job emits metrics to Prometheus; two consecutive failures →
  critical alert.

## Restore verification (binding)

- Monthly automated restore test: latest dump restored into an ephemeral
  PostgreSQL container; row counts and lineage-integrity checks run; result
  reported to Prometheus.
- Failed restore test → critical alert (listed in observability.md).

## RTO / RPO / SLO targets (D11-DR)

| Surface | RTO | RPO | SLO |
|---------|-----|-----|-----|
| Critical path (trading) | 15 min | 1 min (WAL) | 99.9% |
| Analytics (lineage/fills) | 4 h | 5 min (WAL) | 99.5% |
| Audit (journal + WORM anchor) | 1 h | 0 (append-only + WORM, ADR-0017) | 99.99% |
| Market data (ticks/bars) | 1 h | 15 min (re-ingestable from broker) | 99.5% |
| Frontend | 30 min | n/a (stateless) | 99.9% |

RPO=0 for audit because the journal is append-only and WORM-anchored; no
committed transaction is ever lost. The monthly restore test
(`docs/90-governance-and-operations/94-runbooks/restore-test.md`) proves
these targets are achievable — targets without a drill are aspirations.

## Disaster recovery

**Targets:** RPO ≤ 24 h (dump) / ≤ 5 min (WAL). RTO: hours, via the manual
runbook below. (The table above tightens these to SLO-grade targets; this
section's looser numbers are the historical floor.)

**Runbook (summary — the full step-by-step lives in
`docs/90-governance-and-operations/94-runbooks/restore-test.md` for the
drill and below for real DR):**

1. Provision new Linux VPS (same baseline sizing, topology.md).
2. Install Docker + Compose; clone the infrastructure repository.
3. Retrieve the age key from the operator password manager; decrypt
   `.env.enc` → `.env`.
4. `rclone copy` the latest backup set from B2/S3.
5. Restore PostgreSQL (dump + WAL replay to latest point) and Redis AOF.
6. `docker compose up -d`; verify healthchecks; re-point DNS to the new
   node.
7. Confirm kill-switch state and open positions against broker records
   before resuming scheduler (broker-side SL/TP has protected positions
   throughout, per Phase 1).

Trading safety during total VPS loss: all open orders carry broker-side
SL/TP (Phase 1 safety net), so positions remain protected while DR
proceeds.

## Secrets injection (D11-6)

- **At rest:** one encrypted `.env.enc` (SOPS + age) in the private repo —
  the only secret material that ever enters Git.
- **Key custody:** age private key in (a) GitHub Actions secret for deploy,
  (b) operator password manager for local/DR use. Nowhere else.
- **At runtime:** CI decrypts on-target over SSH; containers receive values
  as environment variables at `compose up`. No secrets in image layers, no
  secrets in logs, no secrets on the CI runner workspace.
- **Rotation:** edit → `sops` re-encrypt → commit → deploy. Access policy,
  key-holder list, and audit requirements are Phase 12 scope.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| VPS total loss | This runbook + verified backups + broker-side SL/TP |
| Disk exhaustion (WAL + telemetry) | Retention limits (observability.md), disk alert at 75%, local log rotation |
| Backup corruption (silent) | Monthly restore test with critical alerting |
| Deploy key compromise | Dedicated non-root deploy key scoped to `/srv/lumine`; hardening policy = Phase 12 |
| Vercel outage | Dashboard only; trading unaffected; kill switch operable via direct API/CLI |

## What this document does NOT define

- Concrete rclone/SOPS configuration files, cron expressions in manifests
  (Phase 14+).
- Security policy: who may hold keys, audit cadence (Phase 12).
- Backup integrity test code (Phase 14+).

## Phase boundary

Backup, DR, and secrets-injection architecture are fixed here.
Implementation belongs to Phase 14+.
