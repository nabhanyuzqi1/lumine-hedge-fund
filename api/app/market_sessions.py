"""Sesi pasar per simbol dari tabel `market_sessions` (t_afd7fe4e).

Kartu t_afd7fe4e butir A1: pre-flight gate tidak boleh menebak jam pasar dari
kode. Jam disimpan di tabel `market_sessions` (migrasi o015) supaya owner/ops
bisa mengoreksi (mis. libur bursa, perubahan jam DST) tanpa deploy:

    symbol | weekday | open_minute | close_minute | timezone | enabled

- `weekday` = nomor hari Python `datetime.weekday()` (0=Senin .. 6=Minggu)
  di zona `timezone` (default Asia/Jakarta, sama dengan jam EA & jadwal owner).
- `open_minute`/`close_minute` = menit sejak tengah malam lokal.
- `close_minute < open_minute` = jendela melewati tengah malam; jendela itu
  ditutup pada hari berikutnya pukul `close_minute`.
- `close_minute == 1440` = sampai akhir hari (24/7 untuk crypto).

Modul ini murni logika waktu (tanpa I/O di `session_open`) supaya bisa diuji
deterministik, plus loader tipis dari DB.

Simbol tanpa baris di tabel = TIDAK ada jendela yang bisa dibuktikan ->
fail-closed (pre-flight memblok dengan `market_session_missing`), bukan
dianggap 24/7. Menambah simbol trading baru berarti menambah baris sesi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WIB = ZoneInfo("Asia/Jakarta")

# Kode alasan (dipakai pre-flight + audit order_events).
CODE_CLOSED = "market_closed"
CODE_MISSING = "market_session_missing"
CODE_DISABLED = "market_session_disabled"


def _tz(name: str | None) -> ZoneInfo:
    """Zona waktu baris sesi; nama tak dikenal -> WIB (jam kerja kantor)."""
    if not name:
        return WIB
    try:
        return ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError):
        return WIB


def _minutes(hhmm: str) -> int:
    """'06:00' -> 360 (helper untuk test/CLI)."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def window_contains(row: dict, now: datetime) -> tuple[bool, str]:
    """Apakah `now` (tz-aware) jatuh di jendela sesi satu baris tabel.

    Return (open, keterangan). Keterangan dipakai audit/log, mis.
    "Senin 06:00-04:59 WIB (Asia/Jakarta)".
    """
    tz = _tz(row.get("timezone"))
    local = now.astimezone(tz)
    weekday = int(row["weekday"])
    open_min = int(row["open_minute"])
    close_min = int(row["close_minute"])
    label = (f"{_DAY_NAMES[weekday]} {_hm(open_min)}-{_hm(close_min)} "
             f"{tz.key}")

    if close_min > open_min:
        # Jendela di hari yang sama (klausa 1440 = sampai 24:00).
        same_day = local.weekday() == weekday and open_min <= _local_minutes(local) < close_min
        return same_day, label
    if close_min == open_min:
        return False, label  # jendela kosong (CHECK di DB mencegahnya)
    # Jendela melewati tengah malam: buka di `weekday` mulai open_min, tutup
    # di hari berikutnya sebelum close_min.
    if local.weekday() == weekday and _local_minutes(local) >= open_min:
        return True, label
    yesterday = (weekday + 1) % 7
    if local.weekday() == yesterday and _local_minutes(local) < close_min:
        return True, label
    return False, label


def _local_minutes(local: datetime) -> int:
    return local.hour * 60 + local.minute


def _hm(minutes: int) -> str:
    if minutes >= 1440:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


_DAY_NAMES = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


def session_open(rows: list[dict], now: datetime) -> tuple[bool, str]:
    """Evaluasi semua baris sesi satu simbol.

    Return (open, reason). `reason` menjelaskan keadaan saat `now`:
    - open  -> jendela yang cocok (mis. "Selasa 06:00-04:59 Asia/Jakarta")
    - tutup -> "di luar jam sesi (XAUUSD): ..." berisi jendela hari ini
               dan besok sebagai konteks, atau kode sesi hilang/disabled.
    """
    if not rows:
        return False, CODE_MISSING
    enabled = [r for r in rows if r.get("enabled", True)]
    if not enabled:
        return False, CODE_DISABLED
    for row in enabled:
        open_, label = window_contains(row, now)
        if open_:
            return True, label
    tz = _tz(enabled[0].get("timezone"))
    local = now.astimezone(tz)
    today = local.weekday()
    today_rows = [r for r in enabled if int(r["weekday"]) == today]
    next_rows = [r for r in enabled if int(r["weekday"]) == (today + 1) % 7]
    parts = [f"sekarang {_DAY_NAMES[today]} {_hm(_local_minutes(local))} {tz.key}"]
    if today_rows:
        r = today_rows[0]
        parts.append(f"jendela hari ini {_hm(int(r['open_minute']))}-"
                     f"{_hm(int(r['close_minute']))}")
    if next_rows:
        r = next_rows[0]
        parts.append(f"jendela berikutnya mulai {_DAY_NAMES[(today + 1) % 7]} "
                     f"{_hm(int(r['open_minute']))}")
    if not today_rows and not next_rows:
        parts.append("tidak ada jendela terjadwal")
    return False, f"{CODE_CLOSED}: " + "; ".join(parts)


async def load_all(conn) -> dict[str, list[dict]]:
    """Baca seluruh jadwal sesi (dipakai ingest sebagai cache filter candle)."""
    cur = await conn.execute(
        """
        SELECT symbol, weekday, open_minute, close_minute, timezone, enabled, note
        FROM market_sessions
        ORDER BY symbol, weekday
        """
    )
    out: dict[str, list[dict]] = {}
    for row in await cur.fetchall():
        out.setdefault(str(row["symbol"]).upper(), []).append(dict(row))
    return out


async def load_rows(conn, symbols: list[str] | tuple[str, ...]) -> dict[str, list[dict]]:
    """Baca sesi semua simbol sekaligus (satu query, read-only)."""
    wanted = [str(s).upper() for s in symbols if isinstance(s, str)]
    if not wanted:
        return {}
    cur = await conn.execute(
        """
        SELECT symbol, weekday, open_minute, close_minute, timezone, enabled, note
        FROM market_sessions
        WHERE symbol = ANY(%s)
        ORDER BY symbol, weekday
        """,
        (wanted,),
    )
    out: dict[str, list[dict]] = {sym: [] for sym in wanted}
    for row in await cur.fetchall():
        out.setdefault(str(row["symbol"]).upper(), []).append(dict(row))
    return out


def next_open(rows: list[dict], now: datetime, horizon_days: int = 8) -> datetime | None:
    """Waktu buka terdekat (untuk UI/pesan skip), atau None bila tak ada.

    Iterasi menit adalah cara paling sederhana yang benar untuk jendela yang
    melewati tengah malam; horizon 8 hari mencakup satu siklus mingguan penuh.
    Dipakai hanya untuk pesan/laporan, bukan gate (gate memakai session_open).
    """
    if not rows:
        return None
    enabled = [r for r in rows if r.get("enabled", True)]
    if not enabled:
        return None
    tz = _tz(enabled[0].get("timezone"))
    probe = now.astimezone(tz).replace(second=0, microsecond=0)
    for _ in range(horizon_days * 24 * 60):
        probe += timedelta(minutes=1)
        if session_open(enabled, probe)[0]:
            return probe.astimezone(timezone.utc)
    return None
