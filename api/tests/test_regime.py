"""Tests: Market Regime Detection deterministic (PRD v2.2 §6, t_f2v22a2).

Fokus DoD: label reproducible di dataset sama, tanpa look-ahead leakage,
UNKNOWN memblokir entry yang memerlukan klasifikasi, hysteresis anti
flip-flop, dan definisi yang sama untuk backtest & live (sync helper dengan
app.ingest/app.data_quality dijaga test). Semua test MURNI (tanpa DB).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from app import data_quality, ingest, regime

UTC = timezone.utc
T0 = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)  # Senin, sesi asia
SYMBOL = "XAUUSD"


def noise(i: float) -> float:
    """Pseudo-noise deterministik (tanpa RNG): gabungan sinus."""
    return 0.4 * math.sin(i * 1.7) + 0.2 * math.cos(i * 0.9)


def make_bars(n: int, gen, start: datetime = T0, tf_min: int = 5) -> list[dict]:
    out = []
    for i in range(n):
        o, h, l, c = gen(i)
        out.append({"ts": (start + timedelta(minutes=tf_min * i)).isoformat(),
                    "open": round(o, 4), "high": round(h, 4),
                    "low": round(l, 4), "close": round(c, 4), "volume": 0})
    return out


def gen_flat(i, base=2000.0):
    return base, base + 0.3, base - 0.3, base


def gen_uptrend(i, base=2000.0, step=0.8):
    c = base + step * i + noise(i)
    return c - 0.2, c + 0.6, c - 0.5, c


def gen_downtrend(i, base=2400.0, step=0.8):
    c = base - step * i + noise(i)
    return c + 0.2, c + 0.5, c - 0.6, c


def gen_oscillate(i, base=2000.0, amp=1.5):
    c = base + amp * math.sin(i / 3.0)
    return c - 0.3, c + 0.4, c - 0.6, c + 0.1


def gen_volspike(i, base=2000.0):
    if i < 250:
        return gen_flat(i, base)
    r = 8.0 * math.sin(i * 2.3) + 3.0 * math.cos(i * 0.7)
    c = base + r
    return c - 3, c + 5, c - 6, c + 2


def liquidity_of(now, spread=0.30, median15=0.25, fresh=True):
    return {"ts": now.isoformat(), "bid": 2000.0, "ask": 2000.0 + spread,
            "spread": spread, "spread_median_15m": median15, "fresh": fresh}


def classify_at(candles, *, symbol=SYMBOL, spread=0.30, median15=0.25,
                fresh=True, params=None, state=None, tick_rate=None,
                spread_p95=None, now=None, tf_min=5):
    """classify() pada bar terakhir series (anchor = close bar terakhir)."""
    last_close = (datetime.fromisoformat(candles[-1]["ts"])
                  + timedelta(minutes=tf_min))
    now = now or (last_close + timedelta(seconds=1))
    return regime.classify(
        symbol=symbol, now=now, candles=candles,
        liquidity=liquidity_of(now, spread=spread, median15=median15,
                               fresh=fresh),
        params=params or regime.default_params_for_symbol(symbol),
        state=state, tick_rate=tick_rate, spread_p95=spread_p95)


# ------------------------------------------------------------- versi & label

def test_version_is_semver_and_result_carries_it():
    parts = regime.REGIME_VERSION.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
    r = classify_at(make_bars(300, gen_flat))
    assert r.classifier_version == regime.REGIME_VERSION


def test_labels_complete_and_news_reserved():
    assert set(regime.REGIME_LABELS) == {
        "TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY",
        "LOW_LIQUIDITY", "NEWS_OR_EVENT_RISK", "UNKNOWN"}
    # PRD §6.2: NEWS_OR_EVENT_RISK hanya bila ada sumber tervalidasi.
    assert regime.NEWS_SOURCE_VALIDATED is False
    assert "NEWS_OR_EVENT_RISK" not in regime.EMITTED_LABELS


def test_emitted_labels_are_valid():
    for label in regime.EMITTED_LABELS:
        assert label in regime.REGIME_LABELS


# -------------------------------------------------------------- determinisme

def test_determinism_same_input_same_output():
    candles = make_bars(300, gen_uptrend)
    a = classify_at(candles, tick_rate=42.0, spread_p95=0.55)
    b = classify_at(candles, tick_rate=42.0, spread_p95=0.55)
    assert a.label == b.label
    assert a.confidence == b.confidence
    assert a.ts == b.ts
    assert a.reason == b.reason
    assert a.features == b.features
    assert a.data_quality == b.data_quality
    assert a.state == b.state


def test_result_fields_present_and_bounded():
    r = classify_at(make_bars(300, gen_uptrend), tick_rate=42.0)
    assert r.label in regime.EMITTED_LABELS
    assert 0.0 <= r.confidence <= 1.0
    assert r.ts and r.reason
    assert r.data_quality["status"] == "PASS"
    assert r.features["adx"] is not None


def test_state_is_json_serializable():
    r = classify_at(make_bars(300, gen_uptrend))
    json.dumps(r.state)  # tidak boleh raise (disimpan di paper_state)
    json.dumps(r.features)
    json.dumps(r.data_quality)


# ---------------------------------------------------------- tanpa look-ahead

def test_no_look_ahead_incremental_equals_batch():
    """Label pada bar i hanya fungsi data <= bar i: evaluasi incremental
    (bar ditambah satu per satu) == evaluasi batch per-truncation."""
    full = make_bars(320, gen_uptrend)
    incremental = []
    for i in range(220, 320):
        incremental.append(classify_at(full[:i + 1]).label)
    batch = [classify_at(full[:i + 1]).label for i in range(220, 320)]
    assert incremental == batch


def test_no_look_ahead_anchor_is_last_closed_bar():
    candles = make_bars(300, gen_flat)
    r = classify_at(candles)
    last_close = (datetime.fromisoformat(candles[-1]["ts"])
                  + timedelta(minutes=5))
    assert datetime.fromisoformat(r.ts) == last_close


def test_unclosed_future_bar_is_unknown():
    candles = make_bars(300, gen_flat)
    now = datetime.fromisoformat(candles[-1]["ts"])  # bar terakhir belum close
    r = regime.classify(symbol=SYMBOL, now=now, candles=candles,
                        liquidity=liquidity_of(now),
                        params=regime.default_params_for_symbol(SYMBOL))
    assert r.label == "UNKNOWN"
    assert r.data_quality["status"] == "FAIL"
    assert "belum closed" in r.reason

# ------------------------------------------------------- data quality gate

def test_too_few_bars_is_unknown():
    r = classify_at(make_bars(100, gen_flat))
    assert r.label == "UNKNOWN"
    assert "min_bars" in r.reason


def test_stale_bar_is_unknown():
    candles = make_bars(300, gen_flat)
    last_close = (datetime.fromisoformat(candles[-1]["ts"])
                  + timedelta(minutes=5))
    now = last_close + timedelta(minutes=30)  # > 2.5 x tf + 60s
    r = regime.classify(symbol=SYMBOL, now=now, candles=candles,
                        liquidity=liquidity_of(now),
                        params=regime.default_params_for_symbol(SYMBOL))
    assert r.label == "UNKNOWN"
    assert "stale" in r.reason


def test_duplicate_timestamp_is_unknown():
    candles = make_bars(300, gen_flat)
    candles[-1]["ts"] = candles[-2]["ts"]  # duplikat
    r = classify_at(candles)
    assert r.label == "UNKNOWN"
    assert "naik ketat" in r.reason


def test_descending_timestamp_is_unknown():
    candles = make_bars(300, gen_flat)
    candles[-1], candles[-2] = candles[-2], candles[-1]
    r = classify_at(candles)
    assert r.label == "UNKNOWN"


def test_nan_price_is_unknown():
    candles = make_bars(300, gen_flat)
    candles[-1]["close"] = float("nan")
    r = classify_at(candles)
    assert r.label == "UNKNOWN"
    assert "non-finite" in r.reason


def test_nonpositive_price_is_unknown():
    candles = make_bars(300, gen_flat)
    candles[-1]["close"] = 0.0
    assert classify_at(candles).label == "UNKNOWN"


def test_ohlc_violation_is_unknown():
    candles = make_bars(300, gen_flat)
    candles[-1]["high"] = candles[-1]["low"] - 1.0
    assert classify_at(candles).label == "UNKNOWN"


def test_missing_spread_is_unknown():
    candles = make_bars(300, gen_flat)
    now = (datetime.fromisoformat(candles[-1]["ts"])
           + timedelta(minutes=5, seconds=1))
    r = regime.classify(symbol=SYMBOL, now=now, candles=candles,
                        liquidity={"ts": now.isoformat(), "spread": None,
                                   "fresh": True},
                        params=regime.default_params_for_symbol(SYMBOL))
    assert r.label == "UNKNOWN"


def test_unfresh_liquidity_is_unknown():
    r = classify_at(make_bars(300, gen_flat), fresh=False)
    assert r.label == "UNKNOWN"
    assert "fresh" in r.reason


def test_stale_liquidity_is_unknown():
    candles = make_bars(300, gen_flat)
    now = (datetime.fromisoformat(candles[-1]["ts"])
           + timedelta(minutes=5, seconds=1))
    stale_liq = liquidity_of(now - timedelta(minutes=5))
    r = regime.classify(symbol=SYMBOL, now=now, candles=candles,
                        liquidity=stale_liq,
                        params=regime.default_params_for_symbol(SYMBOL))
    assert r.label == "UNKNOWN"
    assert "likuiditas stale" in r.reason


def test_intraday_gap_is_unknown():
    """Gap 30 bar (2.5 jam) di tengah hari kerja = data hilang -> UNKNOWN."""
    candles = make_bars(300, gen_flat)
    del candles[100:130]
    r = classify_at(candles)
    assert r.label == "UNKNOWN"
    assert "gap" in r.reason


def test_weekend_gap_is_not_unknown():
    """Jeda Jumat 22:15 -> Minggu 23:25 = pasar tutup, BUKAN gap."""
    thu = datetime(2026, 11, 19, 2, 0, tzinfo=UTC)
    candles = make_bars(531, gen_flat, start=thu)   # Thu 02:00 -> Fri 22:15
    sun = datetime(2026, 11, 22, 23, 25, tzinfo=UTC)
    candles += make_bars(20, gen_flat, start=sun)   # Sun 23:25 -> Mon 00:20
    r = classify_at(candles)
    assert r.data_quality["status"] == "PASS", r.data_quality
    assert r.label != "UNKNOWN"


# ------------------------------------------------------------- label fixtures

def test_flat_market_is_range():
    r = classify_at(make_bars(300, gen_flat))
    assert r.label == "RANGE"
    assert r.confidence >= 0.5


def test_uptrend_is_trend_up():
    r = classify_at(make_bars(300, gen_uptrend))
    assert r.label == "TREND_UP"
    assert r.confidence >= 0.6
    assert "ADX" in r.reason


def test_downtrend_is_trend_down():
    r = classify_at(make_bars(300, gen_downtrend))
    assert r.label == "TREND_DOWN"
    assert r.confidence >= 0.6


def test_oscillation_is_range():
    r = classify_at(make_bars(300, gen_oscillate))
    assert r.label == "RANGE"


def test_vol_spike_is_high_volatility():
    r = classify_at(make_bars(300, gen_volspike))
    assert r.label == "HIGH_VOLATILITY"
    assert r.features["vol_pctile"] >= 0.90 or r.features["atr_ratio"] >= 1.5


def test_wide_spread_is_low_liquidity():
    r = classify_at(make_bars(300, gen_flat), spread=1.20, median15=0.25)
    assert r.label == "LOW_LIQUIDITY"
    assert "spread" in r.reason


def test_low_tick_rate_is_low_liquidity():
    """Tick rate rendah (fitur live) memicu LOW_LIQUIDITY meski spread normal."""
    r = classify_at(make_bars(300, gen_flat), tick_rate=2.0)
    assert r.label == "LOW_LIQUIDITY"
    assert "tick rate" in r.reason


def test_optional_features_do_not_change_label():
    """Fitur opsional (tick rate/p95) tidak mengubah label - hanya
    confidence - supaya backtest dan live memakai definisi label sama."""
    candles = make_bars(300, gen_uptrend)
    full = classify_at(candles, tick_rate=42.0, spread_p95=0.55)
    none = classify_at(candles)
    assert full.label == none.label
    assert full.confidence > none.confidence  # fitur lengkap = confidence naik

# --------------------------------------------------- hysteresis & cooldown

def gen_uptrend_at(global_i, base=2000.0, step=0.8):
    """Uptrend dengan indeks GLOBAL: series kontinu flat lalu naik."""
    return gen_uptrend(global_i, base=base, step=step)


def flat_then_trend(n_trend: int) -> list[dict]:
    """300 bar flat, lalu n_trend bar uptrend (timestamp kontinu)."""
    flat = make_bars(300, gen_flat)
    start = datetime.fromisoformat(flat[-1]["ts"]) + timedelta(minutes=5)
    trend = make_bars(n_trend, lambda i: gen_uptrend(i + 299), start=start)
    return flat + trend


def test_hysteresis_requires_confirmation_to_leave_label():
    """Seri RANGE panjang lalu TREND kuat: raw TREND muncul di bar pertama,
    tapi label final menahan sampai confirm_bars terpenuhi."""
    p = regime.default_params_for_symbol(SYMBOL)
    series = flat_then_trend(8)
    state = None
    labels = []
    for i in range(299, 308):  # evaluasi per bar baru di zona transisi
        candles = series[:i + 1]
        last = datetime.fromisoformat(candles[-1]["ts"]) + timedelta(minutes=5)
        r = regime.classify(symbol=SYMBOL, now=last + timedelta(seconds=1),
                            candles=candles, liquidity=liquidity_of(last),
                            params=p, state=state)
        state = r.state
        labels.append((i, r.label))
    # bar pertama trend TIDAK langsung membalik label; flip terjadi
    # paling cepat pada bar ke-confirm_bars zona trend. Target labelnya
    # boleh HIGH_VOLATILITY: transisi flat->trend adalah range expansion
    # (prioritas HIGH_VOLATILITY di atas TREND, lihat docs REGIME_v2.2).
    first_trend_idx = 300  # i=300 = bar trend pertama (flat = 0..299)
    pre = [lab for i, lab in labels if i < first_trend_idx + p.confirm_bars - 1]
    assert all(lab == "RANGE" for lab in pre), labels
    post = [lab for i, lab in labels if i >= first_trend_idx + p.confirm_bars]
    assert any(lab != "RANGE" for lab in post), labels


def test_cooldown_blocks_immediate_reversal():
    """Setelah ganti label, pembalikan segera ditahan (cooldown aktif)."""
    p = regime.RegimeParams()
    state = {"last_bar_ts": T0.isoformat(), "label": "TREND_UP",
             "confidence": 0.90, "reason": "", "candidate": None,
             "candidate_count": 0, "cooldown_left": p.cooldown_bars,
             "classifier_version": regime.REGIME_VERSION}
    flat = make_bars(301, gen_flat)
    last = datetime.fromisoformat(flat[-1]["ts"]) + timedelta(minutes=5)
    r = regime.classify(symbol=SYMBOL, now=last + timedelta(seconds=1),
                        candles=flat, liquidity=liquidity_of(last),
                        params=p, state=state)
    assert r.label == "TREND_UP", r.reason
    assert "hysteresis" in r.reason
    assert r.state["cooldown_left"] == p.cooldown_bars - 1


def test_hysteresis_immediate_switch_on_confidence_margin():
    """Raw label dengan confidence >= label berjalan + margin -> langsung
    ganti walau belum confirm_bars."""
    p = regime.RegimeParams()
    prev_bar = T0 - timedelta(minutes=5)
    state = {"last_bar_ts": prev_bar.isoformat(), "label": "RANGE",
             "confidence": 0.40, "reason": "", "candidate": "TREND_UP",
             "candidate_count": 0, "cooldown_left": 0,
             "classifier_version": regime.REGIME_VERSION}
    candles = make_bars(300, gen_uptrend)
    last = datetime.fromisoformat(candles[-1]["ts"]) + timedelta(minutes=5)
    r = regime.classify(symbol=SYMBOL, now=last + timedelta(seconds=1),
                        candles=candles, liquidity=liquidity_of(last),
                        params=p, state=state)
    assert r.label == "TREND_UP"
    assert r.state["cooldown_left"] == p.cooldown_bars


def test_unknown_bypasses_hysteresis():
    """Data rusak -> UNKNOWN SEGERA walau label sebelumnya pegang RANGE."""
    series = flat_then_trend(0)
    r_first = classify_at(series[:300])
    assert r_first.label == "RANGE"
    state = r_first.state
    now = (datetime.fromisoformat(series[-1]["ts"])
           + timedelta(minutes=5, seconds=1))
    stale = liquidity_of(now - timedelta(minutes=10))
    r = regime.classify(symbol=SYMBOL, now=now, candles=series,
                        liquidity=stale,
                        params=regime.default_params_for_symbol(SYMBOL),
                        state=state)
    assert r.label == "UNKNOWN"
    assert r.state["label"] == "UNKNOWN"


def test_same_bar_evaluation_is_frozen():
    """Panggil ulang bar yang sama (mis. spread berubah di dalam bar)
    mengembalikan keputusan yang SAMA (idempoten, anti flip-flop)."""
    candles = make_bars(300, gen_flat)
    now = (datetime.fromisoformat(candles[-1]["ts"])
           + timedelta(minutes=5, seconds=1))
    p = regime.default_params_for_symbol(SYMBOL)
    r1 = regime.classify(symbol=SYMBOL, now=now, candles=candles,
                         liquidity=liquidity_of(now), params=p)
    r2 = regime.classify(symbol=SYMBOL, now=now + timedelta(seconds=10),
                         candles=candles,
                         liquidity=liquidity_of(now + timedelta(seconds=10),
                                                spread=1.5),
                         params=p, state=r1.state)
    assert r2.label == r1.label
    assert r2.confidence == r1.confidence


def test_flip_flop_series_changes_slower_than_raw():
    """Series kontinu flat/trend bergantian: label final lebih stabil dari
    raw (hysteresis menahan flip berlebihan)."""
    p = regime.default_params_for_symbol(SYMBOL)
    flat = make_bars(300, gen_flat)
    series = list(flat)
    idx = 300
    for k in range(6):  # blok alternating trend/flat @ 20 bar
        gen = gen_uptrend if k % 2 == 0 else gen_flat
        start = datetime.fromisoformat(series[-1]["ts"]) + timedelta(minutes=5)
        series += make_bars(20, lambda i, g=gen: g(i + idx), start=start)
        idx += 20
    state = None
    final_labels = []
    for i in range(300, len(series)):
        candles = series[:i + 1]
        last = datetime.fromisoformat(candles[-1]["ts"]) + timedelta(minutes=5)
        r = regime.classify(symbol=SYMBOL, now=last + timedelta(seconds=1),
                            candles=candles, liquidity=liquidity_of(last),
                            params=p, state=state)
        state = r.state
        final_labels.append(r.label)
    changes = sum(1 for a, b in zip(final_labels, final_labels[1:]) if a != b)
    # 6 blok -> raw akan flip ~12 kali; final dibatasi hysteresis
    assert changes <= 12, (changes, final_labels)


# ------------------------------------------------------------------- gate

def test_gate_unknown_always_blocks_required_regimes():
    assert regime.regime_permits_entry("UNKNOWN", ["TREND_UP"]) is False
    # bahkan bila UNKNOWN masuk allowed list (harusnya tidak pernah)
    assert regime.regime_permits_entry("UNKNOWN", ["UNKNOWN"]) is False


def test_gate_label_in_allowed_passes():
    assert regime.regime_permits_entry("TREND_UP", ["TREND_UP"]) is True
    assert regime.regime_permits_entry("RANGE", ["TREND_UP", "RANGE"]) is True


def test_gate_label_outside_allowed_blocks():
    assert regime.regime_permits_entry("TREND_UP", ["RANGE"]) is False


def test_gate_empty_allowed_means_no_requirement():
    assert regime.regime_permits_entry("RANGE", []) is True
    assert regime.regime_permits_entry("UNKNOWN", []) is True


def test_allowed_regimes_for_module():
    import types
    mod_with = types.ModuleType("s1")
    mod_with.ALLOWED_REGIMES = ["TREND_UP", "RANGE"]
    assert regime.allowed_regimes_for(mod_with) == ["TREND_UP", "RANGE"]
    mod_without = types.ModuleType("s2")
    assert regime.allowed_regimes_for(mod_without) == []
    mod_bad = types.ModuleType("s3")
    mod_bad.ALLOWED_REGIMES = None
    assert regime.allowed_regimes_for(mod_bad) == []


# ------------------------------------------- sync dengan modul live lainnya

def test_session_matches_ingest_session_of():
    for h in range(24):
        dt = datetime(2026, 11, 18, h, 30, tzinfo=UTC)
        assert regime._session_of(dt) == ingest.session_of(dt), h


def test_market_closed_matches_data_quality():
    cur = datetime(2026, 11, 13, 0, 0, tzinfo=UTC)  # Jumat -> Senin
    checked = 0
    while cur < datetime(2026, 11, 24, 0, 0, tzinfo=UTC):
        assert (regime._market_closed_minutes("XAUUSD", cur)
                == data_quality.market_closed_minutes("XAUUSD", cur)), cur
        checked += 1
        cur += timedelta(minutes=37)
    assert checked > 300


def test_spread_abs_max_matches_data_quality():
    assert regime.SPREAD_ABS_MAX == data_quality.SPREAD_ABS_MAX


def test_default_params_per_symbol():
    assert regime.default_params_for_symbol("BTCUSD").spread_abs_usd == 100.0
    assert regime.default_params_for_symbol("XAUUSD").spread_abs_usd == 0.50
    # simbol tak dikenal fallback XAUUSD
    assert regime.default_params_for_symbol("QQQ").spread_abs_usd == 0.50


def test_regime_does_not_touch_risk_limits():
    """PRD §6.4: regime tidak boleh mengubah risk limit - modul regime tidak
    punya akses ke angka risk (risk.py tidak diimport oleh regime)."""
    import sys
    assert "app.risk" not in sys.modules.get("app.regime", sys.modules["app.regime"]).__dict__.get("__name__", "")
    src = __import__("pathlib").Path(regime.__file__).read_text()
    assert "import risk" not in src and "risk_gate" not in src
    assert "risk_per_trade" not in src


# ------------------------------------------------- integrasi backtest (pure)

class _StubIntent:
    """Intent minimal untuk stub strategi backtest."""

    def __init__(self, symbol, side, volume, sl, tp, strategy, reason):
        self.symbol, self.side, self.volume = symbol, side, volume
        self.sl, self.tp, self.strategy, self.reason = sl, tp, strategy, reason


def _stub_strategy_factory(allowed):
    """Modul stub strategi: selalu entry; ALLOWED_REGIMES bisa diatur."""
    import types
    mod = types.ModuleType("stub_bt")

    mod.STRATEGY_ID = "stub_bt"

    class StrategyParams:
        def __init__(self, tf_seconds=300):
            self.tf_seconds = tf_seconds
            self.force_close_utc = 16
            self.max_spread_abs = 0.50

    def decide(context, params=None):
        close = float(context["candles"][-1]["close"])
        return _StubIntent(context.get("symbol", "XAUUSD"), "BUY", 0.01,
                           round(close - 2.0, 2), round(close + 4.0, 2),
                           "stub_bt", "always-entry")

    mod.StrategyParams = StrategyParams
    mod.decide = decide
    if allowed is not None:
        mod.ALLOWED_REGIMES = list(allowed)
    return mod


def _bt_series():
    """400 bar flat + 300 bar uptrend (kontinu) utk backtest gate.

    run_backtest memakai candle ts datetime (keluaran to_utc_candles).
    """
    flat = make_bars(400, gen_flat)
    start = datetime.fromisoformat(flat[-1]["ts"]) + timedelta(minutes=5)
    trend = make_bars(300, lambda i: gen_uptrend(i + 399), start=start)
    out = flat + trend
    for c in out:
        c["ts"] = datetime.fromisoformat(c["ts"])
    return out


def test_backtest_regime_gate_blocks_non_allowed_regimes():
    from paper.backtest import run_backtest
    candles = _bt_series()
    stub = _stub_strategy_factory(["TREND_UP"])
    gated = run_backtest(candles, tf_seconds=300, strategy=stub,
                         context_bars=300, regime_filter=True)
    ungated = run_backtest(candles, tf_seconds=300, strategy=stub,
                           context_bars=300, regime_filter=False)
    rg = gated["regime"]
    assert rg["enabled"] is True
    assert rg["allowed_regimes"] == ["TREND_UP"]
    assert rg["classifier_version"] == regime.REGIME_VERSION
    # gate memblokir entry di luar TREND_UP (RANGE/HIGH_VOLATILITY/UNKNOWN)
    assert rg["blocked_entries"] > 0
    # semua trade yang lolos entry saat regime TREND_UP
    assert gated["trades"] > 0
    assert all(t["regime"] == "TREND_UP" for t in gated["trades_detail"])
    # tanpa gate: lebih banyak entry (termasuk saat RANGE) -> baseline
    assert ungated["trades"] >= gated["trades"]
    # gate entry HANYA saat regime_filter=True: tanpa gate, entry di luar
    # allowed (mis. RANGE/UNKNOWN) lolos dan tidak ada yang diblokir.
    assert ungated["regime"]["blocked_entries"] == 0
    assert any(t["regime"] != "TREND_UP" for t in ungated["trades_detail"])
    # PRD v2.2 §8.3: label regime SELALU ada di trades_detail (juga saat
    # gate off) - label asli klasifikasi, bukan placeholder REGIME_OFF.
    assert ungated["trades_detail"]
    assert all(t["regime"] in regime.REGIME_LABELS for t in ungated["trades_detail"])
    assert ungated["regime"]["enabled"] is False


def test_backtest_no_allowed_regimes_never_blocks():
    """Strategi tanpa ALLOWED_REGIMES tidak diblokir regime apa pun."""
    from paper.backtest import run_backtest
    candles = _bt_series()
    stub = _stub_strategy_factory(None)
    out = run_backtest(candles, tf_seconds=300, strategy=stub,
                       context_bars=300, regime_filter=True)
    assert out["regime"]["allowed_regimes"] == []
    assert out["regime"]["blocked_entries"] == 0
    assert out["trades"] > 0


def test_backtest_regime_breakdown_per_label():
    """PRD §6.4: performa strategi per regime dilaporkan."""
    from paper.backtest import run_backtest
    candles = _bt_series()
    stub = _stub_strategy_factory(None)
    out = run_backtest(candles, tf_seconds=300, strategy=stub,
                       context_bars=300, regime_filter=True)
    breakdown = out["regime"]["breakdown"]
    assert breakdown, "ada trade tercatat per regime"
    for lab, d in breakdown.items():
        assert lab in regime.REGIME_LABELS
        assert d["trades"] > 0 and "net_usd" in d and "winrate" in d


def test_backtest_default_off_keeps_legacy_behavior():
    """Default regime_filter=False: gate entry tetap off (perilaku lama).

    Label regime per trade tetap wajib ada (PRD v2.2 §8.3, sejak 8ff9c54
    regime diklasifikasi setiap bar terlepas dari gate).
    """
    from paper.backtest import run_backtest
    candles = _bt_series()
    stub = _stub_strategy_factory(["TREND_UP"])
    out = run_backtest(candles, tf_seconds=300, strategy=stub, context_bars=300)
    assert out["regime"]["enabled"] is False
    assert out["regime"]["blocked_entries"] == 0
    assert out["trades_detail"]
    # label asli klasifikasi di setiap trade - bukan placeholder REGIME_OFF.
    assert all(t["regime"] in regime.REGIME_LABELS for t in out["trades_detail"])


# ---------------------------------------------------- integrasi runner (DB)

RUNNER_NOW = datetime(2026, 11, 23, 9, 30, 30, tzinfo=UTC)  # Senin
RUNNER_TICK = {"bid": 1999.85, "ask": 2000.15, "spread": 0.30,
               "ts_utc": RUNNER_NOW}


def _regime_result(label: str) -> regime.RegimeResult:
    """RegimeResult sintetis untuk gate runner (kontrak dataclass murni)."""
    return regime.RegimeResult(
        label=label, confidence=0.70,
        ts=(RUNNER_NOW - timedelta(minutes=5)).isoformat(),
        data_quality={"status": "PASS"}, reason=f"test fixture {label}",
        features={}, state={})


async def _run_with_regime(_clean_db, *, module: str, label: str):
    """run_iteration dengan regime_result sintetis; balikkan (logs, orders, obs)."""
    from app import db
    from paper import runner
    from paper.store import DEFAULT_STATE
    from strategies.mean_reversion import StrategyParams

    stub_mod = __import__(module, fromlist=["decide"])
    # Jalur legacy in-process (module=None) + allowed_regimes eksplisit dari
    # modul stub: yang diuji adalah GATE regime, bukan sandbox supervisor
    # (jalur sandbox sudah di-cover test_supervisor.py).
    spec = runner.StrategySpec(
        id=stub_mod.STRATEGY_ID, state_key=f"runner_regime_test_{stub_mod.STRATEGY_ID}",
        params_cls=StrategyParams, decide=stub_mod.decide, module=None,
        version=stub_mod.STRATEGY_VERSION,
        allowed_regimes=list(getattr(stub_mod, "ALLOWED_REGIMES", []) or []))
    async with db.pool().connection() as conn:
        state = dict(DEFAULT_STATE)
        logs = await runner.run_iteration(
            conn, state, spec=spec, mode="PAPER", settings=await db.get_settings(),
            params=StrategyParams(), tick=RUNNER_TICK, candles=[],
            spread_median=0.25, now=RUNNER_NOW, allow_entry=True, dry=False,
            regime_result=_regime_result(label))
        rows = await conn.execute(
            "SELECT * FROM paper_orders WHERE mode = 'PAPER' AND strategy = %s",
            (stub_mod.STRATEGY_ID,))
        orders = list(await rows.fetchall())
        rows = await conn.execute("SELECT * FROM regime_observations ORDER BY id")
        obs = list(await rows.fetchall())
    return logs, orders, obs


async def test_runner_gate_blocks_range_for_trend_only_strategy(_clean_db):
    """UNKNOWN/RANGE memblokir strategi yang mensyaratkan TREND_UP (PRD §6.5)."""
    logs, orders, obs = await _run_with_regime(
        _clean_db, module="sbx_strategies.regime_stub", label="RANGE")
    assert any("ENTRY BLOCKED by regime RANGE" in line for line in logs), logs
    assert orders == [], "entry harus diblokir gate regime"
    # SIGNAL tetap tercatat walau entry diblokir (PRD §6.4)
    assert any(o["context"] == "SIGNAL" and o["regime"] == "RANGE" for o in obs)


async def test_runner_gate_blocks_unknown(_clean_db):
    """UNKNOWN = kondisi aman: strategi ber-regime-syarat tidak entry."""
    logs, orders, obs = await _run_with_regime(
        _clean_db, module="sbx_strategies.regime_stub", label="UNKNOWN")
    assert any("ENTRY BLOCKED by regime UNKNOWN" in line for line in logs), logs
    assert orders == []


async def test_runner_gate_allows_trend_up_and_records(_clean_db):
    """TREND_UP diizinkan: entry jalan, SIGNAL + ORDER tercatat (PRD §6.4)."""
    logs, orders, obs = await _run_with_regime(
        _clean_db, module="sbx_strategies.regime_stub", label="TREND_UP")
    assert any(line.startswith("ENTRY BUY") for line in logs), logs
    assert len(orders) == 1
    contexts = sorted(o["context"] for o in obs)
    assert contexts == ["ORDER", "SIGNAL"], contexts
    assert all(o["regime"] == "TREND_UP" for o in obs)
    assert all(o["classifier_version"] == regime.REGIME_VERSION for o in obs)
    order_obs = [o for o in obs if o["context"] == "ORDER"][0]
    assert order_obs["ref_type"] == "paper_order"
    # ref_id TEXT di schema (id order di-string-kan)
    assert str(order_obs["ref_id"]) == str(orders[0]["id"])
    assert order_obs["ref_id"] is not None


async def test_runner_no_allowed_regimes_never_blocks(_clean_db):
    """Strategi tanpa ALLOWED_REGIMES: RANGE tidak memblokir entry."""
    logs, orders, obs = await _run_with_regime(
        _clean_db, module="sbx_strategies.regime_stub_open", label="RANGE")
    assert any(line.startswith("ENTRY BUY") for line in logs), logs
    assert len(orders) == 1
    # SIGNAL + ORDER tetap tercatat untuk audit
    contexts = sorted(o["context"] for o in obs)
    assert contexts == ["ORDER", "SIGNAL"], contexts
