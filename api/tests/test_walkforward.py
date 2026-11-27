"""Walk-forward runner + backtest_runs registry (PRD 5.4, P2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app import db
from paper.backtest import canonical_tf, run_backtest
from paper.walkforward import (
    PARAM_GRID,
    Window,
    add_months,
    expand_grid,
    plan_windows,
    render_report,
    run_walkforward,
    select_best,
    write_report_rows,
)

UTC = timezone.utc


def _synth_h1(start: date, days: int) -> list[dict]:
    """H1 weekday bars 00:00-11:00 UTC dengan breakout London sintetis.

    Asia range 2000-2004 tiap hari; hari genap breakout naik (close 2006,
    SL 2004.5, TP tersentuh di bar 08), hari ganjil breakout turun (close
    1998, SL 1999.5, TP di bar 08). Deterministik: semua kombinasi grid
    menghasilkan trade yang sama, pemilihan parameter hanya pembeda rr.
    """
    candles: list[dict] = []
    for d in range(days):
        day = start + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        up = d % 2 == 0
        base = day
        for hour in range(12):
            ts = datetime(base.year, base.month, base.day, hour, tzinfo=UTC)
            if hour <= 6:
                if hour == 6:
                    close = 2003.5 if up else 2000.5
                else:
                    close = 2003.5 if hour % 2 == 0 else 2000.5
                bar = (2000.2, 2004.0, 2000.0, close)
            elif hour == 7:
                bar = (2003.6, 2006.4, 2004.5, 2006.0) if up else \
                      (2000.4, 1999.5, 1997.6, 1998.0)
            elif hour == 8:
                bar = (2006.2, 2012.0, 2005.8, 2008.0) if up else \
                      (1997.8, 1998.2, 1988.0, 1994.0)
            else:
                bar = (2008.0, 2009.0, 2007.5, 2008.0) if up else \
                      (1994.0, 1995.0, 1993.5, 1994.0)
            candles.append({"ts": ts, "open": bar[0], "high": bar[1],
                            "low": bar[2], "close": bar[3]})
    return candles


def _window_bounds(data_start: datetime, data_end: datetime) -> list[Window]:
    return plan_windows(data_start, data_end, train_months=1, test_months=1)


# ---------------------------------------------------------------- planning


def test_plan_windows_six_month_train():
    windows = plan_windows(datetime(2026, 1, 19, tzinfo=UTC),
                           datetime(2026, 11, 20, 16, tzinfo=UTC))
    # Data mulai 19 Jan: window latih 1 Jan-30 Jun tidak penuh di data -> first 1 Aug
    assert [w.test_start for w in windows] == [
        datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)]
    for w in windows:
        assert w.train_end == w.test_start
        # 6 bulan kalender: train_end == add_months(train_start, 6)
        assert w.train_end == add_months(w.train_start, 6)
        assert w.train_start >= datetime(2026, 1, 19, tzinfo=UTC)


def test_plan_windows_short_data_empty():
    assert plan_windows(datetime(2026, 1, 1, tzinfo=UTC),
                        datetime(2026, 3, 1, tzinfo=UTC)) == []


def test_expand_grid_deterministic():
    combos = expand_grid()
    assert len(combos) == 12
    assert combos[0] == {"breakout_buffer_usd": 0.10, "rr": 1.0, "min_range_usd": 0.50}
    assert expand_grid() == combos


def test_select_best_prefers_minimum_sample():
    small = {"metrics": {"trades": 2, "expectancy_r": 1.0, "profit_factor": 9.0}}
    robust = {"metrics": {"trades": 10, "expectancy_r": 0.5, "profit_factor": 1.2}}
    assert select_best([small, robust]) is robust


def test_canonical_tf():
    assert canonical_tf("5m") == "M5"
    assert canonical_tf("1h") == "H1"
    assert canonical_tf("H1") == "H1"


# ---------------------------------------------------------------- end-to-end


async def test_run_walkforward_writes_registry():
    candles = _synth_h1(date(2026, 1, 1), 150)
    data_start = candles[0]["ts"]
    data_end = candles[-1]["ts"]
    windows = _window_bounds(data_start, data_end)
    assert len(windows) == 4

    report = run_walkforward(candles, tf="H1", symbol="TESTUSD", windows=windows,
                             data_end=data_end)
    agg = report["aggregate"]
    assert agg["n_windows"] == 4
    assert agg["total_attempts"] == 4 * (len(expand_grid()) + 1)
    assert agg["windows_with_trades"] == 4
    for w in report["windows"]:
        assert w["test_metrics"]["trades"] > 0
        assert w["n_attempts"] == len(expand_grid())
        assert len(w["_train_rows"]) == len(expand_grid())
        assert w["note"].startswith(("OK", "GAGAL", "awas"))

    async with db.pool().connection() as conn:
        written = await write_report_rows(conn, report)
        assert written == agg["total_attempts"]
        rows = (await (await conn.execute(
            "SELECT role, selected, params, metrics, window_index FROM backtest_runs "
            "WHERE run_id = %s ORDER BY id", (report["run_id"],))).fetchall())
        assert len(rows) == agg["total_attempts"]
        for index in range(4):
            chunk = [r for r in rows if r["window_index"] == index]
            train = [r for r in chunk if r["role"] == "train"]
            tests = [r for r in chunk if r["role"] == "test"]
            assert len(train) == len(expand_grid()) and len(tests) == 1
            chosen = [r for r in train if r["selected"]]
            assert len(chosen) == 1
            assert chosen[0]["params"] == tests[0]["params"]  # uji = parameter latih
            assert tests[0]["selected"] is True
            assert tests[0]["metrics"]["trades"] > 0
        # Jumlah percobaan per window terlihat dari registry (PRD 5.4).
        counts = (await (await conn.execute(
            "SELECT window_index, count(*) AS n FROM backtest_runs "
            "WHERE run_id = %s GROUP BY window_index ORDER BY window_index",
            (report["run_id"],))).fetchall())
        assert [c["n"] for c in counts] == [13, 13, 13, 13]
        await conn.execute("DELETE FROM backtest_runs WHERE run_id = %s",
                           (report["run_id"],))

    text = render_report(report)
    assert "Hasil per window uji" in text
    assert "backtest_runs" in text
    assert "2026-02-01" in text  # window uji pertama


# ------------------------------------------------------- context_bars (t_f2mp3)


class _RecorderStrategy:
    """Stub strategi: hanya merekam candles yang diterima decide()."""

    STRATEGY_ID = "recorder"
    CONTEXT_BARS = 64
    seen: list[list[dict]] = []

    class StrategyParams:
        def __init__(self, tf_seconds: int = 3600, **kw):
            self.tf_seconds = tf_seconds
            self.force_close_utc = None
            self.max_spread_abs = 0.50

    @classmethod
    def decide(cls, context, params=None):
        cls.seen.append(list(context["candles"]))
        return None


def test_run_backtest_context_bars_cross_day_history():
    """context_bars > 0 memberi sejarah lintas hari (Butuh Donchian 24 bar H1);
    default 0 tetap hanya candle hari berjalan (strategi #1/#2)."""
    candles = _synth_h1(date(2026, 11, 16), 5)  # Sen-Jum, 12 bar H1/hari
    _RecorderStrategy.seen.clear()
    run_backtest(candles, tf_seconds=3600, strategy=_RecorderStrategy,  # type: ignore[reportArgumentType]
                 params=_RecorderStrategy.StrategyParams(),  # type: ignore[reportArgumentType]
                 context_bars=64)
    seen = _RecorderStrategy.seen
    assert seen, "decide() tidak pernah dipanggil"
    last = seen[-1]
    assert len(last) == 60  # semua bar lintas hari dalam satu context
    assert last[-1]["ts"] - last[0]["ts"] > timedelta(hours=24)

    _RecorderStrategy.seen.clear()
    run_backtest(candles, tf_seconds=3600, strategy=_RecorderStrategy,  # type: ignore[reportArgumentType]
                 params=_RecorderStrategy.StrategyParams(),  # type: ignore[reportArgumentType]
                 context_bars=0)
    assert _RecorderStrategy.seen
    assert all(len(c) <= 12 for c in _RecorderStrategy.seen)  # per hari saja


# ------------------------------------------------- provenance + reproducibility


def test_run_walkforward_records_execution_and_seed():
    """PRD v2.2 §8.2: execution model + seed tercatat di config run."""
    from paper.execution import default_execution_model

    candles = _synth_h1(date(2026, 1, 1), 150)
    windows = _window_bounds(candles[0]["ts"], candles[-1]["ts"])
    report = run_walkforward(candles, tf="H1", symbol="TESTUSD", windows=windows,
                             data_end=candles[-1]["ts"],
                             execution=default_execution_model("TESTUSD"), seed=99)
    assert report["config"]["seed"] == 99
    ex = report["config"]["execution"]
    assert ex is not None and ex["fill_delay_bars"] == 1
    # hasil metrik tetap punya breakdown metrik wajib PRD 8.3
    m = report["windows"][0]["test_metrics"]
    for key in ("profit_factor", "expectancy_usd", "max_drawdown_duration_min",
                "sortino_per_trade", "exposure_pct", "avg_holding_min",
                "tail_loss_cvar95_usd", "worst_day_usd", "spread_distribution",
                "slippage_distribution", "by_session", "by_spread_bucket",
                "methodology"):
        assert key in m, f"metrik {key} hilang dari test_metrics"


async def test_verify_run_reproducible(tmp_path):
    """PRD v2.2 §8.2 DoD: backtest reproducible dari config/data hash.

    Sisipkan candle ke DB test, jalankan walk-forward (dengan provenance +
    config hash seperti main()), tulis registry, lalu verify_run harus
    MATCH untuk config hash, checksum data, dan metrik window uji.
    """
    from paper.execution import default_execution_model
    from paper.provenance import code_provenance, config_hash, data_provenance
    from paper.walkforward import _load_data, verify_run

    raw = _synth_h1(date(2026, 1, 1), 150)
    async with db.pool().connection() as conn:
        for c in raw:
            await conn.execute(
                "INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                ("TESTUSD", "H1", c["ts"], c["open"], c["high"], c["low"],
                 c["close"], c.get("volume", 0)))

    candles, meta = await _load_data("TESTUSD", "H1")
    windows = _window_bounds(candles[0]["ts"], candles[-1]["ts"])
    report = run_walkforward(candles, tf="H1", symbol="TESTUSD", windows=windows,
                             data_end=candles[-1]["ts"],
                             execution=default_execution_model("TESTUSD"), seed=7)
    report["provenance"] = {
        "data": data_provenance(candles, symbol="TESTUSD", tf="H1", raw_dir=None),
        "code": code_provenance(),
    }
    report["config"]["config_hash"] = config_hash(
        {k: v for k, v in report["config"].items() if k != "config_hash"})

    async with db.pool().connection() as conn:
        written = await write_report_rows(conn, report)
        assert written == report["aggregate"]["total_attempts"]
        row = (await (await conn.execute(
            "SELECT config FROM backtest_runs WHERE run_id = %s LIMIT 1",
            (report["run_id"],))).fetchone())
    assert row["config"]["config_hash"].startswith("sha256:")

    ok = await verify_run(report["run_id"])
    assert ok, "run harus reproducible (config/data/metrics MATCH)"
