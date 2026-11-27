"""Security v2.2 (PRD §18): Argon2id, lockout anti-abuse, 2FA step-up,
session revoke/idle-timeout, audit trail, cookie flags."""
from __future__ import annotations

import time

import bcrypt
import pytest
from fastapi import Response
from httpx import ASGITransport, AsyncClient

from app import auth, config, db, totp
from app.main import app
from app.state_machine import fetchone


async def _row(query, params=()):
    async with db.pool().connection() as conn:
        return await fetchone(conn, query, params)


async def _exec(query, params=()):
    async with db.pool().connection() as conn:
        await conn.execute(query, params)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Isolasi limiter in-memory antar-test (login per-IP & 2FA per-user)."""
    auth.reset_login_rate_limit()
    auth.reset_action_rate_limits()
    yield
    auth.reset_login_rate_limit()
    auth.reset_action_rate_limits()


# ------------------------------------------------------------------ password
async def test_password_hash_is_argon2id(user):
    row = await _row("SELECT password_hash FROM users WHERE username = 'tester'")
    assert row["password_hash"].startswith("$argon2id$")


async def test_bcrypt_legacy_verified_and_rehashed_on_login(user):
    pw_hash = bcrypt.hashpw(b"oldpw", bcrypt.gensalt()).decode()
    await _exec(
        "INSERT INTO users (username, password_hash, role) VALUES ('legacy', %s, 'user')",
        (pw_hash,),
    )
    auth.reset_login_rate_limit()
    async with _client() as c:
        r = await c.post("/auth/login", json={"username": "legacy", "password": "oldpw"})
        assert r.status_code == 200, r.text
    row = await _row("SELECT password_hash FROM users WHERE username = 'legacy'")
    assert row["password_hash"].startswith("$argon2id$")


# ------------------------------------------------------------------ lockout
async def test_lockout_blocks_correct_password_until_expiry(user):
    auth.reset_login_rate_limit()
    auth.reset_action_rate_limits()
    async with _client() as c:
        for _ in range(config.LOCKOUT_THRESHOLD):
            r = await c.post("/auth/login",
                             json={"username": "tester", "password": "wrong"})
            assert r.status_code == 401
        # password BENAR pun ditolak selama terkunci (anti-oracle)
        r = await c.post("/auth/login",
                         json={"username": "tester", "password": "testpass"})
        assert r.status_code == 429, r.text

        # paksa kedaluwarga -> login sukses & counter bersih
        await _exec(
            "UPDATE login_failures SET locked_until = now() - interval '1 second' "
            "WHERE username = 'tester'")
        r = await c.post("/auth/login",
                         json={"username": "tester", "password": "testpass"})
        assert r.status_code == 200, r.text
        row = await _row("SELECT * FROM login_failures WHERE username = 'tester'")
        assert row is None  # sukses menghapus counter


async def test_lockout_is_exponential_and_capped(user):
    from datetime import datetime, timezone

    def now():
        return datetime.now(timezone.utc)

    # Percobaan saat terkunci TIDAK menambah counter (lock tidak bisa
    # diperpanjang penyerang) -> increment hanya saat tidak terkunci.
    async with _client() as c:
        # lock 1: LOCKOUT_THRESHOLD kegagalan -> durasi dasar
        for _ in range(config.LOCKOUT_THRESHOLD):
            r = await c.post("/auth/login",
                             json={"username": "tester", "password": "wrong"})
            assert r.status_code == 401
        row = await _row(
            "SELECT lock_events, locked_until FROM login_failures WHERE username = 'tester'")
        assert row["lock_events"] == 1
        dur1 = (row["locked_until"] - now()).total_seconds()
        assert 0 < dur1 <= config.LOCKOUT_BASE_MIN * 60 + 5

        # paksa kedaluwarga, kegagalan lagi -> lock 2 dengan durasi 2x
        await _exec(
            "UPDATE login_failures SET locked_until = now() - interval '1 second' "
            "WHERE username = 'tester'")
        for _ in range(config.LOCKOUT_THRESHOLD):
            r = await c.post("/auth/login",
                             json={"username": "tester", "password": "wrong"})
            assert r.status_code == 401
        row = await _row(
            "SELECT lock_events, locked_until FROM login_failures WHERE username = 'tester'")
        assert row["lock_events"] == 2
        dur2 = (row["locked_until"] - now()).total_seconds()
        assert dur2 >= dur1 * 1.5  # eksponensial
        assert dur2 <= config.LOCKOUT_MAX_MIN * 60 + 5  # ter-capping


# ------------------------------------------------------------------ 2FA step-up
async def test_sensitive_actions_require_2fa(client):
    # admin + CSRF tapi tanpa 2FA -> 403 di release/flatten/triggers/mode live
    r = await client.post("/kill-switch/release", json={})
    assert r.status_code == 403
    assert "2FA" in r.json()["detail"]
    r = await client.post("/kill-switch/flatten", json={"confirm": True})
    assert r.status_code == 403
    r = await client.put("/kill-switch/triggers", json={"daily_drawdown_pct": 5.0})
    assert r.status_code == 403
    r = await client.post("/strategies/london_breakout/mode", json={"mode": "live"})
    assert r.status_code == 403


async def test_2fa_enrollment_and_challenge_flow(client):
    async with _client() as c:
        login = await c.post("/auth/login",
                             json={"username": "tester", "password": "testpass"})
        c.headers["x-csrf-token"] = login.json()["csrf_token"]

        # challenge sebelum enrolment -> 400
        r = await c.post("/auth/2fa/challenge", json={"code": "123456"})
        assert r.status_code == 400

        setup = await c.post("/auth/2fa/setup")
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")

        # kode salah -> enable ditolak
        r = await c.post("/auth/2fa/enable", json={"code": "000000"})
        assert r.status_code == 403
        # kode benar -> aktif
        r = await c.post("/auth/2fa/enable", json={"code": totp.totp_at(secret)})
        assert r.status_code == 200, r.text

        # challenge: kode counter berikutnya (enable membakar counter sekarang)
        r = await c.post("/auth/2fa/challenge",
                         json={"code": totp.totp_at(secret, time.time() + 30)})
        assert r.status_code == 200, r.text

        me = await c.get("/auth/me")
        assert me.json()["totp_enabled"] is True
        assert me.json()["2fa_valid"] is True


async def test_2fa_challenge_rate_limited(client):
    async with _client() as c:
        login = await c.post("/auth/login",
                             json={"username": "tester", "password": "testpass"})
        c.headers["x-csrf-token"] = login.json()["csrf_token"]
        secret = (await c.post("/auth/2fa/setup")).json()["secret"]
        assert (await c.post("/auth/2fa/enable",
                             json={"code": totp.totp_at(secret)})).status_code == 200
        codes = []
        for _ in range(config.TWOFA_CHALLENGE_LIMIT + 1):
            r = await c.post("/auth/2fa/challenge", json={"code": "000000"})
            codes.append(r.status_code)
        assert codes[-1] == 429
        assert codes.count(403) == config.TWOFA_CHALLENGE_LIMIT


async def test_2fa_disable_requires_valid_code(client):
    async with _client() as c:
        login = await c.post("/auth/login",
                             json={"username": "tester", "password": "testpass"})
        c.headers["x-csrf-token"] = login.json()["csrf_token"]
        secret = (await c.post("/auth/2fa/setup")).json()["secret"]
        assert (await c.post("/auth/2fa/enable",
                             json={"code": totp.totp_at(secret)})).status_code == 200
        r = await c.post("/auth/2fa/disable", json={"code": "000000"})
        assert r.status_code == 403
        r = await c.post("/auth/2fa/disable",
                         json={"code": totp.totp_at(secret, time.time() + 30)})
        assert r.status_code == 200, r.text
        me = await c.get("/auth/me")
        assert me.json()["totp_enabled"] is False


# ------------------------------------------------------------------ sessions
async def test_revoke_all_sessions_keeps_current(user):
    auth.reset_login_rate_limit()
    async with _client() as c1, _client() as c2:
        for c in (c1, c2):
            r = await c.post("/auth/login",
                             json={"username": "tester", "password": "testpass"})
            c.headers["x-csrf-token"] = r.json()["csrf_token"]
        assert (await c2.get("/auth/me")).status_code == 200

        r = await c1.post("/auth/sessions/revoke-all")
        assert r.status_code == 200
        assert r.json()["revoked"] >= 1

        # sesi lain mati, sesi saat ini hidup
        assert (await c2.get("/auth/me")).status_code == 401
        assert (await c1.get("/auth/me")).status_code == 200


async def test_idle_session_expires(user):
    auth.reset_login_rate_limit()
    async with _client() as c:
        r = await c.post("/auth/login",
                         json={"username": "tester", "password": "testpass"})
        c.headers["x-csrf-token"] = r.json()["csrf_token"]
        assert (await c.get("/auth/me")).status_code == 200
        await _exec(
            "UPDATE sessions SET last_seen_at = now() - (%s * interval '1 hour')",
            (config.SESSION_IDLE_HOURS + 1,))
        assert (await c.get("/auth/me")).status_code == 401


# ------------------------------------------------------------------ audit & cookie
async def test_audit_trail_records_login(user):
    auth.reset_login_rate_limit()
    async with _client() as c:
        await c.post("/auth/login", json={"username": "tester", "password": "wrong"})
        await c.post("/auth/login", json={"username": "tester", "password": "testpass"})
    row = await _row(
        "SELECT action FROM audit_log WHERE actor = 'tester' "
        "ORDER BY id DESC LIMIT 1")
    assert row["action"] == "LOGIN_SUCCESS"
    row = await _row(
        "SELECT action FROM audit_log WHERE actor = 'tester' AND action = 'LOGIN_FAILED'")
    assert row is not None


def test_cookie_flags_httponly_samesite():
    resp = Response()
    auth.set_session_cookie(resp, "tok" * 10)
    header = resp.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=strict" in header
    assert "fund2_session=" in header


def test_cookie_secure_flag_when_https(monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    resp = Response()
    auth.set_session_cookie(resp, "tok" * 10, scheme="https")
    assert "Secure" in resp.headers["set-cookie"]
