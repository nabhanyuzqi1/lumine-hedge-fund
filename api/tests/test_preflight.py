"""PRD v2.2 §8.2: preflight data quality (bad ticks, survivorship, gap, dll)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from paper.preflight import (
    check_bad_ticks,
    check_survivorship,
    run_preflight,
)

UTC = timezone.utc


def _series(n=60, base=2000.0):
    # close bervariasi deterministik (bukan flat) supaya tidak terhitung
    # stuck feed oleh detektor bad tick
    return [{"ts": datetime(2026, 3, 2, tzinfo=UTC) + timedelta(minutes=i),
             "open": base, "high": base + 0.5, "low": base - 0.5,
             "close": base + (i % 5) * 0.1, "volume": 100.0}
            for i in range(n)]


def test_bad_ticks_clean_series_pass():
    res = check_bad_ticks(_series())
    assert res["status"] == "PASS"
    assert res["flagged"] == 0


def test_bad_ticks_spike_detected():
    rows = _series()
    rows[30]["close"] = 2500.0  # spike +25%
    rows[30]["high"] = 2501.0
    res = check_bad_ticks(rows)
    assert res["status"] in ("WARN", "FAIL")
    assert res["flagged"] >= 1
    assert any(s["reason"] == "spike_revers" for s in res["samples"])


def test_bad_ticks_fail_on_many_spikes():
    rows = _series(200)
    for i in range(20, 40):
        rows[i]["close"] = 2600.0
        rows[i]["high"] = 2601.0
    res = check_bad_ticks(rows)
    assert res["status"] == "FAIL"
    assert res["flagged_pct"] > 0.005


def test_survivorship_symbol_tradeable_documented():
    res = check_survivorship("XAUUSD", ["XAUUSD", "BTCUSD"])
    assert res["status"] == "DOCUMENTED"
    assert "selection" in res["documented"]


def test_survivorship_delisted_symbol_fails():
    res = check_survivorship("OLDSYMBOL", ["XAUUSD", "BTCUSD"])
    assert res["status"] == "FAIL"


def test_run_preflight_overall():
    res = run_preflight(_series(300), symbol="XAUUSD", tf="M1",
                        tradeable_symbols=["XAUUSD"])
    assert res["bars"] == 300
    assert set(res["checks"]) == {"ohlc", "monotonicity", "duplicate_rate",
                                  "gaps", "completeness", "bad_ticks",
                                  "survivorship"}
    assert res["overall_status"] in ("PASS", "DOCUMENTED", "WARN", "FAIL")


def test_run_preflight_detects_gap():
    rows = _series(200)
    # buang bar 60..129 -> gap ~70 menit di M1 (> GAP_WARN_MIN 30 menit)
    rows = rows[:60] + rows[130:]
    res = run_preflight(rows, symbol="XAUUSD", tf="M1", tradeable_symbols=["XAUUSD"])
    assert res["checks"]["gaps"]["gap_count"] >= 1
    assert res["checks"]["gaps"]["status"] in ("WARN", "FAIL")
