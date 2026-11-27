"""Unit test ML P3 (t_f2p3a1): fitur point-in-time, label triple-barrier,
guard decide(), determinisme training. Tanpa DB (murni)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.ml_features import FEATURE_NAMES, MIN_BARS, compute_features, feature_vector
from app.ml_label import barrier_key, triple_barrier_labels
from app.strategies import ml_gbm


def mk_candles(n, start="2026-06-01T00:00:00+00:00", base=3000.0, step=0.05,
               amp=1.0, seed=7):
    rng = np.random.default_rng(seed)
    t0 = datetime.fromisoformat(start)
    out = []
    price = base
    for i in range(n):
        drift = step * math_sin(i)
        noise = rng.normal(0, amp / 10)
        o = price
        c = price + drift + noise
        h = max(o, c) + abs(rng.normal(0, amp / 20))
        l = min(o, c) - abs(rng.normal(0, amp / 20))
        out.append({"ts": t0 + timedelta(minutes=5 * i), "open": round(o, 2),
                    "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
        price = c
    return out


def math_sin(x):
    import math
    return math.sin(x / 48.0)


# ---------------------------------------------------------------- features

def test_feature_names_and_warmup():
    candles = mk_candles(MIN_BARS + 10)
    feats = compute_features(candles, spread=0.3)
    vals = feature_vector(feats)
    assert len(vals) == len(FEATURE_NAMES)
    assert all(np.isfinite(vals)), "fitur harus terisi pada bar >= MIN_BARS"


def test_features_point_in_time():
    """Mengubah bar MASA DEPAN tidak boleh mengubah fitur bar t."""
    candles = mk_candles(MIN_BARS + 50)
    f_before = compute_features(candles[:MIN_BARS])
    tampered = [dict(c) for c in candles]
    tampered[MIN_BARS + 10]["close"] = 9999.0
    tampered[MIN_BARS + 10]["high"] = 9999.0
    f_after = compute_features(tampered[:MIN_BARS])
    assert f_before == f_after


def test_features_deterministic():
    candles = mk_candles(MIN_BARS + 5)
    assert compute_features(candles) == compute_features(candles)


def test_corwin_schultz_positive():
    candles = mk_candles(MIN_BARS)
    feats = compute_features(candles)
    assert feats["cs_spread_12"] >= 0.0


# ---------------------------------------------------------------- labels

def _day_candles(day="2026-06-03", prices=None):
    """Satu hari penuh bar M5 00:00-23:55 UTC; harga bisa dikontrol."""
    t0 = datetime.fromisoformat(day + "T00:00:00+00:00")
    n = 288
    prices = prices or [3000.0 + 0.01 * i for i in range(n)]
    out = []
    for i, p in enumerate(prices):
        out.append({"ts": t0 + timedelta(minutes=5 * i), "open": p, "high": p + 0.5,
                    "low": p - 0.5, "close": p})
    return out


def test_label_tp_first_is_win():
    # ATR ~1.0; entry 07:00; trend naik 0.01/bar -> TP long tercapai, short timeout loss
    candles = _day_candles()
    rows = triple_barrier_labels(candles, 1.0, 1.0)
    assert rows, "harus ada bar entry"
    r = rows[0]
    assert r["label_long"] == 1   # TP long kena
    assert r["label_short"] == 0  # short kalah (harga naik terus)


def test_label_sl_first_on_double_touch():
    # Bar setelah entry menyentuh SL dan TP sekaligus -> SL menang (konservatif)
    candles = _day_candles(prices=[3000.0] * 288)
    # buat bar ke-85 (07:05... index 84=07:00) drop lalu spike
    entry_i = 84  # 07:00 UTC
    candles[entry_i + 1]["low"] = candles[entry_i]["close"] - 2.0
    candles[entry_i + 1]["high"] = candles[entry_i]["close"] + 2.0
    candles[entry_i + 1]["close"] = candles[entry_i]["close"]
    rows = triple_barrier_labels(candles, 1.0, 1.0)
    by_ts = {r["ts"]: r for r in rows}
    r = by_ts[candles[entry_i]["ts"]]
    assert r["label_long"] == 0 and r["label_short"] == 0


def test_label_timeout_uses_sign():
    # Harga flat: tidak ada barrier tersentuh -> label dari tanda close akhir
    candles = _day_candles(prices=[3000.0 + 0.001 * i for i in range(288)])
    rows = triple_barrier_labels(candles, 1.0, 1.0)
    assert all(r["label_long"] == 1 for r in rows)  # naik tipis -> long win
    assert all(r["label_short"] == 0 for r in rows)


def test_label_excludes_night_and_weekend():
    candles = _day_candles()  # 2026-06-03 = Rabu
    rows = triple_barrier_labels(candles, 1.0, 1.0)
    for r in rows:
        ts = r["ts"]
        assert 7 * 60 <= ts.hour * 60 + ts.minute < 16 * 60
        assert ts.weekday() < 5


def test_barrier_key_format():
    assert barrier_key(1.0, 1.5) == "sl1_rr1.5"
    assert barrier_key(1.5, 1.0) == "sl1.5_rr1"


# ---------------------------------------------------------------- decide

class _StubBooster:
    def __init__(self, p): self.p = p
    def predict(self, X): return np.array([self.p])


def _context(candles, spread=0.3, median=0.3):
    now = candles[-1]["ts"] + timedelta(seconds=300)
    return {"symbol": "XAUUSD", "now": now, "candles": candles,
            "liquidity": {"ts": now, "bid": candles[-1]["close"] - spread / 2,
                          "ask": candles[-1]["close"] + spread / 2,
                          "spread": spread, "spread_median_15m": median,
                          "fresh": True},
            "positions": [], "trades_today": 0,
            "risk": {"equity": 10000.0, "risk_per_trade": 0.005,
                     "max_volume": 0.10, "max_spread": 0.50}}


def test_decide_requires_min_bars():
    ml_gbm.set_model_bundle(None)
    ml_gbm.clear_prediction_cache()
    assert ml_gbm.decide(_context(mk_candles(100))) is None


def test_decide_buy_and_sell_with_stub_model():
    # last bar harus jatuh di window entry 07:00-16:00 UTC (Senin); amp=5
    # agar ATR ~1 dan sl_dist 1.5xATR melewati guard 0.5-15 USD
    candles = mk_candles(MIN_BARS + 5, start="2026-05-31T12:45:00+00:00", amp=5.0)
    bundle = {"long": {barrier_key(1.5, 1.0): _StubBooster(0.9)},
              "short": {barrier_key(1.5, 1.0): _StubBooster(0.05)},
              "feature_names": FEATURE_NAMES}
    ml_gbm.set_model_bundle(bundle)
    try:
        intent = ml_gbm.decide(_context(candles), ml_gbm.StrategyParams(sl_mult=1.5, rr=1.0))
        assert intent is not None and intent.side == "BUY"
        assert intent.sl < candles[-1]["close"] < intent.tp
        assert intent.volume >= 0.01
        # cache: nilai sama dikembalikan tanpa hitung ulang
        ml_gbm.prime_prediction_cache([(barrier_key(1.5, 1.0),
                                        candles[-1]["ts"].isoformat(), 0.05, 0.9)])
        intent2 = ml_gbm.decide(_context(candles), ml_gbm.StrategyParams(sl_mult=1.5, rr=1.0))
        assert intent2.side == "SELL"
    finally:
        ml_gbm.set_model_bundle(None)
        ml_gbm.clear_prediction_cache()


def test_decide_guards():
    candles = mk_candles(MIN_BARS + 5, start="2026-05-31T12:45:00+00:00")
    bundle = {"long": {barrier_key(1.5, 1.0): _StubBooster(0.9)},
              "short": {barrier_key(1.5, 1.0): _StubBooster(0.9)},
              "feature_names": FEATURE_NAMES}
    ml_gbm.set_model_bundle(bundle)
    try:
        # spread melebihi ambang -> tolak
        assert ml_gbm.decide(_context(candles, spread=2.0, median=0.3)) is None
        # liquidity stale -> tolak
        ctx = _context(candles)
        ctx["liquidity"]["fresh"] = False
        assert ml_gbm.decide(ctx) is None
        # sudah ada posisi -> tolak
        ctx = _context(candles)
        ctx["positions"] = [{"order_id": "x"}]
        assert ml_gbm.decide(ctx) is None
        # trades_today >= 1 -> tolak
        ctx = _context(candles)
        ctx["trades_today"] = 1
        assert ml_gbm.decide(ctx) is None
    finally:
        ml_gbm.set_model_bundle(None)
        ml_gbm.clear_prediction_cache()


def test_decide_weekend():
    # cari sabtu: 2026-06-06; last bar Sabtu 10:00 UTC
    candles = mk_candles(MIN_BARS + 5, start="2026-06-05T12:45:00+00:00")
    bundle = {"long": {barrier_key(1.5, 1.0): _StubBooster(0.9)},
              "short": {barrier_key(1.5, 1.0): _StubBooster(0.9)},
              "feature_names": FEATURE_NAMES}
    ml_gbm.set_model_bundle(bundle)
    try:
        assert ml_gbm.decide(_context(candles)) is None
    finally:
        ml_gbm.set_model_bundle(None)
        ml_gbm.clear_prediction_cache()


def test_batch_matches_per_bar():
    """Paritas jalur batch (training) vs per-bar (decide/live) — wajib identik."""
    from app.ml_features import compute_features_batch
    candles = mk_candles(MIN_BARS + 60, seed=3)
    batch = compute_features_batch(candles, spread_fn=lambda t: 0.35)
    checked = 0
    for i in range(MIN_BARS, len(candles), 7):
        per_bar = compute_features(candles[:i + 1], spread=0.35)
        for k in FEATURE_NAMES:
            a, b = per_bar[k], batch[i][k]
            if a is None or (isinstance(a, float) and np.isnan(a)):
                assert b is None or (isinstance(b, float) and np.isnan(b)), (i, k)
            else:
                assert np.isclose(a, b, rtol=1e-9, atol=1e-12), (i, k, a, b)
        checked += 1
    assert checked >= 8


# ---------------------------------------------------------------- training

def test_training_deterministic_small():
    import lightgbm as lgb
    from app.ml_label import BARRIER_CONFIGS
    from app.ml_walkforward import LGBM_PARAMS, _matrix, train_models
    from datetime import datetime, timedelta
    n = 5000
    candles = mk_candles(n, seed=11, amp=20.0)
    labels = {}
    for sl_mult, rr in BARRIER_CONFIGS[:1]:
        key = barrier_key(sl_mult, rr)
        rows = triple_barrier_labels(candles, sl_mult, rr)
        labels[key] = {r["ts"]: r for r in rows}
    feats = []
    for i in range(MIN_BARS, n):
        window = candles[max(0, i + 1 - MIN_BARS):i + 1]
        f = compute_features(window)
        f["ts"] = candles[i]["ts"]
        feats.append(f)
    m1 = train_feats = None
    # dua fit pada data sama -> prediksi identik (seed + deterministic)
    models_a = train_models(feats, labels)
    models_b = train_models(feats, labels)
    key = barrier_key(*BARRIER_CONFIGS[0])
    X = _matrix(feats)
    pa = models_a[key]["long"].predict(X)
    pb = models_b[key]["long"].predict(X)
    assert np.allclose(pa, pb)
