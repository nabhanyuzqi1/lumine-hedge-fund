# Scope & Non-Goals

## Initial scope

- **Capital type** — Proprietary capital only.
- **Instrument** — XAUUSD only.
- **Brokerage** — One broker via MetaTrader 5.
- **Accounts** — One MT5 account.
- **Strategies** — Intraday and swing strategy books, operated side by side
  with independent attribution.
- **Autonomy** — Autonomous analysis, trade selection, position sizing,
  entry, management, exit, and reconciliation within owner-set policy.
- **Governance** — CIO-controlled independent kill switch and restart
  authorization.
- **Risk posture** — AI may adjust exposure and internal risk posture
  dynamically; no fixed drawdown ceiling is imposed (see Risks below).
- **Adaptation** — Self-modifying strategy, prompt, model, and policy
  candidates may run in sandbox / shadow mode only.

## Non-goals (first release)

- External investor capital or fund administration.
- Retail signals, copy trading, or strategy marketplace.
- Client tenancy or multi-tenant isolation.
- Multi-asset live trading (forex, indices, commodities, crypto, stocks,
  futures). Architecture must remain modular for future support, but no
  second asset class ships in the first release.
- True high-frequency trading (millisecond-scale). MT5 + Linux VPS + LLM
  decision latency precludes HFT.
- Autonomous production self-modification. Self-modifying artifacts cannot
  self-promote into production.
- Replacing legal human accountability with AI roles. AI CIO/CEO/Officer
  personas are operational roles, not legal accountability holders.
- Guaranteed returns or capital preservation. The mandate accepts
  existential capital risk in exchange for absolute-return pursuit.

## Long-term scope (post first release)

These are directionally in scope for the long-term roadmap but explicitly
out of the first release:

- Additional instruments and asset classes.
- Multiple brokers and multiple accounts.
- Managed fund operations (only if strategy is revised).
- Strategy marketplace (only if strategy is revised).
- Cloud-native horizontal scaling.
- Institutional SaaS licensing (only if strategy is revised).

## Risks accepted by Phase 0

| Risk | Source | Mitigation |
|------|--------|------------|
| No fixed drawdown ceiling | AI controls its own dynamic limit up to an unbounded maximum | CIO kill switch; sandbox-only self-modification; strategy suspension logic. Residual tail risk accepted. |
| Full trade autonomy | System executes without per-trade human approval | Deterministic risk envelope; lineage; CIO emergency authority. |
| Hybrid intraday/swing attribution | Two horizons in one account risk blending | Separate strategy books with independent attribution and suspension. |
| XAUUSD concentration | Single instrument exposure | Accepted for pilot; diversified through regime and strategy variety. |
