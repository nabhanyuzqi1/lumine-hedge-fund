# DataTable

## Purpose

Virtualized table for large realtime datasets (positions, orders, committee
feed). Renders only visible rows plus overscan so the UI stays at 60fps with

> 10k rows.

## Variants

- Fixed row height (default 40px) — simplest and fastest.
- Custom row height via `rowHeight` prop.
- Empty state with configurable `emptyMessage`.

## States

- Loading: parent shows skeleton or placeholder; `DataTable` receives empty
  `data`.
- Empty: renders `emptyMessage` centered across all columns.
- Scrolling: only viewport rows exist in DOM.

## Accessibility

- Uses semantic `<table>`, `<thead>`, `<tbody>`.
- Sticky header remains visible while scrolling.
- Row cells are plain `<div>` inside a single `<tr>` for virtualization; focus
  management is the responsibility of the consuming pane.

## Motion

- None by default. Hover row background uses `bg-table-row-hover` (150ms
  transition). Respect `prefers-reduced-motion` by inheriting the global
  media query in `index.css`.

## Performance

- `@tanstack/react-virtual` measures and recycles rows.
- Parent must pass a stable `getRowId` and a fresh array reference only when
  data actually changes. Avoid mutating row objects in place.
- `overscan: 8` balances paint ahead vs. DOM size.

## Testing

- `data-table.test.tsx`: asserts empty state, virtualized render (only a
  subset of rows mounted), and row-height measurement.
