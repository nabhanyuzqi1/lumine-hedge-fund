"""Shadow Strategy (PRD v2.2 §9, t_f2v22a4).

Tabel baru:
- shadow_signals: catatan lengkap satu sinyal shadow (PRD 9.2): harga
  referensi (bid/ask), spread, timestamp, regime, alasan, label
  kode/parameter yang diuji, dan hasil simulasi fill konservatif.
  `is_simulation` selalu TRUE: P&L shadow adalah simulasi, bukan realized.
- Seed settings `shadow_enabled` + `shadow_strategies` (daftar versi
  strategi yang dijalankan bersamaan, masing-masing berlabel).

Revision ID: h008
Revises: g007
Create Date: 2026-11-24
"""
from __future__ import annotations

from alembic import op

revision = "h008"
down_revision = "g007"
branch_labels = None
depends_on = None

SQL = r"""
-- ── shadow_signals (PRD 9.2) ────────────────────────────────────────────────
-- Satu baris per sinyal shadow. Baris dibuat saat sinyal tercatat dan
-- di-update saat posisi simulasi tertutup (exit price / P&L simulasi).
-- Tabel ini TIDAK berelasi ke orders/bridge_commands: shadow tidak pernah
-- mengirim order ke broker (PRD 9.2), hanya ke signals (source='SHADOW')
-- yang ditulis supervisor sandbox.
CREATE TABLE IF NOT EXISTS shadow_signals (
    id                BIGSERIAL PRIMARY KEY,
    run_id            UUID NOT NULL REFERENCES shadow_runs(run_id) ON DELETE CASCADE,
    signal_ref        TEXT,   -- signals.order_intent->>'signal_id' (uuid, PRD 4.1)
    strategy_id       TEXT NOT NULL,
    strategy_version  TEXT NOT NULL,
    label             TEXT NOT NULL,   -- label perubahan kode/parameter yang diuji
    symbol            TEXT NOT NULL,
    timeframe         TEXT NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,          -- timestamp sinyal
    ref_bid           NUMERIC(12, 5),                -- harga referensi
    ref_ask           NUMERIC(12, 5),
    spread            NUMERIC(12, 5),                -- spread saat sinyal
    spread_median_15m NUMERIC(12, 5),
    regime_label      TEXT,
    regime_confidence NUMERIC(5, 4),
    side              TEXT CHECK (side IN ('BUY', 'SELL')),
    volume            NUMERIC(10, 2),
    sl                NUMERIC(12, 5),
    tp                NUMERIC(12, 5),
    reason            TEXT,
    params_hash       TEXT NOT NULL DEFAULT '',      -- hash parameter yang diuji
    code_commit       TEXT,                          -- commit kode yang diuji
    is_simulation     BOOLEAN NOT NULL DEFAULT TRUE, -- TANDA: simulasi, bukan realized
    sim_status        TEXT NOT NULL DEFAULT 'FILLED' CHECK (sim_status IN
                       ('FILLED', 'REJECTED', 'REGIME_BLOCKED')),
    sim_fill_price    NUMERIC(12, 5),                -- fill model konservatif
    sim_cost_usd      NUMERIC(14, 2),                -- estimasi biaya (komisi+slippage)
    sim_exit_price    NUMERIC(12, 5),
    sim_pnl_usd       NUMERIC(14, 2),                -- P&L SIMULASI
    sim_exit_reason   TEXT,                          -- SL | TP | TIME | END
    sim_opened_at     TIMESTAMPTZ,
    sim_closed_at     TIMESTAMPTZ,
    detail            JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shadow_signals_run ON shadow_signals(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_shadow_signals_strategy
    ON shadow_signals(strategy_id, label, ts);

-- shadow_runs butuh label per versi yang diuji (PRD 9.2: beberapa versi
-- strategi bersamaan + label perubahan kode/parameter).
ALTER TABLE shadow_runs ADD COLUMN IF NOT EXISTS label TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_runs_active_label
    ON shadow_runs(strategy_id, label) WHERE status = 'RUNNING';

-- ── Seed settings shadow (idempotent; override owner tidak pernah ditimpa) ──
INSERT INTO settings (key, value) VALUES
('shadow_enabled', 'true'::jsonb),
('shadow_strategies', '[
    {"label": "lb-base", "module": "strategies.london_breakout", "params": {}},
    {"label": "mr-base", "module": "strategies.mean_reversion", "params": {}},
    {"label": "btc-base", "module": "strategies.btc_range_breakout", "params": {}}
 ]'::jsonb)
ON CONFLICT (key) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shadow_signals")
