# Card

## Purpose

Container for related information on a dense institutional dashboard: position tiles, risk summaries, committee votes.

## Variants

- Single raised surface with panel radius and subtle border.
- Composed of `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`.

## States

- Default only. Consumers add hover/selected states via wrapper classes.

## Accessibility

- `CardTitle` renders an `<h3>` so card hierarchy is explicit.
- Description is a `<p>` linked visually to the title.

## Motion

- None by default. Elevated surfaces rely on static shadow.

## Performance

- No JavaScript; minimal DOM depth.

## Testing

- `card.test.tsx`: composition renders all subcomponents and semantic heading.
