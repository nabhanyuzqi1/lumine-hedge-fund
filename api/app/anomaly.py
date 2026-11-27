"""Deteksi anomali harian → Telegram (PRD v2.1 §5.9 cron harian; task FUND2-P4 t_f2p4a2).

Tiga deteksi, jendela 24 jam dibanding baseline 7 hari sebelumnya:
  1. Latensi order naik  : p95 resolusi order 24 jam >= 2x baseline p95
                           DAN di atas SLO 300 ms (PRD §6).
  2. Spread abnormal     : median spread 24 jam per simbol >= 2x baseline;
                           untuk XAUUSD tambahan ambang absolut 0,50 USD
                           (PRD §5.2 [USULAN]; kalibrasi harga gold — simbol
                           lain seperti BTCUSD memakai rasio baseline saja
                           karena skala harga berbeda).
  3. Rasio FAILED tinggi : >= 20% order terminal 24 jam berstatus FAILED
                           (minimal 5 order terminal).

Scope (penegasan Direktur 22 Nov): rekap harian TIDAK diimplementasi ulang —
itu milik t_f2p1b3 (daemon fund2-alerts, jam 07:00 WIB). Modul ini pesan
tambahan harian yang berdiri sendiri: file baru, tanpa mengedit app.alerts
atau modul API lain (anti-clobber). Dijalankan systemd timer
fund2-anomaly.timer tiap 07:05 WIB (00:05 UTC), 5 menit setelah rekap.

Kirim memakai telegram_bot.notify_owner (token + chat id dari env
TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID). Nilai dinamis di-escape manual
(salinan kecil _md_escape — sengaja tidak import dari app.alerts supaya
modul ini tetap independen dari WIP worker lain di alerts.py).

CLI:
  python -m app.anomaly            # hitung + cetak laporan, tanpa kirim
  python -m app.anomaly --send     # hitung + kirim ke owner Telegram
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from . import config, db
from .state_machine import fetchall
from .telegram_bot import notify_owner

log = logging.getLogger("fund2.anomaly")

WIB = timezone(timedelta(hours=7))

# ── ambang deteksi (PRD §5.2, §5.6, §6; nilai [USULAN] default) ─────────────
LATENCY_RATIO = 2.0        # p95 naik >= 2x baseline (PRD §13: alert bila p95 naik 2x)
LATENCY_SLO_S = 0.300      # SLO T0→T2 p95 < 300 ms (PRD §6); di bawah ini sehat
LATENCY_MIN_ORDERS = 3     # belum ada 3 order selesai 24 jam -> data kurang
SPREAD_RATIO = 2.0         # median spread >= 2x baseline per simbol
SPREAD_ABS_USD = 0.50      # ambang absolut PRD §5.2 [USULAN], kalibrasi XAUUSD
SPREAD_ABS_SYMBOLS = {"XAUUSD"}  # simbol yang memakai ambang absolut
SPREAD_MIN_SAMPLES = 12    # minimal 12 sampel 5-detik per jendela
FAILED_RATIO = 0.20        # >= 20% order terminal FAILED
FAILED_MIN_TERMINAL = 5    # minimal 5 order terminal agar rasio bermakna

WINDOW = "24 hours"        # jendela deteksi
BASELINE = "8 days"        # baseline: 7 hari sebelum jendela (8h - 24h)

TERMINAL_STATUSES = ("FILLED", "FAILED", "RECONCILED",
                     "ORPHAN_ADOPTED", "ORPHAN_CLOSED", "FILLED_THEN_CLOSED")

# t_4651d431 (insiden 25 Nov 2026): order dari layanan QA (driver latensi,
# user ber-role 'qa') BUKAN trafik live -- kalau ikut dihitung, metrik
# anomaly harian terkontaminasi (p95 175 s, FAILED 55%).
#
# Order QA dikenali dari event RECEIVED-nya: payload->>'username' adalah
# user ber-role 'qa' (order API menulis username pembuat; order CLOSE
# flatten menulis username aktor). Dipakai ulang di semua query orders.
#
# Order historis yang salah atribusi ke admin (721 order driver 25 Nov
# 2026) ditandai compensating event QA_REATTRIBUTED (order_events
# append-only, PRD 19.4: koreksi lewat event, bukan UPDATE); atribusi
# ulang itu yang menang atas username RECEIVED lama.
SQL_EXCLUDE_QA = (
    "AND NOT EXISTS ("
    "  SELECT 1 FROM users u"
    "  WHERE u.role = 'qa'"
    "    AND u.username = COALESCE("
    "      (SELECT e3.payload->>'username' FROM order_events e3"
    "        WHERE e3.order_id = orders.id AND e3.to_status = 'QA_REATTRIBUTED'"
    "        ORDER BY e3.id LIMIT 1),"
    "      (SELECT e2.payload->>'username' FROM order_events e2"
    "        WHERE e2.order_id = orders.id AND e2.to_status = 'RECEIVED'"
    "        ORDER BY e2.id LIMIT 1))"
    ")"
)


# Order sintetis (harness latensi p5-latency-gate-final, mode
# 'harness-synthetic-ea') menulis order + event LATENCY ke DB produksi.
# Broker delay buatan 100-250 ms + pace 6,8 s membuat T2-T0 ~110-183 s,
# sehingga p95 24 jam meledak (alert SEV-3 26 Nov 2026: p95 183 s, n=207)
# padahal tidak ada satu pun order broker sungguhan. Order seperti ini
# dikenali dari payload-nya (mode/run/synthetic) dan dikecualikan dari
# metrik live, sama seperti order QA di SQL_EXCLUDE_QA.
SQL_EXCLUDE_SYNTHETIC = (
    "AND NOT EXISTS ("
    "  SELECT 1 FROM order_events es"
    "  WHERE es.order_id = orders.id"
    "    AND (es.payload->'latency'->>'mode' LIKE 'harness%%'"
    "         OR es.payload->>'mode' LIKE 'harness%%'"
    "         OR es.payload->>'run' LIKE 'p5-latency%%'"
    "         OR es.payload->>'synthetic' IN ('true', '1'))"
    ")"
)


# Fixture QA yang sempat menulis ke DB produksi (fail_reason 'qa-fixture'
# dari driver) bukan trafik live. Konstanta terpisah karena memakai kolom
# orders (SQL_EXCLUDE_QA dipakai juga lewat alias).
SQL_EXCLUDE_FIXTURES = (
    " AND COALESCE(orders.fail_reason, '') NOT LIKE 'qa-%%'"
)


def _md_escape(value) -> str:
    """Escape karakter Markdown Telegram pada nilai dinamis (pola app.alerts)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
    )


