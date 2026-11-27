"""Normalisasi SL/TP sebelum order dikirim ke gate.

Konteks cacat (audit 26 Nov 2026): LLM beberapa kali mengirim SL/TP yang tidak
masuk akal untuk harga saat itu (XAUUSD di 3577 dengan sl=2640 tp=2650, TP
sama dengan SL, atau R:R 0.14). Gate deterministik memang menolaknya, tetapi
penolakan itu terjadi setelah 4 specialist + synthesizer dibayar, dan alasan
tolaknya tidak pernah sampai kembali ke prompt siklus berikutnya.

Modul ini murni (tanpa DB, tanpa I/O) dan dipakai dua tempat:
- agent loop, sebagai lapisan sebelum POST /orders (mencegah, bukan menolak);
- unit test, sebagai kontrak yang bisa dibuktikan.

Aturan yang diberlakukan:
1. sisi benar: BUY sl < price < tp, SELL sl > price > tp;
2. jarak SL dikurung: min = max(2 x spread, min_sl_atr x ATR M5),
   max = max_sl_atr x ATR acuan (H1 bila ada, kalau tidak M5);
3. TP tidak boleh kosong: bila LLM mengirim null, TP dihitung pada R:R
   minimal dari SL yang sudah dinormalisasi;
4. R:R di bawah minimum diperbaiki dengan memindah TP (bukan SL), supaya
   risiko per trade tidak membesar;
5. semua harga dibulatkan ke tick simbol.
"""

from __future__ import annotations

from typing import Any, Iterable

MIN_RR_DEFAULT = 1.5
MAX_SL_ATR_DEFAULT = 3.0
MIN_SL_ATR_DEFAULT = 1.5   # sejalan dengan aturan prompt: >=1.5x ATR M5

# Tick size per simbol (harga dua desimal untuk keduanya).
TICK = {"XAUUSD": 0.01, "BTCUSD": 0.01}


class StopPlanError(ValueError):
    """SL/TP tidak bisa dinormalisasi menjadi order yang masuk akal."""


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _round_to(value: float, tick: float) -> float:
    if not tick or tick <= 0:
        return round(value, 2)
    return round(round(value / tick) * tick, 10)


def _levels_under(levels: Iterable, price: float) -> list[float]:
    out = [_f(lv) for lv in (levels or [])]
    return sorted({lv for lv in out if lv is not None and lv < price}, reverse=True)


def _levels_over(levels: Iterable, price: float) -> list[float]:
    out = [_f(lv) for lv in (levels or [])]
    return sorted({lv for lv in out if lv is not None and lv > price})


