"""Config risk per-strategy (RISK-D, t_a172bb7b).

Model: **global = DEFAULT + HARD CEILING**, override per-strategy hanya boleh
MENGETATKAN. Satu sumber kebenaran untuk merge, validasi, dan titik pakai
(lot sizing RISK-A, trailing RISK-B, gate max posisi + batas rugi harian).

Key yang bisa di-override (lihat KEYS):

    risk_pct          % equity per trade (global: settings risk_per_trade_pct)
    max_positions     maks posisi terbuka per strategi (settings max_positions)
    daily_loss_limit  batas rugi harian strategi, USD (plafon RISK-D).
                      AUDIT-A2: plafon ini MASIH diturunkan dari
                      `max_daily_drawdown` (USD) dan hanya bisa menolak order
                      strategi ber-override; ia BUKAN auto-halt akun (A6
                      murni dari kill_switch_triggers.daily_drawdown_pct).
                      Sumber plafon ini menunggu keputusan Director.
    be_trigger_r      trigger break-even dalam R (global: settings auto_sl)
    be_buffer         buffer BE satuan harga, boleh per simbol (settings auto_sl)
    trail_atr_mult    jarak trailing = k x ATR(M5) (settings auto_sl)
    trail_activate_r  aktivasi trailing dalam R (settings auto_sl)

Aturan validasi (`validate_override`): numerik > 0 dan **<= nilai global**
per key; `max_positions` bilangan bulat >= 1; `be_buffer` per simbol dengan
ceiling per simbol (simbol tanpa batas global = ditolak, bukan ditebak).
Nilai `null` = hapus key (kembali ikut global). Invariant RISK-B
`trail_activate_r >= be_trigger_r` divalidasi pada nilai EFEKTIF.

Pertahanan berlapis: `effective()` juga meng-clamp nilai ke global
(`source = "override_capped"`). Jadi walau global mengetat SETELAH override
disetujui, pemakaian tetap tidak bisa melewati ceiling global.

Perubahan override TIDAK bisa ditulis langsung: alur `propose` (admin) ->
`decide` (owner + 2FA, lihat risk_config_routes.py). Keputusan + nilai
lama/baru tercatat di audit_log dan strategy_risk_override_requests.

Modul ini murni di level atas (tanpa I/O saat import); helper DB mengimpor
app.db/state_machine secara lazy supaya aman diimpor dari mana pun.
"""
from __future__ import annotations

from .auto_sl import auto_sl_config

# Ceiling global default bila settings tidak punya key `max_positions`
# (seed migrasi m013 mengisi 5; nilai operator tidak pernah ditimpa).
DEFAULT_MAX_POSITIONS = 5

KEY_ORDER: tuple[str, ...] = (
    "risk_pct",
    "max_positions",
    "daily_loss_limit",
    "be_trigger_r",
    "be_buffer",
    "trail_atr_mult",
    "trail_activate_r",
)

# Metadata untuk UI (label + unit). Arah selalu sama: nilai lebih kecil =
# lebih ketat, dan nilai per-strategy tidak boleh melebihi global.
KEY_META: dict[str, dict] = {
    "risk_pct": {"label": "Risk per trade", "unit": "% equity"},
    "max_positions": {"label": "Max posisi terbuka", "unit": "posisi"},
    "daily_loss_limit": {"label": "Batas rugi harian", "unit": "USD"},
    "be_trigger_r": {"label": "Break-even trigger", "unit": "R"},
    "be_buffer": {"label": "Buffer break-even", "unit": "harga"},
    "trail_atr_mult": {"label": "Trailing (x ATR)", "unit": "x ATR"},
    "trail_activate_r": {"label": "Aktivasi trailing", "unit": "R"},
}

_EPS = 1e-9


class RiskOverrideInvalid(ValueError):
    """Override per-strategy tidak sah (pesan = daftar alasan per key)."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# --------------------------------------------------------------- global/default

def _positive(value, default: float) -> float:
    """float > 0 dari settings; nilai rusak/<=0 -> default (fail-safe)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if f > 0 else default


