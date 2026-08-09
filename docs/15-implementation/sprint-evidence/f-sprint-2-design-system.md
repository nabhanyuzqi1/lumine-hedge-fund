# F-Sprint 2 — Design System Primitives: Plan & Evidence

**Status:** Implementation complete — local gate PASS (eslint / tsc / vitest / vite build / prettier / contrast audit). Pending independent verification + approval gate before F-Sprint 3.
**Date:** 2026-08-10
**Sprint:** F-Sprint 2 (G11) of Phase 15 — Implementation
**Owner:** Chief AI Architect
**Prerequisites:** F-Sprint 1 (Frontend Scaffold) approved 2026-08-09

---

## 1. Sprint Goal

Deliver shadcn/ui-style primitive components, semantic token alignment, tabular-numeral typography, an accessibility baseline, and per-component documentation per `docs/15-implementation/frontend-sprint-plan.md` F-Sprint 2 and `docs/10-frontend/components.md`.

**Exit criteria (from frontend-sprint-plan.md F-Sprint 2):**

- `Button`, `Card`, `Table`, `Badge`, `Dialog`, `Toast`, `NumericText` under `src/components/ui/`
- Semantic color aliases (`bg-base`, `bg-raised`, `text-primary`, `text-secondary`, `text-muted`, `border-subtle`, `accent`, `up`, `down`, `warn`, `danger`, `info`) wired without breaking legacy classes
- Tabular numerals + value-change flash on financial numbers
- Component docs (`purpose`, `variants`, `states`, `accessibility`, `motion`, `performance`, `testing`)
- Accessibility baseline: focus trapping, ARIA live regions, reduced-motion support

**Additional gates (per CLAUDE.md mandatory rules):**

- `npm run lint` zero errors
- `npm run typecheck` zero errors
- `npm run test` all pass
- `npm run build` succeeds
- `npx prettier --check .` clean
- WCAG AA contrast audit passes
- Independent verification agent returns PASS

---

## 2. Scope

### 2.1 In scope

| Component | Files | Description |
|-----------|-------|-------------|
| `cn()` utility | `src/lib/utils.ts` | `clsx` + `tailwind-merge` wrapper matching shadcn convention |
| `Button` | `src/components/ui/button.tsx` + `.test.tsx` + `.md` | Variants `primary / secondary / ghost / danger`; sizes `sm / md / lg`; compact density |
| `Card` | `src/components/ui/card.tsx` + `.test.tsx` + `.md` | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter` |
| `Table` | `src/components/ui/table.tsx` + `.test.tsx` + `.md` | Semantic table primitives with row hover via component token |
| `Badge` | `src/components/ui/badge.tsx` + `.test.tsx` + `.md` | Status pill `ok / warn / danger / info / neutral`; label carries meaning, dot is decorative |
| `Dialog` | `src/components/ui/dialog.tsx` + `.test.tsx` + `.md` | Radix-powered overlay; focus trap, `aria-modal`, Escape, destructive confirmation impact text |
| `Toast` | `src/components/ui/toast.tsx` + `.test.tsx` + `.md` | Context + `useToast` hook; variants `neutral / success / warn / danger`; auto/manual dismiss; assertive live region for danger |
| `NumericText` | `src/components/ui/numeric-text.tsx` + `.test.tsx` + `.md` | Tabular mono digits; 150 ms flash on value change; optional sign/suffix; reduced-motion bypass |
| Semantic tokens | `src/index.css` | Alias layer in `@theme inline` plus `--color-danger` and `--color-table-row-hover`; legacy classes unchanged |
| Motion | `src/index.css` | `flash-up`, `flash-down`, `dialog-overlay-in`, `dialog-content-in` keyframes; disabled under `prefers-reduced-motion` |
| Contrast audit | `scripts/contrast-audit.py` | WCAG AA check for all semantic text/action colors on `bg-base` |
| Docs index | `src/components/ui/README.md` | Conventions and catalog for the `ui/` package |

### 2.2 Out of scope (later F-Sprints)

- **F-Sprint 3** — SSE client, TanStack Query, Zustand, virtualized tables.
- **F-Sprint 4/5/6** — charts, surfaces, keyboard shortcuts, performance budgets.

---

## 3. Implementation Notes

- **Additive token strategy:** Existing legacy classes (`bg-abyss`, `text-ink`, `bg-up`) remain untouched. New portal code uses semantic aliases (`bg-bg-base`, `text-text-primary`, etc.) via Tailwind 4 `@theme inline`.
- **New `--color-danger` token:** Distinct from `--color-down` (short/loss/sell) for kill-switch / 5xx / stream-dropped states.
- **Hand-rolled shadcn patterns:** Installed `class-variance-authority`, `clsx`, `tailwind-merge`, and `@radix-ui/react-dialog` directly so color naming stays aligned to `design-tokens.md` instead of being overwritten by the shadcn CLI defaults.
- **No `lucide-react` yet:** Status dots and numeric signs use text characters to avoid icon bundle cost in this sprint.
- **`--color-ink-faint` adjusted** from `#6b7a90` to `#6d7c92` so `text-muted` on `bg-base` passes WCAG AA (4.52:1).
- **Toast fast-refresh warning:** `toast.tsx` exports both components and `useToast`, so `/* eslint-disable react-refresh/only-export-components */` was added at the top.