def plan_stops(
    *,
    symbol: str,
    side: str,
    price: float | None,
    sl: Any = None,
    tp: Any = None,
    tick: float | None = None,
    atr_m5: float | None = None,
    atr_ref: float | None = None,
    spread: float | None = None,
    supports: Iterable | None = None,
    resistances: Iterable | None = None,
    min_rr: float = MIN_RR_DEFAULT,
    min_sl_atr: float = MIN_SL_ATR_DEFAULT,
    max_sl_atr: float = MAX_SL_ATR_DEFAULT,
) -> dict:
    """Return {"sl","tp","adjusted","notes"} atau raise StopPlanError.

    ``adjusted`` berisi nama field yang diubah, ``notes`` alasannya. Pemanggil
    wajib mencatat keduanya: perubahan harga SL diam-diam adalah cacat audit.
    """
    sym = (symbol or "").strip().upper()
    side_u = (side or "").strip().upper()
    px = _f(price)
    if side_u not in ("BUY", "SELL"):
        raise StopPlanError(f"side tidak dikenal: {side!r}")
    if px is None or px <= 0:
        raise StopPlanError(f"harga acuan tidak valid: {price!r}")
    tick_size = _f(tick) or TICK.get(sym) or 0.01
    m5 = _f(atr_m5)
    ref = _f(atr_ref) or m5
    if not m5 or m5 <= 0:
        raise StopPlanError(
            f"ATR M5 tidak tersedia untuk {sym}; SL/TP tidak bisa dinormalisasi")
    if not ref or ref <= 0:
        ref = m5

    notes: list[str] = []
    adjusted: list[str] = []
    is_buy = side_u == "BUY"

    # --- batas jarak SL -----------------------------------------------------
    min_dist = max(min_sl_atr * m5, 2.0 * (spread or 0.0), 5.0 * tick_size)
    max_dist = max(max_sl_atr * ref, min_dist * 1.2)

    raw_sl = _f(sl)
    sl_ok = raw_sl is not None and (
        (is_buy and raw_sl < px) or (not is_buy and raw_sl > px))
    if raw_sl is not None and not sl_ok:
        notes.append(
            f"SL {raw_sl} di sisi yang salah untuk {side_u} di harga {px}")
        raw_sl = None

    if raw_sl is None:
        anchor = m5 if not (supports or resistances) else None
        if is_buy:
            pool = [lv for lv in _levels_under(supports, px) if px - lv <= max_dist]
            base = pool[0] if pool else px - max(anchor or m5, min_dist)
        else:
            pool = [lv for lv in _levels_over(resistances, px) if lv - px <= max_dist]
            base = pool[0] if pool else px + max(anchor or m5, min_dist)
        sl_val = base - min_dist * 0.25 if is_buy else base + min_dist * 0.25
        notes.append("SL dihitung dari struktur/ATR karena kosong atau salah sisi")
        adjusted.append("sl")
    else:
        sl_val = raw_sl

    dist = abs(px - sl_val)
    if dist < min_dist:
        sl_val = px - min_dist if is_buy else px + min_dist
        notes.append(f"SL terlalu dekat ({dist:.2f} < {min_dist:.2f}); dijauhkan")
        adjusted.append("sl")
    elif dist > max_dist:
        sl_val = px - max_dist if is_buy else px + max_dist
        notes.append(f"SL terlalu jauh ({dist:.2f} > {max_dist:.2f}); didekatkan")
        adjusted.append("sl")
    dist = abs(px - sl_val)
    if dist <= tick_size:
        raise StopPlanError("jarak SL nol setelah normalisasi")

    # --- TP ---------------------------------------------------------------
    raw_tp = _f(tp)
    tp_ok = raw_tp is not None and (
        (is_buy and raw_tp > px) or (not is_buy and raw_tp < px))
    if raw_tp is not None and not tp_ok:
        notes.append(
            f"TP {raw_tp} di sisi yang salah untuk {side_u} di harga {px}")
        raw_tp = None
    if raw_tp is not None and abs(raw_tp - sl_val) <= tick_size:
        notes.append("TP sama dengan SL (order tanpa target); TP dihitung ulang")
        raw_tp = None

    if raw_tp is None:
        pool = [lv for lv in (_levels_over(resistances, px) if is_buy
                              else _levels_under(supports, px))]
        want = min_rr * dist
        pick = next((lv for lv in pool if abs(lv - px) >= want), None)
        tp_val = pick if pick is not None else (
            px + want if is_buy else px - want)
        notes.append(f"TP kosong/tidak sah; dihitung pada R:R {min_rr:.1f}")
        adjusted.append("tp")
    else:
        tp_val = raw_tp

    risk = abs(px - sl_val)
    reward = abs(tp_val - px)
    if risk > 0 and reward / risk < min_rr - 1e-9:
        pool = [lv for lv in (_levels_over(resistances, px) if is_buy
                              else _levels_under(supports, px))]
        want = min_rr * risk
        pick = next((lv for lv in pool if abs(lv - px) >= want), None)
        tp_val = pick if pick is not None else (
            px + want if is_buy else px - want)
        notes.append(
            f"R:R {reward / risk:.2f} < {min_rr:.1f}; TP digeser, SL tidak diubah")
        if "tp" not in adjusted:
            adjusted.append("tp")

    sl_val = _round_to(sl_val, tick_size)
    tp_val = _round_to(tp_val, tick_size)
    if (is_buy and not (sl_val < px < tp_val)) or (
            not is_buy and not (sl_val > px > tp_val)):
        raise StopPlanError(
            f"hasil normalisasi tidak konsisten: {side_u} price={px} sl={sl_val} tp={tp_val}")
    rr_final = abs(tp_val - px) / abs(px - sl_val)
    return {
        "sl": sl_val,
        "tp": tp_val,
        "rr": round(rr_final, 3),
        "sl_distance": round(abs(px - sl_val), 5),
        "adjusted": adjusted,
        "notes": notes,
    }
