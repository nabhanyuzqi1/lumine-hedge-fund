"""Pre-flight gate LLM (t_afd7fe4e): tabel sesi pasar + fail_reason wajib.

Tiga perubahan, semuanya aditif dan idempotent:

1. `market_sessions` — jam sesi pasar per simbol, dibaca pre-flight gate
   (app/market_sessions.py). Sumber kebenaran JAM, bukan hardcode di kode.
   weekday memakai nomor Python `datetime.weekday()` (0=Senin .. 6=Minggu)
   pada zona waktu kolom `timezone`. Jendela yang melewati tengah malam
   ditulis sebagai `close_minute < open_minute` (mis. 06:00 -> 04:59 besok).

2. `orders.fail_detail` JSONB — alasan gagal terstruktur
   `{code, message, stage}`. `orders.fail_reason` tetap TEXT berisi versi
   terbaca manusia (dipakai UI History + introspeksi LLM), jadi tidak ada
   regresi tampilan; detail terstruktur tersedia untuk query/audit.

3. Backfill + CHECK `orders_failed_requires_reason`: setiap baris FAILED
   wajib punya fail_reason. Baris lama yang NULL diisi dari bukti yang ada
   (payload event FAILED terakhir: `reasons` gate risk atau `reason` EA);
   baris tanpa bukti apa pun ditandai `legacy_unknown` — jujur "tidak
   tercatat", bukan menebak penyebab. Setelah backfill, constraint dipasang
   sehingga jalur kode baru yang lupa mengisi alasan akan gagal keras.

Revision ID: o015
Revises: n014
Create Date: 2026-11-26
"""
from __future__ import annotations

from alembic import op

revision = "o015"
down_revision = "n014"
branch_labels = None
depends_on = None

