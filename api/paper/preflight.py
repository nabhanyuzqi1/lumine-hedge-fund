"""Preflight data quality untuk backtest (PRD v2.2 §8.2).

Menggabungkan checks app/data_quality.py (OHLC, monoton, duplicate, gap,
completeness) dengan deteksi bad ticks (spike) dan survivorship/selection
bias. Dijalankan SEBELUM backtest; hasilnya dicatat di laporan run.

- bad ticks: bar dengan close menyimpang jauh dari median lokal (MAD) atau
  range bar ekstrem vs range median window — kandidat spike/kutipan salah.
  Deterministik, ambang tetap.
- survivorship: untuk backtest single-symbol kontinu, delisting tidak
  memotong series; risiko nyata adalah selection bias (memilih simbol/
  periode setelah melihat hasil). Yang bisa dihitung: simbol harus masih
  dapat diperdagangkan (ada di daftar simbol broker), dan simbol+window
  dikunci di config hash SEBELUM eksperimen. Status DOCUMENTED untuk bagian
  yang tidak terhitung — jujur, bukan PASS palsu.
"""
from __future__ import annotations

from datetime import datetime

from app.data_quality import (
    TF_SECONDS,
    check_completeness,
    check_duplicate_rate,
    check_gaps,
    check_ohlc,
    check_monotonicity,
)


def check_bad_ticks(rows: list[dict], *, window: int = 25,
                    k_dev: float = 6.0, k_range: float = 10.0,
                    k_stuck: int = 5, fail_pct: float = 0.005) -> dict:
    """Deteksi bad ticks / error data (PRD §8.2) - BUKAN deteksi volatilitas.

    Tiga pola error data yang dideteksi:
    - spike_revers: close menyimpang dari median lokal > k_dev x (1.4826 x
      MAD) DAN bar berikutnya kembali mendekati median (outlier terisolasi).
      Kaki tren legitimate tidak ter-flag karena bar berikutnya melanjutkan
      deviasi, bukan revers.
    - range_ekstrem: range bar > k_range x median range window.
    - stuck_feed: >= k_stuck close identik berturut-turut (feed beku);
      seluruh bar dalam run terhitung ter-flag.

    Status: PASS (0), WARN (>0), FAIL (>fail_pct bar).
    """
    n = len(rows)
    if n < window + 2:
        return {"status": "PASS", "detail": f"bar {n} < window {window}: skip",
                "flagged": 0, "flagged_pct": 0.0, "samples": []}
    closes = [float(r.get("close") or 0) for r in rows]
    ranges = [float(r.get("high") or 0) - float(r.get("low") or 0) for r in rows]
    flagged: list[dict] = [False] * n
    reasons: dict[int, str] = {}
    for i in range(window, n - 1):
        w = closes[i - window:i]
        med = _median(w)
        mad = _median([abs(x - med) for x in w])
        dev_threshold = k_dev * (1.4826 * mad)
        if dev_threshold > 0 and abs(closes[i] - med) > dev_threshold \
                and abs(closes[i + 1] - med) < dev_threshold:
            flagged[i] = True
            reasons.setdefault(i, "spike_revers")
            continue
        rw = ranges[i - window:i]
        rmed = _median(rw)
        if rmed > 0 and ranges[i] > k_range * rmed:
            flagged[i] = True
            reasons.setdefault(i, "range_ekstrem")
    # stuck feed: run close identik >= k_stuck
    run_start = 0
    for i in range(1, n + 1):
        if i == n or closes[i] != closes[run_start]:
            run_len = i - run_start
            if run_len >= k_stuck and i < n:  # run terakhir tidak diujung data
                for j in range(run_start, i):
                    flagged[j] = True
                    reasons.setdefault(j, "stuck_feed")
            run_start = i
    samples = [{"ts": str(rows[i].get("ts")), "reason": reasons[i],
                "close": closes[i]} for i in range(n) if flagged[i]]
    count = len(samples)
    pct = count / n
    status = "PASS"
    if count:
        status = "WARN"
    if pct > fail_pct:
        status = "FAIL"
    return {"status": status,
            "detail": f"{count}/{n} bar dicurigai bad tick "
                      f"(spike revers > {k_dev}x MAD, range > {k_range}x median, "
                      f"stuck >= {k_stuck} close identik)",
            "flagged": count, "flagged_pct": round(pct, 6),
            "samples": samples[:5]}


