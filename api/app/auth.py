"""Session-cookie auth (PRD v2.2 §18).

- Password Argon2id (hash bcrypt legacy masih diverifikasi + di-rehash
  saat login sukses).
- Session token acak 256-bit, hanya hash SHA-256 yang disimpan di DB.
- Cookie HttpOnly + SameSite=strict + Secure (config COOKIE_SECURE).
- CSRF token per sesi, wajib pada semua endpoint mutasi.
- Rate limit login per IP + account lockout eksponensial yang selalu
  kedaluwarga (anti-abuse: tidak ada lock permanen, alert hanya utk admin).
- Idle timeout sesi (SESSION_IDLE_HOURS) + sliding last_seen_at.
- 2FA TOTP step-up: require_2fa untuk aksi sensitif (release, flatten,
  risk settings, live approval).
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response

from . import config, db
from .state_machine import fetchone

SESSION_COOKIE = "fund2_session"
CSRF_HEADER = "x-csrf-token"

# naive in-memory login rate limit: ip -> list of attempt timestamps
_login_attempts: dict[str, list[float]] = defaultdict(list)
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_S = 60

# rate limit aksi sensitif per-key (username / endpoint)
_action_hits: dict[str, list[float]] = defaultdict(list)

_ph = PasswordHasher()  # argon2id; default OWASP-ish (64 MiB, t=3, p=4)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifikasi Argon2id; hash bcrypt legacy (pra-v2.2) masih diterima."""
    if password_hash.startswith("$argon2"):
        try:
            return _ph.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True bila hash masih bcrypt -> rehash Argon2id saat login sukses."""
    return password_hash.startswith("$2")


# ── rate limit -------------------------------------------------------------
def login_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = _login_attempts[ip]
    attempts[:] = [t for t in attempts if now - t < LOGIN_RATE_WINDOW_S]
    return len(attempts) >= LOGIN_RATE_LIMIT


def record_login_attempt(ip: str) -> None:
    _login_attempts[ip].append(time.time())


def reset_login_rate_limit() -> None:
    _login_attempts.clear()


def action_rate_limited(key: str, limit: int, window_s: int) -> float:
    """Sliding-window limiter per key. Return retry_after detik (0 = lolos)."""
    now = time.time()
    hits = _action_hits[key]
    hits[:] = [t for t in hits if now - t < window_s]
    if len(hits) >= limit:
        return round(window_s - (now - hits[0]), 1)
    hits.append(now)
    return 0.0


def reset_action_rate_limits() -> None:
    _action_hits.clear()


# ── account lockout (DB-backed, anti-abuse) --------------------------------
# login_failures: satu baris per username. Lock pemicu tiap THRESHOLD
# kegagalan beruntun; durasi = BASE * 2^(lock_events-1), dibatasi MAX.
# Selalu kedaluwarga -> penyerang tidak bisa mengunci permanen; login
# sukses menghapus counter. Alert Telegram hanya untuk role admin
# (dikirim dari routes.login, bukan di sini, agar auth bebas dependency).
async def get_login_failures(conn, username: str) -> dict | None:
    return await fetchone(
        conn,
        "SELECT username, failed_count, locked_until, lock_events "
        "FROM login_failures WHERE username = %s",
        (username,),
    )


async def register_login_failure(conn, username: str) -> dict:
    """Catat kegagalan; return baris terbaru (locked_until bisa NULL)."""
    threshold = config.LOCKOUT_THRESHOLD
    base_s = config.LOCKOUT_BASE_MIN * 60
    max_s = config.LOCKOUT_MAX_MIN * 60
    row = await fetchone(
        conn,
        """
        INSERT INTO login_failures (username, failed_count)
        VALUES (%s, 1)
        ON CONFLICT (username) DO UPDATE
            SET failed_count = login_failures.failed_count + 1,
            updated_at = now()
        RETURNING username, failed_count, locked_until, lock_events
        """,
        (username,),
    )
    if row["failed_count"] % threshold == 0:
        events = (row["lock_events"] or 0) + 1
        duration_s = min(base_s * (2 ** (events - 1)), max_s)
        row = await fetchone(
            conn,
            """
            UPDATE login_failures
            SET locked_until = now() + (%s * interval '1 second'),
                lock_events = %s, updated_at = now()
            WHERE username = %s
            RETURNING username, failed_count, locked_until, lock_events
            """,
            (duration_s, events, username),
        )
    return row


async def clear_login_failures(conn, username: str) -> None:
    await conn.execute("DELETE FROM login_failures WHERE username = %s", (username,))


def is_locked(failures: dict | None) -> bool:
    """Terkunci HANYA bila locked_until masih di masa depan.

    Lock selalu kedaluwarga (anti-abuse): tanpa pengecekan waktu, satu
    lock akan mengunci akun selamanya meski durasinya sudah lewat.
    """
    if not failures or not failures.get("locked_until"):
        return False
    return failures["locked_until"].timestamp() > time.time()


# ── sessions ----------------------------------------------------------------
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(conn, user_id: int) -> tuple[str, str]:
    """Returns (session_token, csrf_token). Only the token hash is stored."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    await conn.execute(
        """
        INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at)
        VALUES (%s, %s, %s, now() + (%s * interval '1 hour'))
        """,
        (user_id, _token_hash(token), csrf, config.SESSION_TTL_HOURS),
    )
    return token, csrf


