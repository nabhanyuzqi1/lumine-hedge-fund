# Toast

## Purpose

Non-modal status notifications: fills, errors, stream health, kill-switch events.

## Variants

- `neutral`, `success`, `warn`, `danger`.
- `danger` uses `aria-live="assertive"`; others use `polite`.

## States

- Visible with auto-dismiss (default 5 s), manual dismiss, hover/focus on close button.

## Accessibility

- Viewport has `aria-live="polite"` and `aria-atomic="true"`.
- Each toast has `role="status"` and explicit `aria-live`.
- Dismiss button has accessible name.

## Motion

- None in F-Sprint 2. Motion can be added later under `prefers-reduced-motion`.

## Performance

- React context keeps state centralized; each toast cleans up its own timer.

## Testing

- `toast.test.tsx`: render via `useToast`, manual dismiss, auto-dismiss with fake timers, assertive live region for danger.
