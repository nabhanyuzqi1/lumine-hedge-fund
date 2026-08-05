# Coding Standards

- **Status:** active
- **Owner:** architects
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 180
- **Source:** promoted from `docs/14-implementation/coding-standards.md`

This is the permanent cross-language standard. The phase doc remains the
implementation-planning source; this is the operating reference.

## Python (backend)
- Formatter/linter: `ruff` (`make lint-backend`, `make typecheck-backend`).
- Type hints required on all public functions; `mypy --strict` on `src/`.
- Import style: `from module import thing` (explicit, no wildcard).
- `src/` layout; namespace package `lumine`.
- Determinism rule: no `datetime.now()`, `random()`, `uuid4()` in workflow
  code (Phase 7 determinism). Use injected clocks / ID generators.
- Errors: `FatalError` for unretryable, `ValidationError` for retryable
  (matches Phase 3 error taxonomy).

## TypeScript (frontend)
- `eslint` + `prettier`; `tsc --noEmit` in CI.
- Functional components; hooks; no class components.
- Strict mode; no `any` without an inline justification comment.

## SQL
- Lowercase keywords. Explicit types. `NOT NULL` by default.
- Indexes named `idx_<table>_<cols>`. Foreign keys named `fk_<table>_<col>`.
- Migrations via Alembic; one logical change per migration; reversible.
- Append-only tables (lineage, journal, fills) never UPDATE/DELETE in app code.

## Commits / branches
- Conventional Commits (see `CONTRIBUTING.md`).
- Branches: `feat|fix|docs/<scope>-<desc>`.

## Reviews
- Architectural change → ADR before code.
- Prompt/model/policy change → eval evidence (ADR-0028).
- Non-trivial implementation → separate-agent verification (CLAUDE.md rule 8).
