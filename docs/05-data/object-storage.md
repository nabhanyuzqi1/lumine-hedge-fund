# Object Storage Role

## Overview

Decision **D5-6**: S3-compatible object storage is used **only for
backups** in V1. No data lake, no tick archive, no backtest artifact
store yet — those needs do not exist until real backtesting/research
begins, and building them now is speculative (YAGNI).

## Role

| Use | In scope V1? |
|-----|--------------|
| PostgreSQL WAL archive | yes |
| pgBackRest base/incremental backups | yes |
| Long-term tick/bar archive (Parquet) | no — deferred |
| Backtest artifacts / research datasets | no — deferred |

Rationale: permanent bar tables already live in PostgreSQL and ticks are
dropped after 7 days by design. Archiving ticks to Parquet before any
consumer exists adds an export pipeline, cost, and complexity with no
current consumer.

## Bucket layout

```
s3://<bucket>/
  pgbackrest/
    <stanza>/
      backup/     # base + incremental
      archive/    # WAL segments
```

Single bucket, pgBackRest stanza-namespaced. Provider is S3-compatible
(e.g. Backblaze B2 or self-hosted MinIO) — the exact provider is an
infrastructure choice (Phase 11), the layout is fixed here.

## Lifecycle / retention

- Backup objects follow the retention window in
  `availability-backup.md` (full+incremental ~4 weeks, WAL per archive
  window).
- Permanent-table backups (fills, lineage, registry) are covered by the
  same backup chain; their *source* rows are never deleted, so backup
  retention is about restore windows, not about being the only copy.

## Future expansion (explicitly deferred)

When research/backtesting becomes real (Phase 9+), the following may be
proposed as a *new* decision — they are not in scope now:

- Parquet tick/bar archive before partition DROP.
- Backtest artifact and dataset store.
- Model/prompt artifact blobs (if they outgrow the registry tables).

Each requires its own justification and is deferred until a concrete
consumer exists.

## What this document does NOT define

- Provider selection, credentials, encryption (Phase 11/12).
- Export pipeline code (Phase 14+).

## Phase Boundary

This document fixes the backup-only role and bucket layout. It does not
define provider, security, or code, and it defers all archive/artifact
uses to a future justified decision.
