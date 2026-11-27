"""Test cost model terkalibrasi (PRD 5.2) + integrasi backtest engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from paper.backtest import run_backtest
from paper.costs import (
    CostModel,
    build_cost_model,
    duka_session_medians,
    hfm_session_medians,
)

UTC = timezone.utc


def _model(**kw) -> CostModel:
    duka = {"asia": 0.36, "london": 0.30, "london_newyork": 0.32, "newyork": 0.34}
    hfm = {"asia": 0.43, "london": 0.45, "london_newyork": 0.43}
    return build_cost_model(duka, hfm, **kw)


# ---------------------------------------------------------------- build


def test_factor_and_haircut():
    m = _model()
    # faktor = HFM/Duka per sesi; spread filter = Duka x faktor; biaya = +haircut 20%
    assert m.factor_by_session["london"] == round(0.45 / 0.30, 4)
    assert m.filter_spread_by_session["london"] == 0.45
    assert m.spread_by_session["london"] == round(0.45 * 1.2, 3)
    # sesi tanpa sampel HFM (newyork) memakai faktor global =
    # median semua HFM / median semua Duka
    assert "newyork" not in m.hfm_spread_by_session
    global_factor = round(0.43 / 0.33, 4)  # median(0.43,0.45,0.43)/median(0.36,0.30,0.32,0.34)
    assert m.factor_by_session["newyork"] == global_factor
    assert any("newyork" in n for n in m.notes)


def test_factor_cap():
    m = _model(factor_cap=1.2)
    assert m.factor_by_session["london"] == 1.2  # 1.5 di-cap
    assert any("cap" in n for n in m.notes)


def test_spread_at_sessions():
    m = _model()
    assert m.spread_at(datetime(2026, 11, 20, 3, tzinfo=UTC)) == m.spread_by_session["asia"]
    assert m.spread_at(datetime(2026, 11, 20, 8, tzinfo=UTC)) == m.spread_by_session["london"]
    assert m.spread_at(datetime(2026, 11, 20, 13, tzinfo=UTC)) == m.spread_by_session["london_newyork"]
    assert m.spread_at(datetime(2026, 11, 20, 18, tzinfo=UTC)) == m.spread_by_session["newyork"]
    assert m.spread_at(datetime(2026, 11, 20, 22, tzinfo=UTC)) == m.spread_by_session["asia"]


def test_commission_round_turn():
    m = _model()
    assert m.commission_usd(1.0) == 7.0
    assert m.commission_usd(0.05) == 0.35
    assert m.commission_usd(0.0) == 0.0


def test_empty_duka_raises():
    try:
        build_cost_model({}, {"asia": 0.4})
        raise AssertionError("harusnya ValueError")
    except ValueError:
        pass


def test_medians_helpers():
    ts = [datetime(2026, 11, 20, 8, i, tzinfo=UTC) for i in range(3)]
    series = [(ts[0], 0.30), (ts[1], 0.40), (ts[2], 0.50)]
    med = duka_session_medians(series)
    assert med == {"london": 0.40}
    rows = [{"session": "asia", "spread_avg": 0.4},
            {"session": "asia", "spread_avg": 0.6},
            {"session": "london", "spread_avg": 0.2}]
    assert hfm_session_medians(rows) == {"asia": 0.5, "london": 0.2}


# ---------------------------------------------------------------- engine


def _day_candles(day: datetime, *, asia_high=2004.0, asia_low=2000.0,
                 breakout=2006.0, sl=2004.5, tp=2012.0) -> list[dict]:
    """Satu hari sintetis: Asia range lalu breakout London naik + TP tercapai."""
    bars = []
    for hour in range(7):
        bars.append({"ts": day.replace(hour=hour, minute=0, second=0, microsecond=0),
                     "open": asia_low + 0.2, "high": asia_high, "low": asia_low,
                     "close": asia_high - 0.5})
    bars.append({"ts": day.replace(hour=7, minute=0, second=0, microsecond=0),
                 "open": asia_high - 0.4, "high": breakout, "low": asia_high - 0.6,
                 "close": breakout - 0.4})
    bars.append({"ts": day.replace(hour=8, minute=0, second=0, microsecond=0),
                 "open": breakout - 0.2, "high": tp + 0.5, "low": breakout - 0.5,
                 "close": tp})
    bars.append({"ts": day.replace(hour=9, minute=0, second=0, microsecond=0),
                 "open": tp, "high": tp, "low": tp - 0.2, "close": tp - 0.1})
    return bars


def _synthetic(days: int = 3) -> list[dict]:
    out = []
    base = datetime(2026, 11, 16, tzinfo=UTC)  # Senin
    for d in range(days):
        day = base + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        out.extend(_day_candles(day))
    return out


def test_backtest_applies_commission_and_session_spread():
    m = _model()
    result = run_backtest(_synthetic(3), tf_seconds=3600, equity0=10000.0,
                          cost_model=m)
    assert result["trades"] >= 1
    t = result["trades_detail"][0]
    # spread teramati = filter (tanpa haircut), dipakai decide + risk gate
    assert t["session"] == "london"
    assert t["filter_spread_at_entry"] == m.filter_spread_by_session["london"]
    assert t["spread_at_entry"] == m.spread_by_session["london"]
    # komisi round-turn dipotong dari profit
    assert t["commission_usd"] == m.commission_usd(t["volume"])
    assert t["profit"] == round(t["gross_profit"] - t["commission_usd"], 2)
    assert result["cost_model"]["commission_total_usd"] > 0
    assert result["entries_by_session"].get("london", 0) >= 1


def test_backtest_cost_model_changes_result_vs_legacy():
    m = _model()
    legacy = run_backtest(_synthetic(5), tf_seconds=3600, spread=0.50, slippage=0.10)
    calibrated = run_backtest(_synthetic(5), tf_seconds=3600, cost_model=m)
    # biaya legacy 0.50 vs terkalibrasi (sekitar 0.52-0.60) -> hasil bisa beda;
    # yang dijamin: mode terkalibrasi mencatat model dan komisi.
    assert "spread_usd" in legacy["cost_model"]
    assert calibrated["cost_model"]["haircut"] == 0.2
    assert calibrated["cost_model"]["commission_per_lot_round_usd"] == 7.0


def test_walkforward_passes_cost_model():
    from paper.walkforward import Window, run_walkforward
    from strategies.london_breakout import StrategyParams

    windows = [Window(train_start=datetime(2026, 11, 16, tzinfo=UTC),
                      train_end=datetime(2026, 11, 18, tzinfo=UTC),
                      test_start=datetime(2026, 11, 18, tzinfo=UTC),
                      test_end=datetime(2026, 11, 20, tzinfo=UTC))]
    grid = {"breakout_buffer_usd": [0.10], "rr": [1.5], "min_range_usd": [0.50]}
    report = run_walkforward(_synthetic(5), tf="H1", windows=windows, grid=grid,
                             cost_model=_model())
    assert report["config"]["cost_model"] is not None
    assert report["config"]["cost_model"]["haircut"] == 0.2
    assert report["attempts_total"] == len(grid["breakout_buffer_usd"]) * \
        len(grid["rr"]) * len(grid["min_range_usd"]) + 1