---

## 4. Local Quality Gates (2026-08-10)

| Gate | Command | Result |
|------|---------|--------|
| Install | `npm install` | PASS — deps added: `@radix-ui/react-dialog`, `class-variance-authority`, `clsx`, `tailwind-merge`; dev `@testing-library/user-event` |
| Lint | `npm run lint` (eslint) | PASS — clean after adding eslint-disable for `toast.tsx` hook export |
| Typecheck | `npm run typecheck` (tsc --noEmit) | PASS — clean |
| Test | `npm run test` (vitest) | PASS — 8 files, 19 tests |
| Build | `npm run build` (tsc + vite build) | PASS — dist: index.html 1.48 kB / css 29.53 kB (gzip 6.48 kB) / js 309.89 kB (gzip 98.36 kB) |
| Prettier | `npx prettier --check .` | PASS — 12 UI files reformatted via `prettier --write` |
| Contrast | `python3 scripts/contrast-audit.py` | PASS — all pairs ≥ 4.5:1 on `bg-base` |

**Bundle note:** JS gzip stays at 98.36 kB, well under the 300 kB budget.

---

## 5. Contrast Audit Detail

```text
WCAG AA contrast audit (normal text ≥ 4.5:1)

text-primary   on bg-base     16.44:1  PASS
text-secondary on bg-base      9.04:1  PASS
text-muted     on bg-base      4.52:1  PASS
accent         on bg-base      6.00:1  PASS
up             on bg-base      9.98:1  PASS
down           on bg-base      5.62:1  PASS
warn           on bg-base     10.49:1  PASS
danger         on bg-base      5.91:1  PASS
info           on bg-base     10.61:1  PASS

All pairs meet WCAG AA for normal text.
```

---

## 6. Independent verification

Pending — verification agent will be dispatched after commit per CLAUDE.md rule 8.

---

## 7. Acceptance Criteria Check

| Exit criterion | Status | Evidence |
|----------------|--------|----------|
| Seven primitives implemented | ✅ | `src/components/ui/{button,card,table,badge,dialog,toast,numeric-text}.tsx` |
| Semantic token aliases | ✅ | `src/index.css` `@theme inline` block; legacy classes preserved |
| Tabular numerals + flash | ✅ | `numeric-text.tsx` + `numeric-text.test.tsx` |
| Component docs | ✅ | `src/components/ui/*.md` with seven mandated sections; `README.md` index |
| Accessibility baseline | ✅ | Dialog focus trap/Escape/aria-modal; Toast assertive live region; reduced-motion media queries |
| Local gate | ✅ | lint / typecheck / test / build / prettier / contrast all PASS |

**Status legend:** ⏳ pending → ✅ done → 🚫 blocked

---

## 8. Open items before approval gate

1. **Independent verification agent** — dispatch after commit.
2. **Approval gate: AskUserQuestion** — approve F-Sprint 2 before F-Sprint 3 (SSE/state layer).

---

## 9. Sign-off

F-Sprint 2 (Design System Primitives) is implementation-complete with the local gate PASS. The component layer, semantic token aliases, and accessibility baseline are ready for the SSE client and state-management work in F-Sprint 3.
