"""Strategy Degradation Detection (PRD v2.2 §10, t_f2v22a5).

Mendeteksi perubahan performa strategi dari baseline tervalidasi, tanpa
bereaksi berlebihan terhadap variasi acak (PRD §10.1). Modul ini MURNI
(tanpa I/O, tanpa clock, tanpa RNG): semua input lewat argumen, hasil hanya
fungsi argumen — dapat diuji deterministik seperti app.regime.

Status (PRD §10.3): NORMAL → WATCH → DEGRADED → HALTED
    WATCH    : notifikasi + pemantauan meningkat; entry masih boleh.
    DEGRADED : strategi tidak boleh MENAMBAH RISIKO BARU (entry baru diblok;
               posisi terbuka tetap dikelola normal).
    HALTED   : strategi berhenti membuka posisi baru; posisi ada mengikuti
               policy pengelolaan posisi (PRD §10.3).
    Re-enable HANYA lewat approval owner (API + 2FA); TIDAK pernah otomatis.

Indikator (PRD §10.2) — 11 family, masing-masing punya ambang warn/degraded
(berlevel) dan sample size minimum:
    expectancy, profit_factor, drawdown, mae_mfe (average adverse/favorable
    excursion), spread, slippage, rejection_rate, regime_distribution,
    signal_frequency, paper_live_divergence, feature_drift (PSI).

Anti false alarm (PRD §10.4):
1. Minimum sample size per indikator; sampel kurang -> indikator NONAKTIF
   (severity 0, sample_ok=False), bukan dianggap sehat diam-diam.
2. Evaluasi per regime: indikator trade-based dihitung per grup regime;
   grup dengan sampel >= min_trades_per_regime yang menyalakan sinyal.
3. Konfirmasi berlapis: confirm_evals evaluasi beruntun di ambang yang sama,
   DAN untuk eskalasi pemblok (DEGRADED) harus ada >= min_new_trades_confirm
   trade BARU sejak kandidat mulai — kerugian acak pada window rolling yang
   sama tidak mengkonfirmasi dirinya sendiri (pisahkan kerugian acak dari
   perubahan struktural, PRD §10.4).
4. Cooldown: setelah eskalasi, eskalasi berikutnya ditahan cooldown_s.
5. Eskalasi hanya naik. Penurunan status TIDAK pernah otomatis; hanya
   re-enable owner (PRD §10.3).
6. Drawdown level HALT bersifat safety: langsung HALTED tanpa menunggu
   konfirmasi/cooldown (false HALTED murah — owner bisa re-enable; miss
   account-protection mahal).
7. Semua threshold berversi: DEGRADATION_VERSION + config_hash (sha256 dari
   parameter efektif) dicatat di state dan setiap event. Tidak ada
   optimasi parameter otomatis di modul ini (PRD §10.4).

Kontrak evaluasi (dipanggil degradation_store.evaluate_strategy):

    result = degradation.evaluate(
        strategy_id="london_breakout", now=datetime_utc,
        params=degradation.load_params(settings),
        state=state_dari_db,          # None = NORMAL awal
        inputs={"trades": [...], "equity_curve": [...], ...})
    # result.status / result.escalated / result.indicators / result.state

Runner (paper/runner.py) memanggil gate: entry_allowed(status) — DEGRADED/
HALTED memblokir entry baru; app.risk memakai field degradation_status di
RiskContext untuk gate order path live.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

DEGRADATION_VERSION = "1.0.0"

STATUSES = ("NORMAL", "WATCH", "DEGRADED", "HALTED")
SEVERITY_OF_STATUS = {"NORMAL": 0, "WATCH": 1, "DEGRADED": 2, "HALTED": 3}
STATUS_OF_SEVERITY = {v: k for k, v in SEVERITY_OF_STATUS.items()}

SEV_OK, SEV_WARN, SEV_DEGRADED, SEV_HALT = 0, 1, 2, 3

# Normalisasi status order utk fill/rejection rate (live + paper vocabulary).
FILLED_STATUSES = {"FILLED", "FILLED_THEN_CLOSED", "RECONCILED", "OPEN", "CLOSED"}
FAILED_STATUSES = {"FAILED", "REJECTED"}


# ── Parameter (PRD §10.4: semua threshold terversi) ─────────────────────────
@dataclass(frozen=True)
class DegradationParams:
    """Ambang degradation (PRD §10.2/§10.4). Nilai default = [USULAN] belum
    dikalibrasi penuh; owner dapat override via settings key 'degradation'
    (merge parsial, ter-audit settings_audit). Setiap perubahan efektif
    terdeteksi via config_hash."""

    # ---- window & sample size (PRD §10.4) ----
    trade_window: int = 30           # jumlah trade closed utk rolling metrics
    min_trades: int = 20             # minimum sampel global (indikator trade)
    min_trades_per_regime: int = 12  # minimum sampel per grup regime
    min_fill_events: int = 20        # minimum order terminal utk rejection rate
    min_regime_obs: int = 30         # minimum observasi regime per window
    min_signal_baseline: int = 10    # minimum sinyal baseline utk freq ratio
    min_divergence_trades: int = 10  # minimum trade paper DAN live
    min_feature_samples: int = 30    # minimum sampel fitur per window (PSI)
    min_dd_points: int = 5           # minimum titik equity utk drawdown
    # ---- konfirmasi & cooldown (PRD §10.4) ----
    confirm_evals: int = 3           # evaluasi beruntun di ambang sama
    min_new_trades_confirm: int = 3  # trade baru sejak kandidat (blok level)
    cooldown_s: float = 3600.0       # jeda antar eskalasi
    eval_interval_s: float = 300.0   # cadence evaluasi (caller throttle)
    # ---- window waktu (distribusi / frekuensi / fitur) ----
    recent_window_days: float = 7.0
    baseline_window_days: float = 30.0
    # ---- rolling expectancy (R multiple) ----
    expectancy_warn_r: float = -0.05
    expectancy_degraded_r: float = -0.15
    # ---- rolling profit factor ----
    pf_warn: float = 1.0
    pf_degraded: float = 0.80
    # ---- drawdown (% dari puncak equity) ----
    dd_warn_pct: float = 5.0
    dd_degraded_pct: float = 8.0
    dd_halt_pct: float = 12.0
    # ---- average adverse/favorable excursion: rasio MAE/MFE ----
    mfe_mae_warn_ratio: float = 0.80
    mfe_mae_degraded_ratio: float = 0.60
    # ---- spread & slippage aktual: rasio median vs baseline ----
    spread_warn_mult: float = 1.5
    spread_degraded_mult: float = 2.0
    slippage_warn_mult: float = 1.5
    slippage_degraded_mult: float = 2.0
    # ---- fill/rejection rate ----
    reject_rate_warn: float = 0.20
    reject_rate_degraded: float = 0.40
    # ---- distribusi regime: total variation distance ----
    regime_dist_warn: float = 0.30
    regime_dist_degraded: float = 0.50
    # ---- perubahan frekuensi sinyal: rasio rate harian ----
    freq_drop_warn: float = 0.50     # < 50% baseline
    freq_drop_degraded: float = 0.25
    freq_spike_warn: float = 2.00    # > 2x baseline
    freq_spike_degraded: float = 3.00
    # ---- paper/live divergence (R) ----
    divergence_warn_r: float = 0.20
    divergence_degraded_r: float = 0.35
    # ---- drift fitur (PSI) ----
    psi_warn: float = 0.25
    psi_degraded: float = 0.50


DEFAULT_PARAMS = DegradationParams()


def load_params(settings: dict | None = None) -> DegradationParams:
    """Default <- settings key 'degradation' (merge parsial, key dikenal saja)."""
    override = (settings or {}).get("degradation")
    if not isinstance(override, dict):
        return DEFAULT_PARAMS
    known = set(DegradationParams.__dataclass_fields__)
    clean = {}
    for key, val in override.items():
        if key in known and val is not None:
            default_val = getattr(DEFAULT_PARAMS, key, None)
            try:
                if isinstance(default_val, bool):
                    clean[key] = bool(val)
                elif isinstance(default_val, int):
                    clean[key] = int(float(val))    # field int tetap int
                elif isinstance(default_val, float):
                    clean[key] = float(val)
                else:
                    clean[key] = val
            except (TypeError, ValueError):
                continue
    return DegradationParams(**clean)


def config_hash(params: DegradationParams) -> str:
    """Hash kanonik parameter efektif: identitas threshold set yang dipakai."""
    canonical = json.dumps({
        "version": DEGRADATION_VERSION,
        **{k: v for k, v in sorted(params.__dict__.items())},
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ── Hasil evaluasi ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class IndicatorResult:
    """Satu indikator: severity 0..3 + nilai + ambang + ketersampai sampel."""

    name: str
    severity: int                 # 0 ok, 1 warn, 2 degraded, 3 halt
    value: float | None
    threshold: float | None
    sample_size: int
    sample_ok: bool
    reason: str


@dataclass(frozen=True)
class DegradationResult:
    """Keluaran evaluate(): status terkini + keputusan + state utk dipersist."""

    strategy_id: str
    status: str                   # status SETELAH evaluasi
    previous_status: str
    escalated: bool
    target_status: str            # status terburuk dari indikator saat ini
    indicators: list[IndicatorResult] = field(default_factory=list)
    reason: str = ""
    evaluated_at: str = ""
    config_version: str = DEGRADATION_VERSION
    config_hash: str = ""
    state: dict = field(default_factory=dict)


DEFAULT_STATE: dict = {
    "status": "NORMAL",
    "since": None,                # ISO UTC status sekarang mulai
    "last_evaluated_at": None,
    "cooldown_until": None,
    "confirm_status": None,       # kandidat eskalasi
    "confirm_count": 0,
    "confirm_trades_start": 0,    # closed_trades_total saat kandidat mulai
    "indicators": [],             # snapshot indikator evaluasi terakhir
    "config_version": DEGRADATION_VERSION,
    "config_hash": "",
}


# ── Helpers ─────────────────────────────────────────────────────────────────
def _finite(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(float(x)))


def _num(x) -> float | None:
    return float(x) if _finite(x) else None


def _utc(value) -> datetime:
    """ISO string / datetime -> aware UTC datetime (mirror app.regime)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _inactive(name: str, n: int, need: int, why: str = "") -> IndicatorResult:
    """Indikator nonaktif: sampel kurang -> TIDAK dianggap sehat diam-diam."""
    reason = f"sampel {n} < minimum {need}" + (f" ({why})" if why else "")
    return IndicatorResult(name=name, severity=SEV_OK, value=None, threshold=None,
                           sample_size=n, sample_ok=False, reason=reason)


