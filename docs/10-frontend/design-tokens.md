# Design Tokens

## Overview

Token *structure and semantics* for the Lumine design system. Concrete
palette values are locked during design-system execution with
specialist design tooling (per project direction); the layered
contract below is binding regardless of final values.

## Three-layer structure

1. **Primitive** — raw palette: `gray-900…50`, `green-500`,
   `red-500`, `amber-500`, `blue-500`, etc. Never referenced directly
   by components.
2. **Semantic** — meaning: `--color-bg-base`, `--color-bg-raised`,
   `--color-bg-overlay`, `--color-border-subtle`,
   `--color-text-primary/secondary/muted`, `--color-accent`,
   `--color-up`, `--color-down`, `--color-warn`, `--color-danger`,
   `--color-info`.
3. **Component** — per component: `--chart-grid`,
   `--chart-crosshair`, `--table-row-hover`, `--pane-header-bg`, etc.

Components consume semantic/component tokens only — never primitives,
never hardcoded values.

## Trading domain semantics (mandatory)

| Token | Meaning |
|-------|---------|
| `--color-up` | Long positions, profit, buy orders, rising equity |
| `--color-down` | Short positions, loss, sell orders, falling equity |
| `--color-warn` | Stream stale, `gap_detected`, degraded mode |
| `--color-danger` | Kill switch active, 5xx errors, stream dropped |
| `--color-accent` | Focus, selection, links, primary actions |

Directional colors are always paired with a non-color cue (arrow,
sign, icon) — color is never the sole signal (accessibility).

## Typography

| Role | Face | Scale |
|------|------|-------|
| UI text | sans (Inter / IBM Plex Sans) | base 12px; scale 11/12/13/14/16/20 |
| Numeric/data | mono with **tabular numerals mandatory** (IBM Plex Mono / JetBrains Mono) | 12–13px data; 16–20px key figures (equity, exposure) |

- Pane headers: 11px, uppercase, tracking-wide.
- All prices, P&L, quantities, percentages use tabular-numeral mono —
  digits must not shift horizontally on update.

## Spacing & density

- 4px base scale: 2 / 4 / 6 / 8 / 12 / 16 / 24.
- Default density **compact**: table cell padding 4–6px, pane header
  24px, grid gaps 4–8px (institutional density).
- `comfortable` density available via settings for large displays.

## Elevation, borders, radius

- Dark theme institutional: bg base dark; pane surfaces raised +1
  step; overlays +2.
- 1px subtle borders; no large shadows; 2px accent focus ring.
- Radius 2–4px — crisp, not rounded-SaaS.

## Motion

- Durations: 100 / 150 / 250ms; standard easing.
- Value-change flash: green/red 150ms on P&L/quote updates.
- `prefers-reduced-motion` disables flash and non-essential animation.

## Theming

- CSS custom properties; `dark` default theme; `light` optional.
- Theme switching swaps semantic layer only — components unchanged.

## What this document does NOT define

- Final hex/oklch palette values (design-system execution).
- Font file hosting/subsetting (Phase 11).
- Component implementations (Phase 14+).

## Phase boundary

Token structure, semantics, typography rules, density, and motion are
fixed here. Concrete visual values are finalized with specialist
design tooling before Phase 14 implementation.
