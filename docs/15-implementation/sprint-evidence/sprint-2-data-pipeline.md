# Sprint 2 — Data Pipeline: Plan & Evidence

**Status:** Approved — gate to Sprint 3 (Decision Engine) opened 2026-08-03
**Date:** 2026-08-02 (updated 2026-08-03)
**Sprint:** 2 (Data Pipeline) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prior sprint:** Sprint 1 (Foundation) — Approved 2026-08-02

---

## 1. Sprint Goal

MT5 bridge protocol, tick→bar data pipeline, feature engineering, and the
first Level 2 integration tests against real PostgreSQL + Redis.

**Exit criteria (from `docs/14-implementation/sprint-plan.md`):**
- MT5 bridge receives ticks and publishes to Redis
- FeatureProvider computes ATR, EMA, RSI, pivot points from live data
- OHLCV bars are written to PostgreSQL partitioned tables
- All Level 2 integration tests pass
- No data loss on Redis restart (AOF recovery — infra concern, verified at config level)

**Additional gates (per CLAUDE.md mandatory rules):**
- `make lint-backend`, `make typecheck-backend` pass with zero errors
- `make test` passes (unit + integration)
- bandit + pip-audit clean
- Independent verification agent returns PASS

---

## 2. Scope

### 2.1 In scope

| Component | Files | Description |
|-----------|-------|-------------|
| MT5 bridge protocol | `src/lumine/mt5_bridge/protocol.py` | Pydantic schemas for command (Python→EA) and result (EA→Python) per Phase 8 `mt5-integration.md` |
| MT5 bridge client | `src/lumine/mt5_bridge/bridge.py` | `MT5BridgeClient`: `send_command` (LPUSH + 30s result await), result subscriber, dedup gate before dispatch |
| Partition lifecycle | `src/lumine/data/partitions.py` | `ensure_partitions()` — daily ticks + monthly bars_1m/5m child partitions + DEFAULT safety-net |
| Partition migration | `alembic/versions/0003_add_default_partitions.py` | DEFAULT partitions for `ticks`, `bars_1m`, `bars_5m` |
| Tick ingest | `src/lumine/data/ingest/tick_ingest.py` | Tick → Redis `ticks:{symbol}` buffer + PG `ticks` partition (append-only) |
| OHLCV aggregator | `src/lumine/data/ingest/aggregator.py` | Timer-driven on bar close; builds OHLCV from buffered ticks; writes to `bars_1m`/`bars_5m` |
| FeatureProvider | `src/lumine/features/provider.py` | Async `get_features(symbol, timeframe, count) -> FeatureSnapshot`; reads bars from PG + ticks from Redis; caches via `feat:{symbol}:{name}` |
| Indicators | `src/lumine/features/indicators.py` | ATR, EMA, RSI, pivot points — pure functions |
| Integration test infra | `tests/integration/conftest.py` | testcontainers Postgres + Redis; alembic upgrade head; flushdb per test |
| Level 2 tests | `tests/integration/test_*.py` | tick→bar pipeline, FeatureProvider, MT5 bridge Redis roundtrip, partition lifecycle |

### 2.2 Out of scope (deferred)

- **`price.events` stream transport** — deferred to Sprint 3 (Decision Engine). Sprint 2 caches features to `feat:` only; stream publication is a decision-engine concern.
- **Real MT5 EA integration** — Sprint 2 builds the Python-side bridge + protocol; EA-side bridge + live connection is Sprint 3 paper-trading prep.
- **Volume profile indicator** — not in `test-levels.md` Level 1 list; deferred.
- **Redis AOF/eviction runtime config** — infra concern (Phase 11 `docker-compose.yml`). Sprint 2 verifies the config target, not runtime enforcement.
- **Bar aggregation from historical backfill** — Sprint 2 handles live tick-driven aggregation only; historical backfill is Sprint 3 backtest harness.

---

## 3. Architectural Decisions

Resolving the 7 ambiguities identified during contract research:

### D2-1: Tick schema — ORM authoritative

**Decision:** The `Tick` ORM model (`bid/ask/last/volume/source`, composite PK `(ts, symbol)`) is authoritative for tick ingest.

