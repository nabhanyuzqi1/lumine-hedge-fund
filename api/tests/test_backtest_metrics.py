"""PRD v2.2 §8.3: metrik wajib pada summarize() (Sortino, durasi DD,
exposure, holding, distribusi spread/slippage, tail loss, worst day,
CI, breakdown per sesi/regime/hari/bucket spread)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from paper.backtest import summarize
from paper.execution import ExecutionModel

UTC = timezone.utc


def _trades(specs):
    """specs: list of (open_offset_min, close_offset_min, profit, spread)."""
    out = []
    t0 = datetime(2026, 3, 2, 0, tzinfo=UTC)
    for open_m, close_m, profit, spread in specs:
        out.append({
            "opened_at": (t0 + timedelta(minutes=open_m)).isoformat(),
            "closed_at": (t0 + timedelta(minutes=close_m)).isoformat(),
            "profit": profit, "spread_at_entry": spread,
            "session": "london", "exit_reason": "TP",
        })
    return out


def _summarize(trades, **kw):
    defaults = dict(equity0=10000.0, balance=10000.0 + sum(t["profit"] for t in trades),
                    spread=0.5, slippage=0.1, tf_seconds=300, bars_total=1000)
    defaults.update(kw)
    return summarize(trades, **defaults)


def test_core_metrics_present():
    res = _summarize(_trades([(0, 30, 50.0, 0.4), (60, 90, -20.0, 0.6),
                              (120, 150, 30.0, 0.5)]))
    for key in ("net_profit_usd", "profit_factor", "expectancy_usd", "winrate",
                "trades", "max_drawdown_usd", "max_drawdown_pct",
                "sharpe_per_trade", "sortino_per_trade", "avg_win_usd",
                "avg_loss_usd", "exposure_pct", "avg_holding_min",
                "tail_loss_cvar95_usd", "worst_day_usd", "best_day_usd",
                "spread_distribution", "slippage_distribution", "methodology",
                "by_session", "by_weekday", "by_day", "by_spread_bucket",
                "expectancy_ci95", "max_drawdown_duration_min"):
        assert key in res, f"metrik wajib {key} hilang"


def test_expectancy_and_pf_math():
    res = _summarize(_trades([(0, 30, 50.0, 0.4), (60, 90, -20.0, 0.6)]))
    assert res["expectancy_usd"] == 15.0
    assert res["profit_factor"] == round(50.0 / 20.0, 3)
    assert res["winrate"] == 0.5
    assert res["avg_win_usd"] == 50.0
    assert res["avg_loss_usd"] == -20.0


def test_exposure_and_holding():
    # window 1000 bar x 5 menit = 5000 menit; posisi 30+30+30 = 90 menit
    res = _summarize(_trades([(0, 30, 50.0, 0.4), (60, 90, -20.0, 0.6),
                              (120, 150, 30.0, 0.5)]))
    assert res["exposure_pct"] == round(100 * 90 / 5000, 2)
    assert res["avg_holding_min"] == 30.0
    assert res["max_holding_min"] == 30.0


def test_drawdown_duration():
    # kurva: 10000 -> 10500 -> 10300 -> 10600; DD 10300-10500 pemulihan di 10600
    res = _summarize(_trades([(0, 30, 500.0, 0.4), (60, 90, -200.0, 0.6),
                              (120, 150, 300.0, 0.5)]))
    assert res["max_drawdown_usd"] == 200.0
    # durasi = puncak (trade1 close, t=30) -> pemulihan penuh (trade3 close, t=150)
    assert res["max_drawdown_duration_min"] == 120.0
    assert res["drawdown_open_at_end_min"] is None


def test_sortino_vs_sharpe():
    # PnL: +50, -20, +30; mean=20; std~32.0; downside dev = sqrt((400)/3)=11.547
    res = _summarize(_trades([(0, 30, 50.0, 0.4), (60, 90, -20.0, 0.6),
                              (120, 150, 30.0, 0.5)]))
    assert res["sortino_per_trade"] is not None
    assert res["sortino_per_trade"] > res["sharpe_per_trade"]


def test_tail_loss_and_worst_day():
    # close di hari berbeda (menit sejak t0): 30, 1500, 2900, 4300, 5700
    specs = [(0, 30, -100.0, 0.4), (60, 1500, -50.0, 0.6),
             (120, 2900, 40.0, 0.5), (180, 4300, 30.0, 0.5),
             (240, 5700, 20.0, 0.5)]
    res = _summarize(_trades(specs))
    # 5% terburuk dari 5 trade = 1 trade: -100
    assert res["tail_loss_cvar95_usd"] == -100.0
    assert res["worst_trade_usd"] == -100.0
    assert res["worst_day_usd"] == -100.0
    # hari ke-4 memuat dua trade: +40 +30 = +70
    assert res["best_day_usd"] == 70.0


def test_expectancy_ci95():
    res = _summarize(_trades([(0, 30, 50.0, 0.4), (60, 90, -20.0, 0.6),
                              (120, 150, 30.0, 0.5)]))
    mean = 20.0
    import statistics
    std = statistics.stdev([50.0, -20.0, 30.0])
    se = std / (3 ** 0.5)
    ci = res["expectancy_ci95"]
    assert ci[0] == round(mean - 1.96 * se, 2)
    assert ci[1] == round(mean + 1.96 * se, 2)


def test_spread_buckets():
    res = _summarize(_trades([(0, 30, 50.0, 0.2), (60, 90, -20.0, 0.4),
                              (120, 150, 30.0, 0.6), (180, 210, 10.0, 0.8)]))
    assert len(res["by_spread_bucket"]) == 4
    total = sum(b["trades"] for b in res["by_spread_bucket"].values())
    assert total == 4
    # spread terendah di q1, tertinggi di q4
    assert res["by_spread_bucket"]["q1_rendah"]["range"][0] == 0.2
    assert res["by_spread_bucket"]["q4_tinggi"]["range"][1] == 0.8


def test_session_breakdown_full_metrics():
    trades = _trades([(0, 30, 50.0, 0.4)])
    trades[0]["session"] = "london"
    res = _summarize(trades)
    assert res["by_session"]["london"]["trades"] == 1
    assert res["by_session"]["london"]["net_usd"] == 50.0
    assert res["by_session"]["london"]["expectancy_usd"] == 50.0
    # kompatibilitas: entries_by_session tetap berbentuk hitungan
    assert res["entries_by_session"] == {"london": 1}


def test_rejections_summary():
    res = _summarize(_trades([(0, 30, 50.0, 0.4)]),
                     rejections=[{"reason": "SPREAD_TOO_WIDE"},
                                 {"reason": "SPREAD_TOO_WIDE"},
                                 {"reason": "REQUOTE_GAP"}])
    assert res["rejections"]["total"] == 3
    assert res["rejections"]["by_reason"] == {"SPREAD_TOO_WIDE": 2, "REQUOTE_GAP": 1}


def test_execution_model_in_summary():
    ex = ExecutionModel(fill_delay_bars=1)
    res = _summarize(_trades([(0, 30, 50.0, 0.4)]), execution=ex, swap_total=-5.6)
    assert res["execution"]["fill_delay_bars"] == 1
    assert res["swap_total_usd"] == -5.6
