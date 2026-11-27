"""Test konteks LLM multi-timeframe (t_7c5cc7dc, bagian dari t_2a751a6c).

Cakupan: CANDLE_LIMITS M5/M15/H1/H4 (288/192/120/84, Director: biaya LLM
unlimited), _collect_context mengirim SEMUA timeframe per simbol,
price_now tetap dari close M5 terakhir (fallback TF lain bila M5 kosong),
blok market_structure (swing HH/HL/LH/LL, S/R terdekat per TF + agregat
multi-tf, session range), dan SYSTEM_PROMPT yang menjelaskan konteks baru.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import db, llm_context_extras
from app.llm_agent_loop import (
    CANDLE_LIMITS,
    MAX_TOKENS,
    SYSTEM_PROMPT,
    TF_ORDER,
    _collect_context,
    _market_structure,
    _nearest_sr,
    _session_ranges,
    _structure_label,
    _swing_points,
)


@pytest.fixture(autouse=True)
def _mock_calendar(monkeypatch):
    """Kalender difake ok/tanpa event (pola test_llm_agent_v2.py) supaya
    _collect_context tidak memukul feed kalender live."""

    async def _fake_calendar(now_utc=None):
        return {"status": "ok", "source": "test", "as_of": None, "events": []}

    monkeypatch.setattr(llm_context_extras, "fetch_calendar", _fake_calendar)


# --------------------------------------------------------------- data sintetis
def _mk(ts, close, spread=1.0):
    return {"ts": ts.isoformat(), "open": close, "high": close + spread / 2,
            "low": close - spread / 2, "close": close}


def _trending_zigzag(cycles=4, start=2000.0, leg=5):
    """Zigzag naik: tiap siklus naik +10 (step +2.0) lalu retrace -5
    (step -1.0) -> HH + HL; spread 0 supaya pivot = harga close eksak."""
    candles = []
    ts = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
    price = start
    for _ in range(cycles):
        for _ in range(leg):
            price += 2.0
            candles.append(_mk(ts, price, spread=0.0))
            ts += timedelta(minutes=5)
        for _ in range(leg):
            price -= 1.0
            candles.append(_mk(ts, price, spread=0.0))
            ts += timedelta(minutes=5)
    return candles


async def _insert_candles(conn, symbol, tf, candles):
    for c in candles:
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (symbol, tf, c["ts"], c["open"], c["high"], c["low"], c["close"]),
        )


async def _open_llm_position(conn, ticket):
    """Order strategy 'llm' FILLED + posisi OPEN (pola test_llm_agent_v2.py)."""
    row = await (await conn.execute(
        "INSERT INTO orders (symbol, side, volume, sl, tp, strategy, status) "
        "VALUES ('XAUUSD', 'BUY', 0.10, 1990, 2010, 'llm', 'FILLED') RETURNING id",
    )).fetchone()
    await conn.execute(
        "INSERT INTO positions (ticket, order_id, symbol, side, volume, "
        "open_price, sl, tp, profit, status) "
        "VALUES (%s, %s, 'XAUUSD', 'BUY', 0.10, 2000, 1990, 2010, 0, 'OPEN')",
        (ticket, row["id"]),
    )


# ------------------------------------------------- konstanta multi-timeframe
def test_candle_limits_per_timeframe():
    assert CANDLE_LIMITS == {"M5": 288, "M15": 192, "H1": 120, "H4": 84}
    assert TF_ORDER == ("M5", "M15", "H1", "H4")
    # t_afd7fe4e butir C (menggantikan kelonggaran t_7c5cc7dc): bukti latensi
    # 48,8 s rata-rata / 119,7 s maks dengan completion 3.217-6.804 token
    # membuktikan output panjang inilah biang latensi. Batas 8000 token diganti
    # anggaran per tahap (llm_latency_budget), default jalur satu-prompt 1200.
    assert MAX_TOKENS <= 1500
    assert MAX_TOKENS >= 800  # masih cukup untuk satu OrderIntent + reasoning ringkas


def test_prompt_describes_multi_timeframe_context():
    low = SYSTEM_PROMPT.lower()
    for token in ("m5", "m15", "h1", "h4", "288", "market_structure",
                  "nearest_sr", "sr_nearest_multi_tf", "session_ranges"):
        assert token in low, f"SYSTEM_PROMPT harus menjelaskan {token}"


# ------------------------------------------------------- fungsi struktur pasar
def test_swing_points_detect_pivots():
    pivots = _swing_points(_trending_zigzag(cycles=4))
    highs = [p["price"] for p in pivots if p["kind"] == "high"]
    lows = [p["price"] for p in pivots if p["kind"] == "low"]
    assert highs == [2010.0, 2015.0, 2020.0, 2025.0]
    # Trough terakhir (2020) = candle paling akhir: belum terkonfirmasi
    # (pivot butuh k=2 bar berikutnya) -> sengaja tidak masuk daftar.
    assert lows == [2005.0, 2010.0, 2015.0]


def test_structure_label_bullish_bearish_unknown():
    bull = [{"kind": "high", "price": 2010.0}, {"kind": "high", "price": 2020.0},
            {"kind": "low", "price": 2000.0}, {"kind": "low", "price": 2005.0}]
    assert _structure_label(bull)["trend"] == "bullish"       # HH + HL
    bear = [{"kind": "high", "price": 2020.0}, {"kind": "high", "price": 2010.0},
            {"kind": "low", "price": 2005.0}, {"kind": "low", "price": 1995.0}]
    assert _structure_label(bear)["trend"] == "bearish"       # LH + LL
    assert _structure_label([{"kind": "high", "price": 1.0}])["trend"] == "unknown"


def test_nearest_sr_from_swing_levels():
    candles = _trending_zigzag(cycles=2)   # levels: 2005, 2010, 2015
    assert _nearest_sr(candles, 2012.0) == {"support": 2010.0, "resistance": 2015.0}
    assert _nearest_sr(candles, 2008.0) == {"support": 2005.0, "resistance": 2010.0}
    assert _nearest_sr(candles, 2003.0) == {"support": None, "resistance": 2005.0}
    assert _nearest_sr(candles, 2030.0) == {"support": 2015.0, "resistance": None}


def test_session_ranges_split_on_session_boundary():
    start = datetime(2026, 11, 25, 6, 50, tzinfo=timezone.utc)
    candles = [_mk(start + timedelta(minutes=5 * i), 2000.0 + i) for i in range(25)]
    ranges = _session_ranges(candles)
    assert [r["session"] for r in ranges] == ["asia", "london"]
    assert ranges[0]["candles"] == 2          # 06:50, 06:55 UTC
    assert ranges[1]["candles"] == 23         # 07:00-07:50 UTC
    assert ranges[1]["high"] == 2024.5        # close 2024 + spread 0.5
    assert ranges[0]["low"] == 1999.5


def test_session_ranges_normalizes_non_utc_ts():
    """ts dari DB mengikuti TimeZone koneksi (bisa +07:00): 14:50 WIB =
    07:50 UTC -> london; 21:30 WIB = 14:30 UTC -> london_newyork."""
    wib = timezone(timedelta(hours=7))
    candles = [
        _mk(datetime(2026, 11, 25, 14, 50, tzinfo=wib), 3000.0),
        _mk(datetime(2026, 11, 25, 14, 55, tzinfo=wib), 3001.0),
        _mk(datetime(2026, 11, 25, 21, 30, tzinfo=wib), 3002.0),
    ]
    ranges = _session_ranges(candles)
    assert [r["session"] for r in ranges] == ["london", "london_newyork"]


def test_market_structure_empty_never_raises():
    ms = _market_structure({}, None, datetime.now(timezone.utc))
    assert ms["session_ranges"] == []
    assert ms["M5"] == {"status": "insufficient_data", "candles": 0}


# --------------------------------------------------- konteks dari DB (read-only)
async def test_collect_context_sends_all_timeframes(user):
    """Semua timeframe M5/M15/H1/H4 dikirim per simbol, terpotong limit,
    terurut waktu naik; XAUUSD + BTCUSD sama-sama dapat konteks."""
    async with db.pool().connection() as conn:
        for tf, step, n in (("M5", 5, 300), ("M15", 15, 200),
                            ("H1", 60, 130), ("H4", 240, 90)):
            # Literal di-interpolasi dari konstanta test lokal (bukan input user).
            await conn.execute(
                f"""
                INSERT INTO candles (symbol, timeframe, ts, open, high, low, close)
                SELECT 'XAUUSD', '{tf}', now() - (g || ' minutes')::interval,
                       2000, 2001, 1999, 2000 + g / 1000.0
                FROM generate_series({step}, {n} * {step}, {step}) AS g
                """,
            )
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
                "VALUES ('BTCUSD', %s, now(), 50000, 50001, 49999, 50000)",
                (tf,),
            )
        ctx = await _collect_context(conn)
    block = ctx["symbols"]["XAUUSD"]["candles"]
    assert set(block) == {"M5", "M15", "H1", "H4"}
    assert len(block["M5"]) == 288            # 300 tersedia, dipotong limit
    assert len(block["M15"]) == 192
    assert len(block["H1"]) == 120
    assert len(block["H4"]) == 84
    for tf in TF_ORDER:
        ts_list = [c["ts"] for c in block[tf]]
        assert ts_list == sorted(ts_list), f"{tf} harus terurut waktu naik"
    btc = ctx["symbols"]["BTCUSD"]["candles"]
    assert all(len(btc[tf]) == 1 for tf in TF_ORDER)
    # Struktur pada data flat: tidak ada swing -> unknown, tidak pernah raise.
    ms = ctx["symbols"]["XAUUSD"]["market_structure"]
    assert ms["M5"]["candles"] == 288
    assert ms["M5"]["structure"]["trend"] == "unknown"
    assert ms["session_ranges"]


async def test_collect_context_price_now_from_m5(user):
    """Kompatibilitas perilaku lama: price_now = close M5 terakhir."""
    async with db.pool().connection() as conn:
        await _open_llm_position(conn, 780001)
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
            "VALUES ('XAUUSD', 'M5', now() - interval '5 minutes', "
            "1999, 2001, 1998, 2000.5)",
        )
        ctx = await _collect_context(conn)
    pos = ctx["symbols"]["XAUUSD"]["llm_positions"][0]
    assert pos["price_now"] == 2000.5


async def test_collect_context_price_now_fallback_when_m5_empty(user):
    """M5 kosong -> price_now fallback ke close TF lain (H1), bukan None."""
    async with db.pool().connection() as conn:
        await _open_llm_position(conn, 780002)
        await conn.execute(
            "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close) "
            "VALUES ('XAUUSD', 'H1', now() - interval '60 minutes', "
            "3049, 3051, 3048, 3050.5)",
        )
        ctx = await _collect_context(conn)
    pos = ctx["symbols"]["XAUUSD"]["llm_positions"][0]
    assert pos["price_now"] == 3050.5


async def test_collect_context_market_structure_bullish(user):
    """Zigzag HH+HL -> struktur bullish, S/R multi-tf dan session range terisi."""
    async with db.pool().connection() as conn:
        await _insert_candles(conn, "XAUUSD", "M5", _trending_zigzag(cycles=4))
        ctx = await _collect_context(conn)
    ms = ctx["symbols"]["XAUUSD"]["market_structure"]
    assert ms["M5"]["structure"]["trend"] == "bullish"     # HH + HL
    assert ms["M5"]["candles"] == 40
    assert ms["M15"]["status"] == "insufficient_data"
    # price_now = 2020 (close terakhir); level swing 2005/2010/2015/2020/2025.
    assert ms["M5"]["nearest_sr"] == {"support": 2015.0, "resistance": 2025.0}
    assert ms["sr_nearest_multi_tf"]["support"] == 2015.0
    assert ms["sr_nearest_multi_tf"]["resistance"] == 2025.0
    assert ms["sr_nearest_multi_tf"]["support_timeframe"] == "M5"
    # 40 candle M5 dari 00:00 UTC = 200 menit, semuanya sesi asia.
    assert [r["session"] for r in ms["session_ranges"]] == ["asia"]
    assert ms["session_ranges"][0]["high"] == 2025.0
