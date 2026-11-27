"""Contract + logic tests: BTCUSD 24/7 range breakout (Fund2 PRD 5.3).

Run:
    cd ~/fund2/api && env -u DATABASE_URL TELEGRAM_ALERTS_OFF=1 \
        .venv/bin/python -m pytest -q tests/test_btc_range_breakout.py
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from strategies.btc_range_breakout import (
    BTCUSD_USD_PER_LOT_PER_USD,
    STRATEGY_ID,
    OrderIntent,
    StrategyParams,
    decide,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 23, 8, 0, 0, tzinfo=UTC)  # Monday
BASE = 60000.0

BANNED_TOKENS = (
    "datetime.now(",  # clock
    "utcnow(",  # clock
    "time.time(",  # clock
    "random",  # RNG
    "open(",  # file I/O
    "requests.",  # HTTP I/O
    "urllib",  # HTTP I/O
)


def _bar(ts: datetime, *, o=BASE, h=60100.0, l=59900.0, c=BASE) -> dict:
    return {"ts": ts.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": 0}


def make_context(**overrides) -> dict:
    """40 bar H1 (39 bar biasa + 1 bar pemicu breakout BUY), berakhir `now`.

    Bar biasa: range 200 (high 60100, low 59900, close 60000) -> ATR ~214.
    Channel 24 bar sebelum pemicu: [59900, 60100]; close pemicu 60300 >
    60100 + 50 buffer, close sebelumnya 60000 masih di dalam channel.
    """
    bars = [_bar(NOW - timedelta(hours=40 - i)) for i in range(39)]
    bars.append(_bar(NOW - timedelta(hours=1), o=BASE, h=60350.0, l=59950.0, c=60300.0))
    ctx = {
        "symbol": "BTCUSD",
        "now": NOW.isoformat(),
        "candles": bars,
        "liquidity": {
            "ts": NOW.isoformat(),
            "bid": 60280.0,
            "ask": 60320.0,
            "spread": 40.0,
            "spread_median_15m": 39.0,
            "fresh": True,
        },
        "positions": [],
        "trades_today": 0,
        "risk": {
            "equity": 10000.0,
            "risk_per_trade": 0.005,
            "max_volume": 0.10,
            "max_spread": 100.0,
        },
    }
    ctx.update(overrides)
    return ctx


# ---------------------------------------------------------------- kontrak


def test_identity_declared():
    assert STRATEGY_ID == "btc_range_breakout"
    assert StrategyParams().usd_per_lot_per_usd == 1.0  # 1 lot = 1 BTC (t_f2mp1)


def test_frozen_dataclasses():
    intent = OrderIntent("BTCUSD", "BUY", 0.01, 1.0, 2.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(intent, "volume", 0.02)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(StrategyParams(), "max_volume", 0.20)


def test_pure_module_source():
    """Heuristic: modul strategi tidak boleh menyembunyikan I/O / jam / RNG."""
    import strategies.btc_range_breakout as mod

    src = inspect.getsource(mod)
    for token in BANNED_TOKENS:
        assert token not in src, f"purity: token terlarang {token!r} di modul strategi"


def test_context_not_mutated():
    ctx = make_context()
    frozen = copy.deepcopy(ctx)
    decide(ctx)
    assert ctx == frozen, "decide() memutasi context; context wajib read-only"


def test_deterministic():
    a = decide(make_context())
    b = decide(make_context())
    assert a == b


def test_returns_none_or_valid_intent():
    intent = decide(make_context())
    if intent is None:
        return
    assert isinstance(intent, OrderIntent)
    assert intent.side in {"BUY", "SELL"}
    assert intent.volume > 0
    assert intent.sl > 0 and intent.tp > 0, "SL/TP wajib (risk gate)"
    assert intent.symbol == "BTCUSD"


# ---------------------------------------------------------------- guard standar


@pytest.mark.parametrize(
    "override",
    [
        {"candles": []},
        {"liquidity": {**make_context()["liquidity"], "fresh": False}},
        {"positions": [{"ticket": 1}]},
        {"trades_today": 1},
    ],
)
def test_standard_guards_block(override):
    assert decide(make_context(**override)) is None


def test_stale_candle_blocked():
    # bar terakhir close 07:00; now 08:05 -> umur bar 65 menit > 120 detik
    ctx = make_context(now="2026-11-23T08:05:00+00:00",
                       liquidity={**make_context()["liquidity"],
                                  "ts": "2026-11-23T08:05:00+00:00"})
    assert decide(ctx) is None


def test_unclosed_candle_blocked():
    # bar terakhir close tepat `now` + 1 jam -> belum closed
    ctx = make_context(now="2026-11-23T07:00:00+00:00")
    assert decide(ctx) is None


def test_spread_filter_blocks_wide_spread():
    # gate = max(2 x median 39, abs 100) = 100; spread 150 > 100 -> tolak
    ctx = make_context(liquidity={**make_context()["liquidity"], "spread": 150.0})
    assert decide(ctx) is None


def test_spread_filter_allows_calibrated_spread():
    # spread 40 ~ median; gate 100 -> lolos
    ctx = make_context(liquidity={**make_context()["liquidity"], "spread": 40.0})
    assert decide(ctx) is not None


def test_weekend_allowed_by_default_btc_247():
    """Crypto jalan terus: Sabtu tetap entry (beda dengan strategi XAUUSD)."""
    saturday = datetime(2026, 11, 21, 8, 0, 0, tzinfo=UTC)
    assert saturday.weekday() == 5
    bars = [_bar(saturday - timedelta(hours=40 - i)) for i in range(39)]
    bars.append(_bar(saturday - timedelta(hours=1), h=60350.0, l=59950.0, c=60300.0))
    ctx = make_context(now=saturday.isoformat(), candles=bars,
                       liquidity={**make_context()["liquidity"], "ts": saturday.isoformat()})
    assert decide(ctx) is not None


def test_weekend_blocked_when_reject_weekend_true():
    saturday = datetime(2026, 11, 21, 8, 0, 0, tzinfo=UTC)
    bars = [_bar(saturday - timedelta(hours=40 - i)) for i in range(39)]
    bars.append(_bar(saturday - timedelta(hours=1), h=60350.0, l=59950.0, c=60300.0))
    ctx = make_context(now=saturday.isoformat(), candles=bars,
                       liquidity={**make_context()["liquidity"], "ts": saturday.isoformat()})
    assert decide(ctx, StrategyParams(reject_weekend=True)) is None


# ---------------------------------------------------------------- logika entry


def test_buy_breakout_fires():
    intent = decide(make_context())
    assert intent is not None and intent.side == "BUY"
    atr = (13 * 200.0 + 400.0) / 14  # 13 bar biasa + TR bar pemicu 400
    expected_dist = 1.5 * atr  # 321.43
    assert intent.sl_distance == pytest.approx(round(expected_dist, 2))
    assert intent.sl == pytest.approx(round(60300.0 - expected_dist, 2))
    assert intent.tp == pytest.approx(round(60300.0 + 1.5 * expected_dist, 2))
    # sizing: 50 USD risk / (321.43 x 1) = 0.1556 -> floor 0.15 -> cap 0.10 (PRD 5.6)
    assert intent.volume == pytest.approx(0.10)
    assert intent.risk_usd == 50.0
    assert "BUY" in intent.reason and "breakout" in intent.reason


def test_sell_breakout_fires():
    bars = [_bar(NOW - timedelta(hours=40 - i)) for i in range(39)]
    bars.append(_bar(NOW - timedelta(hours=1), o=BASE, h=60050.0, l=59550.0, c=59600.0))
    ctx = make_context(candles=bars,
                       liquidity={**make_context()["liquidity"],
                                  "bid": 59580.0, "ask": 59620.0})
    intent = decide(ctx)
    assert intent is not None and intent.side == "SELL"
    atr = (13 * 200.0 + 500.0) / 14
    expected_dist = 1.5 * atr
    assert intent.sl_distance == pytest.approx(round(expected_dist, 2))
    assert intent.sl == pytest.approx(round(59600.0 + expected_dist, 2))
    assert intent.tp == pytest.approx(round(59600.0 - 1.5 * expected_dist, 2))


def test_no_fire_inside_channel():
    # close 60050 masih di dalam channel + buffer (60150)
    bars = [_bar(NOW - timedelta(hours=40 - i)) for i in range(39)]
    bars.append(_bar(NOW - timedelta(hours=1), c=60050.0))
    assert decide(make_context(candles=bars)) is None


def test_no_fire_when_prev_close_already_outside():
    # close sebelumnya sudah di atas channel -> bukan breakout pertama
    bars = [_bar(NOW - timedelta(hours=40 - i)) for i in range(38)]
    bars.append(_bar(NOW - timedelta(hours=2), c=60300.0))   # prev: di luar channel
    bars.append(_bar(NOW - timedelta(hours=1), c=60500.0))   # pemicu
    assert decide(make_context(candles=bars)) is None


def test_atr_floor_blocks_dead_market():
    bars = []
    for i in range(39):
        bars.append(_bar(NOW - timedelta(hours=40 - i), h=BASE + 15.0, l=BASE - 15.0))
    bars.append(_bar(NOW - timedelta(hours=1), h=BASE + 80.0, l=BASE - 80.0, c=BASE + 100.0))
    # ATR ~30 + pemicu; jauh di bawah atr_min 150 -> tidak entry
    assert decide(make_context(candles=bars)) is None


def test_atr_ceiling_blocks_extreme_volatility():
    bars = []
    for i in range(39):
        bars.append(_bar(NOW - timedelta(hours=40 - i), h=BASE + 1200.0, l=BASE - 1200.0))
    bars.append(_bar(NOW - timedelta(hours=1), h=BASE + 1400.0, l=BASE - 1400.0, c=BASE + 1200.0))
    # ATR ~2400 > atr_max 900 -> tidak entry
    assert decide(make_context(candles=bars)) is None


def test_sl_distance_above_gate_blocked():
    # atr_sl_mult 5.0 x ATR 214 = 1071 > max 1000 -> tidak entry
    params = StrategyParams(atr_sl_mult=5.0)
    assert decide(make_context(), params) is None


def test_volume_below_minimum_blocked():
    ctx = make_context(risk={**make_context()["risk"], "equity": 100.0})
    assert decide(ctx) is None


def test_volume_capped_at_max():
    ctx = make_context(risk={**make_context()["risk"], "equity": 100000.0})
    intent = decide(ctx)
    assert intent is not None
    assert intent.volume == 0.10  # cap PRD 5.6 (settings max_volume 0.10)


def test_insufficient_history_blocked():
    bars = [_bar(NOW - timedelta(hours=20 - i)) for i in range(20)]
    assert decide(make_context(candles=bars)) is None


def test_btc_contract_size_constant():
    assert BTCUSD_USD_PER_LOT_PER_USD == 1.0
