"""Config risk per-strategy (RISK-D, t_a172bb7b): override + alur approval.

Dua tabel:
- strategy_risk_overrides: nilai override yang BERLAKU per strategi
  (satu baris per strategi; kosong/hilang = ikut global). Global settings
  tetap DEFAULT dan HARD CEILING; override divalidasi <= global di
  app/risk_config.py saat propose DAN saat apply.
- strategy_risk_override_requests: jejak approval (PROPOSED -> APPROVED /
  REJECTED / SUPERSEDED). Append-only secara praktik: baris hanya berubah
  status sekali; keputusan owner (2FA) tercatat siapa/kapan/alasan, jadi
  tabel ini sendiri adalah audit trail perubahan risk per-strategy.

settings key `max_positions` di-seed sebagai ceiling global (default 5,
sama dengan DEFAULT_MAX_POSITIONS di app/risk_config.py). ON CONFLICT DO
NOTHING: nilai operator yang sudah ada tidak pernah ditimpa.

Revision ID: m013
Revises: l012
Create Date: 2026-11-26
"""
from __future__ import annotations

from alembic import op

revision = "m013"
down_revision = "l012"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Override risk per strategi (RISK-D) ────────────────────────────────────
-- Hanya key yang dikenal app/risk_config.KEY_ORDER yang disimpan (validasi di
-- aplikasi, fail-closed); bentuk {risk_pct, max_positions, daily_loss_limit,
-- be_trigger_r, be_buffer, trail_atr_mult, trail_activate_r}.
CREATE TABLE IF NOT EXISTS strategy_risk_overrides (
    strategy_id TEXT PRIMARY KEY,
    overrides   JSONB NOT NULL DEFAULT '{}',
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Alur approval perubahan risk per strategi ──────────────────────────────
-- PROPOSED = menunggu keputusan owner; APPROVED = sudah diterapkan;
-- REJECTED = ditolak owner; SUPERSEDED = usulan lebih baru untuk strategi
-- yang sama menggantikannya (tidak pernah diterapkan).
CREATE TABLE IF NOT EXISTS strategy_risk_override_requests (
    id            BIGSERIAL PRIMARY KEY,
    strategy_id   TEXT NOT NULL,
    overrides     JSONB NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (status IN
                    ('PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    requested_by  TEXT NOT NULL,
    request_note  TEXT,
    decided_by    TEXT,
    decision_note TEXT,
    decided_at    TIMESTAMPTZ,
    applied_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sror_strategy
    ON strategy_risk_override_requests(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sror_status
    ON strategy_risk_override_requests(status);

-- Ceiling global max posisi per strategi. DEFAULT_SETTINGS di app/db.py
-- tidak diubah (file itu dipakai lintas kartu); seed di sini idempoten.
INSERT INTO settings (key, value) VALUES ('max_positions', '5'::jsonb)
ON CONFLICT (key) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS strategy_risk_override_requests")
    op.execute("DROP TABLE IF EXISTS strategy_risk_overrides")
