"""Layer 0: fakta deterministik untuk specialist + synthesizer (t_2a1fbf01).

Tanpa LLM, tanpa I/O: hanya aritmetika dari konteks yang sudah dikumpulkan
`llm_agent_loop._collect_context` (+ portofolio dari `_collect_portfolio`).
Kontrak: modul ini TIDAK PERNAH raise; data kurang = `insufficient_data`/null,
bukan angka karangan (aturan jujur kartu).

Yang dihitung: EMA20/50/200 + slope, RSI14, ATR14 (+ atr_pct), range, susunan
EMA, ringkasan bar terakhir per timeframe; diteruskan apa adanya: struktur
swing/S-R multi-tf (`market_structure`), likuiditas, level fib user, dan posisi.
"""
from __future__ import annotations

from datetime import datetime, timezone

FACTS_VERSION = "1.0.0"

TF_ORDER: tuple[str, ...] = ("M5", "M15", "H1", "H4")
RECENT_BARS: dict[str, int] = {"M5": 6, "M15": 6, "H1": 5, "H4": 4}
EMA_PERIODS: tuple[int, ...] = (20, 50, 200)
RSI_PERIOD = 14
ATR_PERIOD = 14
# Ambang spread relatif terhadap ATR M5 (dipakai juga oleh sanitizer portofolio
# untuk memangkas volume, jadi satu konstanta di sini = satu kebenaran).
SPREAD_ATR_THRESHOLD = 0.2


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        out = round(float(value), digits)
    except (TypeError, ValueError):
        return None
    return out


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def ema(values: list[float], period: int) -> float | None:
    """EMA terakhir; None bila data kurang (bukan memperkirakan)."""
    if len(values) < period or period <= 0:
        return None
    k = 2.0 / (period + 1.0)
    acc = sum(values[:period]) / period
    for value in values[period:]:
        acc = value * k + acc * (1.0 - k)
    return acc


def rsi(values: list[float], period: int = RSI_PERIOD) -> float | None:
    """RSI Wilder sederhana; None bila data kurang."""
    if len(values) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(candles: list[dict], period: int = ATR_PERIOD) -> float | None:
    """ATR Wilder dari true range; None bila candle kurang."""
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        high, low = _num(candles[i].get("high")), _num(candles[i].get("low"))
        prev_close = _num(candles[i - 1].get("close"))
        if high is None or low is None or prev_close is None:
            return None
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    acc = sum(trs[:period]) / period
    for tr in trs[period:]:
        acc = (acc * (period - 1) + tr) / period
    return acc


def ema_stack(emas: dict[str, float | None]) -> str:
    """Label susunan EMA untuk prompt ('unknown' bila salah satu kosong)."""
    fast, mid, slow = emas.get("ema20"), emas.get("ema50"), emas.get("ema200")
    if fast is None or mid is None or slow is None:
        return "unknown"
    if fast > mid > slow:
        return "bullish_stack"
    if fast < mid < slow:
        return "bearish_stack"
    return "mixed"


def timeframe_facts(candles: list[dict], recent_bars: int = 6) -> dict:
    """Ringkasan satu timeframe: indikator + bar terakhir (bukan seluruh history)."""
    rows = [c for c in (candles or []) if isinstance(c, dict)]
    closes = [c for c in (_num(row.get("close")) for row in rows) if c is not None]
    if not closes:
        return {"status": "insufficient_data", "candles": 0}
    emas = {f"ema{period}": _round(ema(closes, period), 2) for period in EMA_PERIODS}
    slope = None
    if len(closes) >= 26:
        older = ema(closes[:-5], 20)
        newer = emas.get("ema20")
        if older and newer and older != 0:
            slope = _round((newer - older) / older * 100.0, 3)
    atr14 = atr(rows, ATR_PERIOD)
    price = closes[-1]
    highs = [v for v in (_num(row.get("high")) for row in rows) if v is not None]
    lows = [v for v in (_num(row.get("low")) for row in rows) if v is not None]
    return {
        "status": "ok",
        "candles": len(rows),
        "close": _round(price, 2),
        "range_high": _round(max(highs), 2) if highs else None,
        "range_low": _round(min(lows), 2) if lows else None,
        **emas,
        "ema20_slope_pct": slope,
        "rsi14": _round(rsi(closes), 2),
        "atr14": _round(atr14, 2),
        "atr_pct": _round(atr14 / price * 100.0, 3) if atr14 and price else None,
        "ema_stack": ema_stack(emas),
        "recent_bars": [
            [row.get("ts"), _round(_num(row.get("open")), 2),
             _round(_num(row.get("high")), 2), _round(_num(row.get("low")), 2),
             _round(_num(row.get("close")), 2)]
            for row in rows[-max(1, recent_bars):]
        ],
    }


