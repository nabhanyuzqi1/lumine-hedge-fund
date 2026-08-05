# Phase 3 — Locked Decisions

## Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Hybrid lineage schema (scalar + JSONB)** | Scalar columns hold what we query and index (book, strategy_id, timestamp, verdict, symbol, size, fill_price); JSONB holds the full decision context (trigger, features, proposal, risk_context) for reproducibility. Fast analytical queries without losing rich context. Append-only, immutable. |
| 2 | **PostgreSQL native partitioned tables for time-series** | PARTITION BY RANGE on timestamp, one parent per timeframe, BRIN indexes for append-ordered data. Keeps tables small, makes retention instantaneous (DROP PARTITION vs slow DELETE). Stays on the PostgreSQL-centric stack from Phase 1. |
| 3 | **Four separate registry tables** | `model_versions`, `prompt_versions`, `strategy_versions`, `policy_versions` — each with id UUID PK, version SEMVER, status ENUM, type-specific fields. One table per versioned artifact; no hardcoding (principle #9); old versions kept forever (principle #6). |
| 4 | **JSON Schema files for payload validation** | One `.json` per stream in `schemas/streams/`, runtime `jsonschema.validate()`. Producer validates before publish, consumer validates after read — both reject invalid payloads. Defense in depth (principle #10). |
| 5 | **JSON wire format for V1, MessagePack upgrade path via adapter** | JSON text is debuggable and universal during build-out. Upgrade to MessagePack happens at the port/adapter boundary (Phase 1 replaceability) — only the transport adapter changes, schemas stay unchanged. Path fixed now; timeline is Phase 14+. |
| 6 | **Tiered retention: 7d / 90d / permanent** | Ticks 7 days, bars_1m/5m 90 days, bars_1h/4h/1d permanent. Tick detail ages out per policy; permanent bar tables preserve reproducibility for old lineage records. Enforced via DROP PARTITION, never row DELETE. |
| 7 | **`lineage_id` as idempotency key** | ExecutionRouter generates `lineage_id` before dispatch; `processed_commands` table uses `INSERT ... ON CONFLICT (lineage_id) DO UPDATE SET replay_count = replay_count + 1, last_replay_at = now(), result = 'duplicate_ignored'`. Replayed commands (stream rewind, crash recovery) are recorded, not re-submitted — no duplicate orders. |
| 8 | **Positions table + fills ledger** | `positions` = mutated current state (snapshot); `fills` = append-only immutable ledger (truth). Event-sourcing pattern: the log is truth, the snapshot is rebuildable convenience. Drift between the two is flagged, never silently auto-corrected. |

## Principles honored

- **#4 Evidence before capital**: reconciliation target is zero drift;
  drift flagged not masked.
- **#5 Books separately attributable**: `book` + `strategy_id` on every
  event and every lineage record.
- **#6 Reproducibility before adaptation**: every decision pins four
  version UUIDs; append-only tables never deleted; permanent market
  data survives forever.
- **#9 Replaceability**: every versioned value resolved via registry
  lookup; no hardcoding; MessagePack upgrade via adapter.
- **#10 Safe state by default**: producer + consumer both validate;
  lineage write blocking ACID; idempotency prevents duplicate orders.

## Phase boundary respected

Phase 3 fixes the data architecture only. It does NOT define: prompt
text (Phase 4), AutoGen configuration (Phase 4), risk math (Phase 7),
MT5 protocol (Phase 8), backtest engine (Phase 9), or code (Phase 14+).
