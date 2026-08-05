# ADR-0037 — Market calendar, holiday, and economic-event contract

- **Status:** Accepted
- **Phase:** 03-agents-and-contracts
- **Date:** 2026-08-02
- **Owner:** architects
- **Supersedes:** —
- **Superseded by:** —

## Context

`physical-erd.md` sizes tick volume at "~23h/day, ~5d/wk" — a
typical-session approximation that ignores holidays, DST session shifts,
and economic-event blackouts. A scheduler that fires on a bank holiday or
during a FOMC blackout wastes a cycle and, worse, can produce a decision
against stale/no-liquidity conditions. The session/holiday/event calendar
must be a versioned, hash-pinned registry artifact so a decision's
calendar context is reproducible.

## Decision

A `calendar_versions` registry table stores session windows (IANA
timezone-referenced, DST-aware), holidays (per exchange/broker), and
economic-event blackout windows. The scheduler consults the calendar
synchronously before triggering: closed market → no trigger; blackout →
defer until window clears. Session windows are computed from IANA tz rules
— hardcoded UTC offsets are forbidden. `lineage_records` gains a
`calendar_version_id` pin so a decision's session/holiday/blackout context
is reproducible. Blackout is per-strategy: a swing strategy may ignore a
15-min FOMC window that an intraday strategy respects.

## Rationale

- IANA tz rules handle DST automatically — hardcoded offsets break twice a
  year.
- Per-strategy blackout respects different strategy sensitivities to news
  events.
- Calendar consultation is cheap (lookup, not computation) and synchronous
  on the trigger path.
- Pinning `calendar_version_id` in lineage makes the calendar context of a
  past decision recoverable forever (principle #6).

## Consequences

- Positive: no wasted cycles on holidays or blackouts.
- Positive: DST shifts are handled automatically, not manually patched.
- Positive: calendar context is auditable per decision.
- Negative: the calendar must be maintained (holidays added annually,
  event feed subscribed).
- Reversibility: the calendar follows the standard supersession model.

## Cross-references

- Related ADRs: ADR-0035, ADR-0014
- Implements principle(s): #6, #10
- Affects phases: 03, 05, 07
- Source document: `../03-agents-and-contracts/market-calendar-contract.md` (S21)
