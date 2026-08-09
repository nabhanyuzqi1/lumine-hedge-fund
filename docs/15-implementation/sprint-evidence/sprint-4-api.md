# Sprint 4 — API Layer (Phase 9 Contract): Plan & Evidence

**Status:** Implementation complete — full gate PASS (ruff / mypy strict / pytest 480 passed). Approval gate granted 2026-08-09 — frontend F-Sprint 1 (G11) in progress.
**Date:** 2026-08-09 (plan + implementation + gate)
**Sprint:** 4 (API Layer) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prior sprint:** Sprint 3 (Decision Engine) — Approved 2026-08-06

---

## 1. Sprint Goal

Close all open Phase 9 API contract gaps identified in the 2026-08-08
audit, so the API surface exactly matches the locked `docs/09-api/`
specs (rest-api.md, auth.md, error-contract.md, sse-api.md), and the
full gate (lint, types, unit + contract tests) passes with zero errors.

**Exit criteria (from `sprint-4-completion-plan.md` G1–G12):**
- All 9 routers mounted under `/api/v1` prefix (G1)
- SSE exposes exactly the 6 spec channels with per-channel query params and spec event names (G2)
- Idempotency: same key+body → 200 + `meta.idempotent_replay: true`; same key+different body → 409 `CONFLICT`; 1h window (G3)
- Rate limiter wired into all write routes; 429 `RATE_LIMITED` + `Retry-After` (G4)
- Level-3 contract coverage complete: credentials, envelope, error codes, idempotency, rate limit, pagination, SSE frames (G5)
- API layer committed (G6)
- Monitoring module: request logging + `trace_id` propagation + `X-Request-ID` echo (G7)
- Full gate PASS + evidence file + approval gate (G8)

**Additional gates (per CLAUDE.md mandatory rules):**
- `ruff check` + `ruff format --check` zero errors
- `mypy --strict` zero errors
- `pytest tests/unit tests/contract` all pass
- Independent verification agent returns PASS for non-trivial implementation

---

## 2. Scope

### 2.1 In scope (G1–G8)

| Component | Files | Description |
|-----------|-------|-------------|
| URL prefix | `api/app.py` | All 9 routers mounted under `/api/v1`; `/health` stays at root; contract tests use versioned paths |
| SSE stream router | `api/routers/streams.py` | Rewritten to the 6 spec channels (`market-data`, `analyst-outputs`, `ic-decisions`, `cio-proposals`, `risk-assessments`, `execution-orders`); per-channel query params per `sse-api.md:72-77`; spec event names (`market_data`, `analyst_output`, `ic_decision`, `cio_proposal`, `risk_assessment`, `execution_order`); heartbeat comment lines (5s market, 15s others); `stream_open`/`stream_resumed` lifecycle; `Last-Event-ID` replay from per-channel ring buffer (1000 events, 5-min retention); per-key (20) / per-host (1000) connection limits |
| Idempotency middleware | `api/middleware/idempotency.py` | Pure ASGI, POST-only, `X-Idempotency-Key`; Redis `lumine:idem:{api_key}:{method}:{path}:{idem_key}`; SHA-256 body hash; replay → 200 original envelope + `meta.idempotent_replay: true`; different body → 409 `CONFLICT` envelope; 1h TTL; fail-open on Redis outage |
| Rate limiting wiring | `api/middleware/rate_limit.py` + routers | `rate_limit_dependency` wired into all 10 write routes (orders, rpc, admin, workflows); Redis sliding-window zset; 429 `RATE_LIMITED` + `Retry-After` preserved through envelope handler; limit ≤0 disables |
| Error envelope | `api/middleware/envelope.py` | Success/error both honor inbound `X-Request-ID` → `meta.request_id` / `error.trace_id`; code mapping (MISSING_AUTH, INVALID_SIGNATURE, EXPIRED_TIMESTAMP, REVOKED_KEY, REPLAY_DETECTED, NOT_FOUND, RATE_LIMITED, INSUFFICIENT_SCOPE, VALIDATION_FAILED, CONFLICT, RISK_REJECTED, KILL_SWITCH_ACTIVE, ...) |
| Request logging | `api/middleware/logging.py` | structlog access logs w/ `trace_id`/`api_key` contextvars; `X-Request-ID` response echo; ENV var overrides; wired outermost in `app.py` |
| Contract tests | `tests/contract/test_api_contract.py` | Level-3 suite expanded to 30 tests (auth codes, envelope consistency, trace_id echo, idempotency replay/conflict, rate limit 429 + Retry-After + disabled, pagination, SSE frames, streaming responses) with FakeRedis stand-in |
| Spec reconciliation | `docs/15-implementation/spec-reconciliation.md` | Monitoring (G7) row updated `api/middleware/logging.py`; drift policy enforced |

