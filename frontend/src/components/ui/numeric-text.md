# NumericText

## Purpose

Displays financial numbers with tabular monospaced digits and value-change flash. Used for prices, P&L, deltas, exposures.

## Variants

- `tone`: `up`, `down`, `neutral`.
- Optional `showSign` and `suffix`.

## States

- Static, flash-up (150 ms green), flash-down (150 ms red).

## Accessibility

- `aria-label` exposes the raw numeric value.
- Tone is paired with sign/suffix text (non-color cue).
- Flash animation disabled under `prefers-reduced-motion`.

## Motion

- 150 ms flash keyframe from `var(--color-up)` / `var(--color-down)` to inherited color.

## Performance

- `tabular-nums` prevents digit-width jitter on updates.
- Memo-friendly; no heavy formatting.

## Testing

- `numeric-text.test.tsx`: tabular numerals class, up/down flash classes, sign/suffix rendering.
