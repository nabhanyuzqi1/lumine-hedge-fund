#!/usr/bin/env python3
"""mt5_guard.py - self-healing MT5/EA yang hemat request.

Dijalankan fund2-mt5-guard.timer tiap 60 detik. Biaya: 1 request HTTP lokal
(/health) + 1 SELECT settings per menit. Tidak ada polling cepat, tidak ada
restart berulang.

Keputusan (histeresis, bukan reaktif satu sampel):
  * API /health gagal            -> tidak menyimpulkan apa pun, keluar.
  * umur EA <= STALE_S           -> sehat, strike = 0.
  * 1..2 kali berturut-turut telat -> catat strike, belum restart.
  * 3 kali (>= ~3 menit) telat   -> restart unit MT5, maksimal 1x/10 menit
                                    dan 3x/jam. Tidak pernah menyentuh API.
  * masih telat > RECOVER_S sesudah restart -> 1 alert eskalasi (sekali saja,
    dedup di state), lalu diam sampai pulih atau sampai jam berikutnya.

Credential dibaca dari file env, tidak pernah dicetak.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UNIT = "lumine-hedge-fund-mt5"
API_HEALTH = "http://127.0.0.1:3110/health"
STATE_PATH = Path("/home/tekka/fund2/data/mt5_guard.json")
ENV_API = Path("/home/tekka/fund2/api/.env")
ENV_ALERT = Path("/home/tekka/fund2/api/.env.alerts")
LOG_PATH = Path("/home/tekka/fund2/data/mt5_guard.log")

STALE_S = 120          # EA dianggap telat setelah 2 menit tanpa heartbeat
STRIKES_TO_RESTART = 3 # 3 sampel berturut-turut (~3 menit)
MIN_GAP_S = 600        # jeda minimum antar-restart
MAX_PER_HOUR = 3       # batas restart per jam
RECOVER_S = 420        # setelah restart, beri 7 menit untuk pulih
ESCALATE_DEDUP_S = 6 * 3600


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp} {msg}"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def api_healthy() -> bool:
    try:
        with urllib.request.urlopen(API_HEALTH, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def ea_age_s() -> float | None:
    """Umur heartbeat EA dalam detik (None kalau belum pernah terlihat)."""
    env = read_env(ENV_API)
    dsn = env.get("DATABASE_URL") or env.get("DSN")
    if not dsn:
        return None
    try:
        import psycopg  # type: ignore
    except ImportError:
        return None
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings WHERE key = 'ea_last_seen_at'")
                row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - guard tidak boleh crash
        log(f"db_error {type(exc).__name__}")
        return None
    if not row or not row[0]:
        return None
    raw = str(row[0]).replace("Z", "+00:00")
    try:
        seen = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - seen).total_seconds()


def unit_state() -> tuple[bool, bool]:
    active = subprocess.run(["systemctl", "--user", "is-active", UNIT],
                            capture_output=True, text=True).stdout.strip() == "active"
    running = subprocess.run(["pgrep", "-f", "terminal64.exe"],
                             capture_output=True, text=True).returncode == 0
    return active, running


def restart_unit() -> bool:
    proc = subprocess.run(["systemctl", "--user", "restart", UNIT],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"restart_failed rc={proc.returncode} err={proc.stderr.strip()[:160]}")
        return False
    log("restarted unit")
    return True


def telegram(text: str) -> None:
    env = read_env(ENV_ALERT)
    token = env.get("TELEGRAM_BOT_TOKEN")
    owner = env.get("TELEGRAM_OWNER_ID")
    if not token or not owner:
        log("alert_skipped no_credentials")
        return
    data = json.dumps({"chat_id": owner, "text": text,
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=8).read()
    except (urllib.error.URLError, OSError) as exc:
        log(f"alert_failed {type(exc).__name__}")


def main() -> int:
    state = load_state()
    now = time.time()

    if not api_healthy():
        log("skip api_unhealthy")
        return 0

    age = ea_age_s()
    if age is None:
        log("skip unknown_age")
        return 0

    if age <= STALE_S:
        if state.get("strikes") or state.get("escalated_at"):
            log(f"healthy age={age:.0f}s reset_state")
        state.update({"strikes": 0, "escalated_at": None})
        save_state(state)
        return 0

    strikes = int(state.get("strikes", 0)) + 1
    state["strikes"] = strikes
    state["last_age_s"] = round(age)

    restarts = [t for t in state.get("restarts", []) if now - t < 3600]
    state["restarts"] = restarts
    last_restart = float(state.get("last_restart", 0))

    if strikes < STRIKES_TO_RESTART:
        save_state(state)
        log(f"stale age={age:.0f}s strike={strikes}/{STRIKES_TO_RESTART}")
        return 0

    recovered_wait = last_restart and (now - last_restart) < RECOVER_S
    if recovered_wait:
        save_state(state)
        log(f"stale age={age:.0f}s waiting_recovery {now - last_restart:.0f}s")
        return 0

    too_soon = last_restart and (now - last_restart) < MIN_GAP_S
    too_many = len(restarts) >= MAX_PER_HOUR
    if too_soon or too_many:
        escalated = state.get("escalated_at") or 0
        if now - float(escalated) > ESCALATE_DEDUP_S:
            reason = "jeda minimum" if too_soon else "batas 3x/jam"
            telegram(
                "MT5 GUARD: EA telat "
                f"{age/60:.0f} menit, restart ditahan ({reason}). "
                "Perlu cek manual: systemctl --user status " + UNIT
            )
            state["escalated_at"] = now
            log("escalated")
        save_state(state)
        return 0

    active, running = unit_state()
    if not active:
        log("unit_inactive start")
        restart_unit()
    elif not running:
        log("terminal_missing restart")
        restart_unit()
    else:
        log("ea_hung restart")
        restart_unit()

    state["restarts"] = restarts + [now]
    state["last_restart"] = now
    state["strikes"] = 0
    state["escalated_at"] = None
    save_state(state)
    telegram(
        "MT5 GUARD: EA tidak heartbeat "
        f"{age/60:.0f} menit -> unit {UNIT} direstart otomatis. "
        "EA self-heal ~2 menit."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - guard tidak boleh mati diam
        log(f"fatal {type(exc).__name__}: {exc}")
        sys.exit(0)
