# Test Levels

## Overview

Seven test levels, each testing a distinct concern at a distinct speed.
Levels 1–4 are blocking CI gates; levels 5–6 are advisory pre-launch
gates; level 7 is mixed (automated blocking, manual advisory).

## Level summary

| Level | Name | Runtime | Environment | LLM | MT5 | Gate |
|-------|------|---------|-------------|-----|-----|------|
| 1 | Unit | < 30s | CI | No | No | Blocking |
| 2 | Integration | < 2m | CI | No | No | Blocking |
| 3 | Contract | < 3m | CI | No | No | Blocking |
| 4 | System | < 5m | CI | Mock | Mock | Blocking |
| 5 | Backtest | < 10m | CI/Staging | Mock | Mock | Advisory |
| 6 | Paper Trading | Weeks | Staging | Real | Paper | Advisory |
| 7 | Security | < 5m + Manual | CI/Manual | No | No | Mixed |

## Level 1 — Unit Tests

**Scope:** Deterministic functions only — no I/O, no LLM, no MT5.

- Risk validator: position limit checks, exposure calculations, kill-switch
  enforcement, strategy book limits.
- Sizing calculator: position sizing formulas, risk-per-trade calculations,
  attribution tagging.
- Feature computation: ATR, EMA, RSI, OHLC aggregation, pivot points.
- Lineage serializer: JSON structure validation, version pinning, artifact
  reference resolution.
- Reconciliation logic: fill comparison, slippage calculation, drift
  detection.
- HMAC signature verifier: signature generation and verification, timestamp
  window validation, nonce handling.
- JSON schema validator: Phase 4 proposal schemas, agent output schemas.
- Trade management rules: breakeven triggers, trailing stop (ATR-based),
  partial close logic.

**Tool:** `pytest` + `pytest-cov`

**Coverage target:** ≥ 80% line coverage for all deterministic modules.
No coverage target for AutoGen orchestration code (tested at contract
level). No coverage target for infrastructure code (FastAPI routers,
middleware, Caddy config — tested at contract and system level).

**Mock policy:** Mock only at I/O boundaries (database calls, Redis
operations, HTTP requests, MT5 API calls). Internal logic must never
be mocked — if a function cannot be tested without mocking its internal
dependencies, the function is too coupled and should be refactored.

**Example:**
```python
def test_risk_validator_rejects_overexposure():
    validator = RiskValidator(max_exposure_pct=0.02)
    proposal = create_proposal(position_size=0.03)  # 3% of equity
    result = validator.check(proposal, current_exposure=0.0)
    assert result.decision == "REJECT"
    assert "exceeds max exposure" in result.reason.lower()
```

## Level 2 — Integration Tests

**Scope:** Interactions between deterministic modules and their data stores.

- RiskValidator reads from PostgreSQL positions table.
- FeatureProvider reads from PostgreSQL time-series + Redis tick cache.
- LineageWriter writes to PostgreSQL lineage_records table.
- ExecutionRouter writes to Redis command stream.
- HMAC verifier integration with API key lookup in PostgreSQL.

**Tool:** `pytest` + `testcontainers` (Python `testcontainers` library for
PostgreSQL and Redis ephemeral containers)

**Policy:** Use real database via testcontainers — no mocks for PostgreSQL
or Redis. Only MT5 bridge and LLM gateway are mocked. Test data is seeded
from SQL files in the repository.

**Runtime target:** < 2 minutes. Testcontainers startup is the dominant
cost; reuse containers across test modules where possible.

**Example:**
```python
def test_lineage_writer_persists_and_reads():
    pg = PostgresContainer("postgres:16").start()
    # Run migrations, seed data
    writer = LineageWriter(pg.get_connection_string())
    lineage = writer.write(decision_cycle_fixture)
    # Verify read-back
    reader = LineageReader(pg.get_connection_string())
    assert reader.get(lineage.id) == lineage
```

