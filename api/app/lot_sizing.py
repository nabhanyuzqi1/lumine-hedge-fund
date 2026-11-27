"""Auto lot sizing deterministik berbasis risk-percent (RISK-A, t_8bf257a2).

Lot dihitung dari jarak SL dan %risk per trade equity (default 0.5%), BUKAN
dari tebakan LLM. LLM tetap menentukan arah/entry/SL/TP; lot selalu hasil
hitung fungsi murni di modul ini (layer risk, tanpa DB/I/O) yang dipanggil
di jalur order LLM (POST /orders) SEBELUM gate A5, sehingga gate A5 yang
existing tetap memvalidasi lot hasil hitung (defense-in-depth).

Aturan (desain CEO kartu RISK-A):
  1. risk_usd     = equity x risk_pct / 100 (default 0.5%, global; per-strategy
                    menyusul di RISK-D).
  2. sl_distance  = |entry - sl| -- SL WAJIB ada; tanpa SL order ditolak
                    (fail-closed), JANGAN menebak lot.
  3. value_per_lot = contract_size per lot (XAUUSD: 100 oz -> pergerakan $1
                    = $100/lot; BTCUSD ikut specs per simbol).
  4. raw_lot      = risk_usd / (sl_distance x value_per_lot).
  5. Bulatkan KE BAWAH ke lot step; clamp ke [vol_min_lot, vol_max_lot] per
     specs. raw_lot < vol_min_lot -> tolak order (risk tidak
     ter-ekspresikan; JANGAN bulatkan ke atas).
  6. Gate A5 existing tetap jalan di atas lot hasil hitung.

Fitur dikontrol feature flag settings key 'llm_auto_lot' -- DEFAULT OFF.
Selama OFF, jalur order berperilaku persis seperti sekarang (volume dari
LLM dipakai apa adanya). Owner yang mengaktifkan setelah verifikasi
staging, mis.:
    python -m app.cli set-setting llm_auto_lot '{"enabled": true}'
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Toleransi floating-point: raw_lot tepat di step boundary (mis. 0.03)
# harus menghasilkan 0.03, bukan turun ke 0.02 karena error biner.
_EPS = 1e-9

# Lot min/step default per lot ketika spec simbol tidak membawanya. Nilai
# 0.01 terverifikasi live untuk XAUUSD dan BTCUSD (E2E live 0.01 lot fill,
# lihat komentar symbol_specs di db.py). Spec simbol SELALU bisa override
# dengan key 'vol_min_lot' / 'vol_step_lot'.
DEFAULT_VOL_MIN_LOT = 0.01
DEFAULT_VOL_STEP_LOT = 0.01

# Feature flag settings key 'llm_auto_lot': parsial terhadap default ini
# (pola sama dengan 'llm_risk'). risk_pct tidak disimpan di sini: default
# mengikuti settings 'risk_per_trade_pct' (satu sumber kebenaran A5);
# override eksplisit bisa diisi bila perlu.
DEFAULT_AUTO_LOT: dict = {
    "enabled": False,  # DEFAULT OFF: behavior lama (volume dari LLM)
    "risk_pct": None,  # None -> ikut settings 'risk_per_trade_pct'
}


@dataclass
class LotDecision:
    """Hasil compute_lot: ok=False berarti order HARUS ditolak (fail-closed)."""

    ok: bool
    lot: float | None = None
    reasons: list[str] = field(default_factory=list)
    # Detail audit (ikut order_events payload saat flag ON): bukti lot hasil
    # hitung, bukan tebakan.
    detail: dict = field(default_factory=dict)


def auto_lot_config(settings: dict) -> dict:
    """Config auto-lot efektif: default <- settings key 'llm_risk'-style merge.

    risk_pct efektif = override 'llm_auto_lot.risk_pct' bila diisi, kalau
    tidak mengikuti 'risk_per_trade_pct' (default 0.5) agar auto-lot dan
    gate A5 selalu memakai persen risiko yang sama.
    """
    cfg = dict(DEFAULT_AUTO_LOT)
    raw = settings.get("llm_auto_lot")
    if isinstance(raw, dict):
        for key in cfg:
            if raw.get(key) is not None:
                cfg[key] = raw[key]
    if cfg["risk_pct"] is None:
        try:
            cfg["risk_pct"] = float(settings.get("risk_per_trade_pct", 0.5))
        except (TypeError, ValueError):
            cfg["risk_pct"] = 0.5
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["risk_pct"] = float(cfg["risk_pct"])
    # Nilai yang BENAR-BENAR dipakai: order path memakai
    # min(risk_pct strategi/global, risk_pct override). Override di atas
    # global tidak pernah menaikkan risiko, jadi UI menampilkan angka ini.
    try:
        global_pct = float(settings.get("risk_per_trade_pct", 0.5))
    except (TypeError, ValueError):
        global_pct = 0.5
    cfg["global_risk_pct"] = global_pct
    cfg["effective_risk_pct"] = min(cfg["risk_pct"], global_pct)
    return cfg


def compute_lot(
    *,
    symbol: str,
    entry: float | None,
    sl: float | None,
    equity: float | None,
    risk_pct: float,
    spec: dict | None,
    spread_usd: float | None = None,
    commission_per_lot_usd: float = 0.0,
) -> LotDecision:
    """Hitung lot dari risk-percent. Fungsi murni; gagal = ok False + alasan.

    `entry` = harga eksekusi yang diukur caller (ask untuk BUY, bid untuk
    SELL -- konsisten dengan pengukuran jarak SL di gate A5). `spec` =
    hasil symbol_spec(symbol, settings) (sudah fail-closed bila tidak
    lengkap). Semua kegagalan input menghasilkan penolakan, bukan tebakan.

    Biaya (mirror portfolio gate, base case): sizing memakai jarak total
    = jarak SL + slippage fill terburuk di entry + (spread + slippage) di
    exit + komisi round-turn per lot. Setengah spread dipakai karena jarak
    diukur dari harga eksekusi (ask/bid), bukan mid. Tanpa ini, lot tepat
    0.5% dari jarak SL mentah selalu DITOLAK portfolio gate yang menghitung
    worst-case termasuk biaya -- fitur tidak akan pernah lolos. Dengan biaya,
    risk efektif sampai SL tetap <= risk_pct equity (arah aman); biaya nol
    mengembalikan formula dasar kartu RISK-A apa adanya.
    """
    detail: dict = {"symbol": symbol, "risk_pct": risk_pct}

    if spec is None:
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: no risk spec for symbol {symbol}"],
            detail=detail,
        )
    try:
        contract_size = float(spec["contract_size"])
    except (KeyError, TypeError, ValueError):
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: contract_size unreadable for {symbol}"],
            detail=detail,
        )
    if contract_size <= 0:
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: contract_size must be positive for {symbol}"],
            detail=detail,
        )
    try:
        slippage_usd = float(spec.get("slippage_usd") or 0.0)
    except (TypeError, ValueError):
        slippage_usd = -1.0
    if slippage_usd < 0:
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: invalid slippage_usd for {symbol}"],
            detail=detail,
        )

    if entry is None:
        return LotDecision(
            ok=False,
            reasons=["auto lot: no market price for entry"],
            detail=detail,
        )
    if sl is None:
        # Fail-closed: SL wajib. Tanpa SL tidak ada jarak -> tidak ada lot.
        return LotDecision(
            ok=False,
            reasons=["auto lot: SL is mandatory (fail-closed)"],
            detail=detail,
        )
    if equity is None or float(equity) <= 0:
        return LotDecision(
            ok=False,
            reasons=["auto lot: equity unavailable or non-positive"],
            detail=detail,
        )
    if risk_pct is None or float(risk_pct) <= 0:
        return LotDecision(
            ok=False,
            reasons=["auto lot: risk_pct must be positive"],
            detail=detail,
        )
    if spread_usd is not None:
        try:
            spread_usd = float(spread_usd)
        except (TypeError, ValueError):
            spread_usd = -1.0
        if spread_usd < 0:
            return LotDecision(
                ok=False,
                reasons=["auto lot: invalid spread (crossed or unreadable tick)"],
                detail=detail,
            )
    try:
        commission_per_lot_usd = float(commission_per_lot_usd or 0.0)
    except (TypeError, ValueError):
        commission_per_lot_usd = -1.0
    if commission_per_lot_usd < 0:
        return LotDecision(
            ok=False,
            reasons=["auto lot: invalid commission_per_lot_usd config"],
            detail=detail,
        )

    entry_f, sl_f, equity_f = float(entry), float(sl), float(equity)
    sl_distance = abs(entry_f - sl_f)
    if sl_distance <= _EPS:
        return LotDecision(
            ok=False,
            reasons=["auto lot: SL distance must be positive (SL != entry)"],
            detail=detail,
        )

    value_per_lot = contract_size  # USD per $1 pergerakan harga per lot
    risk_usd = equity_f * float(risk_pct) / 100.0
    # Jarak total termasuk biaya (lihat docstring): entry terkena slippage
    # melawan posisi, exit melewati spread + slippage.
    half_spread = (spread_usd / 2.0) if spread_usd is not None else 0.0
    total_distance = sl_distance + 2.0 * slippage_usd + half_spread
    per_lot_usd = total_distance * value_per_lot + commission_per_lot_usd
    raw_lot = risk_usd / per_lot_usd
    detail.update(
        equity=equity_f,
        risk_usd=risk_usd,
        sl_distance=sl_distance,
        value_per_lot=value_per_lot,
        spread_usd=spread_usd,
        slippage_usd=slippage_usd,
        commission_per_lot_usd=commission_per_lot_usd,
        total_distance=total_distance,
        raw_lot=raw_lot,
    )

    # Batas lot per spec; key opsional memakai default terverifikasi 0.01
    # (lihat DEFAULT_VOL_*). Nilai eksplisit tidak valid (0/negatif/ salah
    # tipe) TETAP fail-closed -- bukan diam-diam diganti default.
    try:
        raw_min = spec.get("vol_min_lot", DEFAULT_VOL_MIN_LOT)
        raw_step = spec.get("vol_step_lot", DEFAULT_VOL_STEP_LOT)
        vol_min = float(DEFAULT_VOL_MIN_LOT if raw_min is None else raw_min)
        vol_step = float(DEFAULT_VOL_STEP_LOT if raw_step is None else raw_step)
        vol_max = float(spec["vol_max_lot"])
    except (KeyError, TypeError, ValueError):
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: lot bounds unreadable for {symbol}"],
            detail=detail,
        )
    if vol_step <= 0 or vol_min <= 0 or vol_max <= 0 or vol_min > vol_max + _EPS:
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: invalid lot bounds for {symbol} "
                     f"(min={vol_min}, step={vol_step}, max={vol_max})"],
            detail=detail,
        )

    # Bulatkan KE BAWAH ke lot step (lot hasil hitung tidak pernah
    # melebihi risk_usd), lalu clamp ke [vol_min, vol_max].
    steps = math.floor((raw_lot + _EPS) / vol_step)
    lot = round(steps * vol_step, 8)
    detail["lot"] = lot
    if lot < vol_min - _EPS:
        # Risk tidak ter-ekspresikan pada lot minimum -> tolak. JANGAN
        # bulatkan ke atas: itu menaikkan risk di atas risk_pct.
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: computed lot {lot} below min lot {vol_min} "
                     f"for {symbol} (risk not expressible)"],
            detail=detail,
        )
    if lot > vol_max + _EPS:
        # Clamp ke bawah: risk efektif < risk_pct -- arah aman.
        lot = vol_max
        detail["lot"] = lot
        detail["clamped_to_max"] = True
    if lot <= 0:
        return LotDecision(
            ok=False,
            reasons=[f"auto lot: computed lot is zero for {symbol}"],
            detail=detail,
        )

    detail["risk_usd_actual"] = sl_distance * value_per_lot * lot
    # Worst-case termasuk biaya = yang divalidasi portfolio gate
    # (max_risk_per_trade_pct); selalu <= risk_usd by construction.
    detail["worst_case_usd"] = total_distance * value_per_lot * lot \
        + commission_per_lot_usd * lot
    return LotDecision(ok=True, lot=lot, detail=detail)