def _candle_age_min(rows: list[dict], now: datetime) -> float | None:
    if not rows:
        return None
    ts = rows[-1].get("ts")
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _round(max(0.0, (now - parsed).total_seconds() / 60.0), 2)


def _levels_block(structure: dict, price: float | None, atr5: float | None) -> dict:
    """Level S/R M5 + kandidat SL bersih (buffer ATR) dan RR ke level lawan.

    Alasan: harga yang terjepit dua level membuat LLM menyerah ke side=none
    tanpa SL. Angka di sini deterministik supaya setup breakout punya stop
    yang jelas dan RR bisa dihitung, bukan dikarang.
    """
    out: dict = {"support": None, "resistance": None, "atr_m5": _round(atr5, 4),
                 "buffer": None, "sl_long": None, "sl_short": None,
                 "rr_long": None, "rr_short": None, "band_atr": None,
                 "squeeze": False, "reason": None}
    structure = structure if isinstance(structure, dict) else {}
    m5 = structure.get("M5") if isinstance(structure.get("M5"), dict) else {}
    sr = m5.get("nearest_sr") if isinstance(m5.get("nearest_sr"), dict) else {}
    support, resistance = _num(sr.get("support")), _num(sr.get("resistance"))
    out["support"] = _round(support, 2)
    out["resistance"] = _round(resistance, 2)
    if atr5 and atr5 > 0:
        buffer = round(0.25 * atr5, 2)
        out["buffer"] = buffer
        if support is not None:
            out["sl_long"] = _round(support - buffer, 2)
        if resistance is not None:
            out["sl_short"] = _round(resistance + buffer, 2)
    if price is not None and support is not None and resistance is not None and atr5:
        slot = resistance - support
        out["band_atr"] = _round(slot / atr5, 2)
        long_risk = price - (out["sl_long"] if out["sl_long"] is not None else support)
        short_risk = (out["sl_short"] if out["sl_short"] is not None else resistance) - price
        if long_risk > 0:
            out["rr_long"] = _round((resistance - price) / long_risk, 2) if resistance > price else None
        if short_risk > 0:
            out["rr_short"] = _round((price - support) / short_risk, 2) if support < price else None
        if slot <= 0.75 * atr5:
            out["squeeze"] = True
            out["reason"] = (f"harga terjepit: band S/R {support:.2f}/{resistance:.2f} "
                             f"= {out['band_atr']}x ATR M5 (<= 0.75x)")
    return out


def _spread_block(block: dict, atr5: float | None,
                  threshold: float = SPREAD_ATR_THRESHOLD) -> dict:
    """Spread rata-rata vs ATR M5: rasio di atas ambang memangkas volume.

    `spread_avg` datang dari liquidity_samples (recorder HFM), satu-satunya
    angka spread yang deterministik di konteks. Tanpa ATR, ratio null dan
    `high` false (bukan dianggap aman: pakai flag BLIND_TO_VOLATILITY).
    """
    liq = block.get("liquidity") if isinstance(block.get("liquidity"), dict) else {}
    spread = _num(liq.get("spread_avg"))
    ratio = (spread / atr5) if (spread is not None and atr5 and atr5 > 0) else None
    return {
        "avg": _round(spread, 4),
        "atr_m5": _round(atr5, 4),
        "ratio": _round(ratio, 3),
        "threshold": threshold,
        "high": bool(ratio is not None and ratio > threshold),
        "session": liq.get("session"),
        "window_start": liq.get("window_start"),
    }


