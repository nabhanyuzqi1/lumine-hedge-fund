"""Sumber candle (native EA vs rollup vs legacy) — additive saja.

Latar (audit candle pipeline, 26 Nov 2026): chart mencampur dua generasi data
di satu seri. XAUUSD M1 punya 353.500 bar datar (O=H=L=C, rata-rata volume 3)
dari penulis jendela pasar tutup, sementara bar baru (tick/rollup/seed EA)
bervolume 100-500. Di bar yang sama histogram M5 terlihat acak: 32% bar datar
dengan volume 2-5 (legacy) bercampur bar volume 100-500 (baru). Tanpa penanda,
server tidak bisa memisahkan keduanya saat membaca.

Perubahan: satu kolom ``candles.source``
  - 'legacy' : SEMUA baris yang sudah ada (default kolom; tidak ada backfill
               yang menebak, jadi nilai lama jujur disebut legacy);
  - 'ea'     : bar native MT5 dari EA (seeding CopyRates, bar per TF) dan bar
               hasil agregasi tick EA — sumber paling dipercaya;
  - 'rollup' : agregasi server (M1->M5/M15/H1, H1->H4, H4->D1).

Index ``(symbol, timeframe, source, ts)`` dipakai dua query panas: cutover
``min(ts) WHERE source <> 'legacy'`` per (symbol,timeframe) untuk GET /candles,
dan penyaringan sumber pada rollup. Tidak ada kolom/primary key yang diubah,
tidak ada baris yang ditulis ulang: migrasi ini aman dijalankan pada tabel
candles live yang sudah berpartisi (ADD COLUMN + CREATE INDEX idempotent).

Revision ID: p016
Revises: o015
Create Date: 2026-11-26
"""
from __future__ import annotations

from alembic import op

revision = "p016"
down_revision = "o015"
branch_labels = None
depends_on = None

SQL = r"""
-- ── 1. Kolom sumber bar ────────────────────────────────────────────────────
-- DEFAULT 'legacy' + NOT NULL: baris lama otomatis 'legacy' (jujur: sumbernya
-- tidak pernah tercatat), penulis baru wajib menyebut 'ea' atau 'rollup'.
ALTER TABLE candles ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'legacy';

-- ── 2. Index cutover / penyaringan sumber ──────────────────────────────────
-- (symbol, timeframe, source, ts) melayani:
--   SELECT min(ts) ... WHERE symbol=%s AND timeframe=%s AND source <> 'legacy'
--   WHERE symbol=%s AND timeframe=%s AND ts >= cutover ORDER BY ts DESC
CREATE INDEX IF NOT EXISTS idx_candles_source_ts
    ON candles (symbol, timeframe, source, ts);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_candles_source_ts")
    op.execute("ALTER TABLE candles DROP COLUMN IF EXISTS source")
