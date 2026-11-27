"""Rentang kewajaran + validasi bersama kanal tulis guardrail (kartu t_f412fd48).

Satu tempat untuk semua angka yang bisa diubah dari UI:

- auto-trigger kill-switch  -> ``TRIGGER_RANGES``
- batas agent LLM           -> ``LLM_RISK_RANGES`` (gabungan key lama + v2)
- auto-lot agent LLM        -> ``LLM_AUTO_LOT_RANGES``
- interval siklus agent LLM -> ``LLM_INTERVAL_RANGE_S``

`PUT /admin/risk-settings` dan `PUT /kill-switch/triggers` WAJIB memakai
fungsi di modul ini. Temuan audit IA 26 Nov: dua endpoint dengan guard
berbeda membuat Ops bisa menyimpan drawdown 500% tanpa ditolak. Setelah
modul ini, tidak ada endpoint yang bisa menulis trigger di luar rentang,
sekalipun kliennya lama.

Rentang di sini BUKAN policy trading: ia penjaga salah ketik (mis. 500%
atau 0 detik). Angka final kebijakan tetap di KEPUTUSAN_OWNER.md §I.
"""
from __future__ import annotations

from . import config

# ── auto-trigger kill-switch ────────────────────────────────────────────────
# Batas ANTI-SALAH-KETIK (kartu t_dc104883 SEC-GUARD), bukan policy trading.
# Nilai policy final (A6 3%, A7 8%, FAILED 3, A12 6 s, halt 60 s) ada di
# KEPUTUSAN_OWNER.md §I dan berada jauh di dalam rentang ini. Endpoint mana pun
# yang menulis `kill_switch_triggers` wajib lewat rentang ini, supaya Ops tidak
# bisa menyimpan DD 500% atau 0 detik lewat jalur lama.
TRIGGER_RANGES: dict[str, tuple[float, float]] = {
    "daily_drawdown_pct": (0.1, 50.0),
    "total_drawdown_pct": (0.1, 80.0),
    "consecutive_failed_orders": (1, 1000),
    "ea_offline_seconds": (1.0, 3600.0),
    "ea_offline_halt_seconds": (1.0, 86400.0),
    # Default trigger 5 s (kill_switch.DEFAULT_TRIGGERS); 5 s = periode evaluasi
    # paling rapat yang diizinkan, 1 jam = paling lambat.
    "check_interval_seconds": (5.0, 3600.0),
}
TRIGGER_INT_KEYS = frozenset({"consecutive_failed_orders"})

# ── llm_risk (key lama di risk.DEFAULT_LLM_RISK + key v2 di llm_risk.py) ────
LLM_RISK_RANGES: dict[str, tuple[float, float]] = {
    "max_orders_per_min": (1, 60),
    "max_orders_per_day": (1, 2000),
    "cooldown_s": (0.0, 86400.0),
    # AUDIT-A2: sumber kedua drawdown; tidak boleh lebih longgar dari trigger
    # harian (25%) karena ia mem-pause agent, bukan meng-halt akun.
    "drawdown_pause_pct": (0.1, 25.0),
    "consecutive_failed_pause": (1, 50),
    "ea_offline_block_s": (1.0, 3600.0),
    "check_interval_seconds": (1.0, 300.0),
    # key v2 (FUND2-LLM-B1)
    "max_layers": (1, 10),
    "layer_volume_ratio_max": (0.05, 5.0),
}
LLM_RISK_INT_KEYS = frozenset({
    "max_orders_per_min", "max_orders_per_day", "consecutive_failed_pause",
    "max_layers",
})
LLM_RISK_BOOL_KEYS = frozenset({
    "block_new_order_with_position", "modify_sl_only_tighten",
})
# Ambang breaker agent SELALU diturunkan dari kill_switch_triggers
# (llm_risk._apply_breaker_triggers). Menulisnya lewat llm_risk dulu diterima
# lalu ditimpa saat dibaca, jadi owner melihat "tersimpan" tetapi angka tidak
# pernah berubah. Sekarang ditolak keras dengan alamat yang benar.
LLM_RISK_DERIVED_KEYS = frozenset({
    "drawdown_pause_pct", "consecutive_failed_pause", "ea_offline_block_s",
})

# ── llm_auto_lot ────────────────────────────────────────────────────────────
LLM_AUTO_LOT_RANGES: dict[str, tuple[float, float]] = {
    # override risk per trade khusus auto-lot; None = ikut risk_per_trade_pct
    "risk_pct": (0.05, 2.0),
}

