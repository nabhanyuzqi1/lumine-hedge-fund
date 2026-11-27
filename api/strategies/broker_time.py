"""Broker clock <-> UTC mapping for candle timestamps.

Terukur 2026-11-22 (task t_86507d65): jam server MT5 A1 = UTC+7 tetap
(tanpa DST). Bukti: string jam dari CopyRates (TimeToString) yang di-parse
di timezone sesi DB (Asia/Pontianak, juga UTC+7) menghasilkan kunci
true-UTC —

- bar M1 seed EA bertepatan persis dengan kunci M1 true-UTC pipeline
  (single coverage 5002 bar, tanpa series hantu);
- agregat M1 true 19 Nov 10:00-10:04 UTC cocok dengan bar M5 yang
  tersimpan di kunci 10:00 UTC (high/low/volume identik), bukan kunci
  05:00 UTC.

Asumsi lama (US DST, UTC+2/+3) salah untuk broker ini dan membuat
stored_to_utc menggeser waktu candle +5 jam ke masa depan, sehingga
filter "still forming" paper runner membuang 5 jam bar terbaru.

stored_to_utc kini identitas untuk candle fund2, tetapi formula umumnya
dipertahankan: sumber data lain yang menyimpan kunci jam-dinding tetap
terkonversi benar bila offset-nya diberikan dengan tepat.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Asumsi A1' (terukur 2026-11-22): jam server A1 = UTC+7 tetap.
BROKER_UTC_OFFSET_H = 7


def broker_utc_offset_hours(dt_utc: datetime) -> int:
    """Offset jam server A1 terhadap UTC: UTC+7 tetap (terukur, lihat modul)."""
    return BROKER_UTC_OFFSET_H


def stored_to_utc(stored: datetime, db_tz_offset_h: int, broker_offset_h: int) -> datetime:
    """Convert a stored candle timestamp to the true UTC instant.

    stored = broker-naive time rendered in the DB session timezone, so the
    stored instant equals broker_naive - db_tz_offset_h. True UTC equals
    broker_naive - broker_offset_h. Hence:
        true_utc = stored_instant + (db_tz_offset_h - broker_offset_h) hours.
    """
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    return stored.astimezone(timezone.utc) + timedelta(hours=db_tz_offset_h - broker_offset_h)
