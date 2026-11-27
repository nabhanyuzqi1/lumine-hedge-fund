"""Self-improvement loop mingguan (PRD v2.1 §5.9 & P4).

Tabel baru:
- improvement_proposals: satu baris per usulan perbaikan mingguan (analisa +
  hipotesis + hasil backtest otomatis + verdict + keputusan owner + deploy).
  Status: PROPOSED -> APPROVED | REJECTED -> DEPLOYED.

Governance (garis merah PRD §5.9):
- Keputusan owner dicatat append-only di strategy_approvals (b002) dan
  perubahan settings ter-audit otomatis via trigger settings_audit (b002).
- Modul cron/agent TIDAK pernah mengubah flag `enabled` tanpa keputusan
  owner yang tercatat; endpoint keputusan menerima hanya owner (settings
  owner_username) dengan admin + CSRF + 2FA step-up.

Revision ID: f006
Revises: e005
Create Date: 2026-11-23
"""
from __future__ import annotations

from alembic import op

revision = "f006"
down_revision = "e005"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Usulan perbaikan mingguan (self-improvement loop) ─────────────────────
CREATE TABLE IF NOT EXISTS improvement_proposals (
    id                  TEXT PRIMARY KEY,
    week                TEXT NOT NULL,
    title               TEXT NOT NULL,
    hypothesis          TEXT NOT NULL,
    change              JSONB NOT NULL DEFAULT '{}'::jsonb,
    analysis            JSONB NOT NULL DEFAULT '{}'::jsonb,
    backtest_run_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,
    verdict             TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (verdict IN ('PENDING', 'LULUS', 'GAGAL')),
    criteria_result     JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'PROPOSED'
                        CHECK (status IN ('PROPOSED', 'APPROVED', 'REJECTED',
                                          'DEPLOYED')),
    strategy_version_id BIGINT REFERENCES strategy_versions(id),
    reviewer            TEXT,
    rationale           TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at          TIMESTAMPTZ,
    deployed_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_improvement_proposals_week
    ON improvement_proposals(week DESC);

-- ── Owner pemegang kewenangan approve/deploy (PRD §5.9 garis merah) ───────
INSERT INTO settings (key, value) VALUES ('owner_username', '"admin"')
    ON CONFLICT (key) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS improvement_proposals")
