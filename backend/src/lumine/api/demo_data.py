# Copyright (c) 2026 Lumine. All rights reserved.
"""Deterministic demo market data shared by REST routers.

Sprint-phase stand-in until Phase 5 storage is wired into the API layer.
Values are stable within a minute bucket so repeated polling looks live
without flickering, and derived deterministically from the symbol so tests
are reproducible.

INSTRUMENTS maps a symbol to a tuple shaped
(base_mid, decimals, description, base_asset, quote_currency).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

INSTRUMENTS: dict[str, tuple[float, int, str, str, str]] = {
    "XAUUSD": (2420.30, 2, "Gold spot", "XAU", "USD"),
    "XAGUSD": (28.42, 3, "Silver spot", "XAG", "USD"),
    "EURUSD": (1.0850, 5, "Euro / US Dollar", "EUR", "USD"),
    "GBPUSD": (1.2702, 5, "Pound / US Dollar", "GBP", "USD"),
    "USOIL": (78.52, 2, "US Crude Oil", "USOIL", "USD"),
    "BTCUSD": (64_000.0, 1, "Bitcoin", "BTC", "USD"),
    "NAS100": (18_500.0, 1, "Nasdaq 100 Index", "NAS100", "USD"),
    "SPX500": (5_300.0, 2, "S&P 500 Index", "SPX500", "USD"),
}

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1_800,
    "1h": 3_600,
    "4h": 14_400,
    "1d": 86_400,
    "1w": 604_800,
}


def _symbol_seed(symbol: str) -> float:
    """Stable per-symbol phase offset in [0, 2π)."""
    total = sum(ord(c) for c in symbol.upper())
    return (total % 360) * math.pi / 180.0


def base_price(symbol: str) -> float:
    """Return the base mid price for a symbol (deterministic fallback)."""
    entry = INSTRUMENTS.get(symbol.upper())
    if entry is not None:
        return entry[0]
    total = sum(ord(c) for c in symbol.upper())
    return round(1.0 + (total % 4000), 4)


def mid_price(symbol: str, at: datetime | None = None) -> float:
    """Return the current demo mid price: base ± minute-bucket wobble."""
    now = at or datetime.now(UTC)
    minutes = int(now.timestamp() // 60)
    base = base_price(symbol)
    wobble = math.sin(minutes / 7.0 + _symbol_seed(symbol)) * base * 0.0012
    return round(base + wobble, 4)


def spread_units(symbol: str) -> float:
    """Demo spread in price units (0.02% of mid, min 0.01)."""
    return max(0.01, round(base_price(symbol) * 0.0002, 4))


def round_price(value: float, symbol: str) -> float:
    """Round a price to the instrument's display precision."""
    _base, decimals, *_ = INSTRUMENTS.get(symbol.upper(), (0.0, 2, "", "", ""))
    return round(value, decimals)


def quote_for(symbol: str, at: datetime | None = None) -> dict[str, object]:
    """Build a MarketQuote-shaped dict for a symbol at a point in time."""
    now = at or datetime.now(UTC)
    mid = mid_price(symbol, now)
    spread = spread_units(symbol)
    base = base_price(symbol)
    return {
        "symbol": symbol.upper(),
        "bid": round_price(mid - spread / 2, symbol),
        "ask": round_price(mid + spread / 2, symbol),
        "mid": round_price(mid, symbol),
        "last": round_price(mid, symbol),
        "volume_24h": round(50_000 + (sum(ord(c) for c in symbol) * 1_000 % 40_000), 2),
        "change_24h": round_price(mid - base, symbol),
        "change_pct_24h": round((mid - base) / base * 100.0, 3),
        "timestamp": now,
    }


def session_at(at: datetime | None = None) -> dict[str, object]:
    """Return the trading session derived from UTC hour (XAUUSD is 23h/5d)."""
    now = at or datetime.now(UTC)
    hour = now.hour
    if 0 <= hour < 7:
        current, next_session = "asian", "european"
    elif 7 <= hour < 13:
        current, next_session = "european", "american"
    elif 13 <= hour < 21:
        current, next_session = "american", "off"
    else:
        current, next_session = "off", "asian"

    boundary_hours = {"asian": 7, "european": 13, "american": 21, "off": 0}
    next_hour = boundary_hours[next_session]
    now_dt = now.replace(minute=0, second=0, microsecond=0)
    next_boundary = now_dt + timedelta(hours=(next_hour - hour) % 24)

    weekend = now.weekday() >= 5
    return {
        "current_session": current,
        "next_session": next_session,
        "time_until_next": max(0, int((next_boundary - now).total_seconds())),
        "is_trading_open": not weekend,
    }


def features_for(symbol: str, at: datetime | None = None) -> dict[str, float]:
    """Deterministic indicator values for a symbol."""
    now = at or datetime.now(UTC)
    seed = _symbol_seed(symbol)
    bucket = int(now.timestamp() // 300)
    jitter = math.sin(bucket / 5.0 + seed)
    mid = mid_price(symbol, now)
    return {
        "rsi_14": round(50 + jitter * 22, 2),
        "ema_20": round(mid * (1 + jitter * 0.001), 2),
        "ema_50": round(mid * (1 + jitter * 0.002), 2),
        "vwap": round(mid * (1 + jitter * 0.0005), 2),
        "atr_14": round(mid * 0.004, 2),
        "bb_upper": round(mid * (1 + jitter * 0.002), 2),
        "bb_lower": round(mid * (1 - jitter * 0.002), 2),
        "macd": round(jitter * mid * 0.0008, 3),
    }