def _positive_int(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 1 else default


def global_config(settings: dict) -> dict:
    """Nilai global efektif = DEFAULT per key (hard ceiling per-strategy)."""
    s = settings if isinstance(settings, dict) else {}
    sl = auto_sl_config(s)
    return {
        "risk_pct": _positive(s.get("risk_per_trade_pct"), 0.5),
        "max_positions": _positive_int(s.get("max_positions"),
                                       DEFAULT_MAX_POSITIONS),
        # AUDIT-A2: plafon RISK-D (USD) -- bukan ambang halt akun. Hanya
        # menolak order strategi yang override-nya lebih ketat; sumber angka
        # ini (max_daily_drawdown USD) menunggu keputusan Director.
        "daily_loss_limit": _positive(s.get("max_daily_drawdown"), 100.0),
        "be_trigger_r": float(sl["be_trigger_r"]),
        "trail_atr_mult": float(sl["trail_atr_mult"]),
        "trail_activate_r": float(sl["trail_activate_r"]),
        "be_buffer_usd": {str(k).upper(): float(v)
                          for k, v in (sl["be_buffer_usd"] or {}).items()},
    }


def strategy_symbols(strategy_id: str, settings: dict) -> list[str]:
    """Simbol yang di-trade strategi (registry; 'llm' = allowed_symbols)."""
    sid = (strategy_id or "").strip().lower()
    if not sid:
        return []
    try:
        from .strategies import REGISTRY
    except Exception:  # noqa: BLE001 - registry tidak boleh mematikan config
        REGISTRY = []
    for meta in REGISTRY:
        if meta.get("id") == sid:
            return [str(meta.get("symbol")).upper()]
    if sid == "llm":
        return [str(s).upper() for s in
                ((settings or {}).get("allowed_symbols") or [])]
    return []


# ------------------------------------------------------------------- validasi

def _as_float(key: str, raw, errors: list[str]) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        errors.append(f"{key}: harus angka")
        return None
    return float(raw)


def _check_ceiling(key: str, value: float, ceiling: float,
                   errors: list[str], unit: str = "") -> None:
    if value <= 0:
        errors.append(f"{key}: harus > 0{(' ' + unit) if unit else ''}")
    elif value > ceiling + _EPS:
        errors.append(
            f"{key}: {value} melebihi batas global {ceiling}{(' ' + unit) if unit else ''}"
            " (global = hard ceiling)")


def _clean_be_buffer(strategy_id: str, raw, glob: dict,
                     errors: list[str]) -> dict | None:
    """Normalisasi be_buffer ke {SIMBOL: nilai} dengan ceiling per simbol."""
    caps = glob["be_buffer_usd"]
    if isinstance(raw, dict):
        clean: dict[str, float] = {}
        for sym, val in raw.items():
            s = str(sym).upper()
            if s not in caps:
                errors.append(
                    f"be_buffer.{s}: simbol ini tidak punya batas global "
                    "(hard ceiling tidak bisa dilewati)")
                continue
            num = _as_float(f"be_buffer.{s}", val, errors)
            if num is None:
                continue
            if num < 0:
                errors.append(f"be_buffer.{s}: harus >= 0")
            elif num > caps[s] + _EPS:
                errors.append(
                    f"be_buffer.{s}: {num} melebihi batas global {caps[s]} "
                    "(global = hard ceiling)")
            else:
                clean[s] = num
        return clean
    num = _as_float("be_buffer", raw, errors)
    if num is None:
        return None
    symbols = strategy_symbols(strategy_id, {"allowed_symbols": list(caps)})
    if len(symbols) != 1:
        errors.append(
            "be_buffer: nilai tunggal hanya untuk strategi dengan tepat satu "
            "simbol; kirim objek {\"SIMBOL\": nilai} (mis. {\"XAUUSD\": 0.30})")
        return None
    sym = symbols[0]
    cap = caps.get(sym)
    if cap is None:
        errors.append(f"be_buffer: simbol {sym} tidak punya batas global")
        return None
    if num < 0:
        errors.append("be_buffer: harus >= 0")
        return None
    if num > cap + _EPS:
        errors.append(
            f"be_buffer: {num} melebihi batas global {cap} untuk {sym} "
            "(global = hard ceiling)")
        return None
    return {sym: num}


def validate_override(strategy_id: str, overrides, settings: dict) -> dict:
    """Validasi + normalisasi override. Raise RiskOverrideInvalid bila salah.

    Return dict bersih (hanya key dikenal, `null` dibuang = ikut global,
    be_buffer selalu {SIMBOL: nilai}). Ceiling = global_config(settings).
    """
    glob = global_config(settings)
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise RiskOverrideInvalid(["overrides harus objek JSON"])
    errors: list[str] = []
    clean: dict = {}
    for key, raw in overrides.items():
        if key not in KEY_ORDER:
            errors.append(
                f"{key}: key tidak dikenal (valid: {', '.join(KEY_ORDER)})")
            continue
        if raw is None:
            continue  # null = hapus override key ini (ikut global)
        if key == "max_positions":
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) \
                    or float(raw) != int(float(raw)):
                errors.append("max_positions: harus bilangan bulat")
                continue
            n = int(raw)
            if n < 1:
                errors.append("max_positions: harus >= 1")
            elif n > glob["max_positions"]:
                errors.append(
                    f"max_positions: {n} melebihi batas global "
                    f"{glob['max_positions']} (global = hard ceiling)")
            else:
                clean[key] = n
        elif key == "be_buffer":
            buf = _clean_be_buffer(strategy_id, raw, glob, errors)
            if buf is not None:
                clean[key] = buf
        else:
            num = _as_float(key, raw, errors)
            if num is None:
                continue
            _check_ceiling(key, num, glob[key], errors,
                           "USD" if key == "daily_loss_limit" else "")
            if not any(e.startswith(f"{key}:") for e in errors):
                clean[key] = num
    if not errors:
        eff = _merge_scalars(glob, clean)
        if eff["trail_activate_r"] + _EPS < eff["be_trigger_r"]:
            errors.append(
                "trail_activate_r: nilai efektif harus >= be_trigger_r "
                f"efektif ({eff['trail_activate_r']} < {eff['be_trigger_r']})")
    if errors:
        raise RiskOverrideInvalid(errors)
    return clean


