# Wireframes

## Overview

Textual layout wireframes per page. Visual mockups are produced with
specialist design tooling during design-system execution; these
layouts are the binding structure.

## W1 — Terminal `/` (Trading workspace, default)

```
┌────────────────────────────────────────────────────────────────────┐
│ ●LIVE  XAUUSD 2,341.25 ▲  | Kill: OFF | 14:30:01 UTC | ●●●●●● 6/6  │ TopBar 32px
├────┬──────────────────────────────────────────────┬────────────────┤
│ T  │ ┌─ PriceChart ──────────────────────────────┐│ ┌─ Committee ─┐│
│ r  │ │ candle XAUUSD + volume + order markers    ││ │ ▸ Analyst:  ││
│ a  │ │                              ●LIVE        ││ │   Tech Bull ││
│ d  │ ├─ QuotePanel ──────────────────────────────┤│ │   0.82 ▓▓▓  ││
│ e  │ │ Bid 2,341.20 | Ask 2,341.30 | Spr 0.10    ││ │ ▸ IC: APPROVE││
│────│ └────────────────────────────────────────────┘│ │ ▸ CIO prop  ││
│ R  │ ┌─ Positions (ag-Grid) ──────────────────────┐│ │  ▼ expand   ││
│ e  │ │ Sym|Side|Qty|Entry|Curr|P&L                ││ ├─ Activity ─┤│
│ s  │ │ XAU|L|0.5|2,330|2,341|+550.00 ▲flash       ││ │ 14:28 gap_ ││
│────│ ├─ Orders ───────────────────────────────────┤│ │  detected  ││
│ R  │ │ XAU|BUY LIM|0.3|2,335|PENDING [x]          ││ │ 14:25 429  ││
│ i  │ └────────────────────────────────────────────┘│ │  retry 12s ││
│ s  │ ┌─ RiskGauges ───────────────────────────────┐│ └────────────┘│
│ k  │ │ [Exposure 62%] [DD 3.1%] [Margin 18%]      ││                │
│────│ └────────────────────────────────────────────┘│                │
│ O  │                                                │                │
│ p  │                                                │                │
│ s  │                                                │                │
└────┴──────────────────────────────────────────────┴────────────────┘
```

Rail items: Trading (default), Research, Risk, Ops — pane
rearrangement only, streams persist.

## W2 — Order Detail `/orders/:orderId`

```
┌────────────────────────────────────────────────────────────────────┐
│ ← Back | Order #a1b2c3 XAUUSD BUY 0.5                    ●LIVE     │
├──────────────────────────────────────┬─────────────────────────────┤
│ Header card:                         │ OrderLifecycleTimeline:     │
│  Symbol XAUUSD  Side BUY             │ ● RECEIVED                  │
│  Qty 0.5        Type LIMIT           │ ● VALIDATED                 │
│  Entry 2,330.00 Curr 2,341.25        │ ● RISK_CHECK                │
│  P&L +550.00 (▲ mono, flash)         │ ○ ACTIVE   ← current        │
│  Status ACTIVE (Badge)               │ ○ FILLED                    │
│ [Cancel Order] (danger, dialog)      │ (timestamps per state)      │
├──────────────────────────────────────┴─────────────────────────────┤
│ Events feed (SSE execution-orders, symbol filter):                 │
│  14:22:01 status → ACTIVE   14:20:44 status → RISK_CHECK  ...      │
└────────────────────────────────────────────────────────────────────┘
```

## W3 — Workflow Run Detail `/workflows/:id/runs/:runId`

```
┌────────────────────────────────────────────────────────────────────┐
│ ← Back | Run #r-77 workflow:xauusd-committee    Status: RUNNING    │
├──────────────────────────────────────┬─────────────────────────────┤
│ RunStepper (12 progress states):     │ CommitteeFeed (run filter): │
│ ●──●──●──●──◐──○──○──○──○──○──○──○  │ ▸ Analyst Tech: Bull 0.82   │
│ init analysts debate IC CIO risk     │ ▸ Analyst Macro: Neutral    │
│                                      │ ▸ IC Decision: APPROVE      │
│ Terminal: COMPLETED/FAILED/CANCELLED │ ▸ CIO Proposal: BUY 0.5...  │
│ /KILLED (danger Badge if killed by   │   [View Lineage →]          │
│ kill switch, Phase 7 D7-9)           │                             │
├──────────────────────────────────────┴─────────────────────────────┤
│ Journal (REST, cursor-paginated): Phase 7 durable journal events   │
└────────────────────────────────────────────────────────────────────┘
```

## W4 — Lineage Detail `/lineage/:lineageId`

```
┌────────────────────────────────────────────────────────────────────┐
│ ← Back | Lineage #lin-9f3e                        2026-08-01 14:20 │
├──────────────────────────────────────┬─────────────────────────────┤
│ Summary: symbol, decision, size,     │ LineageViewer:              │
│ confidence, analyst votes (4),       │ proposal JSONB tree         │
│ risk verdict, override badge if      │ (expand/collapse, search,   │
│ manual override (Phase 4)            │  copy path)                 │
└──────────────────────────────────────┴─────────────────────────────┘
```

## W5 — Journal `/journal`

```
┌────────────────────────────────────────────────────────────────────┐
│ Journal                        [symbol▾][portfolio▾][date range][↻]│
├────────────────────────────────────────────────────────────────────┤
│ JournalTable (cursor pagination):                                  │
│  ts | symbol | side | qty | price | pnl                            │
│  ... 50 rows/page — Load more (cursor, has_more)                   │
└────────────────────────────────────────────────────────────────────┘
```

## W6 — Admin Keys `/admin/keys`

```
┌────────────────────────────────────────────────────────────────────┐
│ API Keys                                    [+ Create Key]         │
├────────────────────────────────────────────────────────────────────┤
│ ApiKeyTable:                                                       │
│  key_id | prefix | scopes (Tags) | created | last_used | [Revoke]  │
│  lk_a1… | lk_a1b2| read:market…  | Jul 12  | 2m ago    |           │
└────────────────────────────────────────────────────────────────────┘
 CreateKeyModal → secret shown once + copy. Revoke → confirm dialog.
```

## Kill-switch active state (all pages)

Full-width danger banner below TopBar:
`KILL SWITCH ACTIVE — {tier} — {reason} — writes blocked`.
All write-action buttons disabled with tooltip explaining the 403
`KILL_SWITCH_ACTIVE` refusal. Read panes and SSE streams continue
(per error-contract.md kill-switch interaction).

## What this document does NOT define

- Visual design values (colors, exact spacing — design-tokens.md).
- Responsive breakpoints below desktop operator range (implementation
  detail, Phase 14+; institutional terminal targets desktop first).
- Component internals (Phase 14+).

## Phase boundary

Page structures and information hierarchy are fixed here. Visual
refinement happens at design-system execution; implementation at
Phase 14+.
