# Button

## Purpose

Primary action surface for the Lumine portal. Compact institutional density; used for form submission, navigation triggers, and destructive confirmations.

## Variants

- `primary` — default CTA, `bg-accent`.
- `secondary` — low-emphasis action on a raised surface.
- `ghost` — inline action, no background until hover.
- `danger` — destructive actions (kill switch, cancel, revoke). Must be paired with a `Dialog` confirmation stating impact.

## States

- Default, hover, focus-visible (2 px accent ring), active, disabled (`pointer-events-none opacity-50`).

## Accessibility

- Native `<button>`; keyboard activation with Enter/Space.
- Visible `focus-visible:ring-2 focus-visible:ring-accent`.
- Disabled state uses `disabled` attribute, not just styling.

## Motion

- 150 ms color transition on hover/focus.

## Performance

- Pure CSS transition, no layout shift.

## Testing

- `button.test.tsx`: render, danger class, disabled click blocking, ref forwarding.