def _merge_scalars(glob: dict, override: dict) -> dict:
    """Merge nilai skalar (tanpa clamp) - dipakai validasi invariant."""
    out = {k: glob[k] for k in KEY_ORDER if k != "be_buffer"}
    for key in out:
        if override.get(key) is not None:
            out[key] = override[key]
    return out


# ------------------------------------------------------------------- efektif

def effective(strategy_id: str, overrides, settings: dict) -> dict:
    """Config efektif satu strategi: merge(global, override) + clamp ceiling.

    Return:
      values        nilai efektif (be_buffer = {SIMBOL: nilai})
      sources       "global" | "override" | "override_capped" per key
      capped        key yang override-nya dipotong karena global mengetat
      global        nilai global (ceiling) saat ini
      override      override tersimpan yang masih dipakai (tanpa null)
      symbols       simbol strategi
    """
    glob = global_config(settings)
    ov = overrides if isinstance(overrides, dict) else {}
    values: dict = {}
    sources: dict = {}
    capped: list[str] = []
    for key in KEY_ORDER:
        if key == "be_buffer":
            continue
        raw = ov.get(key)
        if raw is None:
            values[key] = glob[key]
            sources[key] = "global"
            continue
        try:
            val = int(raw) if key == "max_positions" else float(raw)
        except (TypeError, ValueError):
            values[key] = glob[key]
            sources[key] = "global"  # data rusak -> default aman
            continue
        ceiling = glob[key]
        if val > ceiling + _EPS:
            values[key] = ceiling
            sources[key] = "override_capped"
            capped.append(key)
        else:
            values[key] = val
            sources[key] = "override"
    # be_buffer per simbol: override hanya untuk simbol yang punya ceiling.
    buf = dict(glob["be_buffer_usd"])
    src = "global"
    raw_buf = ov.get("be_buffer")
    if isinstance(raw_buf, dict):
        for sym, val in raw_buf.items():
            s = str(sym).upper()
            ceiling = glob["be_buffer_usd"].get(s)
            if ceiling is None:
                continue  # tidak ada ceiling -> tidak dipakai (fail-closed)
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if num < 0:
                continue
            if num > ceiling + _EPS:
                buf[s] = ceiling
                src = "override_capped"
                capped.append(f"be_buffer.{s}")
            else:
                buf[s] = num
                if src == "global":
                    src = "override"
    values["be_buffer"] = buf
    sources["be_buffer"] = src
    return {
        "strategy_id": str(strategy_id or ""),
        "values": values,
        "sources": sources,
        "capped": capped,
        "global": glob,
        "override": {k: v for k, v in ov.items()
                     if k in KEY_ORDER and v is not None},
        "symbols": strategy_symbols(strategy_id, settings),
    }