def _norm_trades(trades: list[dict]) -> list[dict]:
    """Normalisasi daftar trade: r/profit float valid, ascending by closed_at."""
    out = []
    for t in trades or []:
        if not isinstance(t, dict):
            continue
        r = _num(t.get("r"))
        profit = _num(t.get("profit"))
        mae = _num(t.get("mae_r"))
        mfe = _num(t.get("mfe_r"))
        out.append({
            "r": r,
            "profit": profit,
            "regime": t.get("regime"),
            "mae_r": mae,
            "mfe_r": mfe,
            "closed_at": str(t.get("closed_at") or ""),
        })
    out.sort(key=lambda t: t["closed_at"])
    return out


# ── Indikator murni (PRD §10.2) ─────────────────────────────────────────────
def rolling_expectancy(trades: list[dict], window: int | None = None) -> float | None:
    """Rolling expectancy = mean R per trade (window trade terakhir)."""
    pool = trades[-window:] if window else trades
    rs = [t["r"] for t in pool if t["r"] is not None]
    if not rs:
        return None
    return statistics.fmean(rs)


def rolling_profit_factor(trades: list[dict], window: int | None = None) -> float | None:
    """Rolling profit factor = gross profit / |gross loss| (window terakhir).

    None bila tidak ada loss (tak terdefinisi) ATAU tidak ada profit —
    PF 0/0 atau x/0 tidak boleh diasumsikan.
    """
    pool = trades[-window:] if window else trades
    profits = [t["profit"] for t in pool if t["profit"] is not None]
    if not profits:
        return None
    gross_profit = sum(p for p in profits if p > 0)
    gross_loss = abs(sum(p for p in profits if p < 0))
    if gross_loss <= 0 or gross_profit <= 0:
        return None
    return gross_profit / gross_loss