### 2.2 Out of scope (deferred)

- **Real multi-worker SSE fan-out** — process-local ring buffer is adequate for the documented single-worker deployment; Redis stream backing is a port/adapter replacement per `sse-api.md` (event surface, filtering, reconnect contract fixed here).
- **Metrics (Prometheus) + distributed tracing** — logging + request tracing done (G7); metrics/tracing are sprint 5 (G12) concern.
- **Integration suite (G9) / env-sensitivity fix (G10)** — blocked on Docker Desktop (user action).
- **Frontend F-Sprints 1–6 (G11)** — separate approval gate before starting.
- **Sprint 5 hardening (G12)** — OpenAPI generation, coverage gate, security scans — separate approval gate.

---

## 3. Implementation Notes

- Middleware stack in `app.py` (Starlette: last added = outermost):
  `RequestLoggingMiddleware` → `IdempotencyMiddleware` → `CommonEnvelopeMiddleware` → routes.
- Contract tests drive the private `streams._event_stream` generator directly
  with a fake request to verify SSE frames without holding a connection.
- SSE test philosophy: heartbeat is a comment line (`: heartbeat`) that does
  NOT increment the event ID; `stream_open` is always first; `stream_resumed`
  only on `Last-Event-ID` reconnect with `gap_detected` flag.

---

## 4. Quality Gates (G8 full gate — 2026-08-09)

| Gate | Command | Result |
|------|---------|--------|
| Lint | `ruff check .` | PASS — All checks passed (133 files) |
| Format | `ruff format --check .` | PASS — 133 files already formatted |
| Types | `mypy src` (strict) | PASS — Success: no issues found in 68 source files |
| Unit tests | `pytest tests/unit -q` | PASS — 448 passed in 8.79s |
| Contract tests (L3) | `pytest tests/contract -q` | PASS — 32 passed (30 + 2 SSE contract tests added post-verifier) |
| Full suite | `pytest tests/unit tests/contract -q` | PASS — 480 passed |
| SSE frames | `test_sse_stream_open_and_heartbeat_frames` | PASS (included in 30) |
| Idempotency | `test_idempotency_replay_returns_original_envelope`, `test_idempotency_conflict_on_different_body` | PASS (after FakeRedis `ex` kwarg fix) |
| Rate limit | `test_rate_limit_429_with_retry_after`, `test_rate_limit_disabled_when_limit_is_zero` | PASS (included in 30) |
| Trace id | `test_trace_id_echoed_and_consistent`, `test_trace_id_echoed_on_error_path` | PASS (included in 30) |
| SSE timestamp Z (verifier finding V1) | `test_sse_frame_timestamp_has_utc_z_suffix` | FIXED — `_iso_utc_ms` now folds the aware `dt` arg via `astimezone(UTC)`; no more deprecated `utcnow()`; envelope timestamp ends with `Z` |
| SSE replay/gap (verifier finding V2) | `test_sse_replay_resumes_with_gap_detected` | FIXED — direct `stream_resumed` + `gap_detected` + buffered replay coverage added (was untested) |

---

## 5. Independent verification & re-verification (2026-08-09)

