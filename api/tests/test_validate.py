"""Validasi ingest PRD v2.2 §4.4 (app.validate): tick & candle rusak ditolak
atau ditandai; duplikat teridentifikasi; schema_version tidak didukung
ditolak bridge."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import validate


def _now():
    """Jam nyata: validator membandingkan ts dengan now proses (future/
    freshness), jadi test memakai now dinamis agar tidak stale."""
    return datetime.now(timezone.utc)


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _iso(offset_min: int) -> str:
    """ISO UTC relatif terhadap now (menit)."""
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_min)).isoformat()


# ------------------------------------------------------------------ pure tick
def test_nonpositive_bid_ask_rejected():
    v = validate.TickValidator()
    for bid, ask in [(0, 1.0), (-1.0, 1.0), (1.0, 0), (1.0, -0.1)]:
        issues = v.check_tick("XAUUSD", bid, ask)
        assert "BID_ASK_NONPOSITIVE" in [i.code for i in issues], (bid, ask)
        assert any(i.severity == "REJECT" for i in issues)


def test_ask_below_bid_rejected():
    v = validate.TickValidator()
    issues = v.check_tick("XAUUSD", 2000.5, 2000.2)
    assert "ASK_BELOW_BID" in [i.code for i in issues]


def test_absurd_price_rejected():
    v = validate.TickValidator()
    # XAUUSD band warasan [100, 10000]
    issues = v.check_tick("XAUUSD", 5.0, 5.1)
    assert "PRICE_ABSURD" in [i.code for i in issues]
    issues = v.check_tick("XAUUSD", 99999.0, 100001.0)
    assert "PRICE_ABSURD" in [i.code for i in issues]


def test_backward_timestamp_rejected():
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    # regresi BESAR (> BACKWARD_TOLERANCE_S): tetap REJECT — stream rusak
    issues = v.check_tick("XAUUSD", 2000.1, 2000.4, _ms(now - timedelta(seconds=30)), now=now)
    assert "TS_BACKWARD" in [i.code for i in issues]
    assert any(i.severity == "REJECT" for i in issues)


def test_backward_small_flagged_not_rejected():
    """t_74b1f18f: jitter offset broker ±1 dtk membuat stream EA tidak
    monoton; regresi mundur kecil (<= BACKWARD_TOLERANCE_S) harus diterima
    (FLAG + counter) agar tidak membuang ~10% tick di bawah ratchet."""
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    issues = v.check_tick("XAUUSD", 2000.1, 2000.4, _ms(now - timedelta(seconds=1)), now=now)
    codes = [i.code for i in issues]
    assert "TS_BACKWARD_SMALL" in codes
    assert "TS_BACKWARD" not in codes
    assert not any(i.severity == "REJECT" for i in issues)
    assert v.counters.get("TS_BACKWARD_SMALL") == 1


def test_backward_small_does_not_weaken_stale_guard():
    """Regresi kecil yang ditoleransi tidak boleh membuka celah: tick tua
    tetap TS_STALE FLAG; tick future tetap TS_FUTURE REJECT."""
    v = validate.TickValidator()
    now = _now()
    stale = v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now - timedelta(minutes=5)), now=now)
    asserted = [i.code for i in stale]
    assert "TS_STALE" in asserted
    assert not any(i.severity == "REJECT" for i in stale)
    fut = v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now + timedelta(minutes=10)), now=now)
    assert "TS_FUTURE" in [i.code for i in fut]
    assert any(i.severity == "REJECT" for i in fut)


def test_backward_small_keeps_high_water_mark():
    """Setelah tick regresi-kecil diterima, high-water mark TIDAK mundur:
    tick berikutnya yang masih di bawah mark lama tetap FLAG (bukan reset)."""
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    small = v.check_tick("XAUUSD", 2000.1, 2000.4, _ms(now - timedelta(seconds=1)), now=now)
    assert not any(i.severity == "REJECT" for i in small)
    again = v.check_tick("XAUUSD", 2000.2, 2000.5, _ms(now - timedelta(seconds=2)), now=now)
    codes = [i.code for i in again]
    assert "TS_BACKWARD_SMALL" in codes
    assert not any(i.severity == "REJECT" for i in again)
    snap = v.snapshot()
    # baseline = ts tick pertama (ms), bukan ts tick regresi; bandingkan
    # via ms agar presisi float tidak mengganggu
    assert int(snap["last_tick"]["XAUUSD"]["ts"].timestamp() * 1000) == _ms(now)


def test_backward_boundary_exactly_tolerance():
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    at = v.check_tick("XAUUSD", 2000.1, 2000.4,
                      _ms(now - timedelta(seconds=validate.BACKWARD_TOLERANCE_S)), now=now)
    assert not any(i.severity == "REJECT" for i in at)
    over = v.check_tick("XAUUSD", 2000.2, 2000.5,
                        _ms(now - timedelta(seconds=validate.BACKWARD_TOLERANCE_S + 1)), now=now)
    assert "TS_BACKWARD" in [i.code for i in over]
    assert any(i.severity == "REJECT" for i in over)


def test_future_timestamp_rejected():
    v = validate.TickValidator()
    issues = v.check_tick("XAUUSD", 2000.0, 2000.3,
                          _ms(_now() + timedelta(minutes=10)), now=_now())
    assert "TS_FUTURE" in [i.code for i in issues]


def test_stale_tick_flagged_not_rejected():
    v = validate.TickValidator()
    issues = v.check_tick("XAUUSD", 2000.0, 2000.3,
                          _ms(_now() - timedelta(minutes=5)), now=_now())
    codes = [i.code for i in issues]
    assert "TS_STALE" in codes
    assert "TS_BACKWARD" not in codes
    assert not any(i.severity == "REJECT" for i in issues)


def test_duplicate_tick_identified():
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    issues = v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    assert "DUPLICATE_TICK" in [i.code for i in issues]
    assert v.counters.get("DUPLICATE_TICK") == 1


def test_price_jump_flagged_but_allowed():
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    # lompatan 25% dalam tick berurutan: FLAG, bukan REJECT
    issues = v.check_tick("XAUUSD", 2500.0, 2500.3, _ms(now + timedelta(seconds=1)), now=now)
    codes = [i.code for i in issues]
    assert "PRICE_JUMP" in codes
    assert not any(i.severity == "REJECT" for i in issues)


def test_price_jump_absurd_outside_band_rejected():
    v = validate.TickValidator()
    now = _now()
    v.check_tick("XAUUSD", 2000.0, 2000.3, _ms(now), now=now)
    # luar band absolut: REJECT meski jump guard FLAG
    issues = v.check_tick("XAUUSD", 50000.0, 50000.3, _ms(now + timedelta(seconds=1)), now=now)
    assert "PRICE_ABSURD" in [i.code for i in issues]


# ----------------------------------------------------------------- candle
def test_ohlc_inconsistent_rejected():
    v = validate.TickValidator()
    issues = v.check_candle("XAUUSD", "M1", _iso(-60),
                            2000.0, 1999.0, 2001.0, 2000.5, 10)
    assert "CANDLE_OHLC" in [i.code for i in issues]


def test_candle_nonpositive_rejected():
    v = validate.TickValidator()
    issues = v.check_candle("XAUUSD", "M1", _iso(-60),
                            0.0, 2001.0, 1999.0, 2000.5, 10)
    assert "CANDLE_NONPOSITIVE" in [i.code for i in issues]


def test_candle_negative_volume_rejected():
    v = validate.TickValidator()
    issues = v.check_candle("XAUUSD", "M1", _iso(-60),
                            2000.0, 2001.0, 1999.0, 2000.5, -1)
    assert "CANDLE_VOLUME" in [i.code for i in issues]


def test_candle_future_ts_rejected():
    v = validate.TickValidator()
    issues = v.check_candle("XAUUSD", "M1", _iso(60),
                            2000.0, 2001.0, 1999.0, 2000.5, 10, now=_now())
    assert "TS_FUTURE" in [i.code for i in issues]


def test_candle_out_of_order_flagged_not_rejected():
    """Seed ulang history harus tetap boleh (upsert idempotent):
    candle lama dikirim ulang = FLAG, bukan REJECT."""
    v = validate.TickValidator()
    i1 = v.check_candle("XAUUSD", "M1", _iso(-60),
                        2000.0, 2001.0, 1999.0, 2000.5, 10)
    assert not any(x.severity == "REJECT" for x in i1)
    i2 = v.check_candle("XAUUSD", "M1", _iso(-120),
                        2000.0, 2001.0, 1999.0, 2000.5, 10)
    assert not any(x.severity == "REJECT" for x in i2)


# --------------------------------------------------------------- simbol/skema
def test_symbol_mapping_normalized_flagged():
    v = validate.TickValidator()
    issues = v.check_tick("#XAUUSD.stp", 2000.0, 2000.3)
    assert "SYMBOL_MAPPED" in [i.code for i in issues]
    assert validate.normalize_symbol("#XAUUSD.stp") == "XAUUSD"


def test_unknown_symbol_rejected():
    v = validate.reset_validator()
    issues = v.check_tick("EURUSDXYZ", 1.0, 1.1)
    assert "SYMBOL_UNKNOWN" in [i.code for i in issues]


def test_schema_version_gate():
    assert validate.schema_version_supported(None)
    assert validate.schema_version_supported("v5")
    assert validate.schema_version_supported("v0")
    assert not validate.schema_version_supported("v99")


def test_validator_counters_snapshot():
    v = validate.reset_validator()
    v.check_tick("XAUUSD", 0.0, 0.0)          # reject
    v.check_tick("XAUUSD", 2000.0, 2000.3)    # ok
    snap = v.snapshot()
    assert snap["counters"].get("BID_ASK_NONPOSITIVE") == 1
    assert "XAUUSD" in snap["known_symbols"]