# ── interval siklus agent LLM ───────────────────────────────────────────────
# Floor 30 s (keputusan owner): lebih cepat dari itu = spam LLM + biaya.
# Ceiling 86400 s (1 hari): salah ketik "3000" bukan "300" tidak boleh
# membuat agent praktis mati tanpa ada yang sadar.
LLM_INTERVAL_RANGE_S: tuple[float, float] = (30.0, 86400.0)
DEFAULT_LLM_INTERVAL_S = 300.0
# Key kanonik (AUDIT-E, t_bb927ec7): `PUT /llm-agent/interval` menulis ini.
LLM_INTERVAL_SETTING_KEY = "llm_agent_interval_s"
# Key lama (kartu t_f412fd48) yang ditulis `PUT /admin/risk-settings`. Tetap
# dibaca sebagai alias supaya nilai yang sudah tersimpan di DB produksi tidak
# hilang saat key kanonik belum pernah ditulis.
LLM_INTERVAL_LEGACY_KEY = "llm_interval_s"


class GuardrailRangeError(ValueError):
    """Nilai di luar rentang kewajaran atau bentuknya salah (-> HTTP 422)."""


def _is_number(value) -> bool:
    # bool adalah subclass int: True tidak boleh lolos sebagai 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_number(key: str, value, lo: float, hi: float, *, integer: bool) -> float | int:
    if not _is_number(value):
        raise GuardrailRangeError(f"{key} harus berupa angka")
    num = float(value)
    if num != num or num in (float("inf"), float("-inf")):  # NaN / inf
        raise GuardrailRangeError(f"{key} harus berupa angka berhingga")
    if not (lo <= num <= hi):
        raise GuardrailRangeError(f"{key} di luar rentang wajar ({lo:g}..{hi:g})")
    if integer:
        if num != int(num):
            raise GuardrailRangeError(f"{key} harus bilangan bulat")
        return int(num)
    return num


def _reject_unknown(updates: dict, allowed, *, object_label: str) -> None:
    unknown = sorted(set(updates) - set(allowed))
    if unknown:
        raise GuardrailRangeError(
            f"{object_label}: key tidak dikenal {', '.join(unknown)} "
            f"(dikenal: {', '.join(sorted(allowed))})"
        )


def validate_trigger_updates(updates: dict, *,
                             allowed_modes: set[str] | frozenset[str] | None = None) -> dict:
    """Validasi patch auto-trigger kill-switch; kembalikan patch bersih.

    Satu-satunya validator untuk `kill_switch_triggers`, dipakai
    `PUT /admin/risk-settings` DAN `PUT /kill-switch/triggers` (kartu
    t_dc104883): dua kanal tulis tidak boleh punya dua set aturan.

    `allowed_modes` = himpunan mode sah (kill_switch.MODES). Bila diberikan,
    `modes` ikut divalidasi di sini supaya pemanggil tidak menduplikasi
    pemeriksaan. Tanpa `allowed_modes`, `modes` dilewati (kompatibilitas
    pemanggil lama yang sudah memvalidasinya sendiri).

    Semua field yang salah dilaporkan sekaligus (satu pesan per field) supaya
    form UI bisa menandai tiap input; pemanggil mengubahnya jadi HTTP 422 dan
    TIDAK ada nilai yang ditulis sebelum fungsi ini selesai.
    """
    if not isinstance(updates, dict):
        raise GuardrailRangeError("kill_switch_triggers harus objek")
    out: dict = {}
    errors: list[str] = []
    for key, value in updates.items():
        if isinstance(value, bool) and key not in (
            "ea_offline_requires_positions", "position_mismatch"
        ):
            # bool bukan angka: True tidak boleh lolos sebagai 1
            errors.append(f"{key} harus berupa angka")
            continue
        if key == "modes":
            if allowed_modes is None:
                continue
            if not isinstance(value, dict):
                errors.append("modes harus objek {trigger: mode}")
                continue
            bad = {t: m for t, m in value.items() if m not in allowed_modes}
            if bad:
                errors.append(
                    "mode tidak dikenal: "
                    + ", ".join(f"{t}={m}" for t, m in sorted(bad.items()))
                    + f" (sah: {', '.join(sorted(allowed_modes))})"
                )
                continue
            out[key] = dict(value)
            continue
        if key in ("ea_offline_requires_positions", "position_mismatch"):
            if not isinstance(value, bool):
                errors.append(f"{key} harus boolean")
                continue
            out[key] = value
            continue
        if key not in TRIGGER_RANGES:
            errors.append(
                f"trigger '{key}' tidak dikenal "
                f"(dikenal: {', '.join(sorted(TRIGGER_RANGES))})")
            continue
        lo, hi = TRIGGER_RANGES[key]
        try:
            out[key] = _check_number(key, value, lo, hi,
                                     integer=key in TRIGGER_INT_KEYS)
        except GuardrailRangeError as exc:
            errors.append(str(exc))
    if errors:
        raise GuardrailRangeError("; ".join(errors))
    return out


