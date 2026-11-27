"""Helper murni untuk GET /regime/current (PRD v2.2 §6/§21, task UI-D0).

TANPA I/O (no DB, no clock, no network): endpoint di app.routes membaca
candle M5 + likuiditas dari DB/tick in-memory, lalu membangun response
lewat build_regime_snapshot di sini. Classifier = app.regime.classify,
yang SAMA dengan paper runner dan backtest (PRD §6.5); modul ini TIDAK
membuat classifier baru dan TIDAK mengubah logika regime/gate apa pun.

Response stabil untuk UI D1 (PRD §21.2):

    {symbol, label, confidence, ts, candle_ts, age_s, allowed_strategies,
     allowed_count, degrade_reason, stale, reason}

  - label null + stale true + reason terisi bila data tidak layak
    diklasifikasi (candle kurang/stale/rusak, likuiditas tidak fresh,
    classifier error). Endpoint tetap HTTP 200: UI wajib menampilkan
    badge "REGIME STALE", bukan error merah.
  - ts        : waktu anchor klasifikasi (close bar terakhir, ISO UTC).
  - candle_ts : ts bar candle M5 terakhir yang dipakai (ISO UTC).
  - age_s     : usia data (now - close bar terakhir, detik).
  - reason    : penjelasan classifier untuk label ini.
  - degrade_reason: non-null hanya bila regime tidak sehat/stale.
  - allowed_strategies: id strategi terdaftar (app.strategies.REGISTRY)
    untuk simbol ini yang lolos gerbang regime (regime_permits_entry,
    PRD §6.4) - aturan gate yang sama dengan paper runner.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

from . import regime
from .strategies import REGISTRY

# UI D1 (PRD §21.2): regime lebih tua dari 10 menit ditampilkan stale.
REGIME_STALE_AFTER_S = 600.0


def _base_snapshot(symbol: str) -> dict:
    """Kerangka response stabil (semua field selalu ada, schema tetap)."""
    return {
        "symbol": symbol,
        "label": None,
        "confidence": None,
        "ts": None,
        "candle_ts": None,
        "age_s": None,
        "allowed_strategies": [],
        "allowed_count": 0,
        "degrade_reason": None,
        "stale": True,
        "reason": None,
    }


def _strategy_module(strategy_id: str):
    """Modul strategi untuk ALLOWED_REGIMES.

    Konvensi sama dengan paper runner (paper.runner.STRATEGIES): module =
    ``strategies.<id>``. Modul tidak ada = strategi legacy tanpa syarat
    regime (allowed_regimes kosong = gate tidak memblokir, PRD §6.4).
    """
    try:
        return importlib.import_module(f"strategies.{strategy_id}")
    except ImportError:
        return None


def allowed_strategies_for_label(symbol: str, label: str) -> list[str]:
    """Id strategi terdaftar utk `symbol` yang lolos gerbang regime `label`.

    Gerbang = regime.regime_permits_entry (yang sama dipakai paper runner):
    allowed_regimes kosong = strategi tidak mensyaratkan regime -> lolos;
    label UNKNOWN memblokir strategi yang mensyaratkan regime (kondisi
    aman, PRD §6.2). Modul rusak -> strategi dianggap TIDAK lolos
    (konservatif utk UI; runner akan mengisolasi errornya sendiri).
    """
    allowed_ids: list[str] = []
    for meta in REGISTRY:
        if str(meta.get("symbol", "")).upper() != str(symbol).upper():
            continue
        module = _strategy_module(str(meta["id"]))
        try:
            permits = regime.regime_permits_entry(
                label, regime.allowed_regimes_for(module))
        except Exception:  # noqa: BLE001 — gate UI gagal -> konservatif
            permits = False
        if permits:
            allowed_ids.append(str(meta["id"]))
    return allowed_ids


def build_regime_snapshot(*, symbol: str, now: datetime, candles: list[dict],
                          liquidity: dict | None,
                          state: dict | None = None) -> dict:
    """Snapshot regime live untuk UI (murni; hasil hanya dari argumen).

    ``candles`` = bar M5 CLOSED ascending (format sama dengan
    paper.runner.load_candles), ``liquidity`` = dict spread (format sama
    dengan kontrak regime.classify), ``state`` = hysteresis state
    (None = tanpa hysteresis; endpoint read-only tidak menyimpan state).
    """
    symbol = str(symbol).upper()
    snap = _base_snapshot(symbol)
    if not candles:
        reason = "tidak ada candle M5 untuk simbol ini di DB"
        return {**snap, "degrade_reason": reason, "reason": reason,
                "stale": True}

    try:
        result = regime.classify(
            symbol=symbol, now=now, candles=candles, liquidity=liquidity,
            params=regime.default_params_for_symbol(symbol), state=state)
    except Exception as exc:  # noqa: BLE001 — classifier error = stale, bukan 500
        reason = f"classifier error: {type(exc).__name__}: {exc}"
        return {**snap, "degrade_reason": reason, "reason": reason,
                "stale": True}

    dq = result.data_quality or {}
    snap["ts"] = result.ts or None
    snap["candle_ts"] = dq.get("last_bar_ts")
    snap["age_s"] = dq.get("last_bar_age_s")
    snap["reason"] = result.reason or None

    # UNKNOWN selalu hasil data-quality fail (classifier tidak pernah
    # mengeluarkan UNKNOWN dari pohon keputusan) -> tampilkan stale.
    stale = result.label == "UNKNOWN"
    if stale:
        snap["stale"] = True
        snap["degrade_reason"] = result.reason or "data tidak layak"
    else:
        snap["stale"] = bool(
            snap["age_s"] is not None and snap["age_s"] > REGIME_STALE_AFTER_S)
        snap["label"] = result.label
        snap["confidence"] = result.confidence

    # allowed_strategies dihitung dari label classifier yang sebenarnya
    # (termasuk UNKNOWN) supaya konsisten dengan gerbang entry runner.
    snap["allowed_strategies"] = allowed_strategies_for_label(
        symbol, result.label)
    snap["allowed_count"] = len(snap["allowed_strategies"])
    return snap
