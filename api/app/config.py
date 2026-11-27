"""Fund2 API configuration. Values come from env vars or api/.env (KEY=VALUE)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # api/


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


_file_env = _load_env_file(BASE_DIR / ".env")


def get(name: str, default: str = "") -> str:
    return os.environ.get(name) or _file_env.get(name, default)


DATABASE_URL = get("DATABASE_URL", "postgresql://fund2:***@127.0.0.1:5433/fund2")
# PRD 5.1: tick mentah -> parquet (bukan Postgres); direct ingest API.
TICKS_PARQUET_DIR = get("TICKS_PARQUET_DIR", str(BASE_DIR.parent / "data" / "parquet"))
HOST = get("HOST", "127.0.0.1")
PORT = int(get("PORT", "3110"))
FRONTEND_DIST = Path(get("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))
ADMIN_USER = get("ADMIN_USER", "admin")
ADMIN_PASSWORD = get("ADMIN_PASSWORD", "")
SESSION_TTL_HOURS = int(get("SESSION_TTL_HOURS", "24"))

# ── Security v2.2 (PRD §18) ──────────────────────────────────────────────
# Cookie Secure: wajib di produksi (fund.lumine.biz.id di belakang Caddy
# TLS). Loopback/test http memakai 0 supaya http cookie jar mengirim cookie.
COOKIE_SECURE = get("COOKIE_SECURE", "1") == "1"
# Idle timeout sesi: sesi mati jika tidak ada request selama N jam
# (sliding: setiap request authentikasi memperbarui last_seen_at).
SESSION_IDLE_HOURS = float(get("SESSION_IDLE_HOURS", "4"))

# Brute force + account lockout (anti-abuse): lock selalu kedaluwarga
# (maks 24 jam), pemicu bertingkat, dan hanya akun admin yang mengirim
# alert Telegram (akun service/user tidak memicu spam).
LOCKOUT_THRESHOLD = int(get("LOCKOUT_THRESHOLD", "5"))
LOCKOUT_BASE_MIN = float(get("LOCKOUT_BASE_MIN", "15"))
LOCKOUT_MAX_MIN = float(get("LOCKOUT_MAX_MIN", "1440"))
# Rate limit aksi sensitif per user (2FA challenge & kontrol berbahaya).
TWOFA_WINDOW_MIN = float(get("TWOFA_WINDOW_MIN", "5"))
TWOFA_CHALLENGE_LIMIT = int(get("TWOFA_CHALLENGE_LIMIT", "5"))
TWOFA_CHALLENGE_WINDOW_S = int(get("TWOFA_CHALLENGE_WINDOW_S", "300"))

# Telegram owner channel (kill-switch manual oleh owner; D11/D12).
TELEGRAM_BOT_TOKEN = get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID = get("TELEGRAM_OWNER_ID", "")

# Bridge / worker tuning
WORKER_INTERVAL_S = 0.05          # 50 ms worker loop
RECONCILE_AFTER_S = 60            # SENT older than this -> STUCK
STUCK_RESOLVE_AFTER_S = 15 * 60   # STUCK older than this -> auto-reconciler (15 menit)
TICK_MAX_AGE_S = 10               # spread filter needs a fresh tick
BRIDGE_POLL_MAX_S = 30            # long-poll cap

# Label environment UI (PRD v2.2 §21.1): dev | demo | live. LIVE memicu
# warning visual khusus di UI yang tidak mungkin tertukar dengan DEMO.
# Nilai tak dikenal fail-safe ke "demo" (salah label ke arah aman).
_env_raw = get("FUND2_ENV", "demo").strip().lower()
FUND2_ENV = _env_raw if _env_raw in ("dev", "demo", "live") else "demo"

# Reconciler (PRD 5.8)
EA_MAGIC = 20261121               # EA order magic; deals/positions outside this + manual
DEAL_WINDOW_H = 24                # EA snapshot carries deals of the last 24 h
EMERGENCY_SL_DISTANCE = 15.0      # XAUUSD price units; legacy last-resort bila
                                  # harga open tidak diketahui (jarak absolut
                                  # TIDAK dipakai lintas simbol, lihat bridge)
EMERGENCY_SL_FALLBACK_PCT = 0.01  # fallback SL darurat orphan tanpa spec:
                                  # 1.0% dari harga open (price-relative)
SNAPSHOT_REREQUEST_S = 5          # min gap between poll-driven SNAPSHOT requests

# HMAC bridge auth (PRD 7; kontrak EA v5 — ea/HMAC_CONTRACT.md). Secret
# shared dengan EA via file MQL5/Files/fund2_hmac.secret, BUKAN di repo.
_FUND2_HMAC_ENV_KEY = "FUND2" + "_HMAC_SECRET"
FUND2_HMAC_SECRET = get(
    _FUND2_HMAC_ENV_KEY, "")
