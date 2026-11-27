"""Hermes research intelligence layer (PRD v2.2 §12, t_f2v22a7).

Tabel baru:
- research_proposals: usulan Hermes (draft strategi/parameter eksperimen)
  yang dipisahkan dari laporan (research_reports, b002). Status:
  PROPOSED -> APPROVED | REJECTED -> DEPLOYED. Keputusan + penandaan
  DEPLOYED hanya lewat endpoint owner (admin + CSRF + 2FA +
  owner_username); Hermes (role 'research') tidak punya jalur write
  selain membuat proposal/laporan baru.

Garis merah PRD 12.1 yang di-enforce di lapisan aplikasi (app/research.py,
app/research_routes.py, middleware main.py):
- Tool riset read-only terhadap tabel produksi; write HANYA ke
  research_reports / research_proposals / backtest_runs.
- Role 'research' ditolak default-deny di semua endpoint non-/research.
- Proposal PROPOSED tidak bisa menyeberang ke DEPLOYED tanpa keputusan
  owner yang tercatat (kolom decided_by/decided_at/decision_note).

Revision ID: j010
Revises: i009
Create Date: 2026-11-24
"""
from __future__ import annotations

from alembic import op

revision = "j010"
down_revision = "i009"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Role 'research' (PRD §12): kredensial service Hermes riset ─────────────
-- Constraint lama (c003) hanya mengenal admin/agent/user. Role research
-- default-deny di semua endpoint mutasi non-/research (auth.require_csrf).
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin', 'agent', 'user', 'research'));

-- ── Usulan riset Hermes (PRD §12.1 "mengusulkan perubahan untuk owner") ────
CREATE TABLE IF NOT EXISTS research_proposals (
    id                  BIGSERIAL PRIMARY KEY,
    proposal_type       TEXT NOT NULL DEFAULT 'EXPERIMENT' CHECK (proposal_type IN
                        ('STRATEGY_PARAM', 'NEW_STRATEGY', 'EXPERIMENT', 'OTHER')),
    title               TEXT NOT NULL,
    hypothesis          TEXT NOT NULL DEFAULT '',
    report_id           BIGINT REFERENCES research_reports(id),
    change              JSONB NOT NULL DEFAULT '{}',   -- usulan parameter/konfigurasi
    baseline_vs_candidate JSONB NOT NULL DEFAULT '{}',
    backtest_run_ids    JSONB NOT NULL DEFAULT '[]',   -- run_id UUID di backtest_runs
    risks               JSONB NOT NULL DEFAULT '[]',
    status              TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (status IN
                        ('PROPOSED', 'APPROVED', 'REJECTED', 'DEPLOYED')),
    author              TEXT NOT NULL DEFAULT 'hermes',
    decided_by          TEXT,
    decided_at          TIMESTAMPTZ,
    decision_note       TEXT,
    strategy_version_id BIGINT REFERENCES strategy_versions(id),
    deployed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_research_proposals_status
    ON research_proposals(status, created_at);

COMMENT ON TABLE research_proposals IS
    'Usulan riset Hermes (PRD §12). Retensi: PERMANEN. Keputusan owner-only.';
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Audit permanen (PRD §18): tabel tidak didrop.
    op.execute("SELECT 1")
