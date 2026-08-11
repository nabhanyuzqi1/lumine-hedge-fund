# Sprint 5 — Hardening Plan

- **Status:** Done — full gate PASS 2026-08-11; evidence
  `sprint-evidence/sprint-5-hardening.md`
- **Owner:** backend
- **Created:** 2026-08-11
- **Depends on:** Sprint 1–4 done, F-Sprint 1–6 done (commit `ea4c003`),
  spec-reconciliation current
- **Source of truth:** `docs/14-implementation/sprint-plan.md` (Sprint 5),
  `docs/14-implementation/ci-cd-pipeline.md`, gap list G12 in
  `sprint-4-completion-plan.md`

## Goal

Close the last open gap of the backend CI surface (G12) plus the
Phase-9 OpenAPI contract, and enforce the coverage gate that F-Sprint 6
already relies on. Everything must run locally without Docker/VPS.

## Scope

| # | Item | Deliverable | Evidence |
|---|------|-------------|----------|
| H1 | OpenAPI generation (ADR-0041*) | `backend/scripts/generate_openapi.py` — dumps FastAPI `app.openapi()` to `docs/09-api/openapi.yaml`; idempotent; run via `make openapi`; CI job diffs it (`git diff --exit-code`) | `docs/09-api/openapi.yaml` generated; ADR-0041 created |
| H2 | OpenAPI contract test | `tests/contract/test_openapi_contract.py` — validates the generated YAML against `api-versioning.md` (paths under `/api/v1/`, 9 routers present, envelope schema, HMAC security scheme) | 1 contract test, gate PASS |
| H3 | Coverage gate (F10) | `make coverage` target; CI `unit-tests` runs `pytest --cov --cov-fail-under=80`; add `[tool.coverage.report] fail_under` in pyproject | CI green with gate |
| H4 | Level-1 test inventory | `docs/15-implementation/test-inventory.md` — map every module in `backend/src/lumine/**` to its test file and level; mark orphan modules | Inventory doc |
| H5 | Security scans local | `make security` target: bandit `-ll`, gitleaks, pip-audit (semgrep stays CI-only) | Makefile target runs clean |
| H6 | Trivy hard-fail re-enable | In `ci.yml` `container-scan`: remove `continue-on-error: true` (comment says "Re-enable hard fail before live capital (Sprint 5)") | ci.yml diff |

## Out of scope

- VPS/UFW/SSH/Caddy/backup (needs live infra — operator action, not code).
- Prometheus/Loki/Grafana metrics (deferred per `spec-reconciliation.md`).
- Sprint 7 (hash chain, WORM, reasoning traces, TCA).
- Spec-gap closures (feature_provider, prompts/registry, agent registry,
  LLM gateway) — separate plan.

## Risks

- Coverage < 80% locally → raise gate only with documented justification,
  never silently.
- OpenAPI diff in CI may churn on unrelated edits → the CI job is
  `--exit-code` on `make openapi`, so regen in the same PR as the change.
- gitleaks/pip-audit may need baseline config (`.gitleaks.toml`) for
  known-safe patterns.
