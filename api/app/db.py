"""Async Postgres access: pool, schema migrations (Alembic), settings store."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from . import config
from .auto_sl import DEFAULT_AUTO_SL
from .risk import DEFAULT_LLM_RISK
from .portfolio_risk import DEFAULT_PORTFOLIO_RISK

log = logging.getLogger("fund2.db")

_pool: AsyncConnectionPool | None = None

# Batas waktu ambil koneksi dari pool. Sebelumnya default library 30 s tanpa
# connect_timeout libpq: socket Postgres yang "separuh terbuka" (server sudah
# bind tapi belum menerima/belum balas startup packet, kondisi nyata saat host
# baru boot) bisa menggantung jauh lebih lama. Insiden 25 Nov 2026 06:45 WIB
# (kartu t_f837fe2c): daemon alert beku diam-diam karena jalur ini.
DEFAULT_ACQUIRE_TIMEOUT_S = 10.0
DEFAULT_CONNECT_TIMEOUT_S = 10
# Budget tunggu "DB siap" saat start; habis -> DBNotReady (daemon keluar
# non-zero supaya systemd mengulang, bukan menggantung).
DEFAULT_DB_READY_TIMEOUT_S = 300.0

# ── Ukuran pool + batas query (t_b827af0c, 26 Nov 2026) ─────────────────────
# max_size 10 terlalu kecil untuk 7 proses yang berbagi satu Postgres dan
# terbukti habis saat /bridge/poll busy-loop (pool timeout 10 s -> SEV-2
# db_unavailable palsu -> kill-switch STOP_NEW_ORDERS). Dinaikkan ke 20 dan
# bisa di-override per unit systemd lewat env (mis. proses ringan cukup 6).
# Catatan kapasitas: Postgres max_connections 100; pool hanya membesar saat
# benar-benar sibuk, dan metrik db_connections (SEV-3 di 80%) jadi alarm dini.
DEFAULT_POOL_MIN_SIZE = max(1, int(os.environ.get("FUND2_POOL_MIN_SIZE", "2")))
DEFAULT_POOL_MAX_SIZE = max(
    DEFAULT_POOL_MIN_SIZE, int(os.environ.get("FUND2_POOL_MAX_SIZE", "20")))
# statement_timeout: query yang menggantung tidak boleh menahan slot pool
# selamanya. 60 s jauh di atas query terberat (rollup/backfill < 1 s), jadi
# hanya query yang benar-benar macet yang kena.
DEFAULT_STATEMENT_TIMEOUT_MS = int(
    os.environ.get("FUND2_STATEMENT_TIMEOUT_MS", "60000"))
# Failsafe server-side untuk transaksi yang ditinggalkan (gejala t_b827af0c:
# koneksi ditahan saat panggilan HTTP LLM -> `idle in transaction`). Jalur yang
# benar tidak pernah mendekati nilai ini; kalau kena, itu bug dan lebih baik
# koneksi dilepas daripada slot pool habis.
DEFAULT_IDLE_IN_TX_TIMEOUT_MS = int(
    os.environ.get("FUND2_IDLE_IN_TX_TIMEOUT_MS", "30000"))


class DBNotReady(RuntimeError):
    """Database belum siap sampai budget tunggu habis (bukan error kode)."""

DEFAULT_SETTINGS: dict = {
    # Nilai default mengikuti policy final (KEPUTUSAN_OWNER §I, 26 Nov 2026):
    # A3 0,10 lot, A8 5 order/menit, A6 3% (absolute dari saldo awal hari).
    # Sumber kebenaran runtime tetap tabel `settings`; default ini hanya
    # dipakai saat key belum ada (instalasi baru / key baru).
    "max_volume": 0.10,           # lots (A3)
    # Profil/informasi (USD = 3% x 10k). BUKAN pemicu halt: auto-halt A6
    # hanya dari kill_switch_triggers.daily_drawdown_pct (AUDIT-A2).
    "max_daily_drawdown": 300.0,
    "max_spread": 0.50,           # XAUUSD price units (ask - bid) (A9)
    "max_orders_per_min": 5,      # A8
    "max_tick_age_s": 3.0,        # A10: usia tick > 3 s -> tolak order
    "halted": False,              # mirror legacy state kill-switch (display saja; keputusan blokir dari kill_switch, t_4d524475)
    "kill_switch": False,         # state kill-switch (bool legacy atau dict state lihat kill_switch.py)
    "allowed_symbols": ["XAUUSD"],
    # Risk per-simbol (KEPUTUSAN_OWNER F1, 22 Nov): A2/A3/A9 per-simbol.
    # XAUUSD = angka A yang dikunci. BTCUSD = dari contract spec MT5,
    # diverifikasi worker t_f2mp1: contract size 1 BTC/lot (8 deal live
    # 22 Nov: profit = Δharga × 1.0 × lot), spread live median $39
    # (10.543 tick 23 Nov), volume min/step 0.01 (E2E live 0.01 lot fill).
    "symbol_specs": {
        "XAUUSD": {
            "contract_size": 100.0,       # oz per lot (HFM; konsisten paper broker)
            "tick_value": 1.00,           # USD per tick (0.01) per lot = 100 oz × 0.01
            "tick_size": 0.01,            # pergerakan harga per tick
            "spec_verified": True,        # diverifikasi worker t_f2v22a3 (PRD §7.3)
            "slippage_usd": 0.35,         # buffer slippage base (satuan harga)
            "sl_min_usd": 0.50,           # A2 (dikunci)
            "sl_max_usd": 15.00,          # A2 (dikunci)
            "vol_max_lot": 0.10,          # A3 (dikunci)
            "vol_min_lot": 0.01,          # lot minimum MT5 (E2E live 0.01 fill)
            "vol_step_lot": 0.01,         # lot step MT5 (RISK-A: pembulatan ke bawah)
            "spread_abs_max_usd": 0.50,   # A9 (dikunci)
        },
        "BTCUSD": {
            "contract_size": 1.0,         # BTC per lot (verifikasi deal live)
            "tick_value": 0.01,           # USD per tick (0.01) per lot = 1 BTC × 0.01
            "tick_size": 0.01,
            "spec_verified": True,        # diverifikasi worker t_f2v22a3 (PRD §7.3)
            "slippage_usd": 5.0,
            "sl_min_usd": 10.00,          # ~0.017% harga, rasio setara XAUUSD (0.50/3579)
            "sl_max_usd": 1000.00,        # ~1.7% harga; volatilitas BTC ~3x gold
            "vol_max_lot": 0.10,          # lot cap setara A3 (0.10 lot = 0.1 BTC)
            "vol_min_lot": 0.01,          # lot minimum MT5 (E2E live 0.01 fill)
            "vol_step_lot": 0.01,         # lot step MT5 (RISK-A: pembulatan ke bawah)
            "spread_abs_max_usd": 100.00, # ~2.5× median spread live $39
        },
    },
    # Portfolio Risk Manager (PRD §7, t_f2v22a3): batas portofolio + stress.
    # Nilai [USULAN]; owner dapat mengubah via settings (ter-audit settings_audit).
    "portfolio_risk": json.loads(json.dumps(DEFAULT_PORTFOLIO_RISK)),
    # A4 akun-level: eksposur terbuka AGREGAT lintas simbol (notional USD,
    # Σ lot × contract_size × harga). Default = 0.30 lot XAUUSD (A4 dikunci)
    # pada harga referensi $3.579/oz saat penguncian (22 Nov).
    "exposure_max_usd": 107370.0,
    # A5 akun-level: risiko per trade maksimum % equity, dihitung dari jarak
    # SL × contract_size × lot simbol terkait.
    "risk_per_trade_pct": 0.5,
    # RISK-A (t_8bf257a2): feature flag auto lot sizing order LLM. DEFAULT
    # OFF -- selama OFF, volume order LLM dipakai apa adanya (behavior lama).
    # Owner aktifkan setelah verifikasi staging:
    #   python -m app.cli set-setting llm_auto_lot '{"enabled": true}'
    # risk_pct mengikuti 'risk_per_trade_pct' (satu sumber kebenaran dgn A5).
    "llm_auto_lot": {"enabled": False},
    # RISK-B (t_f3570608): BE + trailing stop deterministik di bridge layer.
    # DEFAULT OFF -- selama OFF, loop hanya baca settings tanpa menulis apa
    # pun. Owner aktifkan setelah verifikasi staging:
    #   python -m app.cli set-setting auto_sl '{"enabled": true}'
    "auto_sl": dict(DEFAULT_AUTO_SL),
    "daily_start_balance": 10000.0,
    "initial_balance": 10000.0,          # dasar perhitungan drawdown total (A7)
    "equity_high_water_mark": None,      # puncak equity; diratchet oleh monitor
    "paused_strategies": [],             # daftar strategi di-pause (PAUSE_STRATEGY)
    "kill_switch_triggers": None,        # konfigurasi auto-trigger (default di kill_switch.py)
    "trigger_ack": {},                   # marker reset streak FAILED saat pelepasan
    "ea_last_seen_at": None,             # kontak EA terakhir (ISO), persist throttled
    "llm_risk": dict(DEFAULT_LLM_RISK),  # batas khusus agent LLM (t_f2llm2)
    "llm_agent_pause": None,             # state circuit breaker agent LLM
    "llm_breaker_ack": None,             # marker reset streak FAILED LLM saat resume
}


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


@asynccontextmanager
async def _connection_diag(p: AsyncConnectionPool, timeout):
    """Bungkus acquire; saat PoolTimeout catat statistik pool untuk diagnosa.

    Statistik WAJIB dibaca tanpa mengubah jenis exception. psycopg_pool >=3.2
    mengembalikan `dict` dari get_stats() (kelas PoolStats sudah dihapus); kode
    lama memakai atribut (`st.pool_size`) sehingga jalur diagnosa melempar
    AttributeError dan PoolTimeout asli hilang — caller yang menangkap
    PoolTimeout tidak pernah jalan, dan journal hanya menampilkan
    "AttributeError: 'dict' object has no attribute 'pool_size'" saat database
    mati (terbukti di drill F-1, kartu t_f837fe2c). Dukungan dict + atribut
    dipertahankan supaya versi library lain tidak memecahkan diagnosa.
    """
    try:
        async with p.connection(timeout=timeout) as conn:
            yield conn
    except PoolTimeout:
        try:
            st = p.get_stats()
            keys = ("pool_min", "pool_max", "pool_size", "pool_available",
                    "requests_waiting", "requests_num", "requests_errors")
            if isinstance(st, dict):
                detail = {k: st[k] for k in keys if k in st}
                if "errors" in st:
                    detail["errors"] = list(st["errors"])[:2]
            else:  # pragma: no cover — API lama (atribut)
                detail = {k: getattr(st, k, None) for k in keys}
            log.warning("PoolTimeout diag (timeout=%ss): %s", timeout, detail)
        except Exception:  # noqa: BLE001 — diagnosa tidak boleh menutupi error asli
            log.warning("PoolTimeout diag: statistik pool tidak terbaca",
                        exc_info=True)
        raise


def connection(timeout: float | None = DEFAULT_ACQUIRE_TIMEOUT_S):
    """Koneksi pool dengan batas waktu acquire eksplisit.

    Jalur kritis (daemon alert, watcher) WAJIB memakai ini: acquire tanpa
    batas membuat proses bisa menggantung tanpa log saat Postgres belum siap
    (insiden 25 Nov 2026, temuan F-1).
    """
    return _connection_diag(pool(), timeout)


async def init_pool() -> None:
    global _pool
    _pool = AsyncConnectionPool(
        conninfo=config.DATABASE_URL,
        min_size=DEFAULT_POOL_MIN_SIZE,
        max_size=DEFAULT_POOL_MAX_SIZE,
        # Acquire dibatasi (bukan default library 30 s) dan connect libpq
        # dibatasi juga supaya socket yang diam tidak menggantung worker pool.
        timeout=DEFAULT_ACQUIRE_TIMEOUT_S,
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": DEFAULT_CONNECT_TIMEOUT_S,
            # Batas query + failsafe transaksi tertinggal, dipasang per sesi
            # lewat libpq `options` (server-wide tetap 0 = tanpa batas).
            "options": (
                f"-c statement_timeout={DEFAULT_STATEMENT_TIMEOUT_MS} "
                f"-c idle_in_transaction_session_timeout={DEFAULT_IDLE_IN_TX_TIMEOUT_MS}"
            ),
        },
        open=False,
    )
    await _pool.open()


async def wait_ready(
    *,
    timeout_s: float = DEFAULT_DB_READY_TIMEOUT_S,
    attempt_timeout_s: float = DEFAULT_ACQUIRE_TIMEOUT_S,
    base_delay_s: float = 1.0,
    max_delay_s: float = 10.0,
    logger: logging.Logger | None = None,
) -> float:
    """Tunggu Postgres siap: `SELECT 1` dengan retry + backoff eksplisit.

    Return waktu tunggu (detik). Raise `DBNotReady` bila budget `timeout_s`
    habis. Setiap percobaan dicatat supaya kondisi "DB belum siap" terlihat
    di journal, bukan berupa daemon yang diam.
    """
    lg = logger or log
    t_start = time.monotonic()
    deadline = t_start + max(0.0, timeout_s)
    delay = max(0.0, base_delay_s)
    attempt = 0
    last_exc: Exception | None = None
    while True:
        attempt += 1
        t0 = time.monotonic()
        # Satu percobaan tidak boleh melewati sisa budget (mis. budget 3 s
        # tidak menunggu acquire 10 s).
        attempt_timeout = min(attempt_timeout_s, max(1.0, deadline - t0))
        try:
            async with connection(timeout=attempt_timeout) as conn:
                await conn.execute("SELECT 1")
            waited = time.monotonic() - t_start
            lg.info("db siap (percobaan %d, %.1fs): %s",
                    attempt, time.monotonic() - t0, "database menerima query")
            return waited
        except Exception as exc:  # noqa: BLE001 — semua kegagalan = belum siap
            last_exc = exc
            remaining = deadline - time.monotonic()
            lg.warning(
                "db belum siap (percobaan %d): %s: %s; sisa budget %.0fs",
                attempt, type(exc).__name__, exc, max(0.0, remaining),
            )
            if remaining <= 0:
                raise DBNotReady(
                    f"database belum siap setelah {timeout_s:.0f}s "
                    f"({attempt} percobaan): {type(exc).__name__}: {exc}"
                ) from exc
            sleep_s = min(delay, remaining)
            lg.warning("db belum siap: coba lagi dalam %.1fs", sleep_s)
            await asyncio.sleep(sleep_s)
            delay = min(max_delay_s, max(base_delay_s, delay * 2))


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _run_migrations() -> None:
    """Jalankan `alembic upgrade head` (sinkron) terhadap DATABASE_URL aktif."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    # Jangan biarkan fileConfig(alembic.ini) menonaktifkan logger yang sudah ada
    # (insiden 22 Nov: logger fund2.telegram kehilangan propagate -> caplog kosong).
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