| Finding | Severity | Disposition |
|---------|----------|-------------|
| V1 — SSE envelope timestamps lack `Z` suffix (`_iso_utc_ms` used deprecated naive `dt.utcnow()`; `.replace("+00:00","Z")` never fired). sse-api.md freshness contract requires ISO 8601 ms + `Z`; a spec-conformant client doing `now - meta.timestamp` would hit naive/aware TypeError | High | **Fixed.** `_iso_utc_ms(dt)` now folds the caller's aware `datetime.now(UTC)` via `astimezone(UTC)`; verified `...Z` in frames; contract test `test_sse_frame_timestamp_has_utc_z_suffix` added |
| V2 `stream_resumed`/`gap_detected`/replay path untested in suite (verified live by agent) | Medium | **Fixed.** `test_sse_replay_resumes_with_gap_detected` added — drives `_event_stream` with a rolled-over ring buffer, asserts `gap_detected: true`, `from_event_id`, replay frame |
| 41-test adversarial probe (limits via 21/1001 connections, replay, fail-open redis) — no regressions | — | Noted; per-key/per-host limits and fail-open confirmed |

Verdict: FAIL → **FIXED** → **RE-VERIFIED PASS** (2026-08-09, agent `aaa7e051d9a6bd333` — ruff / format / mypy clean; `pytest tests/unit tests/contract` → 480 passed; no files modified by re-verifier).

## 5.1 Audit findings & fixes (2026-08-09, pre-verifier)

| # | Finding | Severity | Disposition |
|---|---------|----------|-------------|
| A1 | FakeRedis.set param `_ex` renamed from `ex` → broke middleware `redis.set(..., ex=3600)` keyword binding; record never stored → 2 idempotency tests failed | High | **Fixed.** Restored `ex` param with `# noqa: ARG002` (tests/ per-file-ignores allow); 478 passed. |
| A2 | `_frame` `# noqa: ARG001` on unused `channel` param was itself flagged `RUF100` (unused noqa) | Cosmetic | **Fixed** — renamed param to `_channel` (underscore convention); ruff clean. |
| A3 | SSE route params `Query(default=None, ...)` + `= None` — FastAPI forbids double default (`AssertionError` at collection) | High | **Fixed with `Annotated[str \| None, Query(description=...)] = None`** pattern (no `default=` in `Query`) — collection OK, contract tests pass. |

---

## 6. Acceptance Criteria Check

| Exit criterion (G#) | Status | Evidence |
|---------------------|--------|----------|
| G1 API prefix `/api/v1` | ✅ | `app.py` routers mount; contract tests versioned paths |
| G2 SSE 6 channels + params + event names | ✅ | `streams.py`; `test_sse_*` (8 tests in suite) |
| G3 Idempotency replay + 409 + TTL + fail-open | ✅ | `middleware/idempotency.py`; 3 tests |
| G4 Rate limit wired + 429 + Retry-After | ✅ | rate_limit dependency in 10 write routes; 2 tests |
| G5 Contract coverage 30 | ✅ | `test_api_contract.py` — 30 passed |
| G6 Committed | ✅ | commit `b09807c` (API core snapshot before G1 edits) + this sprint's working-tree snapshot pending |
| G7 Monitoring/logging + trace_id | ✅ | `middleware/logging.py`; 2 trace tests |
| G8 Evidence + approval gate | ✅ evidence; ✅ approved | this file; user approval via AskUserQuestion 2026-08-09 ("Ya, lanjut frontend") |

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 7. Open items

1. Commit the working tree — backend fix (SSE `Z` suffix), the 2 contract
   tests, and this evidence file (this session, G6 remaining action).
2. **Frontend F-Sprint 1 (G11)** — approved; bootstrap conventions, router
   shell, `/health` route, CI wiring — in progress.

---

## 8. Sign-off

Sprint 4 (API Layer) is implementation-complete with the full gate PASS.
Approval of this evidence unblocks G11 (frontend F-Sprints 1–6) and G12
(Sprint 5 hardening: OpenAPI generation, coverage gate, security scans).