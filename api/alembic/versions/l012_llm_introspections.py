"""Tabel llm_introspections (FUND2-LLM-B1, t_9f36a70a, lanjutan t_2a751a6c).

Append-only store untuk narasi introspeksi agent LLM (D5):
- scope 'trade'  : ref_key = cycle_id/order id -> bukti + narasi satu keputusan.
- scope 'daily'  : ref_key = tanggal (mis. 2026-11-25) -> rekap harian.
UNIQUE(scope, ref_key) membuat penulisan idempoten (re-run siklus tidak
menduplikasi narasi). order_events TIDAK diubah; tabel ini pelengkap, bukan
pengganti audit keputusan.

Revision ID: l012
Revises: k011
Create Date: 2026-11-25
"""
from __future__ import annotations

from alembic import op

revision = "l012"
down_revision = "k011"
branch_labels = None
depends_on = None

SQL = r"""
-- ── llm_introspections (FUND2-LLM-B1 D5): narasi introspeksi agent LLM ─────
-- Append-only: UPDATE/DELETE ditolak trigger fund2_deny_mutation (pola
-- order_events/strategy_approvals, b002). Koreksi = tulis baris baru dengan
-- ref_key versi berikutnya; sejarah tidak diedit.
CREATE TABLE IF NOT EXISTS llm_introspections (
    id             BIGSERIAL PRIMARY KEY,
    scope          TEXT NOT NULL CHECK (scope IN ('trade', 'daily')),
    ref_key        TEXT NOT NULL,
    evidence       JSONB,
    narasi         TEXT,
    model          TEXT,
    prompt_version TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (scope, ref_key)
);
CREATE INDEX IF NOT EXISTS idx_llm_introspections_scope
    ON llm_introspections(scope, created_at);

DROP TRIGGER IF EXISTS llm_introspections_append_only ON llm_introspections;
CREATE TRIGGER llm_introspections_append_only
BEFORE UPDATE OR DELETE ON llm_introspections
FOR EACH ROW EXECUTE FUNCTION fund2_deny_mutation();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS llm_introspections_append_only ON llm_introspections")
    op.execute("DROP TABLE IF EXISTS llm_introspections")
