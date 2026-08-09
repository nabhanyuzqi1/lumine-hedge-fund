# Badge

## Purpose

Compact status pill for instrument state, connection health, or pipeline stage.

## Variants

- `ok`, `warn`, `danger`, `info`, `neutral`.
- Each maps to a semantic background tint and text color.

## States

- Static only.

## Accessibility

- Status dot is `aria-hidden`; the label text carries meaning.
- `aria-label` mirrors the label for screen-reader context.

## Motion

- None.

## Performance

- Single span, no JS.

## Testing

- `badge.test.tsx`: label renders, dot is decorative, danger tone class applied.
