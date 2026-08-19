"""Trading profiles service (18 Aug 2026).

User minta: profile custom untuk scalping (1m), scalping→intraday (5m),
intraday (15m/1h), intraday→swing (4h), swing (1d) — semua auto
SL/TP/BE + entry/exit otomatis. PLUS per-agent prompt override (prompt
bisa diatur sendiri) + output template system Lumine.

Design: profil = JSON di Redis `lumine:trading_profiles` (hash, key =
profile_id) + `lumine:active_profile` (string). Worker baca profil aktif
per decision cycle (realtime, TANPA restart — pola sama llm_routing
overlay). Frontend superadmin manage CRUD via /admin/profiles.
"""

from __future__ import annotations

import json
from typing import Any

ACTIVE_KEY = "lumine:active_profile"
PROFILES_KEY = "lumine:trading_profiles"

# 6 profile bawaan (18 Aug 2026) — user request.
DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "scalping_1m": {
        "id": "scalping_1m",
        "name": "Scalping 1m",
        "description": "Entri cepat di timeframe 1 menit — SMC liquidity sweep + momentum. Auto SL/TP/BE ketat.",
        "timeframe": "1m",
        "risk_per_trade": 0.005,
        "max_exposure": 0.02,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 1.6,
        "be_after_r": 0.5,
        "trail_after_r": 1.0,
        "max_positions": 1,
        "agent_overrides": {
            "technical_analyst": "Fokus eksekusi 1m: EMA(9/21) momentum, RSI(14) > 60 long / < 40 short, recent sweep level.",
            "smc_analyst": "Identifikasi liquidity sweep 1m: BSL/SSL terbaru, FVG, order block segar (2-3 bar).",
        },
        "min_confidence": 0.70,
    },
    "scalping_5m": {
        "id": "scalping_5m",
        "name": "Scalping 5m",
        "description": "Scalping ke intraday — 5 menit, konfirmasi struktur + news filter.",
        "timeframe": "5m",
        "risk_per_trade": 0.008,
        "max_exposure": 0.03,
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 2.0,
        "be_after_r": 0.6,
        "trail_after_r": 1.2,
        "max_positions": 1,
        "agent_overrides": {
            "technical_analyst": "Analisis 5m: trend EMA(21/50), pullback ke MA, RSI normalisasi.",
            "news_analyst": "Filter news 5m: skip entri 15 menit sebelum high-impact event; beri plan pra/pasca news.",
        },
        "min_confidence": 0.70,
    },
    "intraday_15m": {
        "id": "intraday_15m",
        "name": "Intraday 15m",
        "description": "Intraday — 15 menit, bias dari 1h + eksekusi 15m, hold jam.",
        "timeframe": "15m",
        "risk_per_trade": 0.01,
        "max_exposure": 0.04,
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 2.5,
        "be_after_r": 0.8,
        "trail_after_r": 1.5,
        "max_positions": 1,
        "agent_overrides": {
            "macro_analyst": "Bias intraday: DXY & real yields 15m-1h, jadwal ekonomi hari ini (calendar).",
            "smc_analyst": "Struktur 15m: HTF bias (1h), LTF entry, sweep + FVG confluence.",
        },
        "min_confidence": 0.72,
    },
    "intraday_1h": {
        "id": "intraday_1h",
        "name": "Intraday 1h",
        "description": "Intraday utama — 1 jam, akumulasi/distribusi, hold 4-24 jam.",
        "timeframe": "1h",
        "risk_per_trade": 0.012,
        "max_exposure": 0.05,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 3.0,
        "be_after_r": 1.0,
        "trail_after_r": 2.0,
        "max_positions": 2,
        "agent_overrides": {
            "smc_analyst": "Analisis 1h: akumulasi/distribusi (range contraction), order blocks HTF, liquidity besar.",
            "technical_analyst": "1h: trend EMA(50/200), support/resistance kunci, momentum harian.",
        },
        "min_confidence": 0.72,
    },
    "intraday_swing_4h": {
        "id": "intraday_swing_4h",
        "name": "Intraday → Swing 4h",
        "description": "Transisi intraday ke swing — 4 jam, posisi multi-hari, trailing lebar.",
        "timeframe": "4h",
        "risk_per_trade": 0.015,
        "max_exposure": 0.06,
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "be_after_r": 1.2,
        "trail_after_r": 2.5,
        "max_positions": 2,
        "agent_overrides": {
            "macro_analyst": "Konteks swing 4h: siklus dolar mingguan, kebijakan Fed, risiko geopolitik.",
            "smc_analyst": "Struktur 4h: market structure shift (MSS), breaker blocks, equal highs/lows.",
        },
        "min_confidence": 0.75,
    },
    "swing_1d": {
        "id": "swing_1d",
        "name": "Swing 1d",
        "description": "Swing penuh — harian, posisi 1-4 minggu, manajemen longgar.",
        "timeframe": "1d",
        "risk_per_trade": 0.02,
        "max_exposure": 0.08,
        "sl_atr_mult": 2.5,
        "tp_atr_mult": 5.0,
        "be_after_r": 1.5,
        "trail_after_r": 3.0,
        "max_positions": 3,
        "agent_overrides": {
            "technical_analyst": "Swing 1d: trend mingguan, EMA(50/200) daily, pola 1-2-3 / double top-bottom.",
            "macro_analyst": "Swing: siklus makro mingguan, perbandingan real yield global, stagflasi/inflasi.",
            "smc_analyst": "Struktur 1d: major market structure, HTF liquidity (weekly), accumulation/distribution zones.",
        },
        "min_confidence": 0.75,
    },
}


