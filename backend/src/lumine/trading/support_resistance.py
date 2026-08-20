"""Support/Resistance multi-timeframe (19 Aug 2026 — A4).

Lumine sebelumnya TIDAK mengirim S/R ke analyst — hanya indikator
(EMA/ATR/RSI). Trader profesional selalu punya map S/R (minor/major +
multi-TF). Modul ini menghitung:

- Classic pivot (H+L+C)/3 + R1/R2/S1/S2
- Swing highs/lows: minor (window 10) & major (window 50)
- Nearest support / resistance terhadap harga terakhir
- Multi-TF konsolidasi: level yang muncul di >=2 timeframe ditandai `strong`
"""

from __future__ import annotations

from typing import Any


def _pivot_prices(bars: list[dict[str, Any]]) -> dict[str, float] | None:
    if len(bars) < 1:
        return None
    last = bars[-1]
    h, low_v, c = float(last["high"]), float(last["low"]), float(last["close"])
    p = (h + low_v + c) / 3.0
    return {
        "pivot": round(p, 5),
        "r1": round(2 * p - low_v, 5),
        "s1": round(2 * p - h, 5),
        "r2": round(p + (h - low_v), 5),
        "s2": round(p - (h - low_v), 5),
    }


def _swing_levels(bars: list[dict[str, Any]], window: int) -> tuple[list[float], list[float]]:
    """Swing high/low sederhana: bar yang lebih tinggi/rendah dari `window`

    bar di kiri-kanannya. Kembali (resistances, supports) terurut desc.
    """
    highs: list[float] = []
    lows: list[float] = []
    n = len(bars)
    for i in range(window, n - window):
        h = float(bars[i]["high"])
        low_v = float(bars[i]["low"])
        if all(h >= float(bars[j]["high"]) for j in range(i - window, i + window + 1) if j != i):
            highs.append(h)
        if all(low_v <= float(bars[j]["low"]) for j in range(i - window, i + window + 1) if j != i):
            lows.append(low_v)
    # Dedupe dekat (0.05% tolerance) + sort
    def _dedupe(vals: list[float], reverse: bool) -> list[float]:
        vals = sorted(vals, reverse=reverse)
        out: list[float] = []
        for v in vals:
            if not out or abs(v - out[-1]) / (out[-1] or 1) > 0.0005:
                out.append(v)
        return out

    return _dedupe(highs, reverse=True), _dedupe(lows, reverse=False)


def compute_sr(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """S/R untuk SATU timeframe (bars asc by ts)."""
    if len(bars) < 12:
        return {"levels": [], "nearest_support": None, "nearest_resistance": None, "pivot": None}
    pivot = _pivot_prices(bars)
    major_res, major_sup = _swing_levels(bars, window=5)
    minor_res, minor_sup = _swing_levels(bars, window=2)
    last = float(bars[-1]["close"])

    nearest_sup = None
    for s in minor_sup + major_sup:
        if s < last and (nearest_sup is None or s > nearest_sup):
            nearest_sup = round(s, 5)
    nearest_res = None
    for r in minor_res + major_res:
        if r > last and (nearest_res is None or r < nearest_res):
            nearest_res = round(r, 5)

    levels: list[dict[str, Any]] = []
    for r in major_res[:3]:
        levels.append({"type": "resistance", "kind": "major", "price": round(r, 5)})
    for r in minor_res[:3]:
        levels.append({"type": "resistance", "kind": "minor", "price": round(r, 5)})
    for s in major_sup[:3]:
        levels.append({"type": "support", "kind": "major", "price": round(s, 5)})
    for s in minor_sup[:3]:
        levels.append({"type": "support", "kind": "minor", "price": round(s, 5)})

    return {
        "levels": levels,
        "nearest_support": nearest_sup,
        "nearest_resistance": nearest_res,
        "pivot": pivot,
    }


def compute_multi_tf(bar_sets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """S/R per timeframe + konsolidasi multi-TF (level kuat muncul >=2 TF)."""
    per_tf: dict[str, dict[str, Any]] = {}
    all_res: dict[float, int] = {}
    all_sup: dict[float, int] = {}
    for tf, bars in bar_sets.items():
        if not bars:
            continue
        sr = compute_sr(bars)
        per_tf[tf] = sr
        seen_res: set[float] = set()
        seen_sup: set[float] = set()
        for lv in sr["levels"]:
            px = lv["price"]
            if lv["type"] == "resistance" and px not in seen_res:
                seen_res.add(px)
                all_res[px] = all_res.get(px, 0) + 1
            elif lv["type"] == "support" and px not in seen_sup:
                seen_sup.add(px)
                all_sup[px] = all_sup.get(px, 0) + 1

    strong_res = sorted([p for p, n in all_res.items() if n >= 2], reverse=True)[:3]
    strong_sup = sorted([p for p, n in all_sup.items() if n >= 2])[:3]

    return {
        "per_timeframe": per_tf,
        "strong_resistance": strong_res,
        "strong_support": strong_sup,
        "summary": (
            f"strong_res={strong_res} strong_sup={strong_sup} "
            f"tf={list(per_tf.keys())}"
        ),
    }
