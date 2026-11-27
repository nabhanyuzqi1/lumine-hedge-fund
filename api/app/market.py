"""In-memory latest market tick store (source: EA via /bridge/tick)."""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_latest: dict[str, dict] = {}


def update_tick(symbol: str, bid: float, ask: float, exchange_ts=None,
                trade_enabled: bool | None = None) -> dict:
    """Simpan tick terakhir satu simbol.

    `trade_enabled` (opsional, t_afd7fe4e): status trading-enabled simbol
    menurut EA. EA v5 belum mengirimnya (None = belum dilaporkan); pre-flight
    gate memakai nilai ini bila ada, dan jatuh ke bukti tick bila tidak ada.
    Nilai None TIDAK menimpa laporan sebelumnya yang True/False.
    """
    tick = {
        "symbol": symbol,
        "bid": float(bid),
        "ask": float(ask),
        "spread": round(float(ask) - float(bid), 5),
        "ts": time.time(),
        "exchange_ts": exchange_ts,
        "trade_enabled": trade_enabled,
    }
    with _lock:
        prev = _latest.get(symbol)
        if trade_enabled is None and prev and prev.get("trade_enabled") is not None:
            tick["trade_enabled"] = prev["trade_enabled"]
        _latest[symbol] = tick
    return tick


def latest(symbol: str) -> dict | None:
    with _lock:
        tick = _latest.get(symbol)
        return dict(tick) if tick else None
