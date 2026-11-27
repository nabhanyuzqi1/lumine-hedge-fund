"""paper.feed: parsing tick HFM (EA v5 epoch ms & EA v0 string) dan offset broker.

Insiden t_86507d65: EA v5 kirim exchange_ts sebagai epoch ms (TimeGMT),
sedangkan feed.read_ticks hanya mem-parsing string jam broker — akibatnya
semua tick EA v5 dilewati dan paper runner diam ("idle: no ticks") meski
tick mengalir. Offset terukur dari tick TimeGMT juga ~0 (bukan jam wall
broker) sehingga harus jatuh ke asumsi A1' (UTC+7, terukur 2026-11-22).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from paper import feed

DAY = datetime(2026, 11, 22, tzinfo=timezone.utc).date()


def _write_ticks(dir_path, rows):
    path = dir_path / "log" / f"ticks_{DAY.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_read_ticks_parses_ea_v5_epoch_ms(tmp_path, monkeypatch):
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    now = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    _write_ticks(tmp_path, [
        {"ts_utc": "2026-11-22T15:59:59.500Z", "exchange_ts": _epoch_ms(now - timedelta(seconds=1)),
         "symbol": "XAUUSD", "bid": 3537.4, "ask": 3537.9, "spread": 0.5},
        {"ts_utc": "2026-11-22T16:00:00.500Z", "exchange_ts": _epoch_ms(now),
         "symbol": "XAUUSD", "bid": 3537.5, "ask": 3538.0, "spread": 0.5},
    ])
    ticks = feed.read_ticks(16, now)
    assert len(ticks) == 2
    assert ticks[-1]["exchange_ts"] == now
    assert ticks[-1]["bid"] == 3537.5


def test_read_ticks_still_parses_ea_v0_broker_string(tmp_path, monkeypatch):
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    now = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    _write_ticks(tmp_path, [
        {"ts_utc": "2026-11-22T16:00:00.500Z", "exchange_ts": "2026.11.22 18:00:00",
         "symbol": "XAUUSD", "bid": 3537.5, "ask": 3538.0, "spread": 0.5},
    ])
    ticks = feed.read_ticks(16, now)
    assert len(ticks) == 1
    # string jam broker (UTC+2) di-parse sebagai jam wall, bukan true UTC
    assert ticks[0]["exchange_ts"] == datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)


def test_read_ticks_skips_invalid_exchange_ts(tmp_path, monkeypatch):
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    now = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    _write_ticks(tmp_path, [
        {"ts_utc": "2026-11-22T16:00:00.500Z", "exchange_ts": None,
         "symbol": "XAUUSD", "bid": 3537.5, "ask": 3538.0, "spread": 0.5},
    ])
    assert feed.read_ticks(16, now) == []


def test_read_ticks_filters_by_symbol(tmp_path, monkeypatch):
    """Regresi insiden t_86507d65: log tick berisi XAUUSD (beku akhir
    pekan) + BTCUSD (crypto 24/7 bergerak). Pemakai keputusan wajib
    memfilter simbol, kalau tidak market dianggap selalu buka dan tick
    konteks bisa berasal dari simbol lain."""
    monkeypatch.setattr(feed, "HFM_DIR", tmp_path)
    now = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    _write_ticks(tmp_path, [
        {"ts_utc": "2026-11-22T15:59:59.500Z", "exchange_ts": _epoch_ms(now - timedelta(seconds=1)),
         "symbol": "XAUUSD", "bid": 3537.47, "ask": 3537.90, "spread": 0.43},
        {"ts_utc": "2026-11-22T16:00:00.100Z", "exchange_ts": _epoch_ms(now) + 100,
         "symbol": "BTCUSD", "bid": 60800.0, "ask": 60840.0, "spread": 40.0},
        {"ts_utc": "2026-11-22T16:00:00.200Z", "exchange_ts": _epoch_ms(now) + 200,
         "symbol": "BTCUSD", "bid": 60801.0, "ask": 60841.0, "spread": 40.0},
        {"ts_utc": "2026-11-22T16:00:00.300Z", "exchange_ts": _epoch_ms(now) + 300,
         "symbol": "BTCUSD", "bid": 60802.0, "ask": 60842.0, "spread": 40.0},
        {"ts_utc": "2026-11-22T16:00:00.400Z", "exchange_ts": _epoch_ms(now) + 400,
         "symbol": "BTCUSD", "bid": 60803.0, "ask": 60843.0, "spread": 40.0},
        {"ts_utc": "2026-11-22T16:00:00.500Z", "exchange_ts": _epoch_ms(now),
         "symbol": "XAUUSD", "bid": 3537.47, "ask": 3537.90, "spread": 0.43},
        {"ts_utc": "2026-11-22T16:00:00.600Z", "exchange_ts": _epoch_ms(now) + 500,
         "symbol": "BTCUSD", "bid": 60804.0, "ask": 60844.0, "spread": 40.0},
    ])
    xau = feed.read_ticks(16, now, symbol="XAUUSD")
    assert len(xau) == 2
    assert all(t["bid"] == 3537.47 for t in xau)
    assert len(feed.read_ticks(16, now)) == 7  # tanpa filter: semua simbol
    # XAUUSD beku -> market tutup meski BTCUSD bergerak
    assert feed.is_market_open(xau, now) is False
    btc = feed.read_ticks(16, now, symbol="BTCUSD")
    assert feed.is_market_open(btc, now) is True


def _advancing_ticks(offset: timedelta, n: int = 8) -> list[dict]:
    now = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        ts = now - timedelta(seconds=n - i)
        out.append({"ts_utc": ts, "exchange_ts": ts + offset})
    return out


def test_estimate_offset_none_when_exchange_clock_is_utc():
    """EA v5 (TimeGMT): exchange ≈ arrival → offset ~0 = tidak terukur.
    Pemakai harus jatuh ke asumsi A1' (broker_utc_offset_hours, UTC+7 terukur)."""
    assert feed.estimate_offset_hours(_advancing_ticks(timedelta(milliseconds=50))) is None


def test_estimate_offset_measures_wall_clock_when_present():
    """EA v0 (string jam broker): exchange = arrival + 2 jam → terukur +2."""
    assert feed.estimate_offset_hours(_advancing_ticks(timedelta(hours=2))) == 2.0


# ---------------------------------------------------------------- is_market_open

def _tick_rows(now, bid_fn, exch_fn, n=10):
    return [
        {
            "ts_utc": now - timedelta(seconds=i),
            "exchange_ts": exch_fn(now, i),
            "bid": bid_fn(i),
            "ask": bid_fn(i) + 0.5,
            "spread": 0.5,
        }
        for i in range(n)
    ]


def test_is_market_open_requires_moving_quotes():
    """Jam broker berjalan tapi harga beku = pasar tutup (tick phantom EA)."""
    now = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    live = _tick_rows(now, lambda i: 3537.0 + i * 0.1,
                      lambda n, i: n - timedelta(seconds=i, milliseconds=50))
    assert feed.is_market_open(live, now) is True

    frozen = _tick_rows(now, lambda i: 3537.47,
                        lambda n, i: n - timedelta(seconds=i, milliseconds=50))
    assert feed.is_market_open(frozen, now) is False  # harga beku = tutup

    stalled = _tick_rows(now, lambda i: 3537.0 + i * 0.1,
                         lambda n, i: n - timedelta(minutes=30))
    assert feed.is_market_open(stalled, now) is False  # jam beku = tutup

    assert feed.is_market_open(live[:3], now) is False  # < 5 tick terbaru
    assert feed.is_market_open([], now) is False