def symbol_facts(block: dict, now: datetime) -> dict:
    """Fakta satu simbol dari blok konteks: harga, indikator MTF, struktur, posisi."""
    block = block if isinstance(block, dict) else {}
    raw_candles = block.get("candles")
    candles_by_tf: dict = raw_candles if isinstance(raw_candles, dict) else {}
    timeframes = {
        tf: timeframe_facts(candles_by_tf.get(tf) or [], RECENT_BARS.get(tf, 6))
        for tf in TF_ORDER
    }
    price = None
    for tf in TF_ORDER:
        close = (timeframes.get(tf) or {}).get("close")
        if close is not None:
            price = close
            break
    structure = block.get("market_structure")
    if not isinstance(structure, dict):
        structure = {"status": "unavailable", "reason": "market_structure kosong"}
    atr5 = (timeframes.get("M5") or {}).get("atr14")
    return {
        "status": "ok" if price is not None else "insufficient_data",
        "price": price,
        "candle_age_min": _candle_age_min(candles_by_tf.get("M5") or [], now),
        "timeframes": timeframes,
        "structure": structure,
        "levels": _levels_block(structure, price, atr5),
        "spread": _spread_block(block, atr5),
        "liquidity": block.get("liquidity"),
        "fib_zones": block.get("fib_zones") or [],
        "open_positions": block.get("open_positions") or [],
        "llm_positions": block.get("llm_positions") or [],
    }


def _compact_calendar(calendar) -> dict:
    """Kalender untuk prompt: field yang dipakai specialist, bukan mentah penuh."""
    if not isinstance(calendar, dict):
        return {"status": "unavailable", "reason": "calendar kosong"}
    raw_events = calendar.get("events")
    events: list = raw_events if isinstance(raw_events, list) else []
    return {
        "status": calendar.get("status"),
        "source": calendar.get("source"),
        "as_of": calendar.get("as_of"),
        "next_high_impact_utc": calendar.get("next_high_impact_utc"),
        "minutes_to_next_high_impact": calendar.get("minutes_to_next_high_impact"),
        "events": [
            {"title": e.get("title"), "time_utc": e.get("time_utc"),
             "impact": e.get("impact"), "forecast": e.get("forecast"),
             "previous": e.get("previous")}
            for e in events[:8] if isinstance(e, dict)
        ],
    }


def build_facts(ctx: dict, portfolio: dict | None = None,
                now: datetime | None = None) -> dict:
    """Rakit Layer 0: fakta semua simbol + makro + portofolio. Tidak pernah raise."""
    ctx = ctx if isinstance(ctx, dict) else {}
    now = now or datetime.now(timezone.utc)
    symbols: dict[str, dict] = {}
    for symbol, block in (ctx.get("symbols") or {}).items():
        try:
            symbols[str(symbol)] = symbol_facts(block, now)
        except Exception as exc:  # noqa: BLE001 - fakta tidak boleh mematikan siklus
            symbols[str(symbol)] = {"status": "error",
                                    "reason": f"{type(exc).__name__}: {exc}"[:200]}
    macro = {
        "session": ctx.get("session"),
        "calendar": _compact_calendar(ctx.get("calendar")),
        "fundamental": ctx.get("fundamental"),
        "sentiment": ctx.get("sentiment"),
    }
    return {
        "facts_version": FACTS_VERSION,
        "now_utc": ctx.get("now_utc") or now.isoformat(timespec="seconds"),
        "halted": ctx.get("halted"),
        "symbols": symbols,
        "macro": macro,
        "portfolio": portfolio if isinstance(portfolio, dict) else {},
    }
