"""Test suite wiring.

Database isolation after the 22 Nov 2026 05:34 WIB incident (a pytest run
with the live DATABASE_URL exported truncated the live fund2 database twice).
Three independent layers, each on its own enough to protect the live DB:

1. URL resolution (at conftest import): pytest only runs against a database
   named `fund2_test` or `fund2_test_*`. Any other DATABASE_URL (live fund2,
   staging, ...) fails the run loudly instead of being silently redirected.
2. Per-run database: each session creates its own throwaway
   `fund2_test_<UTC timestamp>_<pid>` and drops it at the end, so concurrent
   pytest runs never share data. Falls back to the shared `fund2_test` only
   when CREATE DATABASE is not permitted.
3. TRUNCATE guard: `_clean_db` verifies the actual connection
   (current_database() + server port) immediately before truncating.

Telegram isolation after the 22 Nov 2026 10:40-12:22 WIB incident (a worker
tested the bridge/reconciler with a synthetic snapshot against the LIVE api;
every test cycle called the real notify_owner() with the production token
from api/.env and spammed the owner's Telegram with 'ORPHAN ADOPTED' /
'REKONSILIASI'):

4. No production Telegram credentials, ever: conftest drops any
   TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID from the shell env and blanks the
   config attributes for the whole session, whatever api/.env contains.
5. Alert guard: conftest sets TELEGRAM_ALERTS_OFF=1, which makes
   app.telegram_bot.notify_owner() a logged no-op while the reconciler and
   bridge keep running. A test that deliberately exercises the send path
   must opt in via the `fake_tg` fixture (or monkeypatch.delenv the guard
   AND patch tg_api/send_message with a recorder) — never with a real token.

RULE: bridge/reconciler tests must NOT use production Telegram credentials.
Ad-hoc worker scripts that import app code must run with TELEGRAM_ALERTS_OFF=1.
"""
from __future__ import annotations

import copy
import os
import pathlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

TEST_DB_PREFIX = "fund2_test"
SHARED_TEST_DB = "fund2_test"
ORPHAN_MAX_AGE_S = 6 * 3600  # crashed runs leave DBs behind; sweep older ones

_api_dir = pathlib.Path(__file__).resolve().parent.parent


def _load_env_file(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def _db_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def _with_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def _is_test_db(name: str) -> bool:
    return name == SHARED_TEST_DB or name.startswith(TEST_DB_PREFIX + "_")


def _resolve_base_test_url() -> str:
    """Pick the URL pytest builds on.

    An exported DATABASE_URL is only trusted when it already names a test
    database (the incident: a worker exported the live URL, so the old
    conftest skipped its redirect and truncated the live DB). The api/.env
    URL is always retargeted to the shared test database.
    """
    env_url = (os.environ.get("DATABASE_URL") or "").strip()
    if env_url:
        if _is_test_db(_db_name(env_url)):
            return env_url
        raise RuntimeError(
            f"DATABASE_URL points at non-test database {_db_name(env_url)!r}; "
            f"pytest only runs against {SHARED_TEST_DB} or {TEST_DB_PREFIX}_*. "
            "Unset DATABASE_URL or point it at a test database."
        )
    file_url = (_load_env_file(_api_dir / ".env").get("DATABASE_URL") or "").strip()
    if file_url:
        return _with_db(file_url, SHARED_TEST_DB)
    raise RuntimeError(
        "No DATABASE_URL found in env or api/.env; cannot locate a test database."
    )


# Layer 1 must complete BEFORE app.config binds DATABASE_URL at import time.
BASE_TEST_URL = _resolve_base_test_url()
os.environ["DATABASE_URL"] = BASE_TEST_URL

import psycopg  # noqa: E402
from psycopg.rows import tuple_row  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import config, db, kill_switch, llm_agent_loop, market, market_status, metrics, telegram_bot  # noqa: E402
from app.auth import (  # noqa: E402
    hash_password,
    reset_action_rate_limits,
    reset_login_rate_limit,
)
from app.main import app  # noqa: E402

# --- Layer 4: no production Telegram credentials in the test session -------
# (insiden 22 Nov 2026 10:40-12:22 WIB; lihat docstring modul ini)
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_OWNER_ID", None)
os.environ["TELEGRAM_ALERTS_OFF"] = "1"  # notify_owner() -> logged no-op
config.TELEGRAM_BOT_TOKEN = ""
config.TELEGRAM_OWNER_ID = ""

# --- Layer 2: per-run throwaway database -----------------------------------

_ORPHAN_RE = re.compile(rf"^{TEST_DB_PREFIX}_(\d{{14}})_(\d+)$")


async def _maintenance_connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        _with_db(BASE_TEST_URL, "postgres"), autocommit=True
    )


