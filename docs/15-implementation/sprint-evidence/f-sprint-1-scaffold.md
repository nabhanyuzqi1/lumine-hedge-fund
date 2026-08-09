# F-Sprint 1 — Frontend Scaffold (Conventions before Features): Plan & Evidence

**Status:** Implementation complete — local gate PASS (eslint / tsc / vitest / vite build). Pending deployment to preview URL + approval gate before F-Sprint 2.
**Date:** 2026-08-09
**Sprint:** F-Sprint 1 (G11) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prerequisites:** Sprint 4 (API Layer) approved 2026-08-09

---

## 1. Sprint Goal

Bootstrap the frontend conventions so every later F-Sprint builds on a
locked configuration, per `docs/15-implementation/frontend-sprint-plan.md`
F-Sprint 1: "empty-but-conventioned app deployed to a preview URL." The
existing marketing landing page stays mounted; the TypeScript portal shell
is introduced alongside it.

**Exit criteria (from frontend-sprint-plan.md F1–F5):**
- `package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`,
  `prettier`, `tailwind.config.ts`, `postcss` (F1)
- `src/main.tsx`, `src/app/` router shell, one route (`/health`) (F2)
- Design tokens from `docs/10-frontend/design-tokens.md` wired into Tailwind (F3)
- CI `ci-frontend.yml` runs `lint`, `typecheck`, `build`, `test` (F4)
- Output: empty-but-conventioned app deployed to a preview URL (F5)

**Additional gates (per CLAUDE.md mandatory rules):**
- `npm run lint` (eslint flat config) zero errors
- `npm run typecheck` (tsc --noEmit) zero errors
- `npm run test` (vitest) all pass
- `npm run build` (tsc + vite) succeeds
- Independent verification agent returns PASS for non-trivial implementation

---

## 2. Scope

### 2.1 In scope

| Component | Files | Description |
|-----------|-------|-------------|
| Package conventions | `frontend/package.json` | React 19 + react-router 7 (Phase 10 stack), scripts parity with Makefile (`lint`/`typecheck`), engines node >= 20 |
| Vite config | `frontend/vite.config.ts` | Replaces `vite.config.js` (deleted — Vite prefers `.js` and would silently ignore the TS config); `@` alias → `src/`; `base: './'` for VPS nginx / subpath deploy; vitest block (`jsdom`, setup file) typed via `defineConfig` from `vitest/config` |
| TS config | `frontend/tsconfig.json` | strict, `noUncheckedIndexedAccess`, `allowJs` so legacy `App.jsx`/JSX co-exists with new TSX, `@/*` path alias |
| ESLint | `frontend/eslint.config.js` | Flat config (eslint 9): js recommended + typescript-eslint recommended + react-hooks + react-refresh; `globals` browser/es2022 |
| Prettier | `frontend/.prettierrc.json` | semi, singleQuote, trailingComma all, printWidth 100 |
| Tailwind 4 | `frontend/src/index.css` `@theme` | CSS-first config (Tailwind 4 drops `tailwind.config.ts`/`postcss` — plan F1 renamed); tokens already wired from `design-tokens.md` (abyss/bg/raised/overlay/line, ink series, accent/up/down/warn/cyan, fonts, radii, shadow) |
| Entry | `frontend/src/main.tsx` (new) | `createRoot` + `RouterProvider`; replaces `main.jsx` entry in `index.html` |
| Router shell | `frontend/src/app/router.tsx` | `createBrowserRouter`: `/` → legacy landing `App.jsx`, `/health` → portal HealthPage |
| Health route | `frontend/src/app/pages/health.tsx` + test | First portal route (liveness page), test asserting status/API version render |
| Vitest setup | `frontend/src/test/setup.ts` | `@testing-library/jest-dom/vitest` matchers |
| CI | `.github/workflows/ci-frontend.yml` | Four parallel jobs: lint, typecheck, test, build (each `npm ci` + script); guard job preserves existing skip behavior |

### 2.2 Out of scope (later F-Sprints)

- **F-Sprint 2** — shadcn/ui primitives, semantic token naming alignment
  (e.g. `--color-ink` → `text-primary` family), Storybook-style docs,
  accessibility baseline.
