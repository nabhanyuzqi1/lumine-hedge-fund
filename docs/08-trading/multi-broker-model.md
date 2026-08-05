# Multi-Broker Model

## Overview

Decision **D8-4**: the system is single-broker by deployment but
multi-broker by schema. `risk-engine.md` and the Phase 5 ERD assume a
single MT5 broker — hardcoded symbol semantics, pip values, margin
rules, and session calendars. Adding multi-broker support later as a
schema migration is expensive and error-prone (every position/fill
row needs re-attribution). This document fixes the multi-broker
schema now, so V1 ships with one broker but the schema is
multi-broker-ready.

This document amends `physical-erd.md` (Phase 5) and `risk-engine.md`
(Phase 8).

## Decision(s)

- **D8-4a** — `brokers` registry table (id, name, adapter_class,
  session_calendar_ref, margin_rule_set).
- **D8-4b** — `accounts` table (id, broker_id, account_id_at_broker,
  currency, leverage, status).
- **D8-4c** — `positions.account_id` and `fills.account_id` (NOT
  NULL) — V1 ships with one account, schema is multi-broker-ready.
- **D8-4d** — `BrokerRiskAdapter` interface: symbol/margin/session
  semantics parameterized by adapter, not hardcoded.
- **D8-4e** — Consolidated exposure calculator: net + gross exposure
  per broker, per currency, per account, per book.
- **D8-4f** — Risk engine formulas parameterized by adapter, not
  hardcoded.
- **D8-4g** — "Max total exposure 5% of equity" enforced per-account
  AND consolidated — both must hold.
- **D8-4h** — Migration: existing single-broker rows get a default
  `account_id` backfilled.

## (a) brokers registry table

```sql
CREATE TABLE brokers (
  broker_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                 TEXT NOT NULL UNIQUE,        -- 'mt5_icmarkets' | 'mt5_pepperstone' | ...
  adapter_class        TEXT NOT NULL,               -- 'mt5' | 'fix' | 'crypto_exchange' | ...
  session_calendar_ref TEXT NOT NULL,               -- reference to session calendar (trading hours, holidays)
  margin_rule_set      TEXT NOT NULL,               -- 'retail_fx' | 'pro_fx' | 'crypto_isolated' | ...
  base_currency        TEXT NOT NULL,               -- 'USD' | 'EUR' | ...
  status               TEXT NOT NULL,               -- 'active' | 'suspended' | 'decommissioned'
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  config               JSONB NOT NULL               -- adapter-specific (server URLs, login env)
);
```

`brokers` is a registry table: append-only, never deleted. A
decommissioned broker stays in the table so historical `positions` and
`fills` resolve their `broker_id`. `adapter_class` is the Python class
that implements `BrokerRiskAdapter` (line d) — resolved at runtime,
never hardcoded in risk math.

## (b) accounts table

```sql
CREATE TABLE accounts (
  account_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  broker_id            UUID NOT NULL REFERENCES brokers(broker_id),
  account_id_at_broker TEXT NOT NULL,               -- broker's own account number/login
  currency             TEXT NOT NULL,               -- account deposit currency: 'USD' | 'EUR'
  leverage             NUMERIC(10,2) NOT NULL,      -- 100.00, 500.00, 1.00 (crypto)
  status               TEXT NOT NULL,               -- 'active' | 'suspended' | 'closed'
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (broker_id, account_id_at_broker)
);
```

One broker may have multiple accounts (e.g., a prop account and a live
account at the same broker, or accounts in different currencies). The
`(broker_id, account_id_at_broker)` unique constraint prevents
duplicate registration.

## (c) positions and fills gain account_id

```sql
-- Amend positions (Phase 5 ERD)
ALTER TABLE positions
  ADD COLUMN account_id UUID NOT NULL REFERENCES accounts(account_id);

-- Amend fills (Phase 5 ERD)
ALTER TABLE fills
  ADD COLUMN account_id UUID NOT NULL REFERENCES accounts(account_id);
```

Both columns are `NOT NULL` — every position and fill must attribute
to an account. This is a schema-level invariant: a fill without an
account is a data integrity violation.

`lineage_records` does NOT gain `account_id` directly — the account is
resolved from the execution context (the ExecutionRouter knows which
account it dispatched to). The fill carries `account_id`, and the
lineage-to-fill join provides account attribution. This avoids
denormalizing account into the decision record (which is about the
decision, not the execution venue).

V1 ships with exactly one row in `brokers` (the MT5 broker) and one
row in `accounts` (the live account). The schema is multi-broker-
ready; the deployment is not.

## (d) BrokerRiskAdapter interface

```python
# Logical interface (Phase 14 owns the implementation)
class BrokerRiskAdapter(Protocol):
    def get_max_volume(self, symbol: str, account: Account) -> Decimal:
        """Max tradeable volume for symbol on this broker/account."""
        ...

    def get_pip_value(self, symbol: str, account: Account) -> Decimal:
        """Pip value in account currency for symbol."""
        ...

    def compute_margin(
        self, symbol: str, size: Decimal, price: Decimal, account: Account
    ) -> Decimal:
        """Required margin in account currency."""
        ...

    def session_state(
        self, symbol: str, account: Account, ts: datetime
    ) -> SessionState:
        """Whether the symbol's market is open/closed at ts for this broker."""
        ...
```

V1 ships one implementation: `MT5RiskAdapter` (implements all four
methods against MT5 broker semantics). The risk engine (line f) calls
these methods — it never reads pip values, margin rules, or session
state from hardcoded constants.

