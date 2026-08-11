# Sprint 5 — Hardening: OpenAPI, Coverage Gate, Security Scans

**Status:** Done — full gate PASS 2026-08-11/12; evidence below
**Date:** 2026-08-11 (plan + implementation), 2026-08-12 (final gate + commit)
**Sprint:** 5 (Hardening) of Phase 15 — Implementation
**Owner:** backend
**Prior sprint:** Sprint 4 (API core) — Done 2026-08-09/10; F-Sprint 1–6 (frontend) — Done 2026-08-11

---

## 1. Sprint Goal

Close the last open gaps of the backend CI surface (G12) plus the
Phase-9 OpenAPI contract, and enforce the coverage gate that the
frontend already relies on. Everything runs locally without Docker/VPS.

**Exit criteria (from `sprint-5-hardening-plan.md` H1–H6):**
- H1 OpenAPI generation: `backend/scripts/generate_openapi.py` dumps
  FastAPI `app.openapi()` to `docs/09-api/openapi.yaml`; idempotent;
  `make openapi`; CI `openapi-diff` job fails on drift (ADR-0070)
- H2 OpenAPI contract test: `tests/contract/test_openapi_contract.py`
  (6 tests) validates versioned paths, 9 routers, HMAC header params,
  envelope error schema, and byte-identical regeneration
- H3 Coverage gate (F10): `make coverage`; CI `unit-tests` runs
  `pytest --cov --cov-fail-under=80`; `[tool.coverage.report] fail_under = 80`
- H4 Level-1 test inventory: `docs/15-implementation/test-inventory.md`
  maps every module in `backend/src/lumine/**` to its test file + level
- H5 Security scans local: `make security` — bandit `-ll`, gitleaks,
  pip-audit; runs clean locally (semgrep stays CI-only)
- H6 Trivy hard-fail re-enable: `ci.yml` `container-scan` no longer
  `continue-on-error: true`

**Additional gates (per CLAUDE.md mandatory rules):**
- `ruff check` + `ruff format --check` zero errors
- `mypy src` zero errors
- `pytest tests/unit tests/contract` all pass (coverage ≥ 80%)
- Independent verification agent returns PASS for non-trivial implementation

---

## 2. Scope

### 2.1 In scope (H1–H6)

| # | Component | Files | Description |
|---|-----------|-------|-------------|
| H1 | OpenAPI generation | `backend/scripts/generate_openapi.py`, `backend/scripts/__init__.py`, `docs/09-api/openapi.yaml`, `Makefile` (`openapi` target), `.github/workflows/ci.yml` (`openapi-diff` job), `docs/adr/0070-openapi-contract-generation.md` | `python -m scripts.generate_openapi` → `yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True)` written to `docs/09-api/openapi.yaml`. CI job regenerates and `git diff --exit-code` fails on drift, so the artifact always ships in the same PR as the API change. ADR-0070 records the generated-not-handwritten decision (resolves placeholder ADR-0041\*). |
| H2 | OpenAPI contract test | `backend/tests/contract/test_openapi_contract.py` | 6 tests: 3.1.0 + title/version; all paths under `/api/v1/`; 9 router tags present; every operation declares the 3 HMAC headers; 422 uses the envelope `HTTPValidationError` $ref; checked-in YAML byte-identical to fresh `app.openapi()` output. |
| H3 | Coverage gate | `backend/pyproject.toml` (`[tool.coverage.report] fail_under = 80`), `Makefile` (`coverage` target), `.github/workflows/ci.yml` (unit-tests job `--cov --cov-fail-under=80`) | Local: `make coverage` runs unit+contract with the gate. CI: unit-tests job enforces ≥ 80%. Measured 90.86% → comfortably above gate. |
| H4 | Test inventory | `docs/15-implementation/test-inventory.md` (new) | Module↔test mapping for all 11 `backend/src/lumine/` packages + orphan modules (api/sse, monitoring, registry, security, schemas/agents, schemas/streams, prompts/evals) + gap policy (orphan modules get a contract/unit test before live use). |
| H5 | Security scans | `Makefile` (`security` target) | `uv run bandit -ll -r src/` (no issues, 6592 LOC), `gitleaks detect --no-banner` (skipped gracefully if not installed), `uv run pip-audit` (no known vulnerabilities). Semgrep stays CI-only per plan. |
| H6 | Trivy hard fail | `.github/workflows/ci.yml` (`container-scan` job) | `continue-on-error: true` removed; comment documents the re-enable + Debian base-image CVE caveat. SARIF upload retained for tracking. |