async def get_active_profile(redis: Any) -> dict[str, Any]:
    """Baca profil aktif (realtime dari Redis, tanpa restart)."""
    try:
        active_id_raw = await redis.get(ACTIVE_KEY)
        if active_id_raw:
            # FIX 19 Aug 2026: decode bytes (str(b'..') merusak id → fallback)
            if isinstance(active_id_raw, bytes):
                active_id = active_id_raw.decode()
            else:
                active_id = str(active_id_raw)
            profile = await get_profile(redis, active_id)
            if profile:
                return profile
    except Exception:  # nosec B110 — Redis down → fallback default
        pass
    # Fallback: profil scalping_1m
    return dict(DEFAULT_PROFILES["scalping_1m"])


async def get_profile(redis: Any, profile_id: str) -> dict[str, Any] | None:
    """Baca satu profil (custom dari Redis dulu, fallback default)."""
    try:
        raw = await redis.hget(PROFILES_KEY, profile_id)
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return data
    except Exception:  # nosec B110 — Redis down → fallback default
        pass
    return dict(DEFAULT_PROFILES.get(profile_id, DEFAULT_PROFILES["scalping_1m"]))


async def list_profiles(redis: Any) -> list[dict[str, Any]]:
    """Semua profil: custom dari Redis + default yang belum di-override."""
    out: list[dict[str, Any]] = []
    try:
        raw_map = await redis.hgetall(PROFILES_KEY)
        custom: dict[str, dict[str, Any]] = {}
        for k, v in (raw_map or {}).items():
            key = k.decode() if isinstance(k, bytes) else str(k)
            val = v.decode() if isinstance(v, bytes) else str(v)
            try:
                custom[key] = json.loads(val)
            except Exception as _exc:  # profil korup → skip
                print(f"[profiles] skip corrupt {key}: {str(_exc)[:80]}", flush=True)
                continue
        for pid, default in DEFAULT_PROFILES.items():
            merged = {**default, **(custom.get(pid) or {})}
            out.append(merged)
        for pid, c in custom.items():
            if pid not in DEFAULT_PROFILES:
                out.append(c)
    except Exception:
        out = [dict(v) for v in DEFAULT_PROFILES.values()]
    try:
        active_raw = await redis.get(ACTIVE_KEY)
        # FIX 19 Aug 2026: str(bytes) = "b'intraday_15m'" — BUG! resume
        # decode eksplisit. SEBELUMNYA: active Tidak pernah True di list
        # ("stuck gabisa aktifkan profile") + worker selalu fallback
        # scalping_1m walau profile lain di-set aktif.
        if isinstance(active_raw, bytes):
            active = active_raw.decode()
        else:
            active = str(active_raw or "") or "scalping_1m"
    except Exception:
        active = "scalping_1m"
    return [dict(p, active=(p.get("id") == active)) for p in out]


async def upsert_profile(redis: Any, profile: dict[str, Any]) -> dict[str, Any]:
    """Simpan profil (custom) — realtime, tanpa restart."""
    pid = str(profile.get("id", ""))
    if not pid:
        msg = "profile id required"
        raise ValueError(msg)
    await redis.hset(PROFILES_KEY, pid, json.dumps(profile))
    return profile


async def delete_profile(redis: Any, profile_id: str) -> None:
    await redis.hdel(PROFILES_KEY, profile_id)


async def set_active_profile(redis: Any, profile_id: str) -> None:
    await redis.set(ACTIVE_KEY, profile_id)