# ---------------------------------------------------------------- akses DB

async def _settings(conn) -> dict:
    """Settings penuh (default <- DB) lewat koneksi yang sudah ada."""
    from .state_machine import fetchall

    rows = await fetchall(conn, "SELECT key, value FROM settings")
    from .db import DEFAULT_SETTINGS

    merged = dict(DEFAULT_SETTINGS)
    for row in rows:
        merged[row["key"]] = row["value"]
    return merged


async def load_overrides(conn=None) -> dict[str, dict]:
    """Semua override tersimpan: {strategy_id: {key: value}}."""
    from .state_machine import fetchall

    if conn is None:
        from . import db
        async with db.pool().connection() as own:
            return await load_overrides(own)
    rows = await fetchall(
        conn, "SELECT strategy_id, overrides FROM strategy_risk_overrides")
    out: dict[str, dict] = {}
    for row in rows:
        ov = row["overrides"]
        out[str(row["strategy_id"]).lower()] = ov if isinstance(ov, dict) else {}
    return out


async def override_for(conn, strategy_id: str) -> dict:
    from .state_machine import fetchone

    row = await fetchone(
        conn,
        "SELECT overrides FROM strategy_risk_overrides WHERE strategy_id = %s",
        (str(strategy_id or "").lower(),),
    )
    if row is None:
        return {}
    ov = row["overrides"]
    return ov if isinstance(ov, dict) else {}


async def effective_for(conn, settings: dict, strategy_id: str) -> dict:
    """Config efektif satu strategi, dibaca di titik pakai (gate/trailing/lot)."""
    ov = await override_for(conn, strategy_id)
    return effective(strategy_id, ov, settings)


async def list_effective(conn, settings: dict,
                         strategy_ids: list[str]) -> dict[str, dict]:
    """Config efektif banyak strategi sekaligus (satu query override)."""
    overrides = await load_overrides(conn)
    return {sid: effective(sid, overrides.get(str(sid).lower(), {}), settings)
            for sid in strategy_ids}


# ------------------------------------------------------- alur approval

async def _audit(conn, actor: str, action: str, object_: str,
                 details: dict) -> None:
    """Audit trail perubahan config risk per-strategy (audit_log, PRD §18)."""
    import json

    await conn.execute(
        "INSERT INTO audit_log (actor, actor_role, action, object, details) "
        "VALUES (%s, 'admin', %s, %s, %s)",
        (actor, action, object_, json.dumps(details)),
    )


REQUEST_COLUMNS = ("id, strategy_id, overrides, status, requested_by, "
                   "request_note, decided_by, decision_note, decided_at, "
                   "applied_at, created_at")


