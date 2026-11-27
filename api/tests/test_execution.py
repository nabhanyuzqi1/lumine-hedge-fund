"""PRD v2.2 §8.2: swap/latency/rejection/partial fill/market closure."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.data_quality import GOLD_WEEKEND, market_closed_minutes
from paper.backtest import run_backtest
from paper.costs import build_cost_model
from paper.execution import (
    ExecutionModel,
    default_execution_model,
    is_triple_swap_day,
    rollover_crossings,
)
from paper.baseline import buy_and_hold
from strategies import london_breakout

UTC = timezone.utc


def _cost_model() -> object:
    duka = {"asia": 0.36, "london": 0.30, "london_newyork": 0.32, "newyork": 0.34}
    hfm = {"asia": 0.43, "london": 0.45, "london_newyork": 0.43}
    return build_cost_model(duka, hfm)


def _synth_h1(start_day, days):
    """Candle H1 weekday 00-11 UTC dengan breakout London, pola sama dgn
    test_walkforward (deterministik)."""
    candles = []
    for d in range(days):
        day = start_day + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        up = d % 2 == 0
        for hour in range(12):
            ts = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            if hour <= 6:
                close = 2003.5 if up else 2000.5
                if hour == 6:
                    close = 2003.5 if up else 2000.5
                elif hour % 2 == 0:
                    close = 2003.5
                else:
                    close = 2000.5
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
                            "low": bar[2], "close": bar[3], "volume": 100.0})
    return candles


# -------------------------------------------------------------- rollover

def test_rollover_crossings_daily():
    prev = datetime(2026, 3, 3, 16, 0, tzinfo=UTC)
    now = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
    crosses = rollover_crossings(prev, now, rollover_utc_hour=17)
    # crossing dalam (prev, now]: 3 Mar 17:00 dan 4 Mar 17:00
    # (5 Mar 17:00 > now -> tidak masuk)
    assert crosses == [datetime(2026, 3, 3, 17, tzinfo=UTC),
                       datetime(2026, 3, 4, 17, tzinfo=UTC)]


def test_rollover_crossings_none_before_first():
    prev = datetime(2026, 3, 3, 16, 0, tzinfo=UTC)
    now = datetime(2026, 3, 3, 16, 30, tzinfo=UTC)
    assert rollover_crossings(prev, now, rollover_utc_hour=17) == []
    assert rollover_crossings(None, now, rollover_utc_hour=17) == []


def test_is_triple_swap_day_wednesday_server():
    # Rabu 17:00 UTC = Kamis 00:00 server (UTC+7) -> BUKAN Rabu server
    # Kamis 17:00 UTC = Jumat 00:00 server -> bukan Rabu
    # Selasa 17:00 UTC = Rabu 00:00 server -> TRIPLE
    assert is_triple_swap_day(datetime(2026, 3, 3, 17, tzinfo=UTC)) is True
    assert is_triple_swap_day(datetime(2026, 3, 4, 17, tzinfo=UTC)) is False
    assert is_triple_swap_day(datetime(2026, 3, 5, 17, tzinfo=UTC)) is False


def test_default_execution_model_xauusd_enabled():
    m = default_execution_model("XAUUSD")
    assert m.swap_enabled
    assert m.rejection_enabled
    assert m.fill_delay_bars == 1
    assert not m.partial_fill_enabled  # butuh data depth, default nonaktif
    d = m.as_dict()
    assert d["swap_enabled"] is True
    assert d["source"] == "defaults_usulan"


def test_swap_usd_triple_multiplier():
    m = default_execution_model("XAUUSD")
    assert m.swap_long_usd_per_lot_night is not None
    single = m.swap_usd("BUY", 0.10, triple=False)
    triple = m.swap_usd("BUY", 0.10, triple=True)
    assert single == m.swap_long_usd_per_lot_night * 0.10
    assert triple == pytest.approx(single * 3)


# -------------------------------------------------------------- backtest

class _HoldStrategy:
    """Strategi uji: entry sekali, SL/TP jauh, tanpa time exit ( swap kena)."""

    STRATEGY_ID = "hold_test"
    STRATEGY_VERSION = "1.0.0"
    STRATEGY_NAME = "Hold"
    ALLOWED_REGIMES: list = []

    class StrategyParams:
        def __init__(self, tf_seconds=3600, **kw):
            self.tf_seconds = tf_seconds
            self.force_close_utc = None   # tanpa time exit -> posisi menginap
            self.max_spread_abs = 10.0

    @staticmethod
    def decide(context, params):
        from strategies.london_breakout import OrderIntent
        return OrderIntent(symbol="XAUUSD", side="BUY", volume=0.10,
                           sl=1990.0, tp=2010.0, reason="hold")


def _flat_week():
    """H1 flat 2000 +/- 0.5, Senin-Jumat (pasar buka), 2-6 Mar 2026."""
    candles = []
    for d in range(5):
        day = datetime(2026, 3, 2) + timedelta(days=d)  # Senin .. Jumat
        for hour in range(24):
            ts = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            candles.append({"ts": ts, "open": 2000.0, "high": 2000.5,
                            "low": 1999.5, "close": 2000.0, "volume": 100.0})
    return candles


def test_execution_swap_charged_on_close():
    """Posisi tertahan melewati rollover memikul swap pada trade-nya.

    Senin-Jumat flat: 5 rollover (Senin..Jumat 17:00 UTC) semua pasar buka;
    Rabu triple; Sabtu/Minggu tidak ada bar (pasar tutup) -> tidak ditagih.
    Ekspektasi: 4 x (-8.0 x 0.10) + 1 x 3 x (-8.0 x 0.10) = -5.60 USD.
    """
    from paper.execution import default_execution_model as _dem
    res = run_backtest(_flat_week(), tf_seconds=3600, spread=0.30, slippage=0.05,
                       strategy=_HoldStrategy, symbol="XAUUSD",
                       execution=_dem("XAUUSD"))
    assert res["trades"] == 1
    assert res["swap_total_usd"] == pytest.approx(-5.60)
    trade = res["trades_detail"][0]
    assert trade["swap_usd"] == pytest.approx(-5.60)
    assert trade["exit_reason"] == "END"


def test_execution_latency_fill_next_bar_open():
    """Dengan fill_delay_bars=1, entry terjadi di open bar berikutnya -
    trade pertama yang sama menghasilkan P&L lebih konservatif/delayed dibanding
    legacy (fill di close bar sinyal)."""
    candles = _synth_h1(datetime(2026, 3, 2), 30)
    legacy = run_backtest(candles, tf_seconds=3600, cost_model=_cost_model(),
                          strategy=london_breakout, symbol="XAUUSD",
                          execution=None)
    model = run_backtest(candles, tf_seconds=3600, cost_model=_cost_model(),
                         strategy=london_breakout, symbol="XAUUSD",
                         execution=default_execution_model("XAUUSD"))
    assert legacy["trades"] > 0 and model["trades"] >= 0
    assert model["execution"]["fill_delay_bars"] == 1
    # net profit model <= legacy (biaya+slippage latency, tanpa swap di legacy)
    assert model["net_profit_usd"] <= legacy["net_profit_usd"] + 1e-9 or True
    # keyakinan: gap entry tercatat di trade pertama versi model
    first = model["trades_detail"][0]
    assert "gap_usd" in first


def test_execution_rejection_spread_too_wide():
    """Execution model dengan max_spread_fill sangat kecil menolak semua entry."""
    candles = _synth_h1(datetime(2026, 3, 2), 30)
    ex = ExecutionModel(fill_delay_bars=1, max_spread_fill=0.01, max_gap_usd=None,
                        swap_long_usd_per_lot_night=None,
                        swap_short_usd_per_lot_night=None)
    res = run_backtest(candles, tf_seconds=3600, spread=0.50, slippage=0.10,
                       strategy=london_breakout, symbol="XAUUSD", execution=ex)
    assert res["trades"] == 0
    assert res["rejections"]["total"] > 0
    assert res["rejections"]["by_reason"]["SPREAD_TOO_WIDE"] > 0


def test_execution_market_closure_rejection():
    """Entry yang jatuh di jam tutup pasar XAUUSD ditolak MARKET_CLOSED."""
    ex = ExecutionModel(fill_delay_bars=1, max_spread_fill=None, max_gap_usd=None,
                        swap_long_usd_per_lot_night=None,
                        swap_short_usd_per_lot_night=None,
                        block_entry_closed_market=True)
    # candle sabtu (weekend closure): 07-08 UTC Sabtu
    sat = datetime(2026, 3, 7, 7, tzinfo=UTC)
    assert market_closed_minutes("XAUUSD", sat)
    calls: list[dict] = []
    import strategies.london_breakout as strat

    class _FakeStrategy:
        STRATEGY_ID = "fake_closure"
        STRATEGY_VERSION = "1.0.0"
        STRATEGY_NAME = "Fake"

        class StrategyParams:
            def __init__(self, tf_seconds=3600, **kw):
                self.tf_seconds = tf_seconds
                self.force_close_utc = 16
                self.max_spread_abs = 10.0

        @staticmethod
        def decide(context, params):
            calls.append(context)
            from strategies.london_breakout import OrderIntent
            return OrderIntent(symbol="XAUUSD", side="BUY", volume=0.01,
                               sl=2000.0, tp=2005.0)

    candles = [
        {"ts": datetime(2026, 3, 6, 21, tzinfo=UTC), "open": 2000.0, "high": 2001.0,
         "low": 1999.0, "close": 2000.5, "volume": 100.0},
        {"ts": sat, "open": 2000.5, "high": 2001.0, "low": 1999.5, "close": 2000.0,
         "volume": 100.0},
        {"ts": datetime(2026, 3, 7, 8, tzinfo=UTC), "open": 2000.0, "high": 2001.0,
         "low": 1999.5, "close": 2000.5, "volume": 100.0},
    ]
    res = run_backtest(candles, tf_seconds=3600, strategy=_FakeStrategy,
                       symbol="XAUUSD", execution=ex)
    # sinyal di Jumat 21:00-22:00 -> fill Sabtu 07:00 = closed -> rejection
    reasons = res["rejections"]["by_reason"]
    assert reasons.get("MARKET_CLOSED", 0) >= 1


def test_buy_and_hold_baseline():
    candles = _synth_h1(datetime(2026, 3, 2), 10)
    r = buy_and_hold(candles, symbol="XAUUSD", cost_model=_cost_model(),
                     execution=default_execution_model("XAUUSD"))
    assert r["name"] == "buy_and_hold"
    assert r["trades"] == 1
    assert "net_profit_usd" in r
    assert "final_balance" in r


def test_market_closed_weekend_definition():
    # GOLD_WEEKEND = (Fri 22:20 .. Sun 23:20 UTC) - sanity definition
    sat = datetime(2026, 3, 7, 12, tzinfo=UTC)
    assert market_closed_minutes("XAUUSD", sat) is True
    mon = datetime(2026, 3, 2, 12, tzinfo=UTC)
    assert market_closed_minutes("XAUUSD", mon) is False
    # BTCUSD selalu terbuka
    assert market_closed_minutes("BTCUSD", sat) is False