async def _sweep_orphan_databases() -> None:
    """Drop fund2_test_* databases left behind by crashed runs."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ORPHAN_MAX_AGE_S)
    try:
        async with await _maintenance_connect() as conn:
            cur = await conn.execute(
                "SELECT datname FROM pg_database WHERE datname ~ %s",
                (rf"^{TEST_DB_PREFIX}_\d{{14}}_\d+$",),
            )
            stale = []
            for (name,) in await cur.fetchall():
                match = _ORPHAN_RE.match(name)
                if match is None:
                    continue
                created = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(
                    tzinfo=timezone.utc
                )
                if created < cutoff:
                    stale.append(name)
            for name in stale:
                try:
                    await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
                except psycopg.Error as exc:
                    print(f"[conftest] could not drop orphan {name}: {exc}")
        if stale:
            print(f"[conftest] swept orphan test databases: {stale}")
    except psycopg.Error as exc:
        print(f"[conftest] orphan sweep skipped: {exc}")


async def _create_run_database() -> str:
    dbname = (
        f"{TEST_DB_PREFIX}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        f"_{os.getpid()}"
    )
    try:
        async with await _maintenance_connect() as conn:
            await conn.execute(f'CREATE DATABASE "{dbname}"')
    except psycopg.Error as exc:
        print(f"[conftest] CREATE DATABASE failed ({exc}); using shared {SHARED_TEST_DB}")
        return BASE_TEST_URL
    return _with_db(BASE_TEST_URL, dbname)


async def _drop_database(dbname: str) -> None:
    async with await _maintenance_connect() as conn:
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')


# --- Layer 3: refuse to mutate anything but a fund2_test database ----------


async def _assert_test_connection(conn) -> None:
    # Explicit tuple_row: the guard must not depend on the caller's row factory.
    cur = conn.cursor(row_factory=tuple_row)
    await cur.execute("SELECT current_database(), inet_server_port()")
    dbname, port = await cur.fetchone()
    expected_port = urlsplit(config.DATABASE_URL).port or 5432
    if not _is_test_db(dbname) or port != expected_port:
        raise RuntimeError(
            f"safety stop: connected to database {dbname!r} on port {port}, "
            f"expected {_db_name(config.DATABASE_URL)!r} on port {expected_port}"
        )


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
async def _run_database():
    """Point the app at this run's own database; drop it afterwards."""
    await _sweep_orphan_databases()
    run_url = await _create_run_database()
    os.environ["DATABASE_URL"] = run_url
    config.DATABASE_URL = run_url  # db.init_pool() reads this at call time
    yield
    dbname = _db_name(run_url)
    if dbname != SHARED_TEST_DB:
        try:
            await _drop_database(dbname)
        except psycopg.Error as exc:
            print(f"[conftest] could not drop {dbname}: {exc}")


@pytest.fixture(scope="session", autouse=True)
async def _db_session(_run_database):
    await db.init_pool()
    async with db.pool().connection() as conn:
        await _assert_test_connection(conn)
    await db.apply_schema()
    await db.seed_defaults()
    yield
    await db.close_pool()