## Level 3 — Contract Tests

**Scope:** API contracts (Phase 9 REST + SSE), AutoGen agent output schemas
(Phase 4), prompt version immutability, Phase 9 error envelope, and SSE
reconnect/replay semantics.

**REST contract tests:**
- Every endpoint has at least one test per response code (200, 400, 401,
  403, 404, 409, 429).
- Response envelope matches Phase 9 `error-contract.md` structure.
- Auth headers validated (missing, invalid, expired, wrong scope).
- Pagination and idempotency key behavior.

**SSE contract tests:**
- Heartbeat delivery within expected interval.
- Event type validation against Phase 9 `sse-api.md`.
- Envelope structure matches Phase 3 stream payload envelope.
- Reconnect with `Last-Event-ID` — verify gap-fill or `gap_detected`.
- Behavior on 401/403 (no reconnect per Phase 9 `sse-api.md` rule).

**Schema contract tests:**
- Every AutoGen agent output validates against its Phase 4 JSON schema.
- Edge cases: missing required fields, wrong types, out-of-range values.
- Confidence must be in [0.0, 1.0].
- Bias must be in enum values.
- Citations must be a list (can be empty, cannot be null).

**Tool:** `pytest` + `httpx` (REST), `pytest-asyncio` (SSE client),
Python `jsonschema` library (schema validation)

**Runtime target:** < 3 minutes.

**Example:**
```python
async def test_sse_reconnect_with_last_event_id():
    # Connect, receive 3 events, disconnect
    # Reconnect with Last-Event-ID of event 2
    # Verify event 3 is replayed (or gap_detected if buffer expired)
    events = await collect_sse_events(stream_url, headers=auth_headers)
    event_ids = [e["id"] for e in events[:3]]
    await disconnect()
    replayed = await collect_sse_events(
        stream_url,
        headers={**auth_headers, "Last-Event-ID": event_ids[1]},
    )
    assert replayed[0]["id"] == event_ids[2]
```

## Level 4 — System Tests

**Scope:** Full decision cycle end-to-end: trigger → feature computation →
LLM committee → risk validation → sizing → lineage write → execution
dispatch → fill → reconciliation. LLM and MT5 are mocked.

**Tool:** `pytest` + Docker Compose (test profile). All services except
LLM gateway and MT5 bridge run as real containers. LLM gateway is mocked
with canned AutoGen responses. MT5 bridge is mocked with simulated fills.

**Policy:**
- LLM mock returns pre-recorded AutoGen committee outputs covering
  multiple scenarios: strong buy, strong sell, neutral, split committee,
  CIO override, debate triggered, debate not triggered.
- MT5 mock returns simulated fills with configurable: latency, slippage,
  partial fill probability, rejection probability.
- Every test scenario includes a lineage assertion: the lineage record
  must be written before dispatch, and must contain all required fields.
- Safe-state assertion: if any component fails, the system must not
  dispatch an order.

**Runtime target:** < 5 minutes.

**Example:**
```python
def test_full_decision_cycle_buy_signal():
    # Inject trigger, mock LLM returns "strong buy" proposal
    # Risk validator approves
    # Sizing calculator produces position size
    # Lineage is written
    # Execution is dispatched to mock MT5
    # Mock MT5 returns fill
    # Reconciliation confirms fill matches expected
    lineage = run_decision_cycle(trigger_fixture, llm_mock="strong_buy")
    assert lineage.proposal.action == "BUY"
    assert lineage.risk_decision == "APPROVE"
    assert lineage.fill is not None
    assert lineage.reconciliation_drift == 0.0

def test_lineage_write_failure_halts_dispatch():
    # Simulate PostgreSQL write failure
    # Verify no dispatch occurs
    # Verify safe state is entered
    with simulate_db_failure():
        with pytest.raises(LineageWriteError):
            run_decision_cycle(trigger_fixture)
    assert_no_order_dispatched()
```

