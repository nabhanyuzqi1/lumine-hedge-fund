"""Probe strategi: perilaku dipilih via context['behavior'] (fault injection).

Perilaku:
  ok / none : kontrak normal (intent valid / tanpa entry)
  sleep     : hang 120 s          -> wall-clock timeout (parent killpg)
  crash     : SIGKILL diri        -> subprocess crash
  exit      : os._exit(3)         -> subprocess crash
  spin_cpu  : busy loop           -> RLIMIT_CPU (SIGXCPU)
  huge_memory                 -> RLIMIT_AS (MemoryError)
  malformed_str / malformed_list / extra_field -> output tidak sesuai schema
  nan_volume / inf_sl         -> NaN/Inf (PRD 5.2: reject)
  no_sl / zero_volume / wrong_strategy -> kontrak PRD 4.1 dilanggar
  net       : buka koneksi TCP   -> HARUS gagal (socket patch + Landlock)
  secret    : baca file secret    -> HARUS gagal (Landlock deny-all FS)
  env       : assert env tanpa secret, lalu intent valid
"""
from __future__ import annotations

import os
from dataclasses import dataclass

STRATEGY_ID = "sbx_probe"
STRATEGY_VERSION = "0.0.1"

_SECRET_ENV_KEYS = (
    "DATABASE_URL", "POSTGRES_PASSWORD", "PGPASSWORD", "TELEGRAM_BOT_TOKEN",
    "ADMIN_PASSWORD", "BRIDGE_TOKEN",
)


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    volume: float
    sl: float
    tp: float
    strategy: str = STRATEGY_ID
    reason: str = ""
    sl_distance: float = 0.0
    risk_usd: float = 0.0


@dataclass(frozen=True)
class StrategyParams:
    tf_seconds: int = 300
    force_close_utc: int = 22


def _intent(reason: str = "probe", **kw) -> OrderIntent:
    base: dict = dict(symbol="XAUUSD", side="BUY", volume=0.01, sl=1.0, tp=2.0,
                      strategy=STRATEGY_ID, reason=reason)
    base.update(kw)
    return OrderIntent(**base)


def decide(context, params):
    behavior = (context or {}).get("behavior", "none")
    if behavior == "ok":
        tf = getattr(params, "tf_seconds", "?")
        return _intent(reason=f"tf={tf}")
    if behavior == "none":
        return None
    if behavior == "sleep":
        import time
        time.sleep(120)
        return None
    if behavior == "crash":
        import signal
        os.kill(os.getpid(), signal.SIGKILL)
        return None
    if behavior == "exit":
        os._exit(3)
        return None
    if behavior == "spin_cpu":
        while True:
            pass
    if behavior == "huge_memory":
        _ = bytearray(2 * 1024 * 1024 * 1024)  # 2 GB > RLIMIT_AS
        return None
    if behavior == "malformed_str":
        return "not-an-intent"
    if behavior == "malformed_list":
        return [1, 2, 3]
    if behavior == "extra_field":
        return {"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 1.0,
                "tp": 2.0, "strategy": STRATEGY_ID, "junk": "unexpected"}
    if behavior == "nan_volume":
        return _intent(volume=float("nan"))
    if behavior == "inf_sl":
        return _intent(sl=float("inf"))
    if behavior == "no_sl":
        return _intent(sl=None)
    if behavior == "zero_volume":
        return _intent(volume=0)
    if behavior == "negative_volume":
        return _intent(volume=-0.01)
    if behavior == "wrong_strategy":
        return _intent(strategy="other_strategy")
    if behavior == "net":
        import socket
        sock = socket.create_connection(("127.0.0.1", 1), timeout=2)
        sock.close()
        return None
    if behavior == "raw_socket":
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.close()
        return None
    if behavior == "secret":
        path = (context or {}).get("secret_path") or "/etc/passwd"
        with open(path) as fh:  # noqa: PTH123
            fh.read()
        return None
    if behavior == "subprocess_escape":
        import subprocess
        subprocess.run(["/bin/echo", "escape"], check=False, capture_output=True)
        return None
    if behavior == "env":
        leaked = [k for k in _SECRET_ENV_KEYS if os.environ.get(k)]
        if leaked:
            raise AssertionError(f"secrets leaked into sandbox env: {leaked}")
        return _intent(reason="env clean")
    return None
