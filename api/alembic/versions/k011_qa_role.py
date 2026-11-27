"""Role 'qa' untuk layanan QA terdaftar (t_4651d431).

Insiden 25 Nov 2026: driver QA latensi mengirim 721 order pakai username
admin (user_id=1) sehingga metrik anomaly harian terkontaminasi (p95 175 s,
FAILED 55%) karena order QA tak terpisah dari order live.

Perbaikan: user QA khusus `svc-qa-driver` ber-role 'qa'. Role 'qa' ditambahkan
ke users_role_check; aplikasinya:
- app/anomaly.py mengecualikan order yang event RECEIVED-nya membawa
  username user ber-role 'qa' (SQL_EXCLUDE_QA);
- app/auth.py mengizinkan 'qa' khusus di flatten/release kill-switch
  (require_control_role) -- CSRF + 2FA tetap wajib;
- driver QA (scripts/_p5_latency_driver_v9.py) login pakai user QA, bukan
  admin.

Revision ID: k011
Revises: j010
Create Date: 2026-11-25
"""
from __future__ import annotations

from alembic import op

revision = "k011"
down_revision = "j010"
branch_labels = None
depends_on = None

SQL = r"""
-- ── Role 'qa' (t_4651d431): kredensial layanan QA terdaftar ────────────────
-- Constraint lama (j010) hanya mengenal admin/agent/user/research. Role 'qa'
-- bukan endpoint-lebar: hanya flatten/release kill-switch yang mengizinkan
-- (app/auth.require_control_role), dan order-nya dikecualikan dari metrik
-- anomaly harian (app/anomaly.SQL_EXCLUDE_QA).
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin', 'agent', 'user', 'research', 'qa'));
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Role 'qa' dihapus: gagalkan bila masih ada pemakai agar tidak diam-diam
    # kehilangan akses.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE role = 'qa') THEN
                RAISE EXCEPTION 'masih ada user ber-role qa';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('admin', 'agent', 'user', 'research'))
    """)