async def propose(conn, strategy_id: str, overrides, requested_by: str,
                  note: str | None = None) -> dict:
    """Buat usulan override (status PROPOSED). Tidak mengubah config aktif.

    Validasi ceiling dijalankan SEKARANG (gagal cepat) dan diulang saat
    `decide` karena global bisa berubah selagi usulan menunggu.
    Raises RiskOverrideInvalid.
    """
    import json

    from .state_machine import fetchone

    sid = str(strategy_id or "").strip().lower()
    settings = await _settings(conn)
    clean = validate_override(sid, overrides, settings)
    # Usulan lama untuk strategi sama tidak boleh menumpuk: hanya satu yang
    # masih bisa di-approve (mencegah apply nilai yang sudah basi).
    await conn.execute(
        "UPDATE strategy_risk_override_requests SET status = 'SUPERSEDED', "
        "decided_at = now() WHERE strategy_id = %s AND status = 'PROPOSED'",
        (sid,),
    )
    row = await fetchone(
        conn,
        f"INSERT INTO strategy_risk_override_requests "
        f"(strategy_id, overrides, requested_by, request_note) "
        f"VALUES (%s, %s, %s, %s) RETURNING {REQUEST_COLUMNS}",
        (sid, json.dumps(clean), requested_by, note),
    )
    return dict(row)


async def decide(conn, request_id: int, decision: str, reviewer: str,
                 note: str | None = None) -> dict:
    """Keputusan owner atas usulan. APPROVED = terapkan override.

    Global divalidasi ULANG sebelum apply: bila ceiling global sudah
    mengetat sampai usulan ini tidak sah lagi, raise RiskOverrideInvalid
    (pemanggil memetakan ke 409; owner harus mengusulkan nilai baru).
    """
    import json

    from .state_machine import fetchone

    decision = str(decision or "").upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("decision harus APPROVED atau REJECTED")
    row = await fetchone(
        conn,
        f"SELECT {REQUEST_COLUMNS} FROM strategy_risk_override_requests "
        "WHERE id = %s FOR UPDATE",
        (request_id,),
    )
    if row is None:
        raise KeyError(f"request {request_id} tidak ditemukan")
    if row["status"] != "PROPOSED":
        raise ValueError(f"request sudah diputuskan (status {row['status']})")

    sid = str(row["strategy_id"]).lower()
    if decision == "REJECTED":
        updated = await fetchone(
            conn,
            "UPDATE strategy_risk_override_requests SET status = 'REJECTED', "
            "decided_by = %s, decision_note = %s, decided_at = now() "
            f"WHERE id = %s RETURNING {REQUEST_COLUMNS}",
            (reviewer, note, request_id),
        )
        await _audit(conn, reviewer, "RISK_OVERRIDE_REJECTED",
                     f"strategy:{sid}",
                     {"request_id": request_id, "overrides": row["overrides"],
                      "note": note})
        return dict(updated)

    settings = await _settings(conn)
    clean = validate_override(sid, row["overrides"], settings)
    previous = await override_for(conn, sid)
    await conn.execute(
        "INSERT INTO strategy_risk_overrides "
        "(strategy_id, overrides, updated_by, updated_at) "
        "VALUES (%s, %s, %s, now()) "
        "ON CONFLICT (strategy_id) DO UPDATE SET "
        "overrides = EXCLUDED.overrides, updated_by = EXCLUDED.updated_by, "
        "updated_at = now()",
        (sid, json.dumps(clean), reviewer),
    )
    updated = await fetchone(
        conn,
        "UPDATE strategy_risk_override_requests SET status = 'APPROVED', "
        "decided_by = %s, decision_note = %s, decided_at = now(), "
        "applied_at = now() "
        f"WHERE id = %s RETURNING {REQUEST_COLUMNS}",
        (reviewer, note, request_id),
    )
    await _audit(conn, reviewer, "RISK_OVERRIDE_APPLIED", f"strategy:{sid}",
                 {"request_id": request_id, "previous": previous,
                  "overrides": clean, "note": note,
                  "global_ceiling": global_config(settings)})
    result = dict(updated)
    result["effective"] = effective(sid, clean, settings)
    return result


async def list_requests(conn, strategy_id: str | None = None,
                        limit: int = 50) -> list[dict]:
    from .state_machine import fetchall

    if strategy_id:
        rows = await fetchall(
            conn,
            f"SELECT {REQUEST_COLUMNS} FROM strategy_risk_override_requests "
            "WHERE strategy_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
            (str(strategy_id).lower(), int(limit)),
        )
    else:
        rows = await fetchall(
            conn,
            f"SELECT {REQUEST_COLUMNS} FROM strategy_risk_override_requests "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (int(limit),),
        )
    return [dict(r) for r in rows]