def check_survivorship(symbol: str, tradeable_symbols: list[str] | None) -> dict:
    """Survivorship/selection bias (PRD §8.2).

    Yang terhitung: simbol masih dapat diperdagangkan (bukan delisted).
    Yang didokumentasikan (tidak bisa dihitung dari candle): selection bias
    pemilihan simbol/periode setelah melihat hasil — dimitigasi dengan
    mengunci simbol+window di config hash sebelum eksperimen.
    """
    documented = (
        "single-symbol kontinu (tanpa seleksi delisting). Risiko selection "
        "bias: simbol/periode dipilih setelah melihat hasil. Mitigasi: "
        "simbol + window + grid dikunci di config hash SEBELUM eksperimen "
        "dan semua parameter yang dicoba dicatat di backtest_runs."
    )
    if tradeable_symbols and symbol.upper() not in {s.upper() for s in tradeable_symbols}:
        return {"status": "FAIL",
                "detail": f"simbol {symbol} tidak ada di daftar simbol yang dapat "
                          f"diperdagangkan {tradeable_symbols} — risiko survivorship bias",
                "symbol": symbol, "tradeable_symbols": tradeable_symbols,
                "documented": documented}
    return {"status": "DOCUMENTED",
            "detail": f"simbol {symbol} tradeable; survivorship/selection bias "
                      f"didokumentasikan + dimitigasi (lihat field documented)",
            "symbol": symbol, "tradeable_symbols": tradeable_symbols,
            "documented": documented}


def _median(values: list[float]) -> float:
    xs = sorted(values)
    n = len(xs)
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def run_preflight(candles: list[dict], *, symbol: str, tf: str,
                  tradeable_symbols: list[str] | None = None,
                  window_days: int | None = None) -> dict:
    """Jalankan semua check data quality untuk window candle backtest.

    candles: dict {ts (datetime UTC), open, high, low, close, volume}.
    window_days: panjang window (hari) untuk completeness; default dihitung
    dari rentang data. Mengembalikan dict check -> hasil + overall status.
    """
    rows = [{"ts": c["ts"], "open": c.get("open", 0), "high": c.get("high", 0),
             "low": c.get("low", 0), "close": c.get("close", 0),
             "volume": c.get("volume", 0)} for c in candles]
    checks: dict[str, dict] = {}
    checks["ohlc"] = check_ohlc(rows)
    checks["monotonicity"] = check_monotonicity(rows, tf)
    checks["duplicate_rate"] = check_duplicate_rate(rows)
    checks["gaps"] = check_gaps(rows, symbol, tf)
    if window_days is None:
        ts_list = [c["ts"] for c in candles if isinstance(c["ts"], datetime)]
        if ts_list:
            window_days = max(1, (max(ts_list) - min(ts_list)).days)
        else:
            window_days = 1
    checks["completeness"] = check_completeness(rows, symbol, tf, window_days)
    checks["bad_ticks"] = check_bad_ticks(rows)
    checks["survivorship"] = check_survivorship(symbol, tradeable_symbols)
    rank = {"PASS": 0, "DOCUMENTED": 0, "WARN": 1, "FAIL": 2}
    worst = max(checks.values(), key=lambda c: rank.get(c.get("status", "PASS"), 0))
    return {"symbol": symbol, "timeframe": tf, "bars": len(candles),
            "checks": checks, "overall_status": worst.get("status", "PASS"),
            "note": "FAIL/WARN tidak otomatis membatalkan backtest kecuali "
                    "dikonfigurasi; hasil dicatat di laporan run (PRD §8.2)"}