The adapter is resolved from `brokers.adapter_class` at runtime. To
add a new broker: insert a `brokers` row, implement the adapter class,
no risk-engine code change.

## (e) Consolidated exposure calculator

The exposure calculator produces a multi-dimensional breakdown:

| Dimension | Metric | Purpose |
|-----------|--------|---------|
| Per account | net + gross exposure | account-level risk limit enforcement |
| Per broker | net + gross exposure | broker-level risk (counterparty) |
| Per currency | net + gross exposure | FX exposure (e.g., long USD, short JPY) |
| Per book | net + gross exposure | book-level attribution (principle #5) |

```sql
-- Example: consolidated exposure per account
SELECT
  a.account_id,
  a.currency,
  SUM(CASE WHEN p.side = 'BUY'  THEN p.size * p.current_price ELSE 0 END) AS gross_long,
  SUM(CASE WHEN p.side = 'SELL' THEN p.size * p.current_price ELSE 0 END) AS gross_short,
  SUM(CASE WHEN p.side = 'BUY'  THEN p.size * p.current_price ELSE -p.size * p.current_price END) AS net_exposure
FROM positions p
JOIN accounts a ON p.account_id = a.account_id
WHERE p.status = 'open'
GROUP BY a.account_id, a.currency;
```

Currency exposure requires converting all positions to a common
currency (the account's base currency or a system-wide reporting
currency) using the current FX rate. The adapter provides
`pip_value` (which embeds the FX conversion for the symbol); for
cross-currency consolidation, the calculator uses live FX rates from
the market data layer.

## (f) Risk engine parameterized by adapter

`risk-engine.md` currently hardcodes:

```python
pip_value = get_pip_value(symbol)          # hardcoded MT5 semantics
max_volume = get_broker_max_volume(symbol) # hardcoded
```

These become:

```python
adapter = resolve_adapter(account.broker_id)  # from brokers.adapter_class
pip_value = adapter.get_pip_value(symbol, account)
max_volume = adapter.get_max_volume(symbol, account)
margin = adapter.compute_margin(symbol, size, price, account)
```

The deterministic base formula (risk-engine.md) is unchanged in
structure — it still computes `base_volume = (equity *
risk_per_trade) / (stop_loss_pips * pip_value)`. What changes is that
`pip_value` and `max_volume` are broker-specific, not global
constants.

The `account_equity` is per-account: `get_equity(account)` returns
the equity for the specific account the trade would execute on. In a
multi-account setup, the PortfolioSizer selects the account (based on
allocation policy) and the risk engine computes against that
account's equity.

## (g) Per-account AND consolidated exposure limits

The exposure limits table (risk-engine.md) is enforced at two levels:

| Limit | Per-account check | Consolidated check | Action |
|-------|-------------------|--------------------|--------|
| Max risk per trade | 1% of account equity | 1% of total equity | Reject if either fails |
| Max total exposure | 5% of account equity | 5% of total equity | Reject new orders if either fails |
| Max correlated exposure | 3% of account equity | 3% of total equity | Reduce or reject |
| Max daily loss | 3% of account equity | 3% of total equity | Halt account and/or system |

Both checks must pass. Rationale: a single account could be within its
own 5% limit while the consolidated exposure across 3 accounts is 15%
of total equity — an unacceptable concentration. The consolidated
check prevents this.

In V1 (single account), per-account and consolidated are identical.
The dual check is a no-op overhead (one extra comparison). In
multi-account, it is the critical guardrail.

## (h) Migration note

Existing single-broker rows (from V1 deployments that predate this
document) are backfilled:

```sql
-- 1. Create the default broker
INSERT INTO brokers (broker_id, name, adapter_class, session_calendar_ref,
                     margin_rule_set, base_currency, status, config)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'mt5_default',
  'mt5',
  'default_fx',
  'retail_fx',
  'USD',
  'active',
  '{}'
);

-- 2. Create the default account
INSERT INTO accounts (account_id, broker_id, account_id_at_broker,
                      currency, leverage, status)
VALUES (
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  (SELECT login FROM mt5_connection_config),  -- existing config
  'USD',
  100.00,
  'active'
);

-- 3. Backfill positions and fills
UPDATE positions SET account_id = '00000000-0000-0000-0000-000000000002'
  WHERE account_id IS NULL;
UPDATE fills SET account_id = '00000000-0000-0000-0000-000000000002'
  WHERE account_id IS NULL;

-- 4. Enforce NOT NULL (after backfill confirms no NULLs remain)
ALTER TABLE positions ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE fills ALTER COLUMN account_id SET NOT NULL;
```

The migration is irreversible (NOT NULL columns cannot be unset
without data loss). It is run once, during the Phase 15 implementation
of this document, before any multi-broker rows are inserted.

## What this document does NOT define

- MT5 adapter implementation details (Phase 14+).
- Multi-account allocation policy (which account a trade goes to) —
  that is a PortfolioSizer concern, Phase 8 extension.
- Broker credential management (Phase 12).
- Cross-broker arbitrage detection (future, not V1).
- FIX protocol adapter (future, not V1).

## Phase boundary

This document amends `physical-erd.md` (Phase 5) by adding `brokers`
and `accounts` tables and `account_id` to `positions`/`fills`, and
amends `risk-engine.md` (Phase 8) by parameterizing formulas through
`BrokerRiskAdapter` and enforcing dual per-account/consolidated
exposure limits. It does not define adapter implementation (Phase 14+),
credentials (Phase 12), or allocation policy (Phase 8 extension).