## Level 5 — Backtest Tests

**Scope:** Replay historical OHLCV data through the same decision engine
used in production. Mock LLM responses, simulated fills. Produce
performance metrics and lineage records.

**Tool:** Custom backtest harness (Python) — reads historical data from
PostgreSQL, injects into FeatureProvider, runs decision cycle, simulates
fills with a pessimistic slippage model.

**Metrics output:**
- Sharpe ratio, Sortino ratio, max drawdown, max drawdown duration
- Win rate, profit factor, average win / average loss
- Total trades, total return, annualized return
- Lineage record count (must equal trade count — no gaps)

**Policy:**
- Same code path as live — no conditional branches for backtest mode.
- LLM mock via fixture injection (same mechanism as system test).
- Slippage model: bid/ask spread + 0.1–0.5 pip random, 50–200ms latency
  random, 5% partial fill probability, 2% rejection probability.
- Gate: Sharpe > 0, max drawdown < 20%, profit factor > 1.0. These are
  sanity checks, not performance targets.

**Runtime target:** < 10 minutes for 90 days of 1-hour bar data.

**Full specification:** See `backtest-paper.md`.

## Level 6 — Paper Trading Tests

**Scope:** Live market data, real MT5 connection (paper/demo account),
real LLM calls. Continuous operation for minimum 2 weeks before live
launch.

**Tool:** Staging Docker Compose environment on the same VPS. Separate
database, Redis DB number, and Docker network. MT5 connected to demo
account.

**Policy:**
- Same container images as production (SHA-pinned).
- Real LLM calls with cost tracking (separate from production budget).
- Every decision produces a lineage record — verify zero gaps.
- Zero order errors tolerated.
- Alert on staging anomalies (but not critical-pager priority).

**Full specification:** See `backtest-paper.md`.

## Level 7 — Security Tests

**Scope:** SAST, secret scanning, dependency audit, container scanning,
config audit, and manual penetration test.

**Automated (CI, every push):**
- Bandit: Python SAST (high severity → block)
- Semgrep: multi-language patterns (error severity → block)
- Gitleaks: secret scanning (any finding → block)
- pip-audit + npm audit: dependency audit (critical/high → block, D12-5)
- Trivy: container scan (critical → block, high → block)

**Config audit (staging + monthly cron):**
- Caddy config validation
- UFW rules audit
- Docker daemon config check
- Backup encryption verify

**Manual (pre-launch + quarterly):**
- Grey-box penetration test (3-day engagement)
- Scope: API auth, SSE, SSH, CORS, Grafana, Docker isolation
- Acceptance: no critical or high findings open at launch

**Full specification:** See `security-testing.md`.

## Level relationship

```
Level 1 (Unit)          ── fastest, most isolated ──
Level 2 (Integration)   ── DB/Redis interactions ──
Level 3 (Contract)      ── API + schema compliance ──
Level 4 (System)        ── full cycle with mocks ──
Level 5 (Backtest)      ── historical replay ──
Level 6 (Paper)         ── live market, no real capital ──
Level 7 (Security)      ── automated + manual ──
```

Each level builds on the confidence of the previous level. A unit test
failure means the function is broken. An integration test failure means
the function interacts incorrectly with its data stores. A contract test
failure means the API or schema is broken. A system test failure means
the orchestration is broken. A backtest failure means the strategy
produces negative outcomes with historical data. A paper trading failure
means the strategy produces errors with live data. A security test
failure means a vulnerability exists.

## What this document does NOT define

- Concrete test code, fixtures, or seed data (Phase 14+).
- Coverage configuration and threshold per module (Phase 14+).
- Testcontainers orchestration code (Phase 14+).
- Docker Compose test profiles (Phase 14+).

## Phase boundary

Test levels, their scope, tools, runtime targets, and gate policies are
fixed here. Test code and configuration belong to Phase 14+.