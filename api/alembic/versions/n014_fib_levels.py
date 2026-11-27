"""Level Fibonacci chart (RISK-C, t_00db2872): tabel fib_levels.

Satu baris = satu swing yang digambar user di chart (low->high + arah tren).
`levels` menyimpan hasil hitung server (retracement 0.236/0.382/0.5/0.618/0.786
+ extension 1.272/1.618/2.618) sebagai snapshot JSONB, sehingga level yang
pernah dilihat chart/LLM tetap dapat diaudit walau konstanta di
app/fib_levels.py berubah kelak.

Tabel ini TIDAK dipakai jalur order/bridge/gate risk apa pun: murni alat bantu
visual + konteks opsional LLM (keputusan scope RISK-C: partial close dideScope,
lihat docs/PROBE_PARTIAL_CLOSE_t_00db2872.md).

Revision ID: n014
Revises: m013
Create Date: 2026-11-26
"""
from __future__ import annotations

from alembic import op

revision = "n014"
down_revision = "m013"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Tool Fibonacci chart (RISK-C) ─────────────────────────────────────────
-- direction = arah tren yang diukur: 'UP' (swing naik low->high) atau
-- 'DOWN' (swing turun high->low). CHECK harga: swing_high wajib > swing_low.
CREATE TABLE IF NOT EXISTS fib_levels (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('UP', 'DOWN')),
    swing_low   NUMERIC(14, 5) NOT NULL,
    swing_high  NUMERIC(14, 5) NOT NULL,
    levels      JSONB NOT NULL,
    note        TEXT,
    created_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fib_levels_swing_order CHECK (swing_high > swing_low)
);
CREATE INDEX IF NOT EXISTS idx_fib_levels_symbol
    ON fib_levels (symbol, timeframe, created_at DESC);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fib_levels")
