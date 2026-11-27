"""Degradation Detection (PRD v2.2 §10, t_f2v22a5).

- degradation_state: status + indikator snapshot per strategi (kunci upsert).
- degradation_events: append-only riwayat transisi (audit; governance trigger).
- Seed settings key 'degradation' (threshold berversi; owner-override tidak
  ditimpa: ON CONFLICT DO NOTHING).
- Tambahkan tabel baru ke truncate cleanup DB test.

Revision ID: i009
Revises: h008
Create Date: 2026-11-24
"""
from __future__ import annotations

from alembic import op

revision = "i009"
down_revision = "h008"
branch_labels = None
depends_on = None

SQL = r"""
-- ── State degradation per strategi (PRD §10.3) ─────────────────────────────
CREATE TABLE IF NOT EXISTS degradation_state (
    strategy_id     TEXT NOT NULL PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'NORMAL' CHECK (status IN
                    ('NORMAL', 'WATCH', 'DEGRADED', 'HALTED')),
    since           TIMESTAMPTZ,
    last_evaluated_at TIMESTAMPTZ,
    cooldown_until  TIMESTAMPTZ,
    confirm_status  TEXT,
    confirm_count   INTEGER NOT NULL DEFAULT 0,
    confirm_trades_start INTEGER NOT NULL DEFAULT 0,
    indicators      JSONB NOT NULL DEFAULT '[]',   -- snapshot indikator
    config_version  TEXT NOT NULL DEFAULT '1.0.0',
    config_hash     TEXT NOT NULL DEFAULT '',
    state           JSONB NOT NULL DEFAULT '{}',   -- state evaluator penuh
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_degradation_state_status
    ON degradation_state(status);

-- ── Riwayat transisi append-only (PRD §10/§18 audit) ───────────────────────
CREATE TABLE IF NOT EXISTS degradation_events (
    id              BIGSERIAL PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    trigger         TEXT NOT NULL CHECK (trigger IN
                    ('EVALUATION', 'REENABLE_OWNER')),  -- bukan auto-deescalate
    reason          TEXT,
    indicators      JSONB NOT NULL DEFAULT '[]',
    config_version  TEXT NOT NULL DEFAULT '1.0.0',
    config_hash     TEXT NOT NULL DEFAULT '',
    actor           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_degradation_events_strategy
    ON degradation_events(strategy_id, created_at);

-- Truncate guard untuk cleanup DB test (conftest _clean_db).
DROP TRIGGER IF EXISTS degradation_events_append_only ON degradation_events;
CREATE TRIGGER degradation_events_append_only
BEFORE UPDATE OR DELETE ON degradation_events
FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation();

-- ── Seed settings key 'degradation' (idempotent; override owner menang) ────
INSERT INTO settings (key, value) VALUES ('degradation', '{"trade_window": 30, "min_trades": 20, "min_trades_per_regime": 12, "min_fill_events": 20, "min_regime_obs": 30, "min_signal_baseline": 10, "min_divergence_trades": 10, "min_feature_samples": 30, "min_dd_points": 5, "confirm_evals": 3, "min_new_trades_confirm": 3, "cooldown_s": 3600.0, "eval_interval_s": 300.0, "recent_window_days": 7.0, "baseline_window_days": 30.0, "expectancy_warn_r": -0.05, "expectancy_degraded_r": -0.15, "pf_warn": 1.0, "pf_degraded": 0.8, "dd_warn_pct": 5.0, "dd_degraded_pct": 8.0, "dd_halt_pct": 12.0, "mfe_mae_warn_ratio": 0.8, "mfe_mae_degraded_ratio": 0.6, "spread_warn_mult": 1.5, "spread_degraded_mult": 2.0, "slippage_warn_mult": 1.5, "slippage_degraded_mult": 2.0, "reject_rate_warn": 0.2, "reject_rate_degraded": 0.4, "regime_dist_warn": 0.3, "regime_dist_degraded": 0.5, "freq_drop_warn": 0.5, "freq_drop_degraded": 0.25, "freq_spike_warn": 2.0, "freq_spike_degraded": 3.0, "divergence_warn_r": 0.2, "divergence_degraded_r": 0.35, "psi_warn": 0.25, "psi_degraded": 0.5}'::jsonb)
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE degradation_state IS 'Status degradasi strategi (PRD §10.3). Esensif aktif: DEGRADED/HALTED memblokir entry baru; re-enable owner + 2FA.';
COMMENT ON TABLE degradation_events IS 'Riwayat transisi degradasi append-only (PRD §10/§18). Retensi: PERMANEN (audit).';
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Audit permanen (PRD §18): tabel/trigger tidak didrop; seed settings dilepas.
    op.execute("DELETE FROM settings WHERE key = 'degradation'")