@pytest.fixture(autouse=True)
async def _clean_db(_db_session):
    async with db.pool().connection() as conn:
        await _assert_test_connection(conn)
        # session_replication_role=replica menonaktifkan trigger TRUNCATE
        # order_events (append-only, PRD 19.4) KHUSUS untuk cleanup DB test.
        # Guard _assert_test_connection di atas tetap memastikan ini DB test.
        await conn.execute("SET session_replication_role = replica")
        await conn.execute(
            "TRUNCATE order_events, orders, positions, bridge_commands, candles, sessions, "
            "users, kill_switch_events, paper_orders, paper_state, liquidity_samples, "
            "backtest_runs, strategies, strategy_versions, strategy_approvals, signals, "
            "paper_runs, shadow_runs, regime_observations, risk_decisions, system_events, "
            "reconciliation_runs, deployment_records, research_reports, settings_audit, "
            "position_snapshots, data_quality_runs, data_versions, audit_log, "
            "login_failures, improvement_proposals, degradation_state, degradation_events, "
            "research_proposals, strategy_risk_overrides, strategy_risk_override_requests, "
            "fib_levels "
            "RESTART IDENTITY CASCADE"
        )
        await conn.execute("RESET session_replication_role")
    for key, value in {
        "max_volume": 1.0,
        "max_daily_drawdown": 100.0,
        "max_spread": 0.50,
        "max_orders_per_min": 10,
        "halted": False,
        "kill_switch": False,
        "allowed_symbols": ["XAUUSD"],
        # Isolasi setelan yang bisa diubah test lain (kartu t_f412fd48):
        # portfolio_risk/llm_* dulu tidak di-reset, sehingga test yang
        # menyetel portfolio_risk ketat membuat test kill-switch berikutnya
        # gagal 422 "open risk exceeds" (polusi antar-file, bukan bug kode).
        "portfolio_risk": copy.deepcopy(db.DEFAULT_SETTINGS["portfolio_risk"]),
        "llm_risk": copy.deepcopy(db.DEFAULT_SETTINGS["llm_risk"]),
        "llm_auto_lot": copy.deepcopy(db.DEFAULT_SETTINGS["llm_auto_lot"]),
        "llm_interval_s": None,
        # AUDIT-E: key kanonik interval siklus. Tanpa reset, nilai dari test
        # sebelumnya menumpang ke test berikutnya (pola insiden 25 Nov 2026).
        "llm_agent_interval_s": None,
    }.items():
        await db.set_setting(key, value)
    await db.set_setting("kill_switch", False)  # legacy inactive
    await db.set_setting("paused_strategies", [])
    await db.set_setting("kill_switch_triggers", None)
    await db.set_setting("trigger_ack", {})
    await db.set_setting("ea_last_seen_at", None)
    market._latest.clear()
    # State in-memory last-seen EA di-reset per test: usia heartbeat dari
    # test bridge sebelumnya tidak boleh menumpang ke test berikutnya.
    # Saat suite penuh berjalan lambat (>60 dtk sejak heartbeat terakhir),
    # gate LLM menolak order fail-closed dengan "EA offline Ns exceeds max
    # 60s" pada test yang mengharapkan order diterima (insiden 25 Nov 2026,
    # 4x test_llm_risk). None = EA belum terlihat proses ini; gate
    # ea_offline hanya memblokir bila age terukur > threshold.
    kill_switch._ea_seen_mono = None
    kill_switch._ea_last_persist_mono = 0.0
    # t_b827af0c: state in-memory watchdog db_unavailable + cache tz agent LLM
    # juga harus di-reset, kalau tidak streak/probe test sebelumnya menumpang
    # ke test berikutnya (pola insiden in-memory state 25 Nov 2026).
    metrics.DB_UNAVAIL_TRACKER.reset()
    llm_agent_loop._DB_TZ_CACHE.update({"value": None, "at": 0.0})
    reset_login_rate_limit()
    reset_action_rate_limits()
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Isolasi limiter in-memory antar-test (login per-IP, 2FA/aksi per-user).

    Tanpa ini, challenge 2FA dari test-test sebelumnya dalam satu proses
    menghitung limit TWOFA_CHALLENGE_LIMIT (5 / 300s per username) dan
    test berikutnya dapat 429 pada fixture client_2fa — kegagalan yang
    terlihat sebagai flakiness antar-file, bukan bug kode.
    """
    reset_login_rate_limit()
    reset_action_rate_limits()
    yield
    reset_login_rate_limit()
    reset_action_rate_limits()


@pytest.fixture(autouse=True)
def _reset_market_status():
    """Registry status pasar bersifat modul-global; tanpa reset antar-test,
    laporan CLOSED dari satu tes membekukan penulisan bar di tes lain dan
    entri parsial memicu KeyError pada konsumen (flaky 26 Nov 2026)."""
    market_status.clear()
    yield
    market_status.clear()


@pytest.fixture
async def user(_clean_db):
    """Owner/admin user untuk suite API.

    Role 'admin' (bukan default 'user') karena PRD v2.2 §18 (commit 7108a57,
    t_f2v22a9) menambah RBAC: endpoint kontrol (kill-switch, strategy mode,
    risk settings) hanya untuk admin. Test yang sengaja menguji penolakan
    role lain tetap membuat user sendiri (lihat test_agent_role.py).
    """
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin') "
            "RETURNING id",
            ("tester", hash_password("testpass")),
        )
        created = await row.fetchone()
    return {"id": created["id"], "username": "tester", "password": "testpass",
            "role": "admin"}


@pytest.fixture
async def client(user):
    """HTTP client already logged in as 'tester' (session cookie persisted)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login", json={"username": "tester", "password": "testpass"})
        assert resp.status_code == 200, resp.text
        csrf = resp.json()["csrf_token"]
        c.headers["x-csrf-token"] = csrf
        yield c