### 2.2 Out of scope (deferred)

- VPS/UFW/SSH/Caddy/backup (live infra — operator action).
- Prometheus/Loki/Grafana metrics (per `spec-reconciliation.md`).
- Sprint 7 (hash chain, WORM anchor, reasoning traces, TCA).
- Spec-gap closures (feature_provider, prompts/registry, agent registry,
  LLM gateway) — separate plan.

---

## 3. Implementation Notes

- **OpenAPI shape reality vs. plan:** the generated document has NO
  `securitySchemes` block. HMAC appears as per-operation header
  parameters (`X-Lumine-API-Key`, `X-Lumine-Timestamp`,
  `X-Lumine-Signature`, `required: false`) because auth is enforced by a
  FastAPI dependency (`authenticate_request`), not `Security()`. The
  contract test asserts the headers on every operation and ADR-0070
  documents the trade-off (future `Security()` upgrade keeps the
  wire contract stable).
- **Idempotency:** regenerating `openapi.yaml` is byte-stable — reruns
  produce identical output (verified by the CI diff gate design and the
  byte-identical contract test).
- **Coverage measurement:** `[tool.coverage.run]` scopes to `src/lumine`
  and omits tests + alembic; measured total 90.86% vs. the 80% gate.

---

## 4. Quality Gates (full gate — 2026-08-11/12)

| Gate | Command | Result |
|------|---------|--------|
| Lint | `uv run ruff check src/ tests/ scripts/` | PASS — All checks passed (134 files) |
| Format | `uv run ruff format --check src/ tests/ scripts/` | PASS — 134 files already formatted |
| Types | `uv run mypy src/ scripts/` | PASS — Success: no issues found in 70 source files |
| Contract tests (H2) | `uv run pytest tests/contract/test_openapi_contract.py -v` | PASS — 6 passed (byte-identical check included) |
| Full suite + coverage | `uv run pytest tests/unit/ tests/contract/ --cov --cov-fail-under=80` | PASS — 486 passed, 1 warning in 265.46s; "Required test coverage of 80% reached. Total coverage: 90.86%" |
| Security (H5) | `make security` | PASS — bandit "No issues identified" (6592 LOC); pip-audit "No known vulnerabilities found"; gitleaks skipped (not installed locally, by design) |
| OpenAPI idempotency (H1) | `make openapi && git diff --exit-code` | PASS — regenerate produces no diff |

---

## 5. Independent verification

Verdict: **PASS** — separate verification agent re-ran the gate
independently (ruff / format / mypy / contract tests / coverage) and
confirmed the evidence below; no regressions.

---

## 6. Acceptance Criteria Check

| Exit criterion (H#) | Status | Evidence |
|---------------------|--------|----------|
| H1 OpenAPI generation + CI diff gate | Done | `scripts/generate_openapi.py`; `docs/09-api/openapi.yaml`; `make openapi`; `openapi-diff` job in `ci.yml`; ADR-0070 |
| H2 OpenAPI contract test | Done | `test_openapi_contract.py` — 6 passed |
| H3 Coverage gate 80% | Done | `fail_under = 80`; CI `--cov-fail-under=80`; measured 90.86% |
| H4 Level-1 test inventory | Done | `docs/15-implementation/test-inventory.md` |
| H5 Security scans local | Done | `make security` clean (bandit + pip-audit) |
| H6 Trivy hard fail | Done | `continue-on-error: true` removed from `container-scan` |

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 7. Open items

1. Commit the working tree (API contract + coverage + security + this
   evidence) — final action of this sprint.
2. **Sprint 7** (hash chain, WORM anchor, reasoning traces, TCA) —
   pending, separate plan + approval gate.
3. Spec-gap closures (feature_provider, prompts/registry, agent registry,
   LLM gateway) — separate plan.

---

## 8. Sign-off

Sprint 5 (Hardening) is implementation-complete with the full gate PASS.
The backend CI surface is now: lint, strict types, unit+contract tests
with 80% coverage gate, OpenAPI drift check, security scans (bandit,
gitleaks, pip-audit, semgrep CI-only), and hard-fail container scanning.
Approval of this evidence unblocks Sprint 7 planning.
