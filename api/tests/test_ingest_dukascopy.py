"""Unit test decoder & agregasi Dukascopy (t_3c65f152) - tanpa network."""
from datetime import datetime, timezone

from ingest.dukascopy_client import (day_bytes_to_m1, day_path, day_range,
                                     hour_path, hour_range, ticks_to_m1)


def _tick(ms, ask, bid, av, bv):
    import struct
    return struct.pack(">iiiff", ms, ask, bid, av, bv)


def test_ticks_to_m1_ohlv():
    h0 = int(datetime(2025, 6, 16, 5, tzinfo=timezone.utc).timestamp())
    raw = (_tick(0, 100_000, 99_900, 1.0, 2.0)       # 05:00:00 bid 99.9
           + _tick(30_000, 100_500, 100_100, 1.0, 1.5)  # 05:00:30 bid 100.1
           + _tick(59_000, 99_800, 99_700, 1.0, 0.5)    # 05:00:59 bid 99.7
           + _tick(61_000, 100_200, 100_000, 1.0, 3.0))  # 05:01:01 bid 100.0
    bars = ticks_to_m1(h0, raw, div=1000.0)
    assert len(bars) == 2
    b0, b1 = bars
    assert b0["ts"] == datetime(2025, 6, 16, 5, 0, tzinfo=timezone.utc)
    assert (b0["open"], b0["high"], b0["low"], b0["close"]) == (
        99.9, 100.1, 99.7, 99.7)
    assert b0["volume"] == 4.0  # sum bid_vol
    assert b1["ts"] == datetime(2025, 6, 16, 5, 1, tzinfo=timezone.utc)
    assert (b1["open"], b1["close"], b1["volume"]) == (100.0, 100.0, 3.0)


def test_day_bytes_to_m1():
    import struct
    d0 = int(datetime(2025, 6, 16, tzinfo=timezone.utc).timestamp())
    rec = struct.pack(">iiiiif", 60, 100_000, 100_400, 99_900, 100_300, 7.5)
    bars = day_bytes_to_m1(d0, rec, div=1000.0)
    assert len(bars) == 1
    b = bars[0]
    assert b["ts"] == datetime(2025, 6, 16, 0, 1, tzinfo=timezone.utc)
    assert (b["open"], b["high"], b["low"], b["close"]) == (
        100.0, 100.3, 99.9, 100.4)
    assert b["volume"] == 7.5


def test_path_bulan_0indexed():
    jan = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    assert hour_path("BTCUSD", jan) == "/datafeed/BTCUSD/2024/0/1/0h_ticks.bi5"
    assert day_path("XAUUSD", jan) == "/datafeed/XAUUSD/2024/0/1/BID_candles_min_1.bi5"
    des = int(datetime(2025, 12, 31, 23, tzinfo=timezone.utc).timestamp())
    assert hour_path("BTCUSD", des) == "/datafeed/BTCUSD/2025/11/31/23h_ticks.bi5"


def test_ranges_selaras_batas():
    s = datetime(2024, 11, 24, 0, 30, tzinfo=timezone.utc)
    e = datetime(2024, 11, 24, 3, 10, tzinfo=timezone.utc)
    hours = list(hour_range(s, e))
    assert len(hours) == 3  # 00, 01, 02 UTC
    # end eksklusif di batas hari: sama hari -> 0; lintas tengah malam -> 1
    assert list(day_range(s, e)) == []
    days = list(day_range(s, datetime(2024, 11, 25, 3, tzinfo=timezone.utc)))
    assert len(days) == 1
    assert datetime.fromtimestamp(days[0], tz=timezone.utc).minute == 0
