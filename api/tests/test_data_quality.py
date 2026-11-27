"""Data quality checks (PRD 19.2, kartu t_f2v22a11): check murni + run
orkestrasi terhadap DB test."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import data_quality as dq
from app import db
from app.state_machine import fetchone


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _m1_rows(symbol, start, minutes, *, break_ohlc_at=None):
    rows = []
    for i in range(minutes):
        ts = start + timedelta(minutes=i)
        o = 2000.0 + i * 0.01
        row = {"symbol": symbol, "timeframe": "M1", "ts": ts,
               "open": o, "high": o + 0.5, "low": o - 0.5, "close": o + 0.2,
               "volume": 10}
        if break_ohlc_at is not None and i == break_ohlc_at:
            row["high"] = row["low"] - 1.0   # high < low = pecah
        rows.append(row)
    return rows


# --------------------------------------------------------------- OHLC
def test_ohlc_ok():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 30)
    res = dq.check_ohlc(rows)
    assert res["status"] == "PASS" and res["violation_count"] == 0


def test_ohlc_violation_detected():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 30, break_ohlc_at=10)
    res = dq.check_ohlc(rows)
    assert res["status"] == "FAIL" and res["violation_count"] == 1
    assert res["violations"][0]["reason"]


# ------------------------------------------------------- monotonic & dup
def test_monotonic_and_misalignment():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 30)
    assert dq.check_monotonicity(rows, "M1")["status"] == "PASS"
    # bar M5 dengan ts tidak di bucket kelipatan 300s = misaligned
    bad = dict(rows[0])
    bad["timeframe"] = "M5"
    bad["ts"] = rows[0]["ts"] + timedelta(seconds=37)
    res = dq.check_monotonicity([bad], "M5")
    assert res["misaligned"] == 1 and res["status"] == "FAIL"


def test_duplicate_rate():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 30)
    assert dq.check_duplicate_rate(rows)["status"] == "PASS"
    dup = rows + [dict(rows[0])]
    res = dq.check_duplicate_rate(dup)
    assert res["duplicate_rows"] == 1 and res["status"] in ("WARN", "FAIL")


# ------------------------------------------------------------------ gap
def test_gap_weekend_not_counted():
    """Jumat 22:00 UTC -> Minggu 23:00 UTC (pasar tutup) bukan gap."""
    fri = _utc(2026, 11, 20, 21, 55)   # Jumat
    rows = _m1_rows("XAUUSD", fri, 5)  # 21:55-21:59
    # lompat ke pembukaan Minggu 23:25 UTC (pasar buka lagi Minggu malam)
    sunday = _utc(2026, 11, 22, 23, 25)
    rows.append({"symbol": "XAUUSD", "timeframe": "M1", "ts": sunday,
                 "open": 2000, "high": 2000.5, "low": 1999.5,
                 "close": 2000.2, "volume": 3})
    res = dq.check_gaps(rows, "XAUUSD", "M1")
    assert res["status"] == "PASS"


def test_gap_in_market_hours_detected():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 5)   # Senin 08:00-08:04
    rows.append({"symbol": "XAUUSD", "timeframe": "M1",
                 "ts": _utc(2026, 11, 23, 13, 5),          # gap 300 menit
                 "open": 2000, "high": 2000.5, "low": 1999.5,
                 "close": 2000.2, "volume": 3})
    res = dq.check_gaps(rows, "XAUUSD", "M1")
    assert res["status"] == "FAIL" and res["gaps"][0]["minutes"] > 240


def test_gap_warning_band():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 5)
    rows.append({"symbol": "XAUUSD", "timeframe": "M1",
                 "ts": _utc(2026, 11, 23, 8, 45),          # gap 40 menit
                 "open": 2000, "high": 2000.5, "low": 1999.5,
                 "close": 2000.2, "volume": 3})
    res = dq.check_gaps(rows, "XAUUSD", "M1")
    assert res["status"] == "WARN"


# ------------------------------------------------------------- spread
def test_spread_validity():
    good = [{"window_start": _utc(2026, 11, 23, 8, 0), "spread_avg": 0.3,
             "spread_min": 0.2, "spread_max": 0.4, "tick_count": 12}]
    assert dq.check_spread(good, "XAUUSD")["status"] == "PASS"

    negative = [dict(good[0], spread_min=-0.1)]
    assert dq.check_spread(negative, "XAUUSD")["status"] == "FAIL"

    inverted = [dict(good[0], spread_min=0.5, spread_max=0.2)]
    assert dq.check_spread(inverted, "XAUUSD")["status"] == "FAIL"

    over_spec = [dict(good[0], spread_avg=0.9)]
    assert dq.check_spread(over_spec, "XAUUSD")["status"] == "FAIL"
    # BTCUSD punya spec spread lebih lebar ($100)
    assert dq.check_spread([dict(good[0], spread_avg=40.0)], "BTCUSD")["status"] == "PASS"


# ------------------------------------------------------------ checksum
def test_checksum_stable_and_sensitive():
    rows = _m1_rows("XAUUSD", _utc(2026, 11, 23, 8), 10)
    a = dq.series_checksum(rows)
    b = dq.series_checksum(list(reversed(rows)))   # urutan input bebas
    assert a == b
    changed = [dict(r) for r in rows]
    changed[3]["close"] = changed[3]["close"] + 0.01
    assert dq.series_checksum(changed) != a


# --------------------------------------------------- broker vs historical
def test_broker_vs_historical():
    now = datetime.now(timezone.utc)
    broker = [{"ts": now - timedelta(minutes=i), "close": 2000.0 + i * 0.01}
              for i in range(10)]
    hist = [{"ts": r["ts"], "close": r["close"] * 1.0001} for r in broker]
    res = dq.check_broker_vs_historical(broker, hist)
    assert res["status"] == "PASS" and res["compared"] == 10

    diverged = [{"ts": r["ts"], "close": r["close"] * 1.02} for r in broker]
    res = dq.check_broker_vs_historical(broker, diverged)
    assert res["status"] == "FAIL" and res["mismatches"] == 10

    # tidak ada overlap = SKIPPED
    other = [{"ts": now - timedelta(days=400), "close": 1.0}]
    assert dq.check_broker_vs_historical(broker, other)["status"] == "SKIPPED"


# --------------------------------------------------------- symbol mapping
def test_symbol_mapping():
    settings = {"allowed_symbols": ["XAUUSD"], "symbol_specs": {"BTCUSD": {}}}
    ok = dq.check_symbol_mapping(["XAUUSD", "BTCUSD"], settings)
    assert ok["status"] == "PASS"

    raw = dq.check_symbol_mapping(["#BTCUSD.stp"], settings)
    assert raw["status"] == "FAIL"

    unmapped = dq.check_symbol_mapping(["XAUUSD", "ETHUSD"], settings)
    assert unmapped["status"] == "WARN"


# ------------------------------------------------- ledger & run orkestrasi
async def test_ledger_guard_and_chain():
    """PRD 19.4: trigger append-only terpasang, event kompensasi bisa
    ditambahkan tanpa mengedit sejarah."""
    from app import data_quality as dq
    async with db.pool().connection() as conn:
        guard = await dq._collect_ledger_guard(conn)
        assert guard["append_only_trigger"] is True
        assert guard["truncate_trigger"] is True
        assert guard["non_owner_mutate_grants"] == []

        # koreksi lewat event kompensasi (PRD 19.4): INSERT baru, bukan edit
        cur = await conn.execute(
            "INSERT INTO orders (symbol, side, volume) "
            "VALUES ('XAUUSD', 'BUY', 0.01) RETURNING id")
        order_id = (await cur.fetchone())["id"]
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, NULL, 'RECEIVED', '{}')", (order_id,))
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, 'RECEIVED', 'COMPENSATION_REVERSAL', "
            "'{\"kind\": \"compensation\", \"reason\": \"test\"}')", (order_id,))
        chain = await dq._collect_ledger_chain(conn)
    assert chain["compensation_events"] >= 1
    assert chain["events"] >= 2


async def test_run_quality_checks_end_to_end():
    """DoD: quality checks jalan & melaporkan — seed candle + liquidity,
    run orkestrasi, semua section ada dan data_versions terisi."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        for i in range(120):
            ts = now - timedelta(minutes=120 - i)
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, "
                "close, volume) VALUES ('XAUUSD', 'M1', %s, 2000, 2001, 1999, "
                "2000.5, 10) ON CONFLICT DO NOTHING", (ts,))
        for i in range(10):
            await conn.execute(
                "INSERT INTO liquidity_samples (symbol, window_start, session, "
                "spread_avg, spread_min, spread_max, tick_count) "
                "VALUES ('XAUUSD', %s, 'london', 0.3, 0.2, 0.4, 5) "
                "ON CONFLICT DO NOTHING",
                (now - timedelta(minutes=i * 5),))

    report = await dq.run_quality_checks(window_days=1)
    assert report["status"] in ("PASS", "WARN", "FAIL")
    for section in ("candles", "liquidity", "symbols", "freshness",
                    "broker_vs_historical", "ledger", "data_versions"):
        assert section in report["sections"], section
    assert report["sections"]["ledger"]["append_only_trigger"] is True
    assert "XAUUSD/M1" in report["sections"]["data_versions"]["versions"]
    assert report["sections"]["data_versions"]["versions"]["XAUUSD/M1"]["checksum"].startswith("sha256:")

    await dq.persist_report(report)
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn, "SELECT * FROM data_quality_runs ORDER BY id DESC LIMIT 1")
        assert row is not None and row["status"] == report["status"]
        ver = await fetchone(
            conn, "SELECT * FROM data_versions WHERE symbol='XAUUSD' "
                  "AND timeframe='M1'")
        assert ver is not None and ver["checksum"].startswith("sha256:")


def test_render_text():
    report = {"status": "PASS", "generated_at": "2026-11-23T00:00:00Z",
              "window_days": 3, "sections": {
                  "ledger": {"status": "PASS", "detail": "aman"}},
              "counts": {"PASS": 1, "WARN": 0, "FAIL": 0}}
    text = dq.render_text(report)
    assert "PASS" in text and "ledger" in text
