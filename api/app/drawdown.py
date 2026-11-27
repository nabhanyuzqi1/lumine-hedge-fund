"""Satu sumber logika drawdown harian (A6) untuk SEMUA pemicu otomatis.

Keputusan owner 25 Nov 2026 (kartu AUDIT-A2): parameter drawdown harian
hanya SATU, yaitu persen equity awal hari di settings
`kill_switch_triggers.daily_drawdown_pct` (halaman Ops -> Operations &
Recovery). Gate order (auto-halt), circuit breaker agent LLM, dan evaluator
kill-switch wajib membaca kunci yang sama dan memakai aritmetika yang sama.
Bug yang diperbaiki: gate masih memicu halt dari `max_daily_drawdown` (USD,
default 100) sehingga owner bisa menyetel 10% di Ops tapi yang menembak
tetap -100 USD.

Modul ini murni (tanpa I/O, tanpa import modul app lain) supaya bisa dipakai
`risk.py` (fungsi murni) maupun modul ber-DB (`kill_switch.py`,
`llm_risk.py`) tanpa siklus import.
"""
from __future__ import annotations

# A6, KEPUTUSAN_OWNER.md §I: 3% equity awal hari -> auto-halt.
DEFAULT_DAILY_DRAWDOWN_PCT = 3.0

# Fallback saldo acuan bila settings belum punya saldo awal (instalasi baru,
# simulasi/backtest tanpa akun).
DEFAULT_START_BALANCE = 10000.0


def start_balance(settings: dict | None) -> float:
    """Saldo acuan drawdown harian: daily_start_balance -> initial_balance."""
    s = settings if isinstance(settings, dict) else {}
    for key in ("daily_start_balance", "initial_balance"):
        try:
            val = float(s.get(key))
        except (TypeError, ValueError):
            continue
        if val:
            return val
    return DEFAULT_START_BALANCE


def pct_from_pnl(daily_pnl: float, start: float | None) -> float:
    """Drawdown hari ini (%) dari saldo acuan. Profit (atau nol) -> 0.0."""
    try:
        pnl = float(daily_pnl)
    except (TypeError, ValueError):
        return 0.0
    try:
        base = float(start) if start is not None else 0.0
    except (TypeError, ValueError):
        base = 0.0
    if base <= 0:
        return 0.0
    return max(0.0, -pnl) / base * 100.0


def limit_pct(settings: dict | None) -> float | None:
    """Ambang A6 (%) dari halaman Ops: kill_switch_triggers.daily_drawdown_pct.

    Semantik sama dengan kill_switch.get_triggers():
    - key tidak ada / settings kosong -> DEFAULT_DAILY_DRAWDOWN_PCT;
    - key ada tapi None -> trigger sengaja DIMATIKAN (return None);
    - nilai bukan angka -> fallback default (fail-safe: proteksi tetap ada).
    """
    s = settings if isinstance(settings, dict) else {}
    triggers = s.get("kill_switch_triggers")
    if not isinstance(triggers, dict) or "daily_drawdown_pct" not in triggers:
        return DEFAULT_DAILY_DRAWDOWN_PCT
    raw = triggers.get("daily_drawdown_pct")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_DRAWDOWN_PCT