**Why:** `stream-payloads.md` `mt5.marketdata` payload (`ts, symbol, ohlcv`) describes the *SSE client-facing* shape, not the storage shape. The ORM is already migrated (0001) and matches the raw broker feed. SSE projection (tick → ohlcv summary) is a Sprint 4 API concern.

**How to apply:** `tick_ingest.py` writes `Tick` rows with all 5 fields. Do not adapt to the stream payload shape here.

### D2-2: `ticks:{symbol}` Redis namespace — keep, document gap

**Decision:** Keep the `ticks:{symbol}` LIST buffer in `redis_client.py`. Flag the documentation gap in `redis-roles.md` (out of Sprint 2 code scope; tracked as a doc TODO).

**Why:** The buffer is already implemented, tested implicitly by Sprint 1, and serves the aggregator's read path. Removing it would break the pipeline. The doc omission is a doc bug, not a code bug.

**How to apply:** No code change. Add a `# TODO(doc): add ticks:{symbol} to redis-roles.md keyspace` comment in `redis_client.py`.

### D2-3: FeatureProvider interface — async, returns FeatureSnapshot

**Decision:**
```python
class FeatureProvider:
    async def get_features(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> FeatureSnapshot: ...
```
`FeatureSnapshot` is a Pydantic model: `symbol`, `timeframe`, `bars: list[Bar]`, `indicators: dict[str, float]` (atr, ema, rsi, pivots), `as_of_ts: datetime`.

**Why:** Async matches the async SQLAlchemy session + async Redis client already in place. A typed snapshot (not bare dict) enforces the contract with Sprint 3 analysts and is unit-testable.

**How to apply:** `features/provider.py` defines `FeatureProvider` + `FeatureSnapshot` + `Bar` types. Reads bars from PG via `get_session()`, recent ticks from `get_recent_ticks()`, computes indicators via pure functions in `indicators.py`, caches each indicator under `feat:{symbol}:{name}`.

### D2-4: Partition lifecycle — runtime module + DEFAULT safety-net

**Decision:** New `data/partitions.py` with `ensure_partitions(session, *, lookhead_periods: int = 2)` that creates child partitions for the current + next N periods (daily for `ticks`, monthly for `bars_1m`/`bars_5m`). Migration 0003 adds `DEFAULT` partitions as a safety-net so an out-of-range tick never crashes ingest.

**Why:** `migrations.md` explicitly states partition pre-creation is a runtime lifecycle job, not a migration. But without a DEFAULT partition, a tick arriving before `ensure_partitions` runs → insert fails → pipeline halt (violates "safe state by default"). The DEFAULT partition is the safety net; `ensure_partitions` is the proactive creation.

**How to apply:** `ensure_partitions` runs at startup (wired in Sprint 3 app lifecycle) and on a schedule. Migration 0003 creates `ticks_default`, `bars_1m_default`, `bars_5m_default`. Unit-test the DDL generation logic without a live DB (string assertion on generated SQL).

### D2-5: Bar aggregation trigger — timer-driven on bar close

**Decision:** Aggregation is **timer-driven on bar boundary**. The aggregator maintains an in-memory `BarBuilder` per `(symbol, timeframe)` that accumulates ticks; on the timeframe boundary (e.g. minute rollover for `M1`), it flushes the completed bar to PG.

**Why:** Tick-driven (per-tick PG write) is write-amplified and produces partial bars. Timer-driven produces clean, complete bars with one write per bar. Hybrid adds complexity for no Sprint 2 benefit.

**How to apply:** `aggregator.py` exposes `BarBuilder` (accumulates ticks, emits bar on `flush()`) and `OHLCVAggregator` (orchestrates builders, runs a periodic flush task). Unit-test `BarBuilder` with a synthetic tick sequence asserting OHLCV correctness; integration-test the full flush-to-PG path.

### D2-6: `price.events` transport — defer to Sprint 3

**Decision:** Sprint 2 does NOT implement `price.events` stream publication. Features are cached to `feat:{symbol}:{name}` only.

**Why:** `price.events` is consumed by the decision engine (Sprint 3). Its transport (Redis Stream XADD vs pub/sub) is a decision-engine design choice that depends on how analysts subscribe. Building it now would be speculative.