def set_session_cookie(response: Response, token: str, *, scheme: str = "http") -> None:
    """Cookie sesi: HttpOnly + SameSite=strict.

    Secure diaktifkan untuk akses via https (Caddy, COOKIE_SECURE=1).
    Loopback http tetap tanpa Secure supaya service lokal (recorder,
    llm-agent, harness) tidak rusak; API hanya bind 127.0.0.1, jadi
    permukaan http-loopback tidak terekspose. Test memaksa COOKIE_SECURE=0.
    """
    secure = config.COOKIE_SECURE and scheme == "https"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=config.SESSION_TTL_HOURS * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


async def _load_session(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            SELECT s.id AS session_id, s.csrf_token, s.expires_at, s.last_seen_at,
                   s."2fa_passed_at", u.id AS user_id, u.username, u.role,
                   u.totp_enabled
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = %s
              AND s.expires_at > now()
              AND s.last_seen_at > now() - (%s * interval '1 hour')
            """,
            (_token_hash(token), config.SESSION_IDLE_HOURS),
        )
        if row is not None:
            # sliding idle window (ditulis paling sering 1x/menit)
            await conn.execute(
                """
                UPDATE sessions SET last_seen_at = now()
                WHERE id = %s AND last_seen_at < now() - interval '60 seconds'
                """,
                (row["session_id"],),
            )
    if row is None:
        return None
    return row


async def get_current_user(request: Request) -> dict:
    session = await _load_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return session


async def require_csrf(request: Request, user: dict = Depends(get_current_user)) -> dict:
    header = request.headers.get(CSRF_HEADER, "")
    if not header or not secrets.compare_digest(header, user["csrf_token"]):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
    # RBAC riset (PRD v2.2 §12, t_f2v22a7): role 'research' default-deny untuk
    # SEMUA endpoint mutasi kecuali allowlist eksplisit. Semua endpoint
    # mutasi ber-session melewati dependency ini, jadi satu titik ini
    # menutup POST /orders, /llm-agent/* (audit log), kill-switch, dsb.
    if user.get("role") == "research":
        path = request.url.path
        allowed = path.startswith("/research/") or path in ("/auth/login", "/auth/logout")
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="role research: endpoint di luar allowlist riset "
                       "(PRD v2.2 §12: tidak boleh order/risk/control write)",
            )
    return user


async def require_admin(user: dict = Depends(require_csrf)) -> dict:
    """Endpoint sensibel: admin + CSRF (least privilege, PRD v2.2 §18).

    require_csrf ada di rantai dependency, jadi role check TIDAK
    menggantikan CSRF (menutup lubang lintas-site pada diff pra-v2.2).
    Role 'agent' (fund2-llm-agent) dan 'user' (service/e2e) ditolak 403.
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="admin role required (agent credentials are read-only for controls)",
        )
    return user


def _2fa_missing_detail(user: dict) -> str:
    if not user.get("totp_enabled"):
        return (
            "2FA enrollment required for this action: "
            "POST /auth/2fa/setup then POST /auth/2fa/enable"
        )
    return "2FA verification required: POST /auth/2fa/challenge with a TOTP code"


def _assert_2fa_window(user: dict) -> None:
    """Assert 2FA sesi masih dalam jendela TWOFA_WINDOW_MIN (403 bila tidak)."""
    passed_at = user.get("2fa_passed_at")
    if not user.get("totp_enabled") or passed_at is None:
        raise HTTPException(status_code=403, detail=_2fa_missing_detail(user))
    age_s = time.time() - passed_at.timestamp()
    if age_s > config.TWOFA_WINDOW_MIN * 60:
        raise HTTPException(status_code=403, detail=_2fa_missing_detail(user))


async def require_2fa(user: dict = Depends(require_admin)) -> dict:
    """Step-up 2FA untuk aksi paling sensitif (risk/live/trigger).

    Syarat: admin + CSRF + TOTP terdaftar + assertion 2FA masih dalam
    jendela TWOFA_WINDOW_MIN menit (dibuat via POST /auth/2fa/challenge).
    """
    _assert_2fa_window(user)
    return user


async def require_control_role(user: dict = Depends(require_csrf)) -> dict:
    """Role untuk aksi kontrol operasional flatten/release kill-switch.

    t_4651d431 (insiden 25 Nov 2026): driver QA latensi WAJIB login pakai
    user QA khusus ber-role 'qa' (bukan admin) supaya order QA terpisah
    dari order live di metrik anomaly. Driver me-flat-kan posisi demo
    antar burst dan me-release halt, jadi dua endpoint itu mengizinkan
    'qa' SELAIN admin. Endpoint kontrol lain tetap admin-only
    (require_admin). CSRF tetap wajib (rantai require_csrf) dan 2FA
    tetap wajib (require_2fa_control).
    """
    if user.get("role") not in ("admin", "qa"):
        raise HTTPException(
            status_code=403,
            detail="admin or qa role required (control action)",
        )
    return user


async def require_2fa_control(user: dict = Depends(require_control_role)) -> dict:
    """Step-up 2FA untuk flatten/release: admin ATAU qa + CSRF + TOTP."""
    _assert_2fa_window(user)
    return user


def ensure_2fa(user: dict) -> None:
    """Versi non-dependency utk cek kondisional di dalam handler (403)."""
    _assert_2fa_window(user)


async def create_user(conn, username: str, password: str, role: str = "admin") -> int:
    row = await fetchone(
        conn,
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
        (username, hash_password(password), role),
    )
    return row["id"]
