"""Level Fibonacci (retracement + extension) untuk tool chart (RISK-C, t_00db2872).

Modul MURNI matematika: tidak mengimpor db, order, risk gate, kill-switch,
maupun modul eksekusi. Level fib adalah ALAT BANTU visual/konteks; tidak ada
kode di sini yang boleh mengubah keputusan trading.

Konvensi (penting, dipakai UI + konteks LLM):

- Swing didefinisikan dua harga: ``swing_low`` < ``swing_high`` (range = high-low)
  dan ``direction`` = arah tren yang diukur ("UP" bila swing naik low->high,
  "DOWN" bila swing turun high->low).
- Retracement ``r`` (0.236 / 0.382 / 0.5 / 0.618 / 0.786) adalah fraksi
  MUNDUR dari ujung swing:
    UP   : price = high - range * r      (mis. 0.618 -> 61.8% pullback dari high)
    DOWN : price = low  + range * r      (mis. 0.618 -> 61.8% pullback dari low)
- Extension ``x`` (1.272 / 1.618 / 2.618) adalah kelanjutan melewati ujung swing
  sebesar (x - 1) x range:
    UP   : price = low + range * x       (mis. 1.618 -> high + 61.8% range)
    DOWN : price = high - range * x      (mis. 1.618 -> low - 61.8% range)

Contoh angka (dipakai di test): low=2000, high=2100, range=100.
  UP   : 0.618 = 2038.20 | 1.272 = 2127.20 | 1.618 = 2161.80 | 2.618 = 2261.80
  DOWN : 0.618 = 2061.80 | 1.272 = 1972.80 | 1.618 = 1938.20 | 2.618 = 1838.20

Angka level dibulatkan ke ``digits`` desimal (default 2, diturunkan dari
tick_size simbol; XAUUSD/BTCUSD = 0.01 -> 2). Pembulatan hanya untuk tampilan
dan penyimpanan; nilai yang dipakai UI adalah nilai yang sama yang disimpan
di DB, jadi tidak ada selisih antara preview dan level tersimpan.
"""
from __future__ import annotations

import math

#: Level retracement standar (fraksi mundur dari ujung swing).
RETRACEMENT_RATIOS: tuple[float, ...] = (0.236, 0.382, 0.5, 0.618, 0.786)

#: Level extension standar; 1.272/1.618/2.618 juga acuan tangga TP1/TP2/TP3.
EXTENSION_RATIOS: tuple[float, ...] = (1.272, 1.618, 2.618)

DIRECTIONS: tuple[str, ...] = ("UP", "DOWN")

#: Batas kewarasan harga (kolom harga DB NUMERIC(14,5)); di luar ini tolak.
PRICE_MIN = 0.00001
PRICE_MAX = 9_999_999.99999

DEFAULT_DIGITS = 2


class FibLevelError(ValueError):
    """Input swing/direction tidak valid (dipakai route -> HTTP 400)."""


def _as_price(name: str, value: object) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise FibLevelError(f"{name} harus angka") from None
    if not math.isfinite(out):
        raise FibLevelError(f"{name} harus angka berhingga")
    if out < PRICE_MIN or out > PRICE_MAX:
        raise FibLevelError(f"{name} di luar batas {PRICE_MIN}..{PRICE_MAX}")
    return out


def normalize_direction(direction: object) -> str:
    """'up'/'UP' -> 'UP'; selain itu FibLevelError."""
    text = str(direction or "").strip().upper()
    if text not in DIRECTIONS:
        raise FibLevelError("direction harus 'UP' atau 'DOWN'")
    return text


def normalize_digits(digits: object) -> int:
    try:
        out = int(digits)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise FibLevelError("digits harus bilangan bulat 0..8") from None
    if out < 0 or out > 8:
        raise FibLevelError("digits harus bilangan bulat 0..8")
    return out


def validate_swing(swing_low: object, swing_high: object) -> tuple[float, float]:
    """Validasi + kembalikan (low, high) sebagai float. low < high wajib."""
    low = _as_price("swing_low", swing_low)
    high = _as_price("swing_high", swing_high)
    if not high > low:
        raise FibLevelError("swing_high harus lebih besar dari swing_low")
    return low, high


def compute_levels(swing_low: object, swing_high: object, direction: object,
                   digits: int = DEFAULT_DIGITS) -> list[dict]:
    """Level retracement lalu extension, urut tetap (deterministik).

    Return list of ``{"ratio": float, "kind": "retracement"|"extension",
    "price": float}``. Tidak ada I/O; hasil hanya bergantung pada argumen.
    """
    low, high = validate_swing(swing_low, swing_high)
    trend = normalize_direction(direction)
    nd = normalize_digits(digits)
    span = high - low
    levels: list[dict] = []
    for ratio in RETRACEMENT_RATIOS:
        price = high - span * ratio if trend == "UP" else low + span * ratio
        levels.append({"ratio": ratio, "kind": "retracement",
                       "price": round(price, nd)})
    for ratio in EXTENSION_RATIOS:
        price = low + span * ratio if trend == "UP" else high - span * ratio
        levels.append({"ratio": ratio, "kind": "extension",
                       "price": round(price, nd)})
    return levels


def symbol_digits(symbol: str, settings: dict | None) -> int:
    """Desimal dari ``settings['symbol_specs'][symbol]['tick_size']``.

    Fallback 2 (XAUUSD/BTCUSD) bila spec tidak ada/tidak terbaca; tidak pernah
    melempar exception supaya tool chart tetap jalan saat settings aneh.
    """
    specs = (settings or {}).get("symbol_specs") or {}
    spec = specs.get(symbol) or {}
    raw_tick = spec.get("tick_size")
    if raw_tick is None:
        return DEFAULT_DIGITS
    try:
        tick = float(raw_tick)
    except (TypeError, ValueError):
        return DEFAULT_DIGITS
    if not math.isfinite(tick) or tick <= 0:
        return DEFAULT_DIGITS
    digits = -math.log10(tick)
    return max(0, min(8, int(round(digits))))
