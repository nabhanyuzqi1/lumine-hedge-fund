# Redis Physical Roles

## Overview

Decision **D5-3**: one Redis instance serves all three physical roles.
This document fixes the keyspace, the durability setting, and the
eviction policy per role. It does not define Redis HA/failover (Phase
11) or client code (Phase 14+).

## Three roles, one instance

| Role | Keys | Persistence need | Why |
|------|------|------------------|-----|
| **Command queue** | `mt5:commands` (LIST) | must survive restart | losing an unexecuted order command = silent missed trade |
| **Results pub/sub** | `mt5:results` (channel) | none (ephemeral) | results also persisted to PostgreSQL; channel is a notification, not the store |
| **Cache** | `feat:*`, `snap:*` | none (rebuildable) | derived from PostgreSQL; safe to lose |

Durability is set **per instance**, so the instance runs **AOF
`everysec`** — the queue role drives the durability floor. Cache and
pub/sub tolerate this; they do not need stricter.

## Persistence configuration

- **AOF enabled, `appendfsync everysec`.** At most ~1 second of queued
  commands lost on crash. Acceptable: the idempotency gate
  (`processed_commands`) plus lineage-first write means a lost queue
  entry is detectable and replayable, never silently dropped.
- **RDB snapshots** left at default as a secondary fast-reload path; AOF
  is the authoritative log.

## Eviction & memory policy

- **Cache keys only** carry TTLs (`feat:*`, `snap:*`). Short TTL (e.g.
  seconds–minutes) since they mirror fast-moving feature snapshots.
- **`mt5:commands` and `mt5:results` have no TTL** — they are consumed,
  not expired.
- Instance `maxmemory-policy`: **do NOT evict the queue.** Cache keys are
  the only eviction candidates. Recommended: `volatile-lru` (evict only
  keys with a TTL = the cache namespace), never `allkeys-*` which could
  evict queue entries.

## Keyspace convention

| Pattern | Type | TTL | Owner |
|---------|------|-----|-------|
| `mt5:commands` | LIST | none | Execution Controller → EA |
| `mt5:results` | PUB/SUB channel | none | EA → backend |
| `mt5:dedup:{order_id}:{attempt_N}` | STRING | 3600s | Execution Controller (Phase 8 dedup) |
| `feat:{symbol}:{name}` | STRING/JSON | seconds–minutes | feature cache |
| `snap:{kind}` | STRING/JSON | short | derived snapshot cache |

Namespacing by prefix keeps the queue (`mt5:*`) clearly separated from
disposable cache (`feat:*`, `snap:*`).

The dedup key carries a TTL (so orphaned attempts eventually clear), but
it must **not** be treated as evictable cache: under memory pressure the
policy must evict `feat:*`/`snap:*` first. If a dedup key is ever lost,
the authoritative gate remains PostgreSQL `processed_commands` — Redis
dedup is a fast-path optimization, not the idempotency of record.

## Failure behavior (principle #10)

- **Redis down** → execution halts to safe state: no new commands are
  dispatched (the blocking lineage write already happened, so the
  decision is recorded and replayable). This matches Phase 8 timeout
  rule ("Redis unavailable" → FAILED with reason).
- **AOF gap on crash** → on recovery, `processed_commands` + lineage
  reconcile which commands were actually executed; replays are recorded,
  not re-executed.

## What this document does NOT define

- Redis Sentinel/Cluster HA (Phase 11 — Infrastructure).
- Connection pooling / client libraries (Phase 14+).
- Cache warming strategy (Phase 14+).

## Phase Boundary

This document fixes the single-instance multi-role split, the AOF
durability floor, the eviction policy, and the keyspace. It does not
define HA topology or client code.