def max_drawdown_pct(equity_curve: list[dict]) -> tuple[float | None, float | None]:
    """Max drawdown % dari puncak equity. Return (dd_pct, peak_equity).

    Curve ascending {ts, equity}; titik equity <= 0 / non-finite dilewati.
    """
    peak = None
    dd = 0.0
    for point in equity_curve or []:
        eq = _num(point.get("equity") if isinstance(point, dict) else None)
        if eq is None or eq <= 0:
            continue
        peak = eq if peak is None else max(peak, eq)
        if peak > 0:
            dd = max(dd, (peak - eq) / peak * 100.0)
    if peak is None:
        return None, None
    return round(dd, 4), round(peak, 4)


def mae_mfe_stats(trades: list[dict]) -> dict | None:
    """Average adverse/favorable excursion (R) + rasio MAE/MFE.

    Rasio tinggi = loss rata-rata dalam relatif terhadap win rata-rata
    membesar (eksekusi/SL kena slippage, TP makin sulit tercapai).
    """
    maes = [t["mae_r"] for t in trades if t["mae_r"] is not None]
    mfes = [t["mfe_r"] for t in trades if t["mfe_r"] is not None]
    if not maes or not mfes:
        return None
    mae_avg = statistics.fmean(maes)
    mfe_avg = statistics.fmean(mfes)
    if mfe_avg <= 0:
        return None
    return {
        "mae_avg_r": round(mae_avg, 4),
        "mfe_avg_r": round(mfe_avg, 4),
        "ratio": round(mae_avg / mfe_avg, 4),
        "n": min(len(maes), len(mfes)),
    }


def median_ratio(current: list, baseline: list) -> float | None:
    """Rasio median(current)/median(baseline) utk spread & slippage aktual."""
    cur = [_num(x) for x in (current or [])]
    base = [_num(x) for x in (baseline or [])]
    cur = [x for x in cur if x is not None]
    base = [x for x in base if x is not None]
    if not cur or not base:
        return None
    med_cur = statistics.median(cur)
    med_base = statistics.median(base)
    if med_base <= 0:
        return None
    return med_cur / med_base


def rejection_rate(orders: list[dict]) -> dict | None:
    """Fill/rejection rate dari order terminal (FILLED vs FAILED/REJECTED)."""
    filled = failed = 0
    for o in orders or []:
        status = str((o or {}).get("status") or "").upper()
        if status in FILLED_STATUSES:
            filled += 1
        elif status in FAILED_STATUSES:
            failed += 1
    total = filled + failed
    if total == 0:
        return None
    return {"rate": failed / total, "failed": failed, "filled": filled, "total": total}


def distribution_distance(current: dict, baseline: dict) -> float | None:
    """Total variation distance antara distribusi regime window saat ini vs
    baseline: 0.5 * Σ|p_i - q_i| ∈ [0, 1]. None bila salah satu kosong."""
    cur = {str(k): int(v) for k, v in (current or {}).items() if _finite(v)}
    base = {str(k): int(v) for k, v in (baseline or {}).items() if _finite(v)}
    total_cur, total_base = sum(cur.values()), sum(base.values())
    if total_cur <= 0 or total_base <= 0:
        return None
    keys = set(cur) | set(base)
    tv = sum(abs(cur.get(k, 0) / total_cur - base.get(k, 0) / total_base)
             for k in keys)
    return round(0.5 * tv, 4)