- **F-Sprint 3** — SSE client, TanStack Query, Zustand, virtualized tables.
- **F-Sprint 4/5/6** — charts, surfaces, keyboard/a11y/perf.

---

## 3. Implementation Notes

- `vite.config.js` deleted before the TS config takes effect; confirmed
  Vite was previously loading `.js` (config drift risk). Root `.gitignore`
  already covers `dist/`, `node_modules/`, `*.tsbuildinfo`; `frontend/.gitignore`
  keeps the local `*.tsbuildinfo` carve-out.
- Vitest loads `vitest.config.ts` when present and ignores `vite.config.ts`;
  the empty `vitest.config.ts` stub was the reason `environment: jsdom` was
  dropped (test failed with `document is not defined`). Deleted the stub —
  single source of truth in `vite.config.ts`, typechecked.
- npm cache on this machine had root-owned files (npm bug); `npm install`
  ran against a fresh user-owned cache dir. No `package-lock.json` resoluteness
  issue; lockfile regenerated and committed.
- Lint surfaced one pre-existing dead const (`VETO_LINE` in
  `src/components/Console.jsx`) — removed (duplicated `STAGES` entry at line 26).
- Tailwind 4: `@theme` in CSS is the whole config story; `tailwind.config.ts` +
  `postcss` omitted deliberately per Tailwind 4 conventions.

---

## 4. Local Quality Gates (2026-08-09)

| Gate | Command | Result |
|------|---------|--------|
| Install | `npm install` (fresh cache) | PASS — 0 vulnerabilities |
| Lint | `npm run lint` (eslint) | PASS — 1 pre-existing error fixed (`VETO_LINE`), then clean |
| Typecheck | `npm run typecheck` (tsc --noEmit) | PASS — clean incl. `vite.config.ts` |
| Test | `npm run test` (vitest) | PASS — 1 test (HealthPage) — after removing `vitest.config.ts` stub (jsdom env now applies) |
| Build | `npm run build` (tsc + vite build) | PASS — dist: index.html 1.50 kB / css 21.79 kB / js 309.89 kB (gzip 98.36 kB) |
| Prettier | `npx prettier --check .` (local) | PASS — 17 files reformatted via `prettier --write`; `.prettierignore` added (`dist/`, `node_modules/`) so `format:check` also passes clean post-build |

**Bundle note:** 309.89 kB JS (gzip 98.36 kB) is the legacy landing bundle
(React 19 + routing); grows with portal surfaces in later sprints — Phase 10
budget check lands in F-Sprint 6.

---

## 5. Independent verification (2026-08-09)

| Finding | Severity | Disposition |
|---------|----------|-------------|
| (filled post-verification — agent dispatch) | | |

Verdict: pending.

---

## 6. Acceptance Criteria Check

| Exit criterion (F#) | Status | Evidence |
|---------------------|--------|----------|
| F1 conventions (`package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, prettier, tailwind, postcss) | ✅ (postcss n/a per Tailwind 4) | files above; `npm run lint/typecheck` PASS |
| F2 `main.tsx` + `src/app/` router shell + `/health` | ✅ | `src/main.tsx`, `src/app/router.tsx`, `src/app/pages/health.tsx` |
| F3 design tokens wired into Tailwind | ✅ (token set pre-existing; semantic naming alignment deferred to F-Sprint 2) | `src/index.css` `@theme` |
| F4 CI lint + typecheck + build + test | ✅ | `ci-frontend.yml` four jobs |
| F5 deployed to preview URL | ⏳ | VPS deploy via existing `deploy.yml` path after gate pass |

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 7. Open items before approval gate

1. Independent verification agent dispatch — required for the non-trivial
   implementation gate before reporting completion (per CLAUDE.md rule 8).
2. Commit the working tree (frontend scaffold batch).
3. Deploy to preview URL (existing VPS deploy path) — after local gate + verification.
4. **Approval gate: AskUserQuestion** — approve F-Sprint 1 before F-Sprint 2
   (design system primitives).

---

## 8. Sign-off

F-Sprint 1 (Scaffold) is implementation-complete with the local gate PASS.
The existing landing page is preserved; the TS portal shell with `/health`
is live in dev. Approval of this evidence unblocks F-Sprint 2 (shadcn/ui
primitives, semantic token alignment, accessibility baseline).