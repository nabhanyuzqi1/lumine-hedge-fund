"""Data quality (PRD 19.2) + hardening append-only ledger (PRD 19.4).

Tabel baru:
- data_quality_runs: riwayat laporan kualitas data (JSONB) dari
  app.data_quality (kartu t_f2v22a11).
- data_versions: checksum + jumlah baris per series (symbol, timeframe)
  untuk "data version and checksum" (PRD 19.2); di-update tiap run.

Hardening ledger (PRD 19.4 "DB permission, trigger/policy, backup, audit"):
- REVOKE UPDATE/DELETE/TRUNCATE ON order_events FROM PUBLIC — lapisan
  permission di atas trigger b002. Catatan: owner tabel (role fund2,
  yang juga menjalankan migrasi) secara alasan desain Postgres selalu
  punya privilege owner; guard utama tetap trigger append-only yang
  menolak mutasi meski dari owner. Role non-owner tidak bisa UPDATE/
  DELETE/TRUNCATE sama sekali.
- Konvensi koreksi: event kompensasi (to_status 'COMPENSATION_*' atau
  payload kind='compensation'), bukan edit sejarah. Diverifikasi di
  tests/test_data_quality.py.

Revision ID: e005
Revises: d004
Create Date: 2026-11-23
"""
from __future__ import annotations

from alembic import op

revision = "e005"
down_revision = "d004"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Riwayat laporan kualitas data (PRD 19.2) ──────────────────────────────
CREATE TABLE IF NOT EXISTS data_quality_runs (
    id           BIGSERIAL PRIMARY KEY,
    run_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    status       TEXT NOT NULL CHECK (status IN ('PASS', 'WARN', 'FAIL')),
    report       JSONB NOT NULL,
    checks_failed INTEGER NOT NULL DEFAULT 0,
    checks_warned INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_data_quality_runs_run
    ON data_quality_runs(run_at DESC);

-- ── Versi & checksum series (PRD 19.2 "data version and checksum") ───────
CREATE TABLE IF NOT EXISTS data_versions (
    symbol     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    row_count  INTEGER NOT NULL DEFAULT 0,
    checksum   TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, timeframe)
);

-- ── Hardening permission ledger (PRD 19.4) ────────────────────────────────
-- Trigger append-only (b002) tetap guard utama; REVOKE menutup akses
-- mutasi untuk role non-owner sekalipun trigger dimatikan.
REVOKE UPDATE, DELETE, TRUNCATE ON order_events FROM PUBLIC;

COMMENT ON TABLE data_quality_runs IS
    'Riwayat laporan data quality (PRD 19.2); ditulis app.data_quality.';
COMMENT ON TABLE data_versions IS
    'Checksum & jumlah baris per series candle (PRD 19.2 data version).';
COMMENT ON TABLE order_events IS
    'Append-only ledger (PRD 19.4): UPDATE/DELETE/TRUNCATE ditolak trigger '
    'order_events_append_only / order_events_no_truncate + REVOKE permission. '
    'Koreksi hanya dengan event kompensasi (payload kind=compensation), '
    'bukan mengedit sejarah.';
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Laporan kualitas & checksum boleh di-drop (bukan ledger); REVOKE
    # tidak dibalikkan (least privilege tetap diinginkan).
    op.execute("DROP TABLE IF EXISTS data_quality_runs")
    op.execute("DROP TABLE IF EXISTS data_versions")
