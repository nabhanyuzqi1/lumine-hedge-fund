# Dialog

## Purpose

Modal overlay for confirmations, forms, and critical warnings. Built on `@radix-ui/react-dialog` for focus trapping and ARIA semantics.

## Variants

- Standard content shell plus `DialogHeader`, `DialogFooter`, `DialogTitle`, `DialogDescription`.
- Destructive confirmations must put impact text inside `DialogDescription` per `docs/10-frontend/components.md` L88-94.

## States

- Closed, open (animated), closing (`data-[state=closed]:animate-none`).

## Accessibility

- `aria-modal="true"`, `role="dialog"`.
- Focus moves into the dialog on open; Tab cycles within; Escape closes.
- Title and description wired to Radix for announcement.

## Motion

- Overlay fades in over 250 ms.
- Content scales from 0.98 and translates 4 px up over 250 ms.
- Disabled under `prefers-reduced-motion`.

## Performance

- Portals to `document.body` via Radix; avoids z-index stacking issues.

## Testing

- `dialog.test.tsx`: open/close, `aria-modal`, Escape dismissal, description text presence.
