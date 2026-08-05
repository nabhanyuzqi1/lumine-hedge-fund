# ADR-0062 — Package pinning: uv (Python) + pnpm (TypeScript), lockfiles committed

- **Status:** Accepted
- **Phase:** 14-implementation
- **Date:** 2026-08-02
- **Owner:** Chief AI Architect
- **Supersedes:** —
- **Superseded by:** —

## Context

CI, staging, and production must run the exact same dependency versions.
Non-deterministic builds across environments cause unreproducible failures.
Lockfile drift (a developer adding a dependency but forgetting to commit the
lockfile) must be detectable. Dependencies must be kept current without
overwhelming the operator.

## Decision

Python uses `uv` with `uv.lock` committed to the repository. TypeScript uses
`pnpm` with `pnpm-lock.yaml` committed. CI installs with `--frozen` flag to
detect lockfile drift. Dependabot configured for weekly automated updates.

## Rationale

- `uv` is the fastest Python resolver (Rust/PubGrub-based), produces a
  cross-platform `uv.lock` with content hash verification, and replaces pip,
  venv, pip-tools, and pipx in a single binary.
- `pnpm` is strict by default (no phantom dependencies), uses a
  content-addressable store for disk efficiency, and produces a deterministic
  lockfile.
- Committed lockfiles guarantee that CI, staging, and production run the exact
  same dependency versions. `--frozen` in CI catches the case where a
  developer adds a dependency but forgets to commit the lockfile.
- Weekly Dependabot with grouped PRs keeps dependencies current without
  overwhelming the operator with individual PRs.
- pip + pip-tools rejected: no built-in lockfile hash verification, slower
  resolver, two separate tools to manage.
- npm/yarn rejected: npm's flat node_modules has phantom dependency issues;
  yarn PnP adds compatibility friction with some tools.
- Not committing lockfiles rejected: non-deterministic builds across
  environments; CI and production may run different versions.

## Consequences

- Positive: deterministic, reproducible builds across all environments.
- Positive: lockfile drift is caught at CI time.
- Positive: Dependabot keeps dependencies current automatically.
- Negative: weekly Dependabot PRs require operator attention (mitigated:
  grouped PRs reduce volume).
- Reversibility: swap `uv` or `pnpm` by regenerating lockfiles and updating
  CI config.

## Cross-references

- Related ADRs: ADR-0061, ADR-0063, ADR-0064
- Implements principle(s): #6
- Affects phases: 14
- Source document: `../14-implementation/decisions.md` (D14-2)