**How to apply:** `FeatureProvider` writes to `feat:` cache. A `# TODO(sprint-3): publish to price.events stream` marker in `provider.py`.

### D2-7: Default partitions — yes, as safety-net

**Decision:** Yes. See D2-4. Migration 0003 adds DEFAULT partitions for all three partitioned tables.

---

## 4. Deliverables

| # | Deliverable | Files | Tests |
|---|-------------|-------|-------|
| 1 | MT5 bridge protocol | `mt5_bridge/protocol.py`, `mt5_bridge/__init__.py` | `tests/unit/test_mt5_protocol.py` |
| 2 | MT5 bridge client | `mt5_bridge/bridge.py` | `tests/unit/test_mt5_bridge.py` (mocked redis) |
| 3 | Partition lifecycle | `data/partitions.py`, `alembic/versions/0003_*` | `tests/unit/test_partitions.py` |
| 4 | Tick ingest | `data/ingest/__init__.py`, `data/ingest/tick_ingest.py` | `tests/unit/test_tick_ingest.py` |
| 5 | OHLCV aggregator | `data/ingest/aggregator.py` | `tests/unit/test_aggregator.py` |
| 6 | Indicators | `features/__init__.py`, `features/indicators.py`, `features/types.py` | `tests/unit/test_indicators.py` |
| 7 | FeatureProvider | `features/provider.py` | `tests/unit/test_feature_provider.py` (mocked session+redis) |
| 8 | Integration infra | `tests/integration/conftest.py`, `pyproject.toml` (testcontainers dep) | — |
| 9 | Level 2 integration tests | `tests/integration/test_tick_to_bar_pipeline.py`, `test_feature_provider.py`, `test_mt5_bridge_redis.py`, `test_partitions.py` | — |

---

## 5. Quality Gates

Same six gates as Sprint 1, plus integration tests now execute:

| Gate | Tool | Command | Target |
|------|------|---------|--------|
| Lint | ruff | `make lint-backend` | 0 errors |
| Types | mypy | `make typecheck-backend` | 0 errors |
| Unit tests | pytest | `make test-unit` | all pass |
| Integration tests | pytest + testcontainers | `make test-integration` | all pass, < 2 min |
| SAST | bandit | `uv run bandit -r src/` | 0 High; Medium only if accepted |
| Deps | pip-audit | `uv run pip-audit` | No known vulns |
| Coverage | pytest-cov | `--cov=src/lumine` | ≥ 85% overall (new modules ≥ 95%) |

---

## 6. Dependencies

- **Phase 8:** `mt5-integration.md` (Redis command queue, result pub/sub, idempotency)
- **Phase 5:** `physical-erd.md`, `migrations.md` (partitioning), `redis-roles.md` (namespaces)
- **Phase 3:** `time-series-schema.md` (tick/bar), `stream-payloads.md` (feature payload)
- **Phase 13:** `test-levels.md` (Level 2 definition, testcontainers policy)
- **Sprint 1:** `data/models.py`, `data/session.py`, `data/redis_client.py`, `shared/config.py`, `shared/types.py`

New dev dependency:
- `testcontainers[postgres,redis]>=4.0.0`

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| testcontainers slow / flaky on macOS | Medium | Medium | Session-scoped containers; reuse across modules; < 2 min budget |
| Partition DDL errors on real PG | Low | High | DEFAULT safety-net; integration test `ensure_partitions` against testcontainers PG |
| Aggregator tick-rate edge cases (gaps, out-of-order) | Medium | Medium | `BarBuilder` handles gaps (emits bar with last close); out-of-order rejected with log |
| mypy strict on Pydantic + Decimal indicator math | Medium | Low | Pre-type the indicator signatures; use `Decimal` consistently |
| Redis namespace mismatch with docs | Low | Low | D2-2 decision; doc TODO tracked |

---

## 8. Acceptance Criteria Check

