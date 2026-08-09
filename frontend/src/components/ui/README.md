# UI primitives

This directory contains the institutional design-system primitives for Lumine's frontend. They follow shadcn/ui patterns but consume Lumine's own semantic tokens so the design-tokens contract in `docs/10-frontend/design-tokens.md` stays intact.

## Conventions

- All components are TypeScript + React forward refs where applicable.
- `cn()` from `src/lib/utils.ts` merges Tailwind classes and resolves conflicts.
- `cva` is used for any component with more than two visual variants.
- Colors come from the semantic layer (`bg-bg-base`, `text-text-primary`, `text-up`, `bg-danger`, etc.). Primitive token classes (`bg-abyss`, `text-ink`) are still valid but reserved for legacy landing surfaces.
- Motion durations are 100 ms, 150 ms, or 250 ms. `prefers-reduced-motion` disables non-essential animation.
- Directional colors (`up`, `down`, `danger`) are always paired with a non-color cue: label text, sign character, or aria label.

## Component docs

Each component has a dedicated markdown file with the seven mandated sections from `docs/10-frontend/components.md`:

- [Button](./button.md)
- [Card](./card.md)
- [Table](./table.md)
- [Badge](./badge.md)
- [Dialog](./dialog.md)
- [Toast](./toast.md)
- [NumericText](./numeric-text.md)
