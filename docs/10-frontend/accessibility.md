# Accessibility & Keyboard Model

## Overview

Accessibility contract for the Lumine institutional operator dashboard. This document consumes `design-tokens.md`, `wireframes.md`, `performance.md`, and Phase 9 `error-contract.md`. It defines keyboard navigation, focus management, screen-reader semantics, motion preferences, and contrast rules so the interface remains operable under stress, in noisy dealing rooms, and with assistive technology.

## Principles

1. **Keyboard first.** Every actionable element reachable and operable without a pointer.
2. **Focus is visible.** Operators must know where they are at all times.
3. **Color is never the only signal.** Up/down/warn/danger states carry icon, sign, or text companions.
4. **Motion is optional.** `prefers-reduced-motion` disables non-essential animation without breaking data updates.
5. **Screen-reader efficiency.** Labels and landmarks let users navigate dense tables and streams quickly.

## Color & contrast

| Surface | Minimum ratio | Evidence |
|---------|---------------|----------|
| Text primary on bg base | 7:1 (AAA) | `design-tokens.md` ink on abyss |
| Text secondary on bg base | 4.5:1 (AA) | labels, timestamps |
| Accent on bg base | 4.5:1 | links, focus ring |
| Danger/warn/up/down semantic | paired with non-color cue | arrows, +/- signs, icons |
| Data grid selection/hover | ≥ 3:1 against adjacent | table row hover |

- Directional colors (`--color-up`, `--color-down`, `--color-warn`, `--color-danger`) are always paired with a non-color cue per `design-tokens.md`.
- Charts expose patterns or labels in addition to color (legend, tooltip, shape differences).

## Focus model

### Visible focus ring

- Global `:focus-visible` uses 2px solid `var(--color-accent)`, 2px offset, 2px radius.
- Interactive components (Button, Link, Dialog trigger, table rows, Rail items, command palette items) receive the same ring.
- Never remove focus indicators without a replacement (`outline-none` must be combined with `focus-visible:ring-*`).

### Skip link

- First focusable element on every route is a visually hidden "Skip to main content" link.
- Becomes visible on focus, moves focus to `<main id="main-content">`.

### Focus order

- Follows visual layout: TopBar → KillSwitchBanner (if active) → Rail → main content → dialogs/modals.
- Dialogs trap focus while open; `Esc` closes unless the dialog contains an in-progress destructive action.
- Command palette is a modal dialog with focus initially on the search input; arrow keys move active item; `Enter` executes.

## Keyboard model

### Global shortcuts

| Shortcut | Action | Context |
|----------|--------|---------|
| `Mod+K` | Toggle command palette | global |
| `Mod+1` | Switch workspace to Trading | global |
| `Mod+2` | Switch workspace to Research | global |
| `Mod+3` | Switch workspace to Risk | global |
| `Mod+4` | Switch workspace to Ops | global |
| `Mod+J` | Navigate to Journal | global |
| `Mod+A` | Navigate to Admin Keys | global |
| `Esc` | Close command palette / dialog / flyout | global |

`Mod` = `Meta` on macOS, `Control` on Windows/Linux.

### Local shortcuts

| Scope | Shortcut | Action |
|-------|----------|--------|
| Tables | `↑` / `↓` | Navigate rows (virtualized tables delegate to ag-Grid keyboard model) |
| Tables | `Enter` | Open selected row detail |
| Command palette | `↑` / `↓` | Move active item |
| Command palette | `Enter` | Execute active item |
| Command palette | `Esc` | Close palette |
| Rail | `←` / `→` / `↑` / `↓` | Move between workspace buttons (logical direction) |

### Guard rules

- Shortcuts are suppressed when focus is inside an input, textarea, or `contenteditable`.
- Browser-reserved combos (`Mod+R`, `Mod+W`, `Mod+T`, `Mod+N`) are never overridden.
- `Mod+K` is the only meta shortcut that works inside inputs so operators can open the palette from anywhere.

## Screen reader semantics

### Landmarks

- `header` for TopBar.
- `nav` for Rail/workspace switcher.
- `main` with `id="main-content"` for page content.
- Dialogs use Radix Dialog with `role="dialog"`, `aria-modal="true"`, and `aria-labelledby` pointing to the dialog title.

### Live regions

- Kill-switch banner: `aria-live="polite"` so operators are notified when the global kill switch engages.
- Stream dropped / gap detected alerts: `aria-live="assertive"`.
- ActivityLog appends: polite live region on the log container.

### Labels

- All icon-only buttons carry `aria-label` (e.g. workspace switcher, close dialog, copy path).
- Numeric values include unit context where needed (`aria-label="P and L positive 550 US dollars"`).
- Status badges use `aria-label` combining status and severity.

### Tables

- Data tables have `<caption>` or `aria-label` describing the dataset.
- Column headers use proper `<th scope="col">`.
- Row selection state is communicated via `aria-selected`.

## Motion & reduced motion

- `prefers-reduced-motion` disables:
  - value-flash animations on P&L/quote updates,
  - pane enter/exit transitions,
  - non-essential hover transitions.
- Essential motion remains:
  - real-time data updates (numbers change instantly),
  - stream status dot pulse (static color if reduced motion),
  - progress stepper transitions (instant jump).

## Responsive & zoom

- Layout remains usable at 320 CSS px width.
- Text scales with browser zoom up to 200% without horizontal clipping.
- Touch targets minimum 44×44 px on compact density.

## Component obligations

Every reusable component documents:

- Keyboard operation.
- Focus behavior.
- ARIA roles/states.
- Motion behavior under `prefers-reduced-motion`.
- Screen-reader label strategy.

See `components.md` for the component template.

## Testing strategy

| Level | Tool | Coverage |
|-------|------|----------|
| Lint | `eslint-plugin-jsx-a11y` | static rules in CI |
| Unit | `@testing-library/react` + user-event | keyboard navigation, focus trapping, label presence |
| CI | Lighthouse | Accessibility ≥ 95 |
| Manual | keyboard-only walkthrough | every route, every action |

## What this document does NOT define

- Component prop APIs (see `components.md`).
- Color values (see `design-tokens.md`).
- Performance budgets (see `performance.md`).

## Phase boundary

Accessibility semantics, keyboard model, and contrast rules are fixed here. Implementation and component-level ARIA attributes belong to Phase 14+; this document is the spec against which they are verified.