SQL = r"""
-- ── 1. Sesi pasar per simbol ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_sessions (
    symbol       TEXT NOT NULL,
    -- 0=Senin .. 6=Minggu (datetime.weekday() di zona waktu `timezone`).
    weekday      SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    -- Menit sejak tengah malam lokal. close < open = jendela melewati
    -- tengah malam (ditutup pada hari berikutnya jam close).
    open_minute  SMALLINT NOT NULL CHECK (open_minute BETWEEN 0 AND 1440),
    close_minute SMALLINT NOT NULL CHECK (close_minute BETWEEN 0 AND 1440),
    timezone     TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    enabled      BOOLEAN NOT NULL DEFAULT true,
    note         TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, weekday),
    CONSTRAINT market_sessions_window CHECK (open_minute <> close_minute)
);

-- Seed: XAUUSD bursa spot emas. Buka Senin 06:00 WIB, tutup Sabtu 04:59 WIB,
-- dengan jeda harian 04:59-06:00 WIB => satu baris per hari buka (Sen-Jum)
-- 06:00 -> 04:59 hari berikutnya.
INSERT INTO market_sessions
    (symbol, weekday, open_minute, close_minute, timezone, note) VALUES
    ('XAUUSD', 0, 360, 299, 'Asia/Jakarta', 'Senin 06:00 -> Selasa 04:59 WIB'),
    ('XAUUSD', 1, 360, 299, 'Asia/Jakarta', 'Selasa 06:00 -> Rabu 04:59 WIB'),
    ('XAUUSD', 2, 360, 299, 'Asia/Jakarta', 'Rabu 06:00 -> Kamis 04:59 WIB'),
    ('XAUUSD', 3, 360, 299, 'Asia/Jakarta', 'Kamis 06:00 -> Jumat 04:59 WIB'),
    ('XAUUSD', 4, 360, 299, 'Asia/Jakarta', 'Jumat 06:00 -> Sabtu 04:59 WIB')
ON CONFLICT (symbol, weekday) DO NOTHING;

-- BTCUSD: crypto 24/7 (close_minute 1440 = sampai akhir hari).
INSERT INTO market_sessions
    (symbol, weekday, open_minute, close_minute, timezone, note) VALUES
    ('BTCUSD', 0, 0, 1440, 'Asia/Jakarta', '24/7'),
    ('BTCUSD', 1, 0, 1440, 'Asia/Jakarta', '24/7'),
    ('BTCUSD', 2, 0, 1440, 'Asia/Jakarta', '24/7'),
    ('BTCUSD', 3, 0, 1440, 'Asia/Jakarta', '24/7'),
    ('BTCUSD', 4, 0, 1440, 'Asia/Jakarta', '24/7'),
    ('BTCUSD', 5, 0, 1440, 'Asia/Jakarta', '24/7'),
    ('BTCUSD', 6, 0, 1440, 'Asia/Jakarta', '24/7')
ON CONFLICT (symbol, weekday) DO NOTHING;

-- ── 2. fail_detail terstruktur ─────────────────────────────────────────────
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fail_detail JSONB;

-- ── 3. Backfill bukti lama + constraint wajib alasan ───────────────────────
-- Ambil event FAILED terakhir per order sebagai bukti penyebab.
WITH last_failed AS (
    SELECT DISTINCT ON (e.order_id)
           e.order_id, e.from_status, e.payload
      FROM order_events e
     WHERE e.to_status = 'FAILED' AND e.order_id IS NOT NULL
     ORDER BY e.order_id, e.id DESC
), derived AS (
    SELECT o.id,
           CASE
             WHEN jsonb_typeof(lf.payload->'reasons') = 'array'
                  AND jsonb_array_length(lf.payload->'reasons') > 0
               THEN 'risk_gate_rejected'
             WHEN COALESCE(lf.payload->>'reason', '') <> ''
               THEN 'ea_result_failed'
             ELSE 'legacy_unknown'
           END AS code,
           CASE
             WHEN jsonb_typeof(lf.payload->'reasons') = 'array'
                  AND jsonb_array_length(lf.payload->'reasons') > 0
               THEN (SELECT string_agg(value, '; ')
                       FROM jsonb_array_elements_text(lf.payload->'reasons'))
             WHEN COALESCE(lf.payload->>'reason', '') <> ''
               THEN lf.payload->>'reason'
             ELSE 'alasan tidak tercatat sebelum perbaikan t-afd7fe4e'
           END AS message,
           CASE
             WHEN jsonb_typeof(lf.payload->'reasons') = 'array'
                  AND jsonb_array_length(lf.payload->'reasons') > 0
               THEN 'risk_gate'
             WHEN COALESCE(lf.payload->>'reason', '') <> ''
               THEN 'bridge_result'
             ELSE 'unknown'
           END AS stage
      FROM orders o
      JOIN last_failed lf ON lf.order_id = o.id
     WHERE o.status = 'FAILED' AND o.fail_reason IS NULL
)
UPDATE orders o
   SET fail_reason = d.code || ': ' || d.message || ' (stage=' || d.stage || ')',
       fail_detail = jsonb_build_object('code', d.code, 'message', d.message,
                                        'stage', d.stage,
                                        'backfilled_at', now()),
       updated_at = now()
  FROM derived d
 WHERE o.id = d.id;

-- FAILED tanpa event sama sekali (data pra-audit): tandai jujur.
UPDATE orders
   SET fail_reason = 'legacy_unknown: alasan tidak tercatat sebelum perbaikan '
                     '(stage=unknown)',
       fail_detail = jsonb_build_object(
           'code', 'legacy_unknown',
           'message', 'alasan tidak tercatat sebelum perbaikan',
           'stage', 'unknown',
           'backfilled_at', now()),
       updated_at = now()
 WHERE status = 'FAILED' AND fail_reason IS NULL;

-- Constraint: FAILED tanpa fail_reason = bug jalur kode, bukan data.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_failed_requires_reason'
    ) THEN
        ALTER TABLE orders
            ADD CONSTRAINT orders_failed_requires_reason
            CHECK (status <> 'FAILED' OR fail_reason IS NOT NULL) NOT VALID;
    END IF;
END $$;
ALTER TABLE orders VALIDATE CONSTRAINT orders_failed_requires_reason;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_failed_requires_reason")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS fail_detail")
    op.execute("DROP TABLE IF EXISTS market_sessions")