| Exit criterion | Status | Evidence |
|----------------|--------|----------|
| MT5 bridge receives ticks and publishes to Redis | ✅ | `bridge/client.py` + `bridge/types.py`; `test_bridge.py` (2 int) + `test_bridge_client.py` (6 unit) + `test_bridge_types.py` (16 unit) pass |
| FeatureProvider computes ATR, EMA, RSI, pivots from live data | ✅ | `features/provider.py` + `features/indicators.py`; `test_feature_provider.py` (4 int + 6 unit) + `test_indicators.py` (18 unit) pass |
| OHLCV bars written to PostgreSQL partitioned tables | ✅ | `data/collector.py` + `data/persistence.py`; `test_collector_persistence.py` (6 int) + `test_collector.py` (12 unit) pass |
| All Level 2 integration tests pass | ✅ | 17/17 pass in 10.74s (testcontainers PG+Redis) |
| No data loss on Redis restart (AOF) | ⚠️ | Config-level only — AOF everysec is Phase 11 `docker-compose.yml` concern; not runtime-enforced in Sprint 2 |
| Lint / type / SAST / deps | ✅ | ruff 0 errors; mypy 0 issues (36 files); bandit 0 High / 1 Medium (B104 accepted — container API bind); pip-audit clean |
| Independent verification | ✅ | Verification agent PASS (2026-08-03): 9/9 checks pass — migration reproducibility, test suite (187 pass), lint, types, SAST, deps, dead code removal, lint fix, evidence accuracy; adversarial probe confirmed migration idempotency |

---

## 9. Sign-off

Sprint 2 implementation is complete and APPROVED. All exit criteria met
except the AOF runtime-enforcement caveat (Phase 11 infra concern,
tracked as config-level only). Independent verification returned PASS
(2026-08-03). Gate to Sprint 3 (Decision Engine) opened 2026-08-03.

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 10. Test Results (2026-08-03 close-out)

| Gate | Command | Result |
|------|---------|--------|
| Unit tests | `pytest tests/unit/` | 170/170 pass (2.58s) |
| Integration tests | `pytest tests/integration/` | 17/17 pass (10.74s, testcontainers PG 16 + Redis 7) |
| Migration reproducibility | manual `alembic upgrade head` on clean testcontainer | 0001→0002→0003 pass, rc=0 |
| Lint | `ruff check src/ tests/` | 0 errors |
| Types | `mypy src/lumine` | 0 issues, 36 files |
| SAST | `bandit -r src/` | 0 High, 1 Medium (B104 — accepted) |
| Deps | `pip-audit` | No known vulnerabilities |

**Total: 187 tests pass.**

### DuplicateObjectError investigation

The `DuplicateObjectError` for `registry_status` reported in the prior
session is **not reproducible** on a clean testcontainer. Migration 0001
uses the correct pattern (`ENUM(create_type=False)` + explicit
`op.execute("CREATE TYPE ...")`), so the type is created exactly once.
The error was likely from a dirty container predating the
`_reset_schema.py` reset step, or from a pre-fix version of 0001. No
code change required.

## 11. Reconciliation Notes (plan vs. implementation)

The Sprint 2 plan (section 2.1) listed file paths that differ from the
actual implementation. These are naming choices, not architecture
changes — no ADR required, no Phase 14 spec affected.

| Plan path | Actual path | Reason |
|-----------|-------------|--------|
| `mt5_bridge/protocol.py`, `mt5_bridge/bridge.py` | `bridge/types.py`, `bridge/client.py` | Generic `bridge/` package is multi-broker-ready (CLAUDE.md goal); `mt5_bridge` was over-specific. Dead `mt5_bridge/` package removed 2026-08-03. |
| `data/ingest/tick_ingest.py`, `data/ingest/aggregator.py` | `data/collector.py`, `data/persistence.py` | Flat modules in `data/` chosen over `data/ingest/` subpackage — simpler, YAGNI. `collector.py` handles tick→bar; `persistence.py` handles writes. |
| `features/types.py` `FeatureSnapshot` with `bars: list[Bar]`, `indicators: dict[str, float]` | `FeatureSnapshot` with `indicators: dict[str, Decimal]` + `pivots: PivotPoints`, no `bars` field | Decimal (not float) for financial precision (CLAUDE.md design philosophy); `bars` dropped from snapshot (provider returns computed features, not raw bars — callers fetch bars separately if needed). |

These are documented here so Sprint 3 starts from the real structure,
not the plan's paths.
