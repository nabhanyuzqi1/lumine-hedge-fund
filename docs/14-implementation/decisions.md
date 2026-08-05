# Phase 14 — Locked Decisions

## D14-1 — Monorepo: Python workspace + TypeScript workspace, single repository

> **ADR:** [ADR-0061](../../adr/INDEX.md#adr-0061) — Monorepo: Python workspace + TypeScript workspace, single repository

**Choice:** One repository with two language workspaces: `backend/`
(Python) and `frontend/` (TypeScript/React). Shared code lives in
`backend/src/lumine/shared/` and `frontend/src/lib/`. `docs/` and `.github/`
remain at the repository root. No micro-repo or poly-repo.

**Rationale:**
- Single source of truth for versioning: one commit captures a
  cross-cutting change (API contract + frontend consumer + test).
- Simplified CI: one pipeline definition, one set of secrets, one
  deployment workflow.
- `docs/` stays at the root — architecture documents are the
  cross-cutting reference for both workspaces.
- Micro-repo adds coordination overhead for a team this size (single
  operator). Poly-repo adds CI duplication and cross-repo PR
  orchestration with no benefit at V1 scale.

**Alternatives rejected:**
- Micro-repo (one repo per service): excessive coordination overhead
  for a single-operator project. Cross-cutting changes require
  multiple PRs across repos.
- Poly-repo with shared libraries: adds dependency management
  complexity (versioning shared packages, publishing to internal
  registry). Premature at V1 scale.

## D14-2 — Package pinning: `uv` (Python) + `pnpm` (TypeScript), lockfiles committed

> **ADR:** [ADR-0062](../../adr/INDEX.md#adr-0062) — Package pinning: uv (Python) + pnpm (TypeScript), lockfiles committed

**Choice:** Python uses `uv` with `uv.lock` committed to the repository.
TypeScript uses `pnpm` with `pnpm-lock.yaml` committed. CI installs
with `--frozen` flag to detect lockfile drift. Dependabot configured
for weekly automated updates.

**Rationale:**
- `uv` is the fastest Python resolver (Rust/PubGrub-based), produces
  a cross-platform `uv.lock` with content hash verification, and
  replaces pip, venv, pip-tools, and pipx in a single binary.
- `pnpm` is strict by default (no phantom dependencies), uses a
  content-addressable store for disk efficiency, and produces a
  deterministic lockfile.
- Committed lockfiles guarantee that CI, staging, and production run
  the exact same dependency versions. `--frozen` in CI catches the
  case where a developer adds a dependency but forgets to commit the
  lockfile.
- Weekly Dependabot with grouped PRs keeps dependencies current
  without overwhelming the operator with individual PRs.

**Alternatives rejected:**
- pip + pip-tools: no built-in lockfile hash verification, slower
  resolver, two separate tools to manage.
- npm/yarn: npm's flat node_modules has phantom dependency issues;
  yarn PnP adds compatibility friction with some tools.
- Not committing lockfiles: non-deterministic builds across
  environments; CI and production may run different versions.

## D14-3 — Python standards: `ruff` + `mypy` strict + `pytest`

> **ADR:** [ADR-0063](../../adr/INDEX.md#adr-0063) — Python standards: ruff + mypy strict + pytest

**Choice:** `ruff` for linting and formatting (replacing flake8, isort,
black, pyupgrade). `mypy --strict` for all `src/` except the AutoGen
pipeline (where AutoGen's dynamic types make strict mode impractical).
`pytest` + `pytest-cov` for testing with ≥ 80% line coverage target on
deterministic modules.

**Rationale:**
- `ruff` is a single Rust binary that replaces 4+ Python tools. It
  runs orders of magnitude faster than the tools it replaces and
  implements 800+ rules covering style, bugs, complexity, and security.
- `mypy --strict` catches type errors at development time rather than
  runtime. The AutoGen pipeline exclusion is pragmatic — AutoGen's
  dynamic agent interfaces do not type-check cleanly under strict mode.
- Google-style docstrings for public API only; internal helpers use
  inline comments. Docstrings on every function create noise without
  benefit — the function signature and name should be self-documenting
  for internal code.
- `structlog` for structured JSON logging with `trace_id` on every
  line. `pydantic-settings` for configuration loading with validation.

**Alternatives rejected:**
- flake8 + isort + black + pyupgrade as separate tools: 4x the
  configuration, 4x the CI runtime, 4x the dependency surface.
- `pylint`: slower than ruff, more false positives, more configuration
  overhead.
- Docstrings on all functions: internal helper docstrings rot faster
  than they're updated. Public API docstrings are the contract.

## D14-4 — TypeScript standards: `biome` + TypeScript strict + `vitest`

> **ADR:** [ADR-0064](../../adr/INDEX.md#adr-0064) — TypeScript standards: biome + TypeScript strict + vitest

**Choice:** `biome` for linting and formatting (replacing eslint +
prettier). TypeScript `strict: true`. `vitest` + React Testing Library
for component and hook tests. Named exports only. Functional components
only.

**Rationale:**
- `biome` is a single Rust binary replacing eslint + prettier, with
  faster execution and zero-config defaults that match community
  standards.
- TypeScript strict mode catches `null`/`undefined` errors, missing
  properties, and implicit `any` at compile time.
- `vitest` is Vite-native, shares the same transform pipeline, and
  runs tests orders of magnitude faster than Jest in a Vite project.
- Named exports only: default exports break IDE auto-import, make
  refactoring harder, and create inconsistent import names.
- Functional components + hooks: no class components, no legacy
  patterns. Consistent with React's modern direction.

**Alternatives rejected:**
- eslint + prettier: two separate tools, slower, more configuration,
  plugin compatibility issues.
- Jest: slower in Vite projects, requires separate configuration,
  doesn't share the transform pipeline.
- Default exports: break tree-shaking analysis, make refactoring
  fragile, create inconsistent import naming.

## D14-5 — 5 sprints, 10 weeks total

> **ADR:** [ADR-0065](../../adr/INDEX.md#adr-0065) — 5 sprints, 10 weeks total

**Choice:** Five sprints delivering vertical slices in sequence:
Sprint 1 — Foundation (2 weeks), Sprint 2 — Data Pipeline (2 weeks),
Sprint 3 — Decision Engine (3 weeks), Sprint 4 — API & Frontend
(2 weeks), Sprint 5 — Hardening (1 week).

**Rationale:**
- Vertical slices mean each sprint delivers a working, testable
  increment. Sprint 1 delivers a running stack. Sprint 2 delivers
  live data. Sprint 3 delivers the decision engine. Sprint 4 delivers
  the dashboard. Sprint 5 delivers production readiness.
- Backend-first ordering: the frontend depends on API contracts
  (Phase 9). The API depends on the decision engine (Phase 4/7/8).
  The decision engine depends on data (Phase 5). Data depends on the
  MT5 bridge (Phase 8). The MT5 bridge depends on the foundation
  (Sprint 1).
- Sprint 3 is the longest (3 weeks) — it is the core of the system.
  The AutoGen pipeline, LLM gateway, risk engine, and lineage writer
  are the most complex components and the most critical to get right.
- Sprint 5 is the shortest (1 week) — it is hardening and acceptance,
  not new feature development.

**Alternatives rejected:**
- Horizontal layers (all data layer first, then all logic, then all
  API): no working system until the final sprint. Integration bugs
  between layers are discovered late. No opportunity for early paper
  trading.
- More sprints (8-10): finer granularity but more ceremony. 5 sprints
  matches the natural architectural boundaries.
- Fewer sprints (3): each sprint is too large to review and too risky
  — a problem in Sprint 2 blocks the entire delivery.

## D14-6 — Vertical slice ordering, backend-first

> **ADR:** [ADR-0066](../../adr/INDEX.md#adr-0066) — Vertical slice ordering, backend-first

**Choice:** Each sprint delivers a complete vertical slice. Backend
services are built first; frontend depends on API contracts. Critical
path: MT5 bridge → data pipeline → decision engine → execution → API
→ dashboard. Paper trading begins as soon as the decision engine is
functional (Sprint 3+).

**Rationale:**
- Vertical slices provide continuous integration feedback. Every
  sprint produces something that can be tested end-to-end.
- Backend-first respects the dependency graph: the frontend cannot
  render data that the API cannot serve, and the API cannot serve
  decisions that the engine cannot produce.
- Early paper trading (Sprint 3+) means the system runs against live
  market data for 4+ weeks before go-live — far exceeding the minimum
  2-week requirement (D13-6).
- Cross-cutting concerns (logging, metrics, error handling) are built
  in Sprint 1 and used by every subsequent sprint — they are not an
  afterthought.

**Alternatives rejected:**
- Frontend-first (mock API): produces a polished dashboard with no
  backend to connect to. The mock-to-real transition is a source of
  bugs and rework.
- Parallel backend + frontend: requires the API contract to be stable
  before any implementation. In practice, the contract evolves during
  backend development, causing frontend rework.

## D14-7 — Git: trunk-based, conventional commits, feature flags

> **ADR:** [ADR-0067](../../adr/INDEX.md#adr-0067) — Git: trunk-based, conventional commits, feature flags

**Choice:** Trunk-based development — no long-lived branches. Feature
flags (`LUMINE_FEATURE_<NAME>`) for incomplete features on main.
Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
`chore:`, `ci:`). PR required for all changes; squash merge to main.

**Rationale:**
- Trunk-based development minimizes merge conflicts and keeps the
  integration surface small. Long-lived branches accumulate drift
  and produce painful merges.
- Feature flags allow incomplete work to be merged to main without
  affecting the running system. This is critical for a single-operator
  project — the operator should not be blocked on a feature branch
  while an urgent fix is needed on main.
- Conventional commits produce a machine-readable changelog and make
  it easy to answer "what changed in this release?".
- Squash merge keeps the main branch history linear and clean. Each
  merged PR is one commit with a descriptive message.

**Alternatives rejected:**
- GitFlow (develop/main/feature/release/hotfix): excessive branching
  ceremony for a single-operator project. The develop branch is a
  long-lived branch by another name.
- Merge commits (no squash): creates a non-linear history where
  individual WIP commits clutter the main branch log.
- No feature flags (merge only complete features): forces the operator
  to either keep features on long-lived branches or delay merging
  until the feature is 100% complete. Both are worse than feature flags.

## Principles honored

- **Phase 1 architecture before code**: 14 phases of architecture
  before a single line of implementation — the extreme interpretation
  of this principle.
- **Replaceability**: every tool choice (uv, pnpm, biome, ruff) is
  replaceable. The standards are the contract, not the specific tool.
  Migrating to a different tool requires updating the configuration
  and lockfile, not rewriting code.
- **Evidence before capital**: CI gates and the 8-item acceptance
  checklist (Phase 13 D13-6) ensure no code reaches production without
  passing deterministic, auditable checks.
- **Fail visible**: CI gates are blocking — lint, type-check, and
  security scan failures stop the pipeline explicitly. No silent
  degradation.
- **YAGNI**: no framework, no scaffolding, no boilerplate, no
  speculative code. Sprint 1 starts with Phase 14 as the blueprint.
  Nothing is built that is not in the sprint plan.

## Phase boundary

Decisions D14-1..D14-7 are locked. Concrete code, tests, migrations,
Dockerfiles, CI YAML, and configuration files belong to Phase 15
(Sprint 1-5).