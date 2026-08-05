# Market Calendar Contract — Sessions, Holidays, Economic Events

## Overview

`physical-erd.md` sizes tick volume at "~23h/day, ~5d/wk" — a
typical-session approximation that ignores holidays, DST session
shifts, and economic-event blackouts. A scheduler that fires on a
bank holiday or during a FOMC blackout wastes a cycle and, worse, can
produce a decision against stale/no-liquidity conditions. This
document fixes the authoritative session/holiday/economic-event
calendar, its versioned artifact contract, scheduler consultation
rules, and the amendment to physical-erd tick math.

It amends `physical-erd.md` (Phase 5) and the scheduler (Phase 7).

## Decision: D3-10 — Versioned, hash-pinned calendar as a registry artifact

### Authoritative session calendar per symbol

Each symbol resolves to a session calendar defining when the market
is open. For FX (XAUUSD V1), sessions are named windows in UTC with
IANA timezone references:

| Session | IANA tz | Typical UTC window |
|---------|---------|--------------------|
| Asia | Asia/Tokyo | 23:00–08:00 (prev day) |
| London | Europe/London | 07:00–16:00 |
| New York | America/New_York | 12:00–21:00 |

For stocks/futures (later phases), exchange hours replace FX sessions.
Windows are stored in UTC but derived from IANA rules — never
hardcoded offsets.

### Holiday calendar per exchange/broker

Holidays (Christmas, NYSE holidays, broker-specific closures) are
encoded per exchange/broker. A holiday entry:

```
{ date: "2026-12-25", exchange: "FX-global", reason: "Christmas", closed: true }
{ date: "2026-07-04", exchange: "NYSE", reason: "Independence Day", closed: true }
```

Closed days produce no session windows; the scheduler does not fire.

### DST handling

Session windows shift twice a year because London/NY local time
moves. The calendar encodes IANA tz rules (e.g.
`America/New_York`) and computes the UTC window for any given date
from those rules. Hardcoded UTC offsets are forbidden — they break on
DST transitions. The calendar is regenerated/validated per date from
IANA data, not frozen as static offsets.

### Economic-event feed integration

High-impact events (NFP, FOMC, CPI) carry a configurable blackout
window per strategy:

```
{
  "event_id": "FOMC-2026-03-18",
  "event_ts": "2026-03-18T18:00:00Z",
  "impact": "high",
  "blackout": { "pre_min": 15, "post_min": 15 }
}
```

Each strategy declares which event categories trigger a blackout and
the window. During the blackout window the scheduler defers triggers
for that strategy until the window clears. Blackout is per-strategy —
a swing strategy may ignore a 15-min FOMC window that an intraday
strategy respects.

### Scheduler consults the calendar before triggering

```
on trigger candidate:
  if calendar.is_closed(symbol, candidate_ts):
      skip (no trigger, no decision)
  if calendar.in_blackout(strategy, candidate_ts):
      defer until blackout window clears
  else:
      fire trigger
```

Closed market -> no trigger. Blackout -> defer, not fail. The
calendar is consulted synchronously on the trigger path; it is cheap
(lookup, not computation).

### Versioned, hash-pinned artifact

The calendar is a registry artifact, not a free-floating config. A
new table:

```sql
CREATE TABLE calendar_versions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version         SEMVER NOT NULL,
  calendar_hash   TEXT NOT NULL,                  -- SHA-256 of canonical calendar content
  scope           TEXT NOT NULL,                  -- 'session' | 'holiday' | 'economic_event'
  symbol          TEXT,                           -- NULL = global (holidays apply to all symbols)
  content         JSONB NOT NULL,                 -- sessions, holidays, event feed ref
  effective_from  TIMESTAMPTZ NOT NULL,
  effective_to    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  status          registry_status NOT NULL,
  superseded_by   UUID REFERENCES calendar_versions(id),
  UNIQUE (version, scope, symbol)
);
```

Same supersession model as other registry artifacts
(`registry-schema.md`). Only `production` rows are consulted at
runtime; retired rows stay pinned in lineage forever.

### Lineage pins `calendar_version_id`

`lineage_records` gains a pin (additive):

| Column | Type | Notes |
|--------|------|-------|
| `calendar_version_id` | UUID | FK to `calendar_versions.id`; the calendar version active for this decision |

A decision's session/holiday/blackout context is reproducible: resolve
the pinned calendar version and the event feed reference to
reconstruct exactly which session window and event context the
decision was made under.

## Amendment to physical-erd.md tick math

`physical-erd.md` states "~23h/day, ~5d/wk" for tick volume. This is
amended: ~23h/day is the **typical session**, not a guarantee.
Effective trading days per year exclude holidays and are
calendar-adjusted. Capacity math uses:

```
effective_days_per_year = nominal_trading_days - holiday_count
effective_session_hours = session_window_utc_end - session_window_utc_start (per date, DST-aware)
tick_volume_estimate = tick_rate * effective_session_seconds * effective_days
```

The "~43–216M rows/yr" band in physical-erd remains a reasonable
order-of-magnitude estimate for XAUUSD, but the precise number for
any given year is calendar-adjusted, not a flat 260 days x 23h.

## What this document does NOT define

- IANA tzdata installation/updates — Phase 11 ops.
- Economic-event feed provider selection (Bloomberg/Reuters/Forex
  Factory) — Phase 14, abstracted behind the `content` JSONB.
- Strategy-specific blackout parameter values — strategy
  `params` JSONB, promoted via registry.
- Scheduler internals beyond the consult contract — Phase 7.

## Phase boundary

This document amends `physical-erd.md` (Phase 5) by making tick math
calendar-aware. It amends the scheduler (Phase 7) by requiring
calendar consultation before trigger. It adds `calendar_versions` to
the registry (Phase 3). It does not define the event-feed provider,
tzdata ops, or scheduler code.