def frequency_ratio(freq: dict) -> float | None:
    """Rasio rate sinyal harian (window vs baseline) utk perubahan frekuensi."""
    freq = freq or {}
    window = _num(freq.get("window"))
    baseline = _num(freq.get("baseline"))
    window_days = _num(freq.get("window_days"))
    baseline_days = _num(freq.get("baseline_days"))
    if (window is None or baseline is None or window_days is None
            or baseline_days is None):
        return None
    if window_days <= 0 or baseline_days <= 0:
        return None
    base_rate = baseline / baseline_days
    if base_rate <= 0:
        return None  # baseline tanpa sinyal: rasio tak terdefinisi (nonaktif)
    return (window / window_days) / base_rate


def divergence_r(paper_r: list, live_r: list) -> float | None:
    """Paper/live divergence: |mean R paper - mean R live| (PRD §10.2)."""
    paper = [_num(x) for x in (paper_r or [])]
    live = [_num(x) for x in (live_r or [])]
    paper = [x for x in paper if x is not None]
    live = [x for x in live if x is not None]
    if not paper or not live:
        return None
    return round(abs(statistics.fmean(paper) - statistics.fmean(live)), 4)


def psi(baseline: list, current: list, bins: int = 10) -> float | None:
    """Population Stability Index baseline vs current (drift fitur, PRD §10.2).

    Edge bin = kuantil baseline (deterministik, discrete). PSI = Σ (c-b)·ln(c/b).
    None bila sampel/edge tidak cukup. PSI ~ <0.1 stabil, >0.25 shift signifikan.
    """
    base = sorted(x for x in (_num(v) for v in (baseline or [])) if x is not None)
    cur = [x for x in (_num(v) for v in (current or [])) if x is not None]
    if len(base) < bins or len(cur) < bins:
        return None
    edges = []
    for i in range(1, bins):
        idx = min(len(base) - 1, (i * len(base)) // bins)
        edge = base[idx]
        if not edges or edge > edges[-1]:
            edges.append(edge)
    if len(edges) < 2:
        return None
    bounds = [float("-inf")] + edges + [float("inf")]
    n_base, n_cur = len(base), len(cur)
    eps = 1e-6
    psi_val = 0.0
    for lo, hi in zip(bounds, bounds[1:]):
        b = sum(1 for x in base if lo < x <= hi) / n_base
        c = sum(1 for x in cur if lo < x <= hi) / n_cur
        b = max(b, eps)
        c = max(c, eps)
        psi_val += (c - b) * math.log(c / b)
    return round(psi_val, 4)


def max_feature_psi(features_baseline: dict, features_current: dict,
                    min_samples: int) -> dict | None:
    """PSI maksimum lintas fitur numerik (drift fitur terburuk).

    Return {feature, psi, n_base, n_cur} atau None bila tidak ada fitur yang
    memenuhi sample size.
    """
    worst = None
    for name, base_vals in (features_baseline or {}).items():
        cur_vals = (features_current or {}).get(name)
        if cur_vals is None:
            continue
        base_clean = [x for x in (_num(v) for v in (base_vals or [])) if x is not None]
        cur_clean = [x for x in (_num(v) for v in (cur_vals or [])) if x is not None]
        if len(base_clean) < min_samples or len(cur_clean) < min_samples:
            continue
        value = psi(base_clean, cur_clean)
        if value is None:
            continue
        if worst is None or value > worst["psi"]:
            worst = {"feature": str(name), "psi": value,
                     "n_base": len(base_clean), "n_cur": len(cur_clean)}
    return worst


# ── Check per indikator (severity + sample gate) ────────────────────────────
def _check_expectancy(trades: list[dict], p: DegradationParams,
                      min_sample: int | None = None,
                      window: int | None = None) -> IndicatorResult:
    need = min_sample or p.min_trades
    n = len(trades)
    if n < need:
        return _inactive("expectancy", n, need)
    value = rolling_expectancy(trades, window if window is not None else p.trade_window)
    if value is None:
        return _inactive("expectancy", n, need, "tanpa R valid")
    if value <= p.expectancy_degraded_r:
        sev = SEV_DEGRADED
        why = (f"expectancy {value:+.3f}R <= degraded "
               f"{p.expectancy_degraded_r:+.3f}R")
    elif value <= p.expectancy_warn_r:
        sev = SEV_WARN
        why = f"expectancy {value:+.3f}R <= warn {p.expectancy_warn_r:+.3f}R"
    else:
        sev, why = SEV_OK, f"expectancy {value:+.3f}R dalam batas"
    return IndicatorResult("expectancy", sev, round(value, 4),
                           p.expectancy_degraded_r if sev == SEV_DEGRADED
                           else p.expectancy_warn_r, n, True, why)


def _check_profit_factor(trades: list[dict], p: DegradationParams,
                         min_sample: int | None = None,
                         window: int | None = None) -> IndicatorResult:
    need = min_sample or p.min_trades
    n = len(trades)
    if n < need:
        return _inactive("profit_factor", n, need)
    value = rolling_profit_factor(trades, window if window is not None else p.trade_window)
    if value is None:
        return _inactive("profit_factor", n, need,
                         "PF tak terdefinisi (tanpa loss / tanpa profit)")
    if value <= p.pf_degraded:
        sev = SEV_DEGRADED
        why = f"profit factor {value:.2f} <= degraded {p.pf_degraded:.2f}"
    elif value <= p.pf_warn:
        sev = SEV_WARN
        why = f"profit factor {value:.2f} <= warn {p.pf_warn:.2f} (breakeven)"
    else:
        sev, why = SEV_OK, f"profit factor {value:.2f} dalam batas"
    return IndicatorResult("profit_factor", sev, round(value, 4),
                           p.pf_degraded if sev == SEV_DEGRADED else p.pf_warn,
                           n, True, why)


def _check_drawdown(equity_curve: list[dict], p: DegradationParams) -> IndicatorResult:
    points = [pt for pt in (equity_curve or [])
              if isinstance(pt, dict) and _num(pt.get("equity")) is not None]
    n = len(points)
    if n < p.min_dd_points:
        return _inactive("drawdown", n, p.min_dd_points, "titik equity kurang")
    value, peak = max_drawdown_pct(equity_curve)
    if value is None:
        return _inactive("drawdown", n, p.min_dd_points, "equity tidak valid")
    if value >= p.dd_halt_pct:
        sev = SEV_HALT
        why = f"drawdown {value:.2f}% >= halt {p.dd_halt_pct:.2f}% (safety)"
    elif value >= p.dd_degraded_pct:
        sev = SEV_DEGRADED
        why = f"drawdown {value:.2f}% >= degraded {p.dd_degraded_pct:.2f}%"
    elif value >= p.dd_warn_pct:
        sev = SEV_WARN
        why = f"drawdown {value:.2f}% >= warn {p.dd_warn_pct:.2f}%"
    else:
        sev, why = SEV_OK, f"drawdown {value:.2f}% dalam batas"
    thr = (p.dd_halt_pct if sev == SEV_HALT else
           p.dd_degraded_pct if sev == SEV_DEGRADED else p.dd_warn_pct)
    return IndicatorResult("drawdown", sev, value, thr, n, True, why)


def _check_mae_mfe(trades: list[dict], p: DegradationParams,
                   min_sample: int | None = None,
                   window: int | None = None) -> IndicatorResult:
    need = min_sample or p.min_trades
    n_with = sum(1 for t in trades if t["mae_r"] is not None and t["mfe_r"] is not None)
    if n_with < need:
        return _inactive("mae_mfe", n_with, need)
    stats = mae_mfe_stats(trades[-(window if window is not None else p.trade_window):])
    if stats is None:
        return _inactive("mae_mfe", n_with, need, "MAE/MFE tak valid")
    value = stats["ratio"]
    if value >= p.mfe_mae_degraded_ratio:
        sev = SEV_DEGRADED
        why = (f"MAE/MFE {value:.2f} >= degraded {p.mfe_mae_degraded_ratio:.2f} "
               f"(mae {stats['mae_avg_r']:.2f}R vs mfe {stats['mfe_avg_r']:.2f}R)")
    elif value >= p.mfe_mae_warn_ratio:
        sev = SEV_WARN
        why = f"MAE/MFE {value:.2f} >= warn {p.mfe_mae_warn_ratio:.2f}"
    else:
        sev, why = SEV_OK, f"MAE/MFE {value:.2f} dalam batas"
    return IndicatorResult("mae_mfe", sev, value,
                           p.mfe_mae_degraded_ratio if sev == SEV_DEGRADED
                           else p.mfe_mae_warn_ratio, n_with, True, why)


def _check_ratio_indicator(name: str, current: list, baseline: list,
                           warn_mult: float, degraded_mult: float,
                           min_baseline: int) -> IndicatorResult:
    """Indikator rasio median aktual vs baseline (spread / slippage)."""
    n = len(current or [])
    base_n = len(baseline or [])
    if n < 1 or base_n < min_baseline:
        return _inactive(name, n, min_baseline, "baseline aktual kurang")
    value = median_ratio(current, baseline)
    if value is None:
        return _inactive(name, n, min_baseline, "rasio tak terdefinisi")
    if value >= degraded_mult:
        sev = SEV_DEGRADED
        why = f"{name} aktual {value:.2f}x baseline >= degraded {degraded_mult:.2f}x"
    elif value >= warn_mult:
        sev = SEV_WARN
        why = f"{name} aktual {value:.2f}x baseline >= warn {warn_mult:.2f}x"
    else:
        sev, why = SEV_OK, f"{name} aktual {value:.2f}x baseline dalam batas"
    return IndicatorResult(name, sev, round(value, 4),
                           degraded_mult if sev == SEV_DEGRADED else warn_mult,
                           n, True, why)


def _check_rejection(orders: list[dict], p: DegradationParams) -> IndicatorResult:
    stats = rejection_rate(orders)
    if stats is None:
        return _inactive("rejection_rate", 0, p.min_fill_events)
    n = stats["total"]
    if n < p.min_fill_events:
        return _inactive("rejection_rate", n, p.min_fill_events)
    value = stats["rate"]
    if value >= p.reject_rate_degraded:
        sev = SEV_DEGRADED
        why = (f"rejection rate {value:.1%} >= degraded "
               f"{p.reject_rate_degraded:.0%} ({stats['failed']}/{n})")
    elif value >= p.reject_rate_warn:
        sev = SEV_WARN
        why = f"rejection rate {value:.1%} >= warn {p.reject_rate_warn:.0%}"
    else:
        sev, why = SEV_OK, f"rejection rate {value:.1%} dalam batas"
    return IndicatorResult("rejection_rate", sev, round(value, 4),
                           p.reject_rate_degraded if sev == SEV_DEGRADED
                           else p.reject_rate_warn, n, True, why)


def _check_regime_distribution(current: dict, baseline: dict,
                               p: DegradationParams) -> IndicatorResult:
    n_cur = sum(int(v) for v in (current or {}).values() if _finite(v))
    n_base = sum(int(v) for v in (baseline or {}).values() if _finite(v))
    if n_cur < p.min_regime_obs or n_base < p.min_regime_obs:
        return _inactive("regime_distribution", n_cur, p.min_regime_obs,
                         "observasi regime window kurang")
    value = distribution_distance(current, baseline)
    if value is None:
        return _inactive("regime_distribution", n_cur, p.min_regime_obs)
    if value >= p.regime_dist_degraded:
        sev = SEV_DEGRADED
        why = (f"distribusi regime shift TV {value:.2f} >= degraded "
               f"{p.regime_dist_degraded:.2f}")
    elif value >= p.regime_dist_warn:
        sev = SEV_WARN
        why = f"distribusi regime shift TV {value:.2f} >= warn {p.regime_dist_warn:.2f}"
    else:
        sev, why = SEV_OK, f"distribusi regime TV {value:.2f} dalam batas"
    return IndicatorResult("regime_distribution", sev, value,
                           p.regime_dist_degraded if sev == SEV_DEGRADED
                           else p.regime_dist_warn, n_cur, True, why)


def _check_signal_frequency(freq: dict, p: DegradationParams) -> IndicatorResult:
    freq = freq or {}
    n_win = int(_num(freq.get("window")) or 0)
    n_base = int(_num(freq.get("baseline")) or 0)
    if n_base < p.min_signal_baseline:
        return _inactive("signal_frequency", n_base, p.min_signal_baseline,
                         "baseline sinyal kurang")
    value = frequency_ratio(freq)
    if value is None:
        return _inactive("signal_frequency", n_win, p.min_signal_baseline)
    degraded = (value <= p.freq_drop_degraded or value >= p.freq_spike_degraded)
    warned = (value <= p.freq_drop_warn or value >= p.freq_spike_warn)
    if degraded:
        sev = SEV_DEGRADED
        why = (f"frekuensi sinyal {value:.2f}x baseline di luar "
               f"[{p.freq_drop_degraded:.2f}, {p.freq_spike_degraded:.2f}]")
    elif warned:
        sev = SEV_WARN
        why = (f"frekuensi sinyal {value:.2f}x baseline di luar "
               f"[{p.freq_drop_warn:.2f}, {p.freq_spike_warn:.2f}]")
    else:
        sev, why = SEV_OK, f"frekuensi sinyal {value:.2f}x baseline dalam batas"
    return IndicatorResult("signal_frequency", sev, round(value, 4),
                           p.freq_drop_degraded if degraded else p.freq_drop_warn,
                           n_win, True, why)


def _check_divergence(paper_r: list, live_r: list,
                      p: DegradationParams) -> IndicatorResult:
    n_paper = len([x for x in (paper_r or []) if _num(x) is not None])
    n_live = len([x for x in (live_r or []) if _num(x) is not None])
    n = min(n_paper, n_live)
    if n < p.min_divergence_trades:
        return _inactive("paper_live_divergence", n, p.min_divergence_trades,
                         f"paper {n_paper} / live {n_live}")
    value = divergence_r(paper_r, live_r)
    if value is None:
        return _inactive("paper_live_divergence", n, p.min_divergence_trades)
    if value >= p.divergence_degraded_r:
        sev = SEV_DEGRADED
        why = (f"divergensi paper/live {value:.3f}R >= degraded "
               f"{p.divergence_degraded_r:.3f}R")
    elif value >= p.divergence_warn_r:
        sev = SEV_WARN
        why = f"divergensi paper/live {value:.3f}R >= warn {p.divergence_warn_r:.3f}R"
    else:
        sev, why = SEV_OK, f"divergensi paper/live {value:.3f}R dalam batas"
    return IndicatorResult("paper_live_divergence", sev, value,
                           p.divergence_degraded_r if sev == SEV_DEGRADED
                           else p.divergence_warn_r, n, True, why)


def _check_feature_drift(features_baseline: dict, features_current: dict,
                         p: DegradationParams) -> IndicatorResult:
    worst = max_feature_psi(features_baseline, features_current,
                            p.min_feature_samples)
    if worst is None:
        return _inactive("feature_drift", 0, p.min_feature_samples,
                         "sampel fitur per window kurang")
    value = worst["psi"]
    if value >= p.psi_degraded:
        sev = SEV_DEGRADED
        why = (f"PSI fitur {worst['feature']} {value:.2f} >= degraded "
               f"{p.psi_degraded:.2f}")
    elif value >= p.psi_warn:
        sev = SEV_WARN
        why = f"PSI fitur {worst['feature']} {value:.2f} >= warn {p.psi_warn:.2f}"
    else:
        sev, why = SEV_OK, f"PSI fitur maksimum {value:.2f} dalam batas"
    return IndicatorResult("feature_drift", sev, value,
                           p.psi_degraded if sev == SEV_DEGRADED else p.psi_warn,
                           worst["n_cur"], True, why)


# ── Indikator berbasis trade (evaluasi per regime, PRD §10.4) ────────────────
def _trade_indicators(trades: list[dict],
                      p: DegradationParams) -> tuple[list[IndicatorResult], str]:
    """Indikator berbasis trade (expectancy, PF, MAE/MFE) per PRD §10.4.

    Evaluasi per regime: setiap grup regime dengan sampel >=
    min_trades_per_regime dinilai sendiri-sendiri; hasil terburuk yang
    dipakai (grup buruk tidak diencerkan grup sehat). Tidak ada grup
    memenuhi syarat -> fallback semua trade dengan sample gate global
    min_trades.
    """
    groups: dict[str | None, list[dict]] = {}
    for t in trades:
        groups.setdefault(str(t["regime"]) if t["regime"] else None, []).append(t)
    qualifying = [(r, g) for r, g in groups.items()
                  if r is not None and len(g) >= p.min_trades_per_regime]
    per_regime = bool(qualifying)
    candidates = qualifying if per_regime else [(None, trades)]
    min_sample = p.min_trades_per_regime if per_regime else p.min_trades
    # Grup per-regime TIDAK di-slice ulang window-nya: collector sudah
    # mengirim trade_window trade; slice atas gabungan grup mengencerkan
    # sinyal grup terburuk.
    window = None if per_regime else p.trade_window
    worst: dict[str, tuple[IndicatorResult, str | None]] = {}
    for label, group in candidates:
        for ind in (_check_expectancy(group, p, min_sample=min_sample, window=window),
                    _check_profit_factor(group, p, min_sample=min_sample,
                                         window=window),
                    _check_mae_mfe(group, p, min_sample=min_sample, window=window)):
            cur = worst.get(ind.name)
            if cur is None or ind.severity > cur[0].severity:
                worst[ind.name] = (ind, label)
    worst_label = worst["expectancy"][1] if worst else None
    scope = (f"per-regime[{worst_label}]" if per_regime else "global")
    return [worst[n][0] for n in ("expectancy", "profit_factor", "mae_mfe")], scope


# ── Evaluator utama ─────────────────────────────────────────────────────────
def evaluate(*, strategy_id: str, now: datetime, params: DegradationParams,
             state: dict | None, inputs: dict) -> DegradationResult:
    """Evaluasi satu strategi (PRD v2.2 §10). MURNI: hasil hanya fungsi argumen.

    inputs (semua key opsional; indikator tanpa data = nonaktif, bukan sehat):
        trades:               [{r, profit, regime, mae_r, mfe_r, closed_at}]
        equity_curve:         [{ts, equity}] ascending
        orders:               [{status}] (FILLED/FAILED/REJECTED/...)
        spread_current/_baseline, slippage_current/_baseline: list[float]
        regime_counts, baseline_regime_counts: {label: count}
        signal_freq:          {window, window_days, baseline, baseline_days}
        paper_r, live_r:      list[float]
        features_baseline/_current: {feature: list[float]}
        closed_trades_total:  int (counter monotonic utk konfirmasi new-data)
    """
    p = params
    now = _utc(now)
    st = dict(DEFAULT_STATE)
    if isinstance(state, dict):
        for key in st:
            if state.get(key) is not None:
                st[key] = state[key]
    previous = str(st["status"])
    previous_sev = SEVERITY_OF_STATUS.get(previous, 0)

    trades = _norm_trades((inputs or {}).get("trades") or [])
    trade_results, scope = _trade_indicators(trades, p)
    indicators = [
        *trade_results,
        _check_drawdown((inputs or {}).get("equity_curve") or [], p),
        _check_ratio_indicator(
            "spread", (inputs or {}).get("spread_current") or [],
            (inputs or {}).get("spread_baseline") or [],
            p.spread_warn_mult, p.spread_degraded_mult, p.min_regime_obs),
        _check_ratio_indicator(
            "slippage", (inputs or {}).get("slippage_current") or [],
            (inputs or {}).get("slippage_baseline") or [],
            p.slippage_warn_mult, p.slippage_degraded_mult, p.min_fill_events),
        _check_rejection((inputs or {}).get("orders") or [], p),
        _check_regime_distribution(
            (inputs or {}).get("regime_counts") or {},
            (inputs or {}).get("baseline_regime_counts") or {}, p),
        _check_signal_frequency((inputs or {}).get("signal_freq") or {}, p),
        _check_divergence((inputs or {}).get("paper_r") or [],
                          (inputs or {}).get("live_r") or [], p),
        _check_feature_drift((inputs or {}).get("features_baseline") or {},
                             (inputs or {}).get("features_current") or {}, p),
    ]

    worst = max(i.severity for i in indicators)
    target = STATUS_OF_SEVERITY[worst]
    firing = [i for i in indicators if i.severity > 0 and i.sample_ok]
    reason = "; ".join(f"{i.name}: {i.reason}" for i in firing) or \
        "semua indikator dalam batas / nonaktif (sampel kurang)"
    if scope.startswith("per-regime"):
        reason = f"[{scope}] {reason}"

    escalated = False
    current = previous
    if worst > previous_sev:
        in_cooldown = False
        cooldown_until = st.get("cooldown_until")
        if cooldown_until:
            try:
                in_cooldown = now < _utc(cooldown_until)
            except (TypeError, ValueError):
                in_cooldown = False
        if worst >= SEV_HALT:
            # Safety (PRD §10.3): level halt langsung, bypass confirm+cooldown.
            escalated = True
            current = "HALTED"
            reason = f"HALT (safety): {reason}"
        elif not in_cooldown:
            if st.get("confirm_status") == target:
                st["confirm_count"] = int(st.get("confirm_count") or 0) + 1
            else:
                st["confirm_status"] = target
                st["confirm_count"] = 1
                st["confirm_trades_start"] = int(
                    (inputs or {}).get("closed_trades_total") or 0)
            new_trades = (int((inputs or {}).get("closed_trades_total") or 0)
                          - int(st.get("confirm_trades_start") or 0))
            need_new = 0 if target == "WATCH" else p.min_new_trades_confirm
            if (int(st["confirm_count"]) >= p.confirm_evals
                    and new_trades >= need_new):
                escalated = True
                current = target
                reason = (f"eskalasi {previous} -> {target} setelah "
                          f"{st['confirm_count']} evaluasi beruntun, "
                          f"{new_trades} trade baru: {reason}")
            else:
                reason = (f"kandidat {target} "
                          f"(confirm {st['confirm_count']}/{p.confirm_evals}, "
                          f"trade baru {new_trades}/{need_new}): {reason}")
        else:
            reason = f"cooldown aktif, eskalasi ditahan: {reason}"
    else:
        st["confirm_status"] = None
        st["confirm_count"] = 0
        st["confirm_trades_start"] = 0

    if escalated:
        st["status"] = current
        st["since"] = now.isoformat()
        st["cooldown_until"] = (now.fromtimestamp(
            now.timestamp() + p.cooldown_s, tz=timezone.utc)).isoformat()
        st["confirm_status"] = None
        st["confirm_count"] = 0
        st["confirm_trades_start"] = 0

    st["last_evaluated_at"] = now.isoformat()
    st["indicators"] = [
        {"name": i.name, "severity": i.severity, "value": i.value,
         "threshold": i.threshold, "sample_size": i.sample_size,
         "sample_ok": i.sample_ok, "reason": i.reason}
        for i in indicators
    ]
    st["config_version"] = DEGRADATION_VERSION
    st["config_hash"] = config_hash(p)

    return DegradationResult(
        strategy_id=strategy_id, status=current, previous_status=previous,
        escalated=escalated, target_status=target, indicators=indicators,
        reason=reason, evaluated_at=now.isoformat(),
        config_version=DEGRADATION_VERSION, config_hash=st["config_hash"],
        state=st)


# ── Gate entry (dipakai runner + risk gate) ─────────────────────────────────
def entry_allowed(status: str | None) -> bool:
    """True hanya utk NORMAL/WATCH (PRD §10.3).

    DEGRADED = tidak boleh tambah risiko baru (entry baru diblok, posisi
    dikelola normal); HALTED = berhenti entry baru.
    """
    return SEVERITY_OF_STATUS.get(str(status or "NORMAL"), 0) <= SEV_WARN


def entry_block_reason(status: str | None) -> str | None:
    """Alasan penolakan entry, atau None bila boleh entry."""
    status = str(status or "NORMAL")
    if status == "DEGRADED":
        return ("degradation DEGRADED: strategi tidak boleh menambah risiko "
                "baru (PRD §10.3); re-enable butuh approval owner")
    if status == "HALTED":
        return ("degradation HALTED: strategi berhenti entry baru (PRD §10.3); "
                "re-enable butuh approval owner")
    return None if entry_allowed(status) else f"degradation {status}"


# ── Re-enable owner (PRD §10.3) ─────────────────────────────────────────────
def re_enable_state(state: dict | None, *, now: datetime, actor: str,
                    note: str) -> dict:
    """Reset status ke NORMAL oleh owner. TIDAK pernah dipanggil otomatus.

    State baru menyimpan riwayat re-enable (append) sebagai bukti approval;
    cooldown/confirm di-reset. Caller (store) mencatat event REENABLE.
    """
    now = _utc(now)
    prev = dict(DEFAULT_STATE)
    if isinstance(state, dict):
        for key in prev:
            if state.get(key) is not None:
                prev[key] = state[key]
    prev_status = str(prev["status"])
    if prev_status == "NORMAL":
        raise ValueError("strategi sudah NORMAL; re-enable tidak diperlukan")
    history = prev.get("reenable_history") or []
    history = list(history) if isinstance(history, list) else []
    history.append({
        "from_status": prev_status,
        "at": now.isoformat(),
        "actor": str(actor),
        "note": str(note)[:500],
        "config_version": DEGRADATION_VERSION,
    })
    prev["reenable_history"] = history[-50:]
    prev["status"] = "NORMAL"
    prev["since"] = now.isoformat()
    prev["cooldown_until"] = None
    prev["confirm_status"] = None
    prev["confirm_count"] = 0
    prev["confirm_trades_start"] = 0
    return prev


# ═══ EOF ═══
