"""Portfolio Risk Manager (PRD v2.2 §7, t_f2v22a3).

Data migration (bukan tabel baru):
- Seed settings key 'portfolio_risk' (batas portofolio + stress scenario)
  bila belum ada; override operator yang sudah ada tidak pernah ditimpa.
- Backfill symbol_specs XAUUSD/BTCUSD yang sudah ada di DB dengan tick_value,
  tick_size, spec_verified, slippage_usd agar contract spec terverifikasi
  untuk perhitungan risiko portofolio (PRD §7.3: tolak bila contract
  spec/tick value tidak dapat diverifikasi). Verifikasi tick value:
  XAUUSD contract 100 oz/lot × tick 0.01 = $1.00/tick/lot; BTCUSD contract
  1 BTC/lot × tick 0.01 = $0.01/tick/lot (deal live 22 Nov, t_f2mp1).

Revision ID: g007
Revises: f006
Create Date: 2026-11-23
"""
from __future__ import annotations

from alembic import op

revision = "g007"
down_revision = "f006"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Seed konfigurasi portfolio risk (idempotent) ───────────────────────────
INSERT INTO settings (key, value) VALUES ('portfolio_risk', '{"enabled": true, "max_risk_per_trade_pct": 0.5, "max_open_risk_pct": 2.0, "stress_max_risk_pct": 3.0, "max_total_volume_lot": 0.30, "max_margin_utilization_pct": 20.0, "max_symbol_risk_pct": 1.0, "commission_per_lot_usd": 7.0, "leverage": 100.0, "max_feed_age_s": 60.0, "stress": {"gap_pct": 0.5, "spread_multiplier": 3.0, "slippage_usd": 0.35}}'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- ── Backfill tick value terverifikasi utk symbol_specs existing ────────────
-- XAUUSD: hanya isi key yang belum ada (jsonb_set berantai; WHERE guard
-- membuat migration ini idempotent dan tidak mengubah override owner).
UPDATE settings
SET value = jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(value,
    '{XAUUSD,tick_value}', '1.00'::jsonb),
    '{XAUUSD,tick_size}', '0.01'::jsonb),
    '{XAUUSD,spec_verified}', 'true'::jsonb),
    '{XAUUSD,slippage_usd}', '0.35'::jsonb),
    '{XAUUSD,contract_size}', '100.0'::jsonb)
WHERE key = 'symbol_specs'
  AND value->'XAUUSD' IS NOT NULL
  AND (value->'XAUUSD'->>'tick_value') IS NULL;

-- BTCUSD: contract 1 BTC/lot, tick 0.01 -> tick value $0.01/tick/lot.
UPDATE settings
SET value = jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(value,
    '{BTCUSD,tick_value}', '0.01'::jsonb),
    '{BTCUSD,tick_size}', '0.01'::jsonb),
    '{BTCUSD,spec_verified}', 'true'::jsonb),
    '{BTCUSD,slippage_usd}', '5.0'::jsonb),
    '{BTCUSD,contract_size}', '1.0'::jsonb)
WHERE key = 'symbol_specs'
  AND value->'BTCUSD' IS NOT NULL
  AND (value->'BTCUSD'->>'tick_value') IS NULL;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Data migration: settings dan symbol_specs adalah state operator.
    # Tidak ada yang dihapus saat downgrade; portfolio_risk boleh dilepas.
    op.execute("DELETE FROM settings WHERE key = 'portfolio_risk'")
