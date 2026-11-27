"""Baseline skema P1 (fund core) — kondisi produksi saat rilis P1.

Membuat semua tabel operasional yang sudah berjalan di produksi:
users, sessions, orders, order_events, positions, bridge_commands,
candles (partisi bulanan), liquidity_samples, settings, paper_orders,
paper_state, kill_switch_events, backtest_runs.

Idempotent: aman dijalankan pada DB yang sudah berisi tabel-tabel ini
(CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

Revision ID: a001
Revises: -
Create Date: 2026-11-22
"""
from __future__ import annotations

from alembic import op

revision = "a001"
down_revision = None
branch_labels = None
depends_on = None

SQL = r"""
-- ── Auth ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT UNIQUE NOT NULL,
    csrf_token   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Order ledger (PRD 13) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_id      UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    volume          NUMERIC(10, 2) NOT NULL,
    sl              NUMERIC(12, 5),
    tp              NUMERIC(12, 5),
    status          TEXT NOT NULL DEFAULT 'RECEIVED',
    price_requested NUMERIC(12, 5),
    ticket          BIGINT,
    price_filled    NUMERIC(12, 5),
    fail_reason     TEXT,
    strategy        TEXT NOT NULL DEFAULT 'manual',
    action          TEXT NOT NULL DEFAULT 'OPEN',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_sent ON orders(sent_at) WHERE status = 'SENT';

CREATE TABLE IF NOT EXISTS order_events (
    id          BIGSERIAL PRIMARY KEY,
    order_id    UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id, id);

CREATE TABLE IF NOT EXISTS positions (
    id          BIGSERIAL PRIMARY KEY,
    ticket      BIGINT UNIQUE NOT NULL,
    order_id    UUID REFERENCES orders(id),
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    volume      NUMERIC(10, 2) NOT NULL,
    open_price  NUMERIC(12, 5),
    open_time   TIMESTAMPTZ,
    close_price NUMERIC(12, 5),
    close_time  TIMESTAMPTZ,
    sl          NUMERIC(12, 5),
    tp          NUMERIC(12, 5),
    profit      NUMERIC(14, 2) NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    raw         JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);

-- Reconciler command queue (P1b): MODIFY_SL / CLOSE actions for the EA.
CREATE TABLE IF NOT EXISTS bridge_commands (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id     UUID REFERENCES orders(id),
    action       TEXT NOT NULL,                  -- 'MODIFY_SL' | 'CLOSE'
    payload      JSONB NOT NULL DEFAULT '{}',    -- {ticket, sl, tp, reason}
    status       TEXT NOT NULL DEFAULT 'QUEUED', -- QUEUED|DELIVERED|DONE|FAILED
    fail_reason  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bridge_commands_status ON bridge_commands(status, created_at);

-- ── Market data ───────────────────────────────────────────────────────────
-- Candles partisi bulanan (PRD 5.1). Dibuat langsung partisi; DB lama yang
-- masih tabel biasa sudah dikonversi saat rilis P1b.
CREATE TABLE IF NOT EXISTS candles (
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts        TIMESTAMPTZ NOT NULL,
    open      NUMERIC(12, 5) NOT NULL,
    high      NUMERIC(12, 5) NOT NULL,
    low       NUMERIC(12, 5) NOT NULL,
    close     NUMERIC(12, 5) NOT NULL,
    volume    NUMERIC(16, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, timeframe, ts)
) PARTITION BY RANGE (ts);

-- liquidity_samples (PRD 8, P1a): agregat spread per 5 detik + sesi.
CREATE TABLE IF NOT EXISTS liquidity_samples (
    symbol       TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,   -- awal jendela 5 detik (UTC)
    session      TEXT NOT NULL,          -- asia|london|london_newyork|newyork
    spread_avg   NUMERIC(12, 5) NOT NULL,
    spread_min   NUMERIC(12, 5) NOT NULL,
    spread_max   NUMERIC(12, 5) NOT NULL,
    tick_count   INTEGER NOT NULL,
    PRIMARY KEY (symbol, window_start)
);
CREATE INDEX IF NOT EXISTS idx_liquidity_samples_window
    ON liquidity_samples(window_start);

-- ── Settings ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Paper trading (P1b) ───────────────────────────────────────────────────
-- mode: PAPER (live paper ledger) | REPLAY (historical dress rehearsal).
CREATE TABLE IF NOT EXISTS paper_orders (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode          TEXT NOT NULL DEFAULT 'PAPER' CHECK (mode IN ('PAPER', 'REPLAY')),
    strategy      TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    volume        NUMERIC(10, 2) NOT NULL,
    sl            NUMERIC(12, 5) NOT NULL,
    tp            NUMERIC(12, 5) NOT NULL,
    status        TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'REJECTED')),
    risk_decision JSONB NOT NULL DEFAULT '{}',
    entry_price   NUMERIC(12, 5),
    exit_price    NUMERIC(12, 5),
    profit        NUMERIC(14, 2) NOT NULL DEFAULT 0,
    reason        TEXT,
    opened_at     TIMESTAMPTZ,
    closed_at     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_paper_orders_mode ON paper_orders(mode, strategy, created_at);

CREATE TABLE IF NOT EXISTS paper_state (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Kill-switch audit (PRD v2.1 §5.7, v2.2 §16) ───────────────────────────
CREATE TABLE IF NOT EXISTS kill_switch_events (
    id         BIGSERIAL PRIMARY KEY,
    action     TEXT NOT NULL,      -- ACTIVATE / RELEASE / AUTO_TRIGGER / ESCALATE / FLATTEN_REQUEST / TRIGGERS_UPDATED
    mode       TEXT,               -- STOP_NEW_ORDERS / STOP_AND_FLATTEN / PAUSE_STRATEGY / GLOBAL_HALT
    strategy   TEXT,               -- untuk PAUSE_STRATEGY
    source     TEXT NOT NULL,      -- dashboard / telegram / auto:<trigger> / system
    actor      TEXT NOT NULL,      -- username, telegram owner id, atau 'auto'
    reason     TEXT,
    details    JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kill_switch_events_created ON kill_switch_events(created_at);

-- ── Backtest registry (PRD 5.4 / bagian 8, P2) ────────────────────────────
CREATE TABLE IF NOT EXISTS backtest_runs (
    id               BIGSERIAL PRIMARY KEY,
    run_id           UUID NOT NULL,
    strategy_id      TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    timeframe        TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN ('train', 'test')),
    window_index     INT  NOT NULL DEFAULT 0,
    train_start      TIMESTAMPTZ,
    train_end        TIMESTAMPTZ,
    test_start       TIMESTAMPTZ,
    test_end         TIMESTAMPTZ,
    params           JSONB NOT NULL DEFAULT '{}',
    config           JSONB NOT NULL DEFAULT '{}',
    metrics          JSONB NOT NULL DEFAULT '{}',
    selected         BOOLEAN NOT NULL DEFAULT FALSE,
    note             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs(strategy_id, created_at);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_run ON backtest_runs(run_id);

-- ── Partisi candles: bulan berjalan, bulan depan, dan default ─────────────
DO $$
DECLARE
    m RECORD;
BEGIN
    IF to_regclass('public.candles') IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'candles'
    ) THEN
        FOR m IN
            SELECT generate_series(
                       date_trunc('month', now())::date,
                       date_trunc('month', now() + interval '1 month')::date,
                       interval '1 month') AS m
        LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS candles_%s PARTITION OF candles '
                'FOR VALUES FROM (%L) TO (%L)',
                to_char(m.m, 'YYYY_MM'), m.m, m.m + interval '1 month');
        END LOOP;
        EXECUTE 'CREATE TABLE IF NOT EXISTS candles_default PARTITION OF candles DEFAULT';
    END IF;
END $$;

-- ── Normalisasi timeframe kanonik PRD (M1/M5/M15/H1/H4/D1) ────────────────
-- Seed EA lama memakai 1m/5m/15m/1h/4h/1d. Idempotent: bar yang sudah ada
-- tidak dobel (konflik kunci dihapus, bar kanonik yang menang).
UPDATE candles c SET timeframe = m.target
FROM (VALUES ('1m','M1'), ('5m','M5'), ('15m','M15'),
             ('1h','H1'), ('4h','H4'), ('1d','D1')) AS m(old, target)
WHERE c.timeframe = m.old
  AND NOT EXISTS (SELECT 1 FROM candles c2
                  WHERE c2.symbol = c.symbol AND c2.timeframe = m.target
                    AND c2.ts = c.ts);
DELETE FROM candles WHERE timeframe IN ('1m','5m','15m','1h','4h','1d');
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Baseline produksi: tidak didrop (audit trail & ledger harus bertahan).
    raise NotImplementedError("baseline P1 tidak memiliki downgrade")
