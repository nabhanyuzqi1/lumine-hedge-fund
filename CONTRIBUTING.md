# Contributing to Lumine

## Branching

- `main` is always deployable.
- Feature branches: `feat/<scope>-<short-desc>` (e.g. `feat/risk-determinism`).
- Fix branches: `fix/<scope>-<short-desc>`.
- Docs branches: `docs/<scope>-<short-desc>`.

## Commit messages

Conventional Commits:

```
feat(risk): remove LLM sizing multiplier, add registry lookup
fix(bridge): handle MT5 reconnect during open position
docs(adr): add ADR-0016 risk determinism
chore(ci): add supply-chain scanning job
```

## Pull requests

Every PR must:

1. Reference an ADR for any architectural change. No ADR → no merge.
2. Pass `make lint test typecheck` locally. CI runs the same targets.
3. Update affected docs in the same PR (CLAUDE.md rule 4: architecture
   changes update docs first).
4. Include tests for new behavior (Phase 13 quality gates).
5. For prompt/model/policy changes: include eval evidence (ADR-0028).

## Architectural changes require an ADR

Any non-trivial architectural change requires a new ADR (or superseding an
existing one) **before** code. See `docs/adr/0000-template.md` and
`docs/adr/INDEX.md`. The RFC process (`docs/90-governance-and-operations/97-change-management/rfc-process.md`)
governs larger changes.

## Phase discipline

- Never mix phases in one PR or one document (CLAUDE.md rule 2).
- Phase boundaries are documented in `docs/phase-mapping.md`.
- Cross-phase changes cite the boundary they cross and why.

## Verification

Non-trivial implementation (3+ files, backend/API, infrastructure) must be
verified by a separate agent before reporting completion (CLAUDE.md rule 8).
Cross-engine review is preferred (rule 9).

## Code style

- Python: `docs/14-implementation/coding-standards.md`, enforced by `ruff`.
- TypeScript: enforced by `eslint` + `prettier`.
- SQL: lowercase keywords, explicit types, indexes named `idx_<table>_<cols>`.

## Secrets

- Never commit secrets. `.env*` is gitignored (except `.env.example`).
- Credentials use `@outputai/credentials` convention or the Phase 12 secrets
  management contract (`docs/12-security/secrets-management.md`).
- If you accidentally commit a secret, treat it as a security incident
  (`SECURITY.md`).

## Anti-scope

Before adding a feature, check `docs/90-governance-and-operations/91-anti-scope-register.md`.
Reintroducing a rejected feature requires superseding the ADR that rejected it.