def validate_llm_risk_updates(updates: dict) -> dict:
    """Validasi patch llm_risk (angka + boolean v2). Key asing ditolak."""
    if not isinstance(updates, dict):
        raise GuardrailRangeError("llm_risk harus objek")
    derived = sorted(set(updates) & LLM_RISK_DERIVED_KEYS)
    if derived:
        raise GuardrailRangeError(
            "llm_risk." + ", llm_risk.".join(derived)
            + " dikelola di kill_switch_triggers (tab Batas Risiko / Kontrol "
            "Darurat), bukan di setelan agent; ubah di sana agar breaker dan "
            "kill-switch memakai satu angka")
    allowed = set(LLM_RISK_RANGES) | LLM_RISK_BOOL_KEYS
    _reject_unknown(updates, allowed, object_label="llm_risk")
    out: dict = {}
    for key, value in updates.items():
        if key in LLM_RISK_BOOL_KEYS:
            if not isinstance(value, bool):
                raise GuardrailRangeError(f"llm_risk.{key} harus boolean")
            out[key] = value
            continue
        lo, hi = LLM_RISK_RANGES[key]
        out[key] = _check_number(key, value, lo, hi,
                                 integer=key in LLM_RISK_INT_KEYS)
    return out


def validate_auto_lot_updates(updates: dict) -> dict:
    """Validasi patch llm_auto_lot: `enabled` boolean + `risk_pct` opsional."""
    if not isinstance(updates, dict):
        raise GuardrailRangeError("llm_auto_lot harus objek")
    allowed = {"enabled", *LLM_AUTO_LOT_RANGES}
    _reject_unknown(updates, allowed, object_label="llm_auto_lot")
    out: dict = {}
    for key, value in updates.items():
        if key == "enabled":
            if not isinstance(value, bool):
                raise GuardrailRangeError("llm_auto_lot.enabled harus boolean")
            out[key] = value
            continue
        if value is None:  # None = hapus override, ikut risk_per_trade_pct
            out[key] = None
            continue
        lo, hi = LLM_AUTO_LOT_RANGES[key]
        out[key] = _check_number(key, value, lo, hi, integer=False)
    return out


def validate_interval_s(value) -> float:
    """Interval siklus agent dalam detik; floor 30 s, ceiling 24 jam."""
    lo, hi = LLM_INTERVAL_RANGE_S
    return float(_check_number(LLM_INTERVAL_SETTING_KEY, value, lo, hi, integer=False))


def _clamp_interval(value: float) -> float:
    lo, hi = LLM_INTERVAL_RANGE_S
    return min(max(value, lo), hi)


def effective_interval(settings: dict) -> tuple[float, str]:
    """(detik efektif, sumber); sumber = settings | env | default.

    Urutan baca: settings key kanonik `llm_agent_interval_s` (AUDIT-E) ->
    settings key lama `llm_interval_s` (kartu t_f412fd48, alias) -> env
    ``LLM_INTERVAL_S`` -> 300 s. Nilai di luar rentang DI-CLAMP, bukan
    ditolak: baris settings lama atau env yang salah ketik tidak boleh
    membuat agent berhenti sama sekali.

    Dipakai GET /llm-agent/status, GET /llm-agent/config, dan loop agent
    (dibaca ulang TIAP siklus), supaya angka yang tampil di UI adalah angka
    yang benar-benar dipakai (bukan env yang tak terlihat).
    """
    for key in (LLM_INTERVAL_SETTING_KEY, LLM_INTERVAL_LEGACY_KEY):
        raw = settings.get(key)
        if raw is None or raw == "":
            continue
        try:
            return _clamp_interval(float(raw)), "settings"
        except (TypeError, ValueError):
            continue  # nilai rusak di settings: jatuh ke sumber berikutnya
    raw_env = config.get("LLM_INTERVAL_S", "")
    if raw_env not in (None, ""):
        try:
            return _clamp_interval(float(raw_env)), "env"
        except (TypeError, ValueError):
            pass
    return DEFAULT_LLM_INTERVAL_S, "default"


def effective_interval_s(settings: dict) -> float:
    """Interval efektif dalam detik (lihat `effective_interval`)."""
    return effective_interval(settings)[0]