def _p95(values: list[float]) -> float | None:
    """Persentil-95 dari sampel; None bila kosong."""
    if not values:
        return None
    s = sorted(values)
    import math
    idx = max(0, math.ceil(0.95 * len(s)) - 1)
    return s[idx]


def _median(values: list[float]) -> float | None:
    """Median sampel; None bila kosong."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


# ---------------------------------------------------------------- detektor murni

def check_latency(recent: list[float], baseline: list[float]) -> str | None:
    """Deteksi latensi order naik. recent/baseline: durasi resolusi (detik).

    Anomali bila p95 24 jam >= 2x p95 baseline DAN p95 24 jam > SLO 300 ms.
    Data kurang (< LATENCY_MIN_ORDERS) atau baseline kosong -> None.
    """
    if len(recent) < LATENCY_MIN_ORDERS or not baseline:
        return None
    p_recent = _p95(recent)
    p_base = _p95(baseline)
    if p_recent is None or p_base is None:
        return None
    if p_recent >= LATENCY_RATIO * p_base and p_recent > LATENCY_SLO_S:
        return (
            f"⚠️ LATENSI ORDER NAIK: p95 resolusi 24 jam {p_recent * 1000:.0f} ms "
            f"(baseline 7 hari: {p_base * 1000:.0f} ms, "
            f"{p_recent / p_base:.1f}x; SLO p95 300 ms)"
        )
    return None


def check_spread(symbol: str, recent: list[float],
                 baseline: list[float]) -> str | None:
    """Deteksi spread abnormal per simbol (median 24 jam vs baseline 7 hari).

    Anomali bila median 24 jam >= 2x median baseline (baseline > 0), atau
    untuk simbol terkalibrasi (XAUUSD) bila median >= ambang absolut
    0,50 USD. Sampel kurang -> None.
    """
    if len(recent) < SPREAD_MIN_SAMPLES:
        return None
    m_recent = _median(recent)
    m_base = _median(baseline)
    if m_recent is None:
        return None
    if m_base is not None and m_base > 0 and m_recent >= SPREAD_RATIO * m_base:
        return (
            f"⚠️ SPREAD ABNORMAL {_md_escape(symbol)}: median 24 jam "
            f"{m_recent:.2f} USD (baseline 7 hari: {m_base:.2f} USD, "
            f"{m_recent / m_base:.1f}x)"
        )
    if symbol in SPREAD_ABS_SYMBOLS and m_recent >= SPREAD_ABS_USD:
        return (
            f"⚠️ SPREAD ABNORMAL {_md_escape(symbol)}: median 24 jam "
            f"{m_recent:.2f} USD >= ambang absolut {SPREAD_ABS_USD:.2f} USD"
        )
    return None


def check_failed_ratio(statuses) -> str | None:
    """Deteksi rasio FAILED tinggi pada order terminal 24 jam.

    `statuses` boleh berisi string status ("FILLED", "FAILED", ...) atau dict
    {"status": ..., "gate": bool}. Order FAILED yang berhenti di risk gate
    (stage='risk_gate', payload risk='rejected') tidak dihitung sebagai
    kegagalan: gate menolak order karena aturan risiko (kill-switch, drawdown,
    limit harian), bukan karena eksekusi broker gagal.

    Penyebut tetap SEMUA order terminal (termasuk yang ditolak gate), karena
    pertanyaannya "berapa persen eksekusi yang gagal", bukan "berapa persen
    order yang bukan penolakan gate yang gagal".
    """
    rows = []
    for s in statuses:
        if isinstance(s, dict):
            rows.append((s.get("status"), bool(s.get("gate"))))
        else:
            rows.append((s, False))
    terminal = [(st, gate) for st, gate in rows if st in TERMINAL_STATUSES]
    if len(terminal) < FAILED_MIN_TERMINAL:
        return None
    failed = sum(1 for st, gate in terminal if st == "FAILED" and not gate)
    ratio = failed / len(terminal)
    if ratio >= FAILED_RATIO:
        return (
            f"⚠️ RASIO FAILED TINGGI: {failed}/{len(terminal)} order terminal "
            f"24 jam FAILED ({ratio * 100:.0f}%; ambang {FAILED_RATIO * 100:.0f}%)"
        )
    return None


def build_report(anomalies: list[str], now: datetime | None = None) -> str:
    """Gabungkan hasil deteksi -> teks laporan Telegram."""
    now = now or datetime.now(WIB)
    lines = [f"🔎 *ANOMALI HARIAN fund2* — {now.strftime('%d %b %Y')} (window 24 jam)", ""]
    if anomalies:
        lines.extend(anomalies)
    else:
        lines.append("✅ Tidak ada anomali: latensi, spread, rasio FAILED semua dalam batas.")
    return "\n".join(lines)


# ---------------------------------------------------------------- kumpul dari DB

async def collect_anomalies() -> list[str]:
    """Jalankan ketiga deteksi terhadap Postgres. Return daftar teks anomali."""
    async with db.pool().connection() as conn:
        # PRD §6: latensi = T0→T2 (dari order_events payload latency, mono_us),
        # bukan resolved_at - created_at (itu termasuk holding time posisi).
        lat_rows = await fetchall(
            conn,
            "SELECT EXTRACT(EPOCH FROM (to_timestamp((oe.payload->'latency'->>'T2')::bigint / 1000000.0)"
            " - to_timestamp((oe.payload->'latency'->>'T0')::bigint / 1000000.0))) AS secs, o.created_at "
            "FROM orders o JOIN order_events oe ON oe.order_id = o.id "
            "WHERE oe.payload->'latency'->>'T2' IS NOT NULL "
            "AND oe.payload->'latency'->>'T0' IS NOT NULL "
            "AND o.created_at >= now() - (%s)::interval "
            + SQL_EXCLUDE_QA.replace("orders.id", "o.id")
            + SQL_EXCLUDE_SYNTHETIC.replace("orders.id", "o.id")
            + SQL_EXCLUDE_FIXTURES.replace("orders.", "o.") +
            " ORDER BY o.created_at",
            (WINDOW,),
        )
        lat_base = await fetchall(
            conn,
            "SELECT EXTRACT(EPOCH FROM (to_timestamp((oe.payload->'latency'->>'T2')::bigint / 1000000.0)"
            " - to_timestamp((oe.payload->'latency'->>'T0')::bigint / 1000000.0))) AS secs "
            "FROM orders o JOIN order_events oe ON oe.order_id = o.id "
            "WHERE oe.payload->'latency'->>'T2' IS NOT NULL "
            "AND oe.payload->'latency'->>'T0' IS NOT NULL "
            "AND o.created_at >= now() - (%s)::interval AND o.created_at < now() - (%s)::interval "
            + SQL_EXCLUDE_QA.replace("orders.id", "o.id")
            + SQL_EXCLUDE_SYNTHETIC.replace("orders.id", "o.id")
            + SQL_EXCLUDE_FIXTURES.replace("orders.", "o."),
            (BASELINE, WINDOW),
        )
        spread_rows = await fetchall(
            conn,
            "SELECT symbol, spread_avg FROM liquidity_samples "
            "WHERE window_start >= now() - (%s)::interval",
            (WINDOW,),
        )
        spread_base = await fetchall(
            conn,
            "SELECT symbol, spread_avg FROM liquidity_samples "
            "WHERE window_start >= now() - (%s)::interval AND window_start < now() - (%s)::interval",
            (BASELINE, WINDOW),
        )
        status_rows = await fetchall(
            conn,
            # t_3e43440c: order ditolak risk gate (payload risk=rejected) bukan
            # gagal eksekusi. Penyaringannya dipindah ke check_failed_ratio
            # supaya penyebut tetap semua order terminal (26 Nov 2026: 11/11
            # order lolos filter membuat rasio 27% dari sampel kecil, padahal
            # 3/360 = 0,8% dari seluruh trafik).
            "SELECT o.status, EXISTS ("
            "  SELECT 1 FROM order_events e WHERE e.order_id = o.id "
            "  AND e.to_status = 'FAILED' AND (e.payload->>'risk' = 'rejected' "
            "       OR e.payload->'fail'->>'stage' = 'risk_gate')"
            ") AS gate "
            "FROM orders o WHERE o.created_at >= now() - (%s)::interval "
            + SQL_EXCLUDE_QA.replace("orders.id", "o.id")
            + SQL_EXCLUDE_SYNTHETIC.replace("orders.id", "o.id")
            + SQL_EXCLUDE_FIXTURES.replace("orders.", "o."),
            (WINDOW,),
        )

    recent_lat = [float(r["secs"]) for r in lat_rows if r["secs"] is not None]
    base_lat = [float(r["secs"]) for r in lat_base if r["secs"] is not None]
    anomalies = []
    lat = check_latency(recent_lat, base_lat)
    if lat:
        anomalies.append(lat)

    recent_by_sym: dict[str, list[float]] = {}
    for r in spread_rows:
        recent_by_sym.setdefault(r["symbol"], []).append(float(r["spread_avg"]))
    base_by_sym: dict[str, list[float]] = {}
    for r in spread_base:
        base_by_sym.setdefault(r["symbol"], []).append(float(r["spread_avg"]))
    for symbol in sorted(recent_by_sym):
        sp = check_spread(symbol, recent_by_sym[symbol], base_by_sym.get(symbol, []))
        if sp:
            anomalies.append(sp)

    failed = check_failed_ratio([dict(r) for r in status_rows])
    if failed:
        anomalies.append(failed)
    return anomalies


# ---------------------------------------------------------------- CLI

async def _amain(send: bool) -> None:
    await db.init_pool()
    try:
        anomalies = await collect_anomalies()
        text = build_report(anomalies)
        print(text)
        if send:
            if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_OWNER_ID):
                print("[anomaly] TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID tidak diset; "
                      "laporan tidak terkirim", flush=True)
                sys.exit(2)
            ok = await notify_owner(text)
            log.info("anomali harian terkirim: %s", ok)
            print(f"\n[anomaly] laporan terkirim: {ok}", flush=True)
    finally:
        await db.close_pool()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_amain(send="--send" in sys.argv))


if __name__ == "__main__":
    main()
