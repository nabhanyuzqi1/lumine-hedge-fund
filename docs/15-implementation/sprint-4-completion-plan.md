# Sprint 4 Completion Plan — Remaining Work

- **Status:** approved-pending
- **Owner:** backend + frontend
- **Created:** 2026-08-08
- **Depends on:** `sprint-3-decision-engine.md` evidence, verifier PASS for Sprint 4 API core (2026-08-08, agent `a3b09a15f725148ff`)

## Verified done (verifier PASS, 2026-08-08)

- Application factory + 9 routers (portfolio, orders, workflows, lineage, market,
  journal, streams, admin, rpc) — `backend/src/lumine/api/`
- Common envelope middleware + error contract (MISSING_AUTH, INVALID_SIGNATURE,
  EXPIRED_TIMESTAMP, REVOKED_KEY, REPLAY_DETECTED, NOT_FOUND, RATE_LIMITED, ...)
- HMAC-SHA256 auth per `auth.md` (query string signed, 300s window, replay cache)
- Contract suite: 17 passed; unit suite: 448 passed; ruff clean; mypy strict clean

## Open gaps (audit 2026-08-08, source of truth: Phase 9 docs)

| # | Gap | Spec reference | Implementation reality |
|---|-----|----------------|------------------------|
| G1 | URL prefix `/api/v1` missing | `rest-api.md:6-7` — all endpoints under `/api/v1/` | Routers register bare paths (`/portfolio/summary`); contract tests hit unversioned paths |
| G2 | SSE channels don't match spec | `sse-api.md:18-23` — 6 channels: `market-data`, `analyst-outputs`, `ic-decisions`, `cio-proposals`, `risk-assessments`, `execution-orders`; per-channel query params `sse-api.md:72-77`; event names `market_data`, `analyst_output`, ... | `streams.py` implements 5 different channels (`portfolio`, `positions`, `market`, `workflow_events`, `alerts`), no query params, event name = channel |
| G3 | Idempotency contract unimplemented | `error-contract.md:56-57,178-189` — `X-Idempotency-Key`; same key+body → 200 + `meta.idempotent_replay: true`; same key+diff body → 409 `CONFLICT` | Only schema field `idempotency_key` (`schemas/api.py:79`); no enforcement, no 409 path |
| G4 | Rate limiter not wired | `error-contract.md:59` — 429 `RATE_LIMITED`, `Retry-After` header | `middleware/rate_limit.py` exists (Redis sliding window) but no router uses it; no 429 contract test |
| G5 | Contract tests incomplete | `docs/13-testing/` Level 3 | Missing: 400 `INVALID_REQUEST`/`VALIDATION_FAILED`, 403 `INSUFFICIENT_SCOPE`, 409, 429, `EXPIRED_TIMESTAMP`, `REVOKED_KEY`, pagination, SSE `Last-Event-ID`/heartbeat/reconnect, `meta.idempotent_replay` |
| G6 | API layer uncommitted | git status | All `backend/src/lumine/api/**` + `tests/contract/test_api_contract.py` untracked |
| G7 | `monitoring/` module empty | `spec-reconciliation.md` (High gap) | `backend/src/lumine/monitoring/__init__.py` only |
| G8 | Sprint 4 evidence file missing | `phase-implementation-workflow` memory — plan artifact + approval gate | No `sprint-evidence/sprint-4-*.md` |
| G9 | Integration suite blocked | `docs/13-testing/` | Docker daemon down locally — testcontainers can't start PG/Redis; 38 errors environmental |
| G10 | `test_settings_point_at_containers` env-sensitive | — | Fails when `LUMINE_ENV`/`.env` absent in shell (expects `test`) |
| G11 | Frontend F-Sprints 1–6 not started | `frontend-sprint-plan.md` | Pre-condition (API contracts implemented/mocked) becomes true once G1–G4 done |
| G12 | Sprint 5 hardening not started | `sprint-plan.md` | OpenAPI generation, coverage gate, security scans, level-1 test inventory |

## Execution order

1. **G6 commit first** — the verified core is uncommitted; snapshot it before further edits.
2. **G1** — add `/api/v1` prefix to all routers; update contract tests to versioned paths; check `auth.md` examples stay consistent.
3. **G2** — rewrite `streams.py` channels to the 6 spec channels with per-channel query params + spec event names; keep heartbeat + `Last-Event-ID`; update SSE contract tests.
4. **G3** — idempotency middleware/dependency (Redis `processed_commands`-style or keyed cache): 200 replay w/ `meta.idempotent_replay`, 409 `CONFLICT`; contract tests.
5. **G4** — wire `rate_limit_dependency` into write-capable routers (orders, rpc, admin); contract test 429 with fake Redis; ensure bootstrap key exemption.
6. **G5** — complete Level 3 contract coverage for all codes above + pagination + SSE reconnect/heartbeat.
7. **G7** — implement monitoring module (structured logging, request tracing, `trace_id` propagation per `error-contract.md` traceability + Phase 7 observability).
8. **G8** — run full gate (ruff, mypy strict, pytest unit+contract), spec-reconciliation audit, save `sprint-evidence/sprint-4-api.md`, then **approval gate** (AskUserQuestion) before starting frontend F-Sprint 1.
9. **G9/G10** — integration suite once Docker Desktop is up (user action); fix env-var defaults if needed.
10. **G11** — frontend F-Sprints per `frontend-sprint-plan.md` (separate approval).
11. **G12** — Sprint 5 hardening per `sprint-plan.md` (separate approval).

## Out of scope (this plan)

- New API endpoints beyond the Phase 9 contract surface.
- Trading/execution engine changes (Sprint 3 territory, already evidenced).
- Docs `docs/09-api/*` edits beyond what G1–G5 require (docs-first rule applies per change).
