# Table

## Purpose

Dense tabular data: positions, orders, risk metrics, agent votes. Does not include virtualization; that lands in F-Sprint 4+ surfaces.

## Variants

- Header row with uppercase, tracking-wide labels.
- Body rows with subtle bottom border and hover highlight via `--color-table-row-hover`.

## States

- Hover, `data-[state=selected]` (accent 10 % tint).

## Accessibility

- Native `<table>` semantics: `thead`, `tbody`, `tr`, `th`, `td`.
- Numeric cells should add `font-mono tabular-nums`.

## Motion

- 150 ms background transition on row hover.

## Performance

- Avoid large un-virtualized tables in production; this primitive is for moderate datasets.

## Testing

- `table.test.tsx`: semantic roles render, numeric cell classes present.