async def apply_schema() -> None:
    """Terapkan migrasi database hingga versi terbaru (Alembic, PRD 19.3)."""
    await asyncio.to_thread(_run_migrations)


async def seed_defaults() -> None:
    """Insert default settings (never overwrite existing) + bridge token."""
    async with pool().connection() as conn:
        for key, value in DEFAULT_SETTINGS.items():
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                (key, json.dumps(value)),
            )
        row = await conn.execute("SELECT 1 FROM settings WHERE key = 'bridge_token'")
        if await row.fetchone() is None:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ('bridge_token', %s)",
                (json.dumps(secrets.token_urlsafe(32)),),
            )


async def get_settings() -> dict:
    """Merged view: defaults <- DB rows."""
    async with pool().connection() as conn:
        cur = await conn.execute("SELECT key, value FROM settings")
        rows = await cur.fetchall()
    merged = dict(DEFAULT_SETTINGS)
    for row in rows:
        merged[row["key"]] = row["value"]
    return merged


async def settings_snapshot(conn) -> dict:
    """Merged view settings dibaca pada koneksi yang SUDAH dipegang.

    Dipakai jalur yang tidak boleh menambah permintaan slot pool (siklus agent
    LLM, collect_metrics). Semantik sama dengan `get_settings()`: defaults <- DB.
    """
    cur = await conn.execute("SELECT key, value FROM settings")
    merged = dict(DEFAULT_SETTINGS)
    for row in await cur.fetchall():
        merged[row["key"]] = row["value"]
    return merged


async def set_setting(key: str, value, *, actor: str | None = None) -> None:
    """Tulis satu key settings (ter-audit otomatis oleh trigger DB).

    `actor` diisi untuk perubahan yang berasal dari aksi user (guardrail,
    trigger risiko): nilainya dipasang sebagai `app.actor` di transaksi yang
    sama sehingga `settings_audit.changed_by` mencatat USERNAME, bukan role
    koneksi DB. Tanpa actor, trigger memakai `current_user` (perilaku lama).
    """
    async with pool().connection() as conn:
        if actor:
            await conn.execute("SELECT set_config('app.actor', %s, true)", (actor,))
        await conn.execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (key, json.dumps(value)),
        )