@pytest.fixture
async def client_2fa(client):
    """Client admin dengan 2FA terdaftar + challenge aktif (jendela 2FA terbuka).

    Dipakai test yang meng-hitung endpoint step-up 2FA (PRD v2.2 §18):
    /kill-switch/release, /kill-switch/flatten, /kill-switch/triggers,
    /strategies/{id}/mode live, /llm-agent/resume.
    """
    from app import totp

    import time

    secret = (await client.post("/auth/2fa/setup")).json()["secret"]
    r = await client.post("/auth/2fa/enable", json={"code": totp.totp_at(secret)})
    assert r.status_code == 200, r.text
    # challenge pakai time-step BERIKUTNYA: kode yang sama dipakai enable sudah
    # tercatat di anti-replay counter (verify_rejects_reused_counter).
    r = await client.post(
        "/auth/2fa/challenge", json={"code": totp.totp_at(secret, time.time() + 30)})
    assert r.status_code == 200, r.text
    yield client


@pytest.fixture
async def bridge_token():
    settings = await db.get_settings()
    return settings["bridge_token"]


@pytest.fixture
def tick_2000():
    """Fresh XAUUSD tick, spread 0.30 (within max 0.50)."""
    market.update_tick("XAUUSD", bid=1999.85, ask=2000.15)
    return market.latest("XAUUSD")


@pytest.fixture
def fake_tg(monkeypatch):
    """Notifier Telegram uji: opt-in jalur kirim untuk SATU test.

    Menghapus guard TELEGRAM_ALERTS_OFF, memasang token/chat ID palsu, dan
    mengganti telegram_bot.tg_api (batas jaringan) dengan perekam yang
    TIDAK pernah menyentuh api.telegram.org. Return list of
    {"method", "params"} untuk setiap panggilan yang dicoba.
    """
    monkeypatch.delenv("TELEGRAM_ALERTS_OFF", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_OWNER_ID", "12345")
    calls: list[dict] = []

    async def fake_tg_api(token, method, **params):
        calls.append({"method": method, "params": params})
        return {"ok": True, "result": []}

    monkeypatch.setattr(telegram_bot, "tg_api", fake_tg_api)
    return calls
