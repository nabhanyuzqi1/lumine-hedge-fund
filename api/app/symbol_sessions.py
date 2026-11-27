"""Jadwal simbol aktif: XAUUSD hari kerja, BTCUSD akhir pekan (t_2a1fbf01).

Keputusan owner 26 Nov 2026: "bnb usd hanya jalan saat weekend, xau weekdays".
Tujuannya dua: (1) tidak ada order ke pasar yang tutup (retcode 10018 yang
menghabiskan 917 order gagal/24 jam), (2) prompt per siklus hanya memuat simbol
yang benar-benar bisa ditradingkan -> konteks lebih kecil dan relevan.

Batas hari memakai zona waktu broker/WIB (Asia/Jakarta), karena sesi yang
dipakai EA dan jadwal manual owner sama-sama WIB.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

# Simbol yang hanya ditradingkan Senin-Jumat (XAUUSD tutup akhir pekan).
WEEKDAY_SYMBOLS = frozenset({"XAUUSD"})
# Simbol yang hanya ditradingkan Sabtu-Minggu (crypto 24/7 di MT5, dipakai
# owner untuk mengisi akhir pekan saat XAUUSD tutup).
WEEKEND_SYMBOLS = frozenset({"BTCUSD"})


def is_weekend(now: datetime) -> bool:
    return now.astimezone(WIB).weekday() >= 5  # Sabtu=5, Minggu=6


def active_symbols(now: datetime, allowed: list[str] | None, default: tuple[str, ...] = ()) -> list[str]:
    """Simbol yang boleh dianalisa siklus ini.

    - Filter pertama: `allowed_symbols` dari settings (tidak pernah menambah
      simbol yang tidak diizinkan owner).
    - Filter kedua: jadwal hari. Simbol tanpa aturan jadwal (tidak ada di
      WEEKDAY_WEEKEND set) selalu dianggap aktif.
    """
    base = [s for s in (allowed or []) if isinstance(s, str)]
    if not base:
        base = list(default)
    weekend = is_weekend(now)
    out = []
    for sym in base:
        s = sym.upper()
        if s in WEEKDAY_SYMBOLS and weekend:
            continue
        if s in WEEKEND_SYMBOLS and not weekend:
            continue
        out.append(sym)
    return out


def schedule_note(now: datetime) -> dict:
    """Info jadwal untuk UI/prompt (bukan instruksi, hanya keterangan)."""
    wib = now.astimezone(WIB)
    return {
        "wib": wib.isoformat(timespec="minutes"),
        "hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][wib.weekday()],
        "weekend": is_weekend(now),
        "aktif": "BTCUSD" if is_weekend(now) else "XAUUSD",
    }
