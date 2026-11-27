"""Skema security v2.2 (PRD §18, kartu t_f2v22a9).

Perubahan:
- users: kolom TOTP 2FA (totp_secret, totp_enabled, totp_last_counter)
  dan default role 'user' (least privilege; bootstrap admin eksplisit
  melewatkan role='admin').
- sessions: 2fa_passed_at (step-up assertion TOTP, jendela 5 menit).
- login_failures: account lockout eksponensial anti-abuse (selalu
  kedaluwarga, maks 24 jam; login sukses menghapus counter).
- audit_log: jejak audit auth (login sukses/gagal, logout, 2FA enable/
  disable/challenge, revoke session, lockout). Audit konfigurasi sudah
  di-cover settings_audit (b002), approval strategy_approvals, deployment
  deployment_records, emergency kill_switch_events.
- Downgrade akun service/e2e pra-v2.2 dari 'admin' ke 'user' (least
  privilege; mereka hanya membaca /stream dan membuat order).

Revision ID: d004
Revises: c003
Create Date: 2026-11-23
"""
from __future__ import annotations

from alembic import op

revision = "d004"
down_revision = "c003"
branch_labels = None
depends_on = None

SQL = r"""
-- ── 2FA TOTP (step-up aksi sensitif) ─────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_last_counter BIGINT NOT NULL DEFAULT -1;

-- Default role 'user' (least privilege). Baris lama tidak diubah di sini
-- (sudah 'admin' sejak c003); akun service/e2e diturunkan di bawah.
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user';

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "2fa_passed_at" TIMESTAMPTZ;

-- ── Account lockout anti-abuse ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS login_failures (
    username     TEXT PRIMARY KEY,
    failed_count INTEGER NOT NULL DEFAULT 0,
    lock_events  INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Audit trail auth (PRD §18: login/2FA/session) ────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor      TEXT NOT NULL,      -- username atau 'system'
    actor_role TEXT,               -- admin | agent | user | NULL
    action     TEXT NOT NULL,      -- LOGIN_SUCCESS | LOGIN_FAILED | LOGOUT |
                                   -- 2FA_SETUP | 2FA_ENABLED | 2FA_DISABLED |
                                   -- 2FA_CHALLENGE_OK | 2FA_CHALLENGE_FAILED |
                                   -- SESSION_REVOKED | ACCOUNT_LOCKED
    object     TEXT,               -- id sesi / username target
    details    JSONB NOT NULL DEFAULT '{}',
    ip         TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor, created_at);

-- ── RBAC least privilege: akun service/e2e bukan admin ───────────────────
UPDATE users SET role = 'user'
WHERE username IN ('svc-recorder', 'e2e_btc_v2', 'demo_mp1')
  AND role = 'admin';
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # Audit trail bersifat permanen (PRD §18); downgrade dinonaktifkan.
    raise NotImplementedError("downgrade d004 dinonaktifkan (audit permanen)")
