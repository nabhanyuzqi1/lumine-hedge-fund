"""Metrics & alerting SEV-1..SEV-4 (PRD v2.2 §20, task t_f2v22a10).

Definisi metrics + threshold + routing. PEMBATASAN Direktur (22 Nov):
infra pengirim Telegram milik t_f2p1b3 (daemon fund2-alerts +
telegram_bot.notify_owner). Modul ini TIDAK membuat pipeline kedua:
  - GET /metrics  -> data untuk dashboard (PRD §21.2);
  - sev_watch_loop -> dijalankan DI DALAM daemon fund2-alerts (satu sender),
    kirim via notify_owner;
  - auto-action memakai kill_switch.activate (idempotent, satu sumber state).

Sumber data:
  - Postgres: orders, order_events, positions, candles, liquidity_samples,
    paper_state, kill_switch_events, settings, audit_log, pg_stat_activity;
  - /proc (CPU/RAM/swap/disk I/O) + os.statvfs + systemctl --user;
  - backup: JSON hasil fund2_backup.sh di ~/fund2-backups/logs/.

Threshold mengacu PRD: SLO T0→T2 p95<300 ms p99<500 ms (v2.1 §6), spread
XAUUSD 0.50 [USULAN] (§5.2), EA offline 60 s, 3 FAILED beruntun, DD harian
3% / total 8% (kill_switch.DEFAULT_TRIGGERS). Nilai watch di bawah ambang
auto-halt diberi label [USULAN] dan dapat dikalibrasi.

CLI:
  python -m app.metrics            # collect + evaluate, cetak JSON + alert
  python -m app.metrics --send-test# kirim alert [TEST] SEV-1 & SEV-2 ke owner
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from . import config, db, kill_switch
from .auth import get_current_user
from .state_machine import fetchall, fetchone
from .telegram_bot import notify_owner
from strategies.broker_time import broker_utc_offset_hours, stored_to_utc

log = logging.getLogger("fund2.metrics")

WIB = timezone(timedelta(hours=7))
START_MONO = time.monotonic()

SEV_CHECK_INTERVAL_S = 30.0
EVENT_WINDOW_S = 90.0        # jendela "event baru" utk rule berbasis event
BACKUP_ROOT = os.path.expanduser("~/fund2-backups/logs")
DRILL_ROOT = os.path.expanduser("~/fund2-backups/drill")
# Backup harian: 26 jam memberi ruang satu jadwal terlewat sebelum dianggap
# basi. Satu definisi dipakai server + UI supaya verdict tidak berbeda.
BACKUP_MAX_AGE_S = 26 * 3600

# ── SEV-2 db_unavailable: konfirmasi sebelum halt (t_b827af0c) ──────────────
# Insiden 26 Nov 2026 01:22 & 01:44 WIB: satu `PoolTimeout: couldn't get a
# connection after 10.00 sec` (pool fund2-api habis karena busy-loop
# /bridge/poll) langsung mengaktifkan STOP_NEW_ORDERS padahal Postgres sehat
# (13/100 koneksi). Kill-switch hanya lepas lewat /resume manual, jadi satu
# false positive = order diblokir berjam-jam. Pool penuh != database mati.
#
# Kebijakan halt (dua syarat, OR):
#   (i)  probe langsung ke Postgres GAGAL (psycopg.connect + SELECT 1) -> DB
#        memang mati, halt pada pemeriksaan pertama;
#   (ii) minimal DB_UNAVAIL_MIN_STREAK pemeriksaan pool gagal BERTURUT-TURUT
#        (probe tetap OK) -> pool benar-benar tidak dapat dipakai order.
# Satu kegagalan transien tidak pernah memicu halt.
DB_UNAVAIL_MIN_STREAK = max(1, int(os.environ.get("FUND2_DB_UNAVAIL_MIN_STREAK", "2")))
DB_PROBE_TIMEOUT_S = float(os.environ.get("FUND2_DB_PROBE_TIMEOUT_S", "3"))

# ── threshold (PRD §20.2 + v2.1 §6 + kill_switch.DEFAULT_TRIGGERS) ──────────
T02_P95_MS = 300.0           # SLO internal mengikat
T02_P99_MS = 500.0
SPREAD_ABS_XAUUSD = 0.50     # §5.2 [USULAN]
CANDLE_STALE_S = 600.0       # 10 menit (sama dgn candle watch)
TICK_GAP_S = 60.0            # sampel likuiditas 5 dtk: gap > 60 dtk = gap data
DB_CONN_PCT = 80.0           # [USULAN]
DISK_PCT = 80.0              # [USULAN]
BACKUP_AGE_H = 26.0          # backup harian 11:30 WIB; 26 jam = 1 siklus lewat
DAILY_DD_WATCH_PCT = 1.5     # [USULAN] watch, di bawah auto-halt 3%
STUCK_MIN_S = 60.0           # = config.RECONCILE_AFTER_S
RE_ALERT_S = 1800.0          # SEV-1/2 persisten: kirim ulang tiap 30 menit
FAILED_RATE_WATCH = 0.20     # [USULAN] SEV-3 watch; sama dgn app.anomaly

# Runner yang sudah dipensiunkan. State-nya tertinggal di paper_state dan
# dulu memicu alert "paper runner stale" selamanya (shadow_dbg 60 jam dan
# shadow_lb-replay-d0 59 jam pada 26 Nov 2026). Runner replay/debug itu
# tidak lagi dijalankan fund2-paper-runner (yang hidup: runner,
# runner_mean_reversion, runner_btc_range_breakout, shadow_*_base), jadi
# umur state-nya tidak berarti apa-apa. Alert stale hanya untuk runner hidup.
RETIRED_PAPER_RUNNERS = {"shadow_dbg", "shadow_lb-replay-d0"}

FUND2_UNITS = (
    "fund2-api", "fund2-postgres", "fund2-alerts", "fund2-paper-runner",
    "fund2-hfm-recorder", "fund2-llm-agent", "fund2-candle-rollup",
    "fund2-edge-proxy",
)


# ---------------------------------------------------------------- helpers kecil

def _pct(values: list[float], p: float) -> float | None:
    """Persentil-p dari sampel; None bila kosong."""
    if not values:
        return None
    s = sorted(values)
    import math
    idx = max(0, math.ceil(p / 100.0 * len(s)) - 1)
    return s[idx]


def _median(values: list[float]) -> float | None:
    return _pct(values, 50.0)


def _md_escape(value) -> str:
    """Escape Markdown Telegram pada nilai dinamis (pola app.alerts)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
    )


def _parse_iso_age(raw) -> float | None:
    """String ISO (settings) -> usia detik."""
    if not isinstance(raw, str):
        return None
    try:
        return max(0.0, time.time() - datetime.fromisoformat(raw).timestamp())
    except ValueError:
        return None


# ---------------------------------------------------------------- host (/proc)

_cpu_prev: tuple[int, int] | None = None   # (total, idle)
_disk_prev: tuple[int, int, float] | None = None  # (read_sec, write_sec, mono)


def _read_cpu_percent() -> float | None:
    """CPU% sejak pemanggilan sebelumnya (delta /proc/stat); None saat pertama."""
    global _cpu_prev
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
        vals = [int(x) for x in parts[1:8]]  # user nice system idle iowait irq softirq
        total = sum(vals)
        idle = vals[3] + vals[4]
    except OSError:
        return None
    if _cpu_prev is None:
        _cpu_prev = (total, idle)
        return None
    dt, di = total - _cpu_prev[0], idle - _cpu_prev[1]
    _cpu_prev = (total, idle)
    if dt <= 0:
        return None
    return round(max(0.0, (1.0 - di / dt) * 100.0), 1)


def _read_meminfo() -> dict:
    out = {"mem_used_pct": None, "swap_used_pct": None}
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k.strip()] = int(v.strip().split()[0])
        mt, mf = info.get("MemTotal", 0), info.get("MemAvailable", 0)
        st, sf = info.get("SwapTotal", 0), info.get("SwapFree", 0)
        if mt:
            out["mem_used_pct"] = round((mt - mf) / mt * 100.0, 1)
        if st:
            out["swap_used_pct"] = round((st - sf) / st * 100.0, 1)
    except (OSError, ValueError, IndexError):
        pass
    return out


def _read_disk_io() -> dict:
    """Read/write B/s semua disk fisik sejak panggilan sebelumnya."""
    global _disk_prev
    try:
        r = w = 0
        with open("/proc/diskstats") as f:
            for line in f:
                p = line.split()
                dev = p[2]
                if not (dev.startswith(("sd", "nvme", "vd")) and not dev.endswith(("t", "p1", "p2", "p3", "p4"))):
                    continue
                r += int(p[5])   # sectors read
                w += int(p[9])   # sectors written
    except (OSError, ValueError, IndexError):
        return {"disk_read_bps": None, "disk_write_bps": None}
    now = time.monotonic()
    if _disk_prev is None:
        _disk_prev = (r, w, now)
        return {"disk_read_bps": None, "disk_write_bps": None}
    dt = now - _disk_prev[2]
    out = {
        "disk_read_bps": round((r - _disk_prev[0]) * 512 / dt, 0) if dt > 0 else None,
        "disk_write_bps": round((w - _disk_prev[1]) * 512 / dt, 0) if dt > 0 else None,
    }
    _disk_prev = (r, w, now)
    return out


def _disk_usage_pct(path: str) -> float | None:
    try:
        st = os.statvfs(path)
        if st.f_blocks == 0:
            return None
        return round((st.f_blocks - st.f_bavail) / st.f_blocks * 100.0, 1)
    except OSError:
        return None


def _services_status() -> dict:
    """Status unit systemd user sekaligus (satu subprocess)."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", *FUND2_UNITS],
            capture_output=True, text=True, timeout=5,
        )
        lines = out.stdout.split()
        return dict(zip(FUND2_UNITS, lines))
    except Exception:
        return {}


def _host_metrics() -> dict:
    out = {
        "cpu_percent": _read_cpu_percent(),
        "load1": None,
        **_read_meminfo(),
        **_read_disk_io(),
        "disk_root_pct": _disk_usage_pct("/"),
        "disk_home_pct": _disk_usage_pct("/home"),
        "uptime_s": round(time.monotonic() - START_MONO, 1),
    }
    try:
        with open("/proc/loadavg") as f:
            out["load1"] = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return out


# ---------------------------------------------------------------- collector DB

async def _backup_age() -> dict:
    """Usia backup harian sukses terakhir dari JSON hasil fund2_backup.sh."""
    try:
        files = sorted(
            (f for f in os.listdir(BACKUP_ROOT) if f.startswith("backup-") and f.endswith(".json")),
            reverse=True,
        )
    except OSError:
        return {"age_s": None, "max_age_s": BACKUP_MAX_AGE_S, "fresh": False, "last": None}
    for name in files:
        try:
            with open(os.path.join(BACKUP_ROOT, name)) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if data.get("status") == "ok" and data.get("label") == "daily":
            ts = data.get("ts")
            try:
                t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                age = max(0.0, (datetime.now(timezone.utc) - t).total_seconds())
            except (TypeError, ValueError):
                age = None
            return {
                "age_s": age,
                "max_age_s": BACKUP_MAX_AGE_S,
                "fresh": (age is not None and age <= BACKUP_MAX_AGE_S),
                "last": {"ts": ts, "archive": data.get("archive"),
                         "offsite": data.get("offsite"), "bytes": data.get("bytes")},
            }
    return {"age_s": None, "max_age_s": BACKUP_MAX_AGE_S, "fresh": False, "last": None}


async def _restore_drill() -> dict:
    """Hasil restore drill terakhir (PRD §17.3, §21.5) dari
    ~/fund2-backups/drill/LATEST (path file .md) -> result.json sekolongnya.
    Read-only: drill tidak pernah dijalankan dari sini."""
    try:
        with open(os.path.join(DRILL_ROOT, "LATEST")) as f:
            latest = f.read().strip()
    except OSError:
        return {"status": None, "ts": None, "age_s": None}
    drill_dir = os.path.dirname(latest) or DRILL_ROOT
    try:
        with open(os.path.join(drill_dir, "result.json")) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"status": None, "ts": None, "age_s": None, "dir": drill_dir}
    ts = data.get("ts")
    age_s = None
    if isinstance(ts, str):
        try:
            t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age_s = max(0.0, (datetime.now(timezone.utc) - t).total_seconds())
        except ValueError:
            pass
    return {
        "status": data.get("status"),
        "ts": ts,
        "age_s": age_s,
        "duration_s": data.get("duration_s"),
        "pg_restore_s": data.get("pg_restore_s"),
        "archive": data.get("archive"),
        "error": data.get("error"),
    }


async def _latency_metrics(conn) -> dict:
    """Latensi T0→T2/T2→T3/T0→T4 p50/p95/p99 (PRD §20.1, v2.1 §6).

    Primer: payload.latency (titik T0..T4, diinjeksi harness latensi QA).
    Fallback: kolom orders (T0=created, T1=delivered, T4=resolved) — segmen
    T2→T3 hanya ada bila EA mengirim titik T2/T3.
    """
    rows = await fetchall(
        conn,
        """
        SELECT oe.payload->'latency' AS lat FROM order_events oe
        WHERE oe.payload ? 'latency'
          AND oe.created_at >= now() - interval '24 hours'
          AND NOT EXISTS (
            SELECT 1 FROM order_events es
            WHERE es.order_id = oe.order_id
              AND (es.payload->'latency'->>'mode' LIKE 'harness%%'
                   OR es.payload->>'mode' LIKE 'harness%%'
                   OR es.payload->>'run' LIKE 'p5-latency%%'))
        """,
    )
    seg_t02: list[float] = []
    seg_t23: list[float] = []
    seg_t04: list[float] = []
    for r in rows:
        lat = r["lat"] or {}

        def pt(k):
            v = lat.get(k)
            return float(v) / 1000.0 if isinstance(v, (int, float)) else None

        t0, t1, t2, t3, t4 = (pt(k) for k in ("T0", "T1", "T2", "T3", "T4"))
        if t0 is not None and t2 is not None:
            seg_t02.append(t2 - t0)
        if t2 is not None and t3 is not None:
            seg_t23.append(t3 - t2)
        if t0 is not None and t4 is not None:
            seg_t04.append(t4 - t0)

    def dist(vals):
        return {"p50": _pct(vals, 50), "p95": _pct(vals, 95), "p99": _pct(vals, 99), "n": len(vals)}

    # fallback dari kolom orders (detik, wall-clock lintas proses)
    fb = await fetchone(
        conn,
        """
        SELECT
          percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (delivered_at - created_at))) AS t0t1_p50,
          percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (delivered_at - created_at))) AS t0t1_p95,
          percentile_cont(0.99) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (delivered_at - created_at))) AS t0t1_p99,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at))) AS t0t4_p50,
          percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at))) AS t0t4_p95,
          percentile_cont(0.99) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at))) AS t0t4_p99,
          COUNT(*) AS n
        FROM orders
        WHERE action = 'OPEN' AND resolved_at IS NOT NULL
          AND created_at >= now() - interval '24 hours'
        """,
    )
    return {
        "t0_t2_ms": dist(seg_t02),
        "t2_t3_ms": dist(seg_t23),
        "t0_t4_ms": dist(seg_t04),
        "orders_fallback": {
            "t0_t1_s": {"p50": fb["t0t1_p50"], "p95": fb["t0t1_p95"], "p99": fb["t0t1_p99"]},
            "t0_t4_s": {"p50": fb["t0t4_p50"], "p95": fb["t0t4_p95"], "p99": fb["t0t4_p99"]},
            "n": fb["n"],
        },
    }


async def _spread_metrics(conn) -> dict:
    """Spread median/p95 per simbol, jendela 1 jam dan 24 jam (liquidity_samples)."""
    rows = await fetchall(
        conn,
        """
        SELECT symbol,
               AVG(spread_avg) FILTER (WHERE window_start >= now() - interval '1 hour') AS m1h,
               MIN(spread_avg) FILTER (WHERE window_start >= now() - interval '1 hour') AS min1h,
               MAX(spread_avg) FILTER (WHERE window_start >= now() - interval '1 hour') AS max1h,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY spread_avg) FILTER (WHERE window_start >= now() - interval '1 hour') AS p50_1h,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY spread_avg) FILTER (WHERE window_start >= now() - interval '1 hour') AS p95_1h,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY spread_avg) FILTER (WHERE window_start >= now() - interval '24 hours') AS p50_24h,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY spread_avg) FILTER (WHERE window_start >= now() - interval '24 hours') AS p95_24h,
               COUNT(*) FILTER (WHERE window_start >= now() - interval '1 hour') AS n1h,
               COUNT(*) FILTER (WHERE window_start >= now() - interval '24 hours') AS n24h
        FROM liquidity_samples
        GROUP BY symbol ORDER BY symbol
        """,
    )
    return {
        r["symbol"]: {
            "p50_1h": float(r["p50_1h"]) if r["p50_1h"] is not None else None,
            "p95_1h": float(r["p95_1h"]) if r["p95_1h"] is not None else None,
            "p50_24h": float(r["p50_24h"]) if r["p50_24h"] is not None else None,
            "p95_24h": float(r["p95_24h"]) if r["p95_24h"] is not None else None,
            "n_1h": r["n1h"], "n_24h": r["n24h"],
        }
        for r in rows
    }


async def _feed_metrics(conn, now: datetime) -> dict:
    """Tick/candle age + gap data likuiditas (PRD §20.1: tick age & data gaps)."""
    out: dict = {"candles": {}, "liquidity_age_s": None, "gaps_1h": {}}
    now_utc = datetime.now(timezone.utc)
    rows = await fetchall(
        conn,
        "SELECT symbol, timeframe, MAX(ts) AS ts FROM candles "
        "WHERE timeframe IN ('M1', 'M5') GROUP BY symbol, timeframe ORDER BY symbol, timeframe",
    )
    db_tz = None
    for r in rows:
        if db_tz is None:
            tzrow = await fetchone(conn, "SELECT current_setting('TimeZone') AS tz")
            name = (tzrow or {}).get("tz", "UTC")
            try:
                from zoneinfo import ZoneInfo
                off = datetime.now(ZoneInfo(name)).utcoffset()
                db_tz = int(off.total_seconds() // 3600) if off else 0
            except Exception:
                db_tz = 0
        true_ts = stored_to_utc(r["ts"], db_tz, broker_utc_offset_hours(now))
        out["candles"][f"{r['symbol']}:{r['timeframe']}"] = {
            "age_s": round(max(0.0, (now_utc - true_ts).total_seconds()), 1),
        }
    liq = await fetchone(
        conn, "SELECT MAX(window_start) AS mx FROM liquidity_samples"
    )
    if liq and liq["mx"] is not None:
        mx = liq["mx"]
        if mx.tzinfo is None:
            mx = mx.replace(tzinfo=timezone.utc)
        out["liquidity_age_s"] = round(max(0.0, (now_utc - mx).total_seconds()), 1)
    gaps = await fetchall(
        conn,
        """
        SELECT symbol, COUNT(*) AS gaps, MAX(delta) AS max_gap
        FROM (
            SELECT symbol, window_start - LAG(window_start) OVER (PARTITION BY symbol ORDER BY window_start) AS delta
            FROM liquidity_samples WHERE window_start >= now() - interval '1 hour'
        ) d
        WHERE delta > %s
        GROUP BY symbol
        """,
        (timedelta(seconds=TICK_GAP_S),),
    )
    for g in gaps:
        out["gaps_1h"][g["symbol"]] = {
            "count": g["gaps"],
            "max_gap_s": g["max_gap"].total_seconds() if g["max_gap"] else None,
        }
    return out


async def _order_metrics(conn) -> dict:
    """Order state counts, rejection/failure rate, slippage, stuck (PRD §20.1)."""
    counts = await fetchall(conn, "SELECT status, COUNT(*) AS n FROM orders GROUP BY status")
    state_counts = {r["status"]: r["n"] for r in counts}
    stuck = await fetchone(
        conn,
        "SELECT COUNT(*) AS n FROM orders WHERE status = 'SENT' AND sent_at < now() - interval '60 seconds'",
    )
    failed = await fetchone(
        conn,
        # Rasio FAILED = kegagalan EKSEKUSI pasar saja. Penolakan risk gate
        # (stage='risk_gate', payload risk='rejected') adalah sistem yang
        # bekerja sesuai desain (kill-switch, drawdown, limit harian), bukan
        # degradasi eksekusi. Ikut menghitungnya membuat alert 26 Nov 2026
        # berbunyi "40% FAILED (145/360)" padahal 145/145 adalah gate
        # rejection dan 0 kegagalan broker.
        "SELECT COUNT(*) AS n FROM orders o WHERE o.status = 'FAILED' "
        "AND o.created_at >= now() - interval '24 hours' "
        "AND COALESCE(o.fail_reason, '') NOT LIKE 'qa-%%' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM order_events e WHERE e.order_id = o.id "
        "  AND e.to_status = 'FAILED' "
        "  AND (e.payload->>'risk' = 'rejected' "
        "       OR e.payload->'fail'->>'stage' = 'risk_gate'))",
    )
    failed_exec = await fetchone(
        conn,
        "SELECT COUNT(*) AS n FROM orders o WHERE o.status = 'FAILED' "
        "AND o.created_at >= now() - interval '24 hours' "
        "AND COALESCE(o.fail_reason, '') NOT LIKE 'qa-%%' "
        "AND EXISTS ("
        "  SELECT 1 FROM order_events e WHERE e.order_id = o.id "
        "  AND e.to_status = 'FAILED' "
        "  AND (e.payload->>'risk' = 'rejected' "
        "       OR e.payload->'fail'->>'stage' = 'risk_gate'))",
    )
    rejected = await fetchone(
        conn,
        """
        SELECT COUNT(*) AS n FROM order_events
        WHERE to_status = 'FAILED' AND payload->>'risk' = 'rejected'
          AND created_at >= now() - interval '24 hours'
        """,
    )
    terminal = await fetchone(
        conn,
        "SELECT COUNT(*) AS n FROM orders WHERE status = ANY("
        "ARRAY['FILLED','FAILED','FILLED_THEN_CLOSED','ORPHAN_CLOSED','RECONCILED']) "
        "AND created_at >= now() - interval '24 hours' "
        "AND COALESCE(fail_reason, '') NOT LIKE 'qa-%%'",
    )
    slip = await fetchall(
        conn,
        """
        SELECT symbol, side, price_requested, price_filled FROM orders
        WHERE action = 'OPEN' AND price_filled IS NOT NULL AND price_requested IS NOT NULL
          AND created_at >= now() - interval '24 hours'
        """,
    )
    vals: list[float] = []
    per_symbol: dict[str, list[float]] = {}
    for r in slip:
        diff = float(r["price_filled"]) - float(r["price_requested"])
        signed = diff if r["side"] == "BUY" else -diff
        vals.append(signed)
        per_symbol.setdefault(r["symbol"], []).append(signed)
    slip_out = {
        "by_symbol": {
            s: {"n": len(v), "median": _median(v), "p95_abs": _pct([abs(x) for x in v], 95),
                "max_abs": max((abs(x) for x in v), default=None)}
            for s, v in per_symbol.items()
        },
    }
    n_terminal = terminal["n"] or 0
    n_failed = failed["n"] or 0
    n_gate = failed_exec["n"] or 0
    return {
        "state_counts": state_counts,
        "stuck_sent_60s": stuck["n"] or 0,
        "failed_24h": n_failed,
        "failed_risk_gate_24h": n_gate,
        "rejected_24h": rejected["n"] or 0,
        "terminal_24h": n_terminal,
        "failure_rate_24h": round(n_failed / n_terminal, 3) if n_terminal else None,
        "slippage": slip_out,
    }


async def _reconciliation_metrics(conn, window_s: float) -> dict:
    """Rekonsiliasi: mismatch tak terjelaskan + orphan baru (PRD §5.8, §20.1)."""
    agg = await fetchone(
        conn,
        """
        SELECT
          COUNT(*) FILTER (WHERE payload->>'event' = 'reconciled_unexplained'
                            AND created_at >= now() - interval '24 hours') AS mismatch_24h,
          COUNT(*) FILTER (WHERE to_status = 'ORPHAN_ADOPTED'
                            AND created_at >= now() - interval '24 hours') AS orphan_24h,
          COUNT(*) FILTER (WHERE payload->>'event' = 'reconciled_closed'
                            AND created_at >= now() - interval '24 hours') AS reconciled_closed_24h,
          COUNT(*) FILTER (WHERE payload->>'event' = 'reconciled_unexplained') AS mismatch_all,
          COUNT(*) FILTER (WHERE to_status = 'ORPHAN_ADOPTED') AS orphan_all
        FROM order_events
        """,
    )
    ev_window = await fetchone(
        conn,
        """
        SELECT
          COUNT(*) FILTER (WHERE payload->>'event' = 'reconciled_unexplained') AS mismatch_new,
          COUNT(*) FILTER (WHERE to_status = 'ORPHAN_ADOPTED') AS orphan_new,
          COUNT(*) FILTER (WHERE payload->>'event' = 'reconciled_closed') AS reconciled_closed_new
        FROM order_events WHERE created_at >= now() - (%s * interval '1 second')
        """,
        (window_s,),
    )
    return {**agg, "new": ev_window}


async def _strategy_metrics(conn) -> dict:
    """Runtime/error/timeout per strategi (paper_state + mode + FAILED 24 jam)."""
    rows = await fetchall(
        conn,
        "SELECT key, value, updated_at FROM paper_state ORDER BY key",
    )
    failed_by = await fetchall(
        conn,
        "SELECT strategy, COUNT(*) AS n FROM orders WHERE status = 'FAILED' "
        "AND created_at >= now() - interval '24 hours' GROUP BY strategy",
    )
    failed_map = {r["strategy"]: r["n"] for r in failed_by}
    paused = await kill_switch.get_paused_strategies()
    settings = await db.get_settings()
    now = datetime.now(timezone.utc)
    out: dict = {}
    retired: list[str] = []
    for r in rows:
        if r["key"] in RETIRED_PAPER_RUNNERS:
            retired.append(r["key"])
            continue
        ts = r["updated_at"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[r["key"]] = {
            "paper_state_age_s": round(max(0.0, (now - ts).total_seconds()), 1),
            "balance": float((r["value"] or {}).get("balance", 0.0)),
            "failed_24h": failed_map.get(r["key"].removeprefix("runner_"), 0),
        }
    return {
        "runners": out,
        "retired_runners": sorted(retired),
        "paused": paused,
        "llm_agent_pause": settings.get("llm_agent_pause"),
        "strategy_modes": {
            k.removeprefix("strategy_mode_"): v
            for k, v in settings.items()
            if k.startswith("strategy_mode_")
        },
        "backtest_runs_total": (await fetchone(
            conn, "SELECT COUNT(*) AS n FROM backtest_runs"))["n"],
    }


async def _risk_metrics(conn) -> dict:
    """Risiko: drawdown, eksposur, margin, posisi tanpa SL, kill-switch status."""
    base = await kill_switch.compute_metrics(conn)
    settings = await db.get_settings()
    specs = settings.get("symbol_specs") or {}
    positions = await fetchall(
        conn,
        "SELECT symbol, side, volume, open_price, sl, tp, profit FROM positions "
        "WHERE status = 'OPEN' ORDER BY open_time",
    )
    exposure = 0.0
    unprotected: list[dict] = []
    for p in positions:
        price = float(p["open_price"] or 0.0)
        contract = float((specs.get(p["symbol"]) or {}).get("contract_size", 1.0))
        exposure += float(p["volume"]) * contract * price
        if p["sl"] is None:
            unprotected.append(
                {"ticket_sym": f"{p['symbol']} {p['side']} {float(p['volume']):.2f}",
                 "open_price": price})
    state = await kill_switch.get_state()
    return {
        **base,
        "exposure_usd": round(exposure, 2),
        "margin_note": "margin broker-side tidak tersimpan di DB (EA snapshot "
                       "positions/deals saja); metrik margin = exposure + equity",
        "unprotected_positions": unprotected,
        "kill_switch": {k: state[k] for k in
                        ("active", "mode", "strategy", "reason", "source", "activated_at")},
    }


class DbUnavailTracker:
    """State mesin "database tidak tersedia" untuk watchdog SEV (di memori proses).

    Satu PoolTimeout = transient: pool penuh beberapa detik bukan alasan
    memblokir semua order. Streak di-reset setiap pemeriksaan sukses, jadi
    kegagalan yang terselang sehat tidak pernah menumpuk menjadi halt.
    """

    def __init__(self, min_streak: int = DB_UNAVAIL_MIN_STREAK):
        self.min_streak = max(1, int(min_streak))
        self.streak = 0
        self.last_reason = "db ok"

    def reset(self) -> None:
        self.streak = 0
        self.last_reason = "db ok"

    def observe(self, dbm: dict | None) -> dict:
        """Catat satu hasil pemeriksaan; return keputusan halt + alasannya."""
        dbm = dbm or {}
        if dbm.get("available"):
            self.reset()
            return {"activate": False, "streak": 0, "probe_ok": True,
                    "reason": self.last_reason}
        self.streak += 1
        probe_ok = dbm.get("probe_ok")
        if probe_ok is False:
            detail = dbm.get("probe_error") or dbm.get("error") or "unknown"
            self.last_reason = (
                f"probe langsung ke Postgres GAGAL ({detail}); "
                f"database benar-benar tidak dapat dihubungi"
            )
            return {"activate": True, "streak": self.streak, "probe_ok": False,
                    "reason": self.last_reason}
        if self.streak >= self.min_streak:
            self.last_reason = (
                f"pengambilan metrics gagal {self.streak}x berturut-turut "
                f"(pool tidak dapat dipakai order; probe langsung ke Postgres OK)"
            )
            return {"activate": True, "streak": self.streak, "probe_ok": True,
                    "reason": self.last_reason}
        self.last_reason = (
            f"pengambilan metrics gagal {self.streak}x (transient; ambang halt "
            f"{self.min_streak}x berturut-turut; probe langsung ke Postgres OK): "
            f"{dbm.get('error', 'unknown')}"
        )
        return {"activate": False, "streak": self.streak, "probe_ok": True,
                "reason": self.last_reason}


# Satu instans per proses (daemon fund2-alerts). Test wajib reset (conftest).
DB_UNAVAIL_TRACKER = DbUnavailTracker()


def _probe_db_sync(timeout_s: float = DB_PROBE_TIMEOUT_S) -> dict:
    """Probe langsung ke Postgres, SENGAJA di luar pool (blocking, dipanggil
    lewat asyncio.to_thread). Return {"ok", "latency_ms", "error"}."""
    import psycopg

    t0 = time.perf_counter()
    try:
        with psycopg.connect(config.DATABASE_URL,
                             connect_timeout=int(max(1, round(timeout_s)))) as conn:
            conn.execute("SELECT 1")
        return {"ok": True,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "error": None}
    except Exception as exc:  # noqa: BLE001 — kegagalan probe = data, bukan crash
        return {"ok": False, "latency_ms": None,
                "error": f"{type(exc).__name__}: {exc}"[:300]}


async def probe_db_direct(timeout_s: float = DB_PROBE_TIMEOUT_S) -> dict:
    """Versi async dari `_probe_db_sync` (thread, tidak memblokir event loop)."""
    return await asyncio.to_thread(_probe_db_sync, timeout_s)


async def collect_metrics(window_s: float = EVENT_WINDOW_S) -> dict:
    """Kumpulkan seluruh metrics PRD §20.1. DB gagal -> db.available=False."""
    out: dict = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "window_s": window_s,
        "api": {
            "uptime_s": round(time.monotonic() - START_MONO, 1),
            "pid": os.getpid(),
            "services": await asyncio.to_thread(_services_status),
        },
        "host": _host_metrics(),
        "db": {"available": False},
    }
    t0 = time.perf_counter()
    try:
        async with db.pool().connection() as conn:
            dbinfo = await fetchone(
                conn,
                """
                SELECT (SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()) AS conns,
                       (SELECT setting FROM pg_settings WHERE name = 'max_connections') AS max_conns,
                       pg_database_size(current_database()) AS size_bytes
                """,
            )
            db_ms = (time.perf_counter() - t0) * 1000.0
            out["db"] = {
                "available": True,
                "latency_ms": round(db_ms, 2),
                "connections": dbinfo["conns"],
                "max_connections": int(dbinfo["max_conns"]),
                "size_bytes": dbinfo["size_bytes"],
            }
            # Satu koneksi untuk settings+triggers. Sebelumnya `db.get_settings()`
            # lalu `kill_switch.get_triggers()` (yang memanggil get_settings lagi)
            # mengakuisisi 2 koneksi baru SELAGI koneksi metrics masih ditahan:
            # 3 slot pool habis per koleksi -> watcher lain kena PoolTimeout 10 s
            # (insiden 26 Nov 2026, alerts daemon restart 10x/jam).
            settings = dict(db.DEFAULT_SETTINGS)
            triggers = dict(kill_switch.DEFAULT_TRIGGERS)
            raw_triggers = None
            for row in await fetchall(conn, "SELECT key, value FROM settings"):
                settings[row["key"]] = row["value"]
                if row["key"] == "kill_switch_triggers":
                    raw_triggers = row["value"]
            if isinstance(raw_triggers, dict):
                triggers.update(
                    {k: v for k, v in raw_triggers.items() if k != "modes"}
                )
                modes = dict(kill_switch.DEFAULT_TRIGGERS["modes"])
                modes.update(raw_triggers.get("modes") or {})
                triggers["modes"] = modes
            out["ea"] = {
                "last_seen_age_s": _parse_iso_age(settings.get("ea_last_seen_at")),
                # A12: ambang TANDAI offline (6 s); halt menunggu ambang kedua.
                "offline_threshold_s": triggers.get("ea_offline_seconds"),
                "offline_halt_threshold_s": triggers.get("ea_offline_halt_seconds", 60.0),
            }
            out["feed"] = await _feed_metrics(conn, datetime.now(timezone.utc))
            out["spread"] = await _spread_metrics(conn)
            out["latency"] = await _latency_metrics(conn)
            out["orders"] = await _order_metrics(conn)
            out["reconciliation"] = await _reconciliation_metrics(conn, window_s)
            out["strategies"] = await _strategy_metrics(conn)
            out["risk"] = await _risk_metrics(conn)
            out["backup"] = await _backup_age()
            out["drill"] = await _restore_drill()
            out["triggers"] = {
                "ea_offline_seconds": triggers.get("ea_offline_seconds"),
                "ea_offline_halt_seconds": triggers.get("ea_offline_halt_seconds", 60.0),
                "consecutive_failed": triggers.get("consecutive_failed_orders"),
                "daily_drawdown_pct": triggers.get("daily_drawdown_pct"),
                "total_drawdown_pct": triggers.get("total_drawdown_pct"),
                # Ambang tick basi yang dipakai preflight gate. UI memakainya
                # untuk label STALE supaya tidak bilang "live" saat order
                # sebenarnya bakal ditolak.
                "max_tick_age_s": settings.get("max_tick_age_s"),
            }
            out["audit"] = {
                "admin_lockouts_new": (await fetchone(
                    conn,
                    """
                    SELECT COUNT(*) AS n FROM audit_log a
                    WHERE a.action = 'LOGIN_FAILED'
                      AND (a.details->>'locked') = 'true'
                      AND EXISTS (SELECT 1 FROM users u
                                  WHERE u.username = a.actor AND u.role = 'admin')
                      AND a.created_at >= now() - (%s * interval '1 second')
                    """,
                    (window_s,),
                ))["n"],
            }
    except Exception as exc:  # noqa: BLE001 — DB down adalah metrik, bukan crash
        # Timeout pool != DB mati (t_b827af0c): probe langsung di luar pool
        # membedakan "pool habis" dari "Postgres tidak dapat dihubungi".
        # Hasil probe ikut di metrik supaya keputusan halt (watchdog) dan
        # tampilan dashboard memakai bukti yang sama.
        probe = await probe_db_direct()
        out["db"] = {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "probe_ok": probe["ok"],
            "probe_error": probe["error"],
            "probe_latency_ms": probe["latency_ms"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
    return out


# ---------------------------------------------------------------- evaluator SEV

def _alert(sev: int, key: str, what: str, impact: str, auto: str,
           manual: list[str], action_mode: str | None = None) -> dict:
    """Kerangka alert actionable (PRD §20: apa, dampak, waktu, otomatis, manual)."""
    return {
        "sev": sev,
        "key": key,
        "what": what,
        "impact": impact,
        "when": datetime.now(WIB).strftime("%d %b %Y %H:%M WIB"),
        "auto": auto,
        "manual": manual,
        "action_mode": action_mode,
    }


def evaluate_sev(m: dict) -> list[dict]:
    """Evaluasi metrics -> daftar alert SEV-1..SEV-3 (SEV-4 = rekap harian ada
    di app.alerts.build_recap / app.anomaly, bukan di sini).

    Murni (tanpa DB): mudah di-unit-test. Nilai None -> rule dilewati.
    """
    alerts: list[dict] = []
    dbm = m.get("db") or {}
    ea = m.get("ea") or {}
    risk = m.get("risk") or {}
    rec = m.get("reconciliation") or {}
    rec_new = rec.get("new") or {}
    lat = m.get("latency") or {}
    spread = m.get("spread") or {}
    feed = m.get("feed") or {}
    orders = m.get("orders") or {}
    host = m.get("host") or {}
    backup = m.get("backup") or {}
    strat = m.get("strategies") or {}
    runners = strat.get("runners") or {}

    if not dbm.get("available"):
        probe_ok = dbm.get("probe_ok")
        if probe_ok is False:
            evidence = (f"Probe langsung ke Postgres GAGAL "
                        f"({dbm.get('probe_error') or 'unknown'}): database "
                        f"benar-benar tidak dapat dihubungi.")
        elif probe_ok is True:
            evidence = ("Probe langsung ke Postgres BERHASIL: ini kegagalan "
                        "pool/koneksi aplikasi, bukan database mati.")
        else:
            evidence = "Probe langsung belum dijalankan."
        alerts.append(_alert(
            2, "db_unavailable",
            f"Database tidak dapat dihubungi: {dbm.get('error', 'unknown')} | {evidence}",
            "Order baru tidak bisa diproses; risk gate & kill-switch state tidak "
            "bisa dibaca/ditulis; dashboard menampilkan data basi.",
            # Halt diputuskan watchdog (DbUnavailTracker): probe gagal atau
            # >=2 pemeriksaan gagal berturut-turut. Satu PoolTimeout tidak
            # pernah cukup (t_b827af0c).
            ("Alert ini dikirim langsung via Telegram (tidak lewat DB). Halt "
             "entry tidak bisa ditulis ke DB selama DB down."),
            ["Cek service: systemctl --user status fund2-postgres",
             "Cek log: journalctl --user -u fund2-postgres -n 50",
             "Jika disk penuh, kosongkan ruang sebelum restart Postgres"],
            # STOP_NEW_ORDERS hanya bila bukti langsung bahwa DB mati; pool
            # timeout dengan probe OK tidak memblokir order.
            "STOP_NEW_ORDERS" if probe_ok is False else None))
        return alerts  # tanpa DB, rule lain tak bisa dinilai

    # ── SEV-1 ────────────────────────────────────────────────────────────
    unprot = risk.get("unprotected_positions") or []
    if unprot:
        alerts.append(_alert(
            1, "posisi_tanpa_sl",
            f"{len(unprot)} posisi terbuka TANPA SL broker-side: "
            + "; ".join(u["ticket_sym"] for u in unprot[:5]),
            "Posisi tidak terlindungi bila disconnect/EA mati; kerugian bisa "
            "melebihi batas risiko per trade.",
            "GLOBAL_HALT otomatis (kill-switch; tidak pernah auto-flatten, D6).",
            ["Verifikasi posisi di MT5 dan pasang SL manual bila perlu",
             "Bila perlu menutup: /stopflatten confirm (risiko slippage)",
             "Setelah aman: /resume ACK dengan checklist recovery"],
            "GLOBAL_HALT"))
    mismatch_new = rec_new.get("mismatch_new") or 0
    if mismatch_new:
        alerts.append(_alert(
            1, "ledger_mismatch",
            f"{mismatch_new} posisi hilang dari snapshot broker TANPA deal "
            f"penutup yang bisa dijelaskan (total 24 jam: {rec.get('mismatch_24h', 0)}).",
            "Ledger DB tidak cocok dengan broker; posisi bisa menganggur tanpa "
            "manajemen risiko; audit trail tidak valid.",
            "GLOBAL_HALT otomatis via auto:position_mismatch (kill-switch).",
            ["Jalankan rekonsiliasi manual: bandingkan posisi MT5 vs /positions",
             "Cek deal di MT5 (History) untuk ticket yang hilang",
             "Catat temuan di order_events; /resume ACK setelah cocok"],
            "GLOBAL_HALT"))
    orphan_new = rec_new.get("orphan_new") or 0
    if orphan_new:
        alerts.append(_alert(
            1, "order_tak_diketahui",
            f"{orphan_new} posisi broker TANPA order di DB terdeteksi "
            f"(orphan; total 24 jam: {rec.get('orphan_24h', 0)}).",
            "Ada order yang tidak diketahui sistem (manual di MT5 / hasil "
            "kegagalan command); eksposur riil != eksposur tercatat.",
            "GLOBAL_HALT otomatis (SEV-1 order tak diketahui, PRD §20.2); "
            "reconciler memasang SL darurat pada orphan.",
            ["Identifikasi asal orphan (manual MT5? command gagal?)",
             "Adopsi manual ke DB atau tutup posisi (confirm)",
             "/resume ACK setelah ledger cocok"],
            "GLOBAL_HALT"))
    lockouts = (m.get("audit") or {}).get("admin_lockouts_new") or 0
    if lockouts:
        alerts.append(_alert(
            1, "credential_compromise",
            f"{lockouts} penguncian akun admin setelah login gagal beruntun.",
            "Indikasi credential compromise / brute force terhadap akun admin.",
            "GLOBAL_HALT otomatis (PRD §20.2: credential compromise).",
            ["Pastikan percobaan login bukan milik Anda",
             "Bila bukan: ganti password admin + cabut semua sesi "
             "(/auth/sessions/revoke-all), periksa audit_log",
             "Bila milik Anda: /resume ACK setelah verifikasi"],
            "GLOBAL_HALT"))

    # ── SEV-2 ────────────────────────────────────────────────────────────
    ea_age = ea.get("last_seen_age_s")
    thr = ea.get("offline_threshold_s") or 60
    open_pos = risk.get("open_positions", 0)
    if ea_age is not None and ea_age > thr and open_pos > 0:
        alerts.append(_alert(
            2, "ea_offline",
            f"EA offline {ea_age:.0f}s (threshold {thr:.0f}s) saat "
            f"{open_pos} posisi terbuka.",
            "Posisi terbuka tanpa manajemen EA; SL/TP broker-side tetap aktif "
            "tetapi trailing/close otomatis tidak berjalan.",
            "GLOBAL_HALT otomatis via auto:ea_offline (kill-switch).",
            ["Cek VPS/MT5: proses wine, koneksi broker, log EA",
             "Restart MT5 bila perlu; EA reconnect otomatis",
             "Verifikasi posisi di MT5; /resume setelah EA online"],
            "GLOBAL_HALT"))
    elif ea_age is not None and ea_age > thr and open_pos == 0:
        alerts.append(_alert(
            3, "ea_offline_tanpa_posisi",
            f"EA offline {ea_age:.0f}s (threshold {thr:.0f}s), tanpa posisi terbuka.",
            "Tidak ada posisi terbuka; sinyal/order baru tidak bisa dieksekusi.",
            "Order baru sudah ditolak risk gate (PRD 5.8); kill-switch auto "
            "menyala bila dikonfigurasi.",
            ["Cek VPS/MT5 dan koneksi broker",
             "Pastikan EA online sebelum membuka entry baru"],
            None))
    streak = risk.get("consecutive_failed", 0)
    thr_fail = (m.get("triggers") or {}).get("consecutive_failed", 3)
    if streak >= thr_fail:
        alerts.append(_alert(
            2, "repeated_execution_failures",
            f"{streak} order FAILED beruntun (threshold {thr_fail}).",
            "Kegagalan eksekusi berulang: harga bisa slip, sinyal hilang, "
            "posisi bisa terbuka tanpa pendampingan.",
            "STOP_NEW_ORDERS otomatis via auto:consecutive_failed.",
            ["Cek fail_reason order terakhir di /orders",
             "Verifikasi koneksi broker & simbol aktif",
             "Reset streak: /resume (marker trigger_ack)"],
            "STOP_NEW_ORDERS"))

    # ── SEV-3 (degradasi: watch/pause) ───────────────────────────────────
    t02 = lat.get("t0_t2_ms") or {}
    p95 = t02.get("p95")
    if p95 is not None and p95 * 1000.0 >= T02_P95_MS:
        alerts.append(_alert(
            3, "latensi_t02",
            f"T0→T2 p95 {p95 * 1000:.0f} ms >= SLO {T02_P95_MS:.0f} ms "
            f"(n={t02.get('n', 0)}).",
            "Eksekusi melambat; risiko slippage & entry pada harga yang sudah "
            "tidak valid.",
            "Tidak ada aksi otomatis (watch).",
            ["Cek beban API/DB dan jaringan ke broker",
             "Jalankan scripts/latency_harness.py untuk verifikasi",
             "Pause strategi aktif bila berlanjut"],
            None))
    for sym, s in spread.items():
        p95s = s.get("p95_1h")
        limit = SPREAD_ABS_XAUUSD if sym == "XAUUSD" else None
        if p95s is not None and limit is not None and p95s >= limit:
            alerts.append(_alert(
                3, "spread_tinggi",
                f"Spread {sym} p95 1 jam {p95s:.2f} >= {limit:.2f} USD "
                f"(median {s.get('p50_1h') or 0:.2f}).",
                "Order bisa ditolak spread filter; fill buruk bila lolos.",
                "Tidak ada aksi otomatis (spread filter risk gate tetap aktif).",
                ["Watch: tunda entry sampai spread normal",
                 "Cek sesi pasar & berita (news spike)",
                 "Kalibrasi ambang bila struktural"],
                None))
    for key, c in (feed.get("candles") or {}).items():
        age = c.get("age_s")
        if age is not None and age > CANDLE_STALE_S:
            alerts.append(_alert(
                3, "feed_stale",
                f"Candle {key} terakhir {age / 60:.0f} menit lalu "
                f"(threshold {CANDLE_STALE_S / 60:.0f} menit).",
                "Sinyal dari candle basi; strategi bisa mengambil keputusan "
                "dari harga tidak valid.",
                "Order baru ditolak risk gate saat data basi (PRD 0.2).",
                ["Cek EA/tick pipeline dan service fund2-candle-rollup",
                 "Cek log ingest & koneksi broker"],
                None))
    for sym, g in (feed.get("gaps_1h") or {}).items():
        if (g.get("count") or 0) > 0:
            alerts.append(_alert(
                3, "data_gap",
                f"{g['count']} gap data likuiditas {sym} dalam 1 jam "
                f"(gap terbesar {g.get('max_gap_s') or 0:.0f}s).",
                "Tick hilang: spread/candle bisa tidak akurat.",
                "Tidak ada aksi otomatis (watch).",
                ["Cek koneksi EA dan jaringan ke broker",
                 "Periksa log ingest tick"],
                None))
    conns = (m.get("db") or {}).get("connections")
    maxc = (m.get("db") or {}).get("max_connections")
    if conns is not None and maxc and conns / maxc * 100.0 >= DB_CONN_PCT:
        alerts.append(_alert(
            3, "db_connections",
            f"Koneksi DB {conns}/{maxc} ({conns / maxc * 100:.0f}%).",
            "Koneksi habis: API/worker bisa gagal membuka koneksi baru.",
            "Tidak ada aksi otomatis (watch).",
            ["Cek koneksi bocor: pg_stat_activity state/idle",
             "Restart service yang menumpuk koneksi"],
            None))
    for dpath in ("disk_root_pct", "disk_home_pct"):
        val = host.get(dpath)
        if val is not None and val >= DISK_PCT:
            alerts.append(_alert(
                3, "disk_penuh",
                f"Pemakaian disk {dpath.removeprefix('disk_').removesuffix('_pct')} "
                f"{val:.0f}% (threshold {DISK_PCT:.0f}%).",
                "Disk penuh: Postgres bisa berhenti, backup & log gagal.",
                "Tidak ada aksi otomatis (watch).",
                ["Bersihkan log/parquet lama & backup kadaluarsa",
                 "Cek journalctl --disk-usage"],
                None))
    bage = backup.get("age_s")
    if bage is None or bage > BACKUP_AGE_H * 3600:
        age_txt = "belum ada backup sukses" if bage is None else f"{bage / 3600:.1f} jam"
        alerts.append(_alert(
            3, "backup_age",
            f"Backup harian: {age_txt} (threshold {BACKUP_AGE_H:.0f} jam).",
            "RPO 24 jam terancam; bila DB rusak, data hilang lebih banyak.",
            "Tidak ada aksi otomatis (watch).",
            ["Cek journalctl --user -u fund2-backup -n 50",
             "Cek ~/fund2-backups/logs/backup-*.json terbaru",
             "Jalankan manual: ~/fund2/scripts/fund2_backup.sh"],
            None))
    dd = risk.get("daily_drawdown_pct", 0.0) or 0.0
    if dd >= DAILY_DD_WATCH_PCT:
        alerts.append(_alert(
            3, "drawdown_watch",
            f"Drawdown harian {dd:.2f}% (watch {DAILY_DD_WATCH_PCT}%, "
            f"auto-halt 3%).",
            "Mendekati ambang auto-halt; entry lanjutan bisa memperburuk.",
            "Tidak ada aksi otomatis (auto-halt menyala di 3%).",
            ["Review posisi & sinyal terakhir",
             "Pause strategi yang men-loss bila pola berlanjut"],
            None))
    stuck = orders.get("stuck_sent_60s", 0)
    if stuck:
        alerts.append(_alert(
            3, "order_stuck",
            f"{stuck} order SENT > 60s tanpa hasil (STUCK).",
            "Status order tidak pasti: bisa fill di broker tanpa DB tahu.",
            "Sweep worker akan transisi ke STUCK; reconciler menyusul.",
            ["Cek /orders untuk command_id yang macet",
             "Verifikasi di MT5; reconciler akan adopsi/fail-kan"],
            None))
    frate = orders.get("failure_rate_24h")
    if frate is not None and frate >= FAILED_RATE_WATCH and (orders.get("terminal_24h") or 0) >= 5:
        alerts.append(_alert(
            3, "failure_rate",
            f"Rasio FAILED 24 jam {frate * 100:.0f}% "
            f"({orders.get('failed_24h')}/{orders.get('terminal_24h')} terminal, "
            f"watch {FAILED_RATE_WATCH * 100:.0f}%).",
            "Degradasi eksekusi; bila berlanjut bisa capai 3 FAILED beruntun "
            "(SEV-2, halt entry).",
            "Tidak ada aksi otomatis (watch; streak >= 3 memicu SEV-2).",
            ["Cek fail_reason di /orders (reject broker? simbol? spread?)",
             "Verifikasi koneksi broker"],
            None))
    for name, r in runners.items():
        age = r.get("paper_state_age_s")
        if age is not None and age > 900:
            alerts.append(_alert(
                3, "paper_runner_stale",
                f"Paper runner {name} tidak update paper_state {age / 60:.0f} menit.",
                "Sinyal paper tidak terekam; evaluasi gerbang paper terhenti.",
                "Tidak ada aksi otomatis (watch; watcher paper runner juga "
                "mengalert).",
                ["systemctl --user status fund2-paper-runner",
                 "Cek feed candle & market jam"],
                None))
    return alerts


def format_alert(a: dict, *, test: bool = False) -> str:
    """Alert -> teks Telegram actionable (apa, dampak, waktu, otomatis, manual).

    Semua nilai dinamis di-escape (parse_mode 'Markdown' di telegram_bot):
    underscore pada key/trigger (mis. auto:position_mismatch) dan tanda []
    membuat entity tak tertutup -> Telegram 400 -> alert tak terkirim.
    """
    icon = {1: "🚨", 2: "🔥", 3: "⚠️"}.get(a["sev"], "•")
    head = f"{icon} \\[TEST\\] " if test else f"{icon} "
    lines = [f"{head}SEV-{a['sev']} · {_md_escape(a['key'].replace('_', ' ').upper())}",
             f"Apa: {_md_escape(a['what'])}",
             f"Dampak: {_md_escape(a['impact'])}",
             f"Waktu: {_md_escape(a['when'])}",
             f"Otomatis: {_md_escape(a['auto'])}"]
    if a.get("manual"):
        lines.append("Manual:")
        lines.extend(f"  {i}. {_md_escape(step)}" for i, step in enumerate(a["manual"], 1))
    return "\n".join(lines)


# ---------------------------------------------------------------- watch loop

def _key(a: dict) -> str:
    return f"sev{a['sev']}:{a['key']}"


async def _apply_auto_action(a: dict) -> None:
    """Auto-action SEV-1/SEV-2 via kill_switch.activate (idempotent: mode sama
    / lebih ringan = no-op; ledger event tetap dicatat oleh activate)."""
    mode = a.get("action_mode")
    if not mode:
        return
    try:
        await kill_switch.activate(
            mode,
            reason=f"SEV-{a['sev']} {a['key']}: {a['what']}",
            source=f"auto:sev_{a['key']}",
            actor="auto",
        )
    except Exception as exc:  # noqa: BLE001 — alert tetap terkirim
        log.warning("auto-action %s gagal: %s", mode, exc)


async def sev_watch_loop(stop: asyncio.Event, beat=None) -> None:
    """Loop SEV-1..SEV-3 DI DALAM daemon fund2-alerts (satu sender, bukan
    pipeline kedua). Pola insiden:
      - SEV-1/2: alert SAAT DETEKSI, termasuk kondisi yang sudah ada saat
        daemon start (SEV-1/2 tidak boleh diam 30 menit hanya karena restart);
      - SEV-3: observasi pertama = baseline (anti-spam restart; noise watch
        tidak sebanding dengan risiko ketinggalan SEV-1/2);
      - SEV-1/2 persisten: kirim ulang tiap RE_ALERT_S;
      - pulih: pesan ✅ sekali per insiden.
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_OWNER_ID):
        return
    incidents: dict[str, dict] = {}  # key -> {"alert": dict, "since": epoch, "last_sent": epoch}
    log.info("alerts sev-watch aktif (interval %.0fs)", SEV_CHECK_INTERVAL_S)
    first = True
    while not stop.is_set():
        if beat is not None:
            beat("sev")
        try:
            m = await collect_metrics()
            fired = evaluate_sev(m)
            # t_b827af0c: keputusan halt untuk db_unavailable diambil state
            # mesin (probe langsung gagal ATAU >=2 pemeriksaan gagal
            # berturut-turut), bukan oleh satu PoolTimeout. observe() wajib
            # dipanggil tiap iterasi supaya streak reset begitu DB sehat lagi.
            db_verdict = DB_UNAVAIL_TRACKER.observe(m.get("db") or {})
            now = time.monotonic()
            fired_keys = {_key(a) for a in fired}
            for a in fired:
                if a["key"] == "db_unavailable":
                    activate = bool(db_verdict["activate"])
                    a = {**a,
                         "action_mode": "STOP_NEW_ORDERS" if activate else None,
                         "auto": (f"STOP_NEW_ORDERS otomatis: {db_verdict['reason']}."
                                  if activate else
                                  f"TIDAK mengaktifkan STOP_NEW_ORDERS: "
                                  f"{db_verdict['reason']}. Timeout pool bukan "
                                  f"bukti database mati.")}
                k = _key(a)
                inc = incidents.get(k)
                if inc is None:
                    inc = incidents[k] = {"alert": a, "since": now, "last_sent": now,
                                          "acted": False}
                    if a["sev"] <= 2 or not first:
                        if a.get("action_mode"):
                            await _apply_auto_action(a)
                            inc["acted"] = True
                        await notify_owner(format_alert(a))
                        log.warning("SEV-%d %s: %s", a["sev"], a["key"], a["what"])
                elif a["sev"] <= 2 and now - inc["last_sent"] >= RE_ALERT_S:
                    # SEV-1/2 persisten: kirim ulang tiap RE_ALERT_S
                    inc["alert"], inc["last_sent"] = a, now
                    await notify_owner(format_alert(a) +
                                       f"\n(persisten sejak {int((now - inc['since']) / 60)} menit)")
                # Eskalasi: kondisi yang saat pertama terdeteksi belum memenuhi
                # ambang halt (mis. 1x PoolTimeout) sekarang memenuhinya
                # (2x berturut / probe DB gagal) -> baru di sini kill-switch
                # diaktifkan, tanpa menunggu incident berikutnya (t_b827af0c).
                if (a["sev"] <= 2 and a.get("action_mode") and not inc["acted"]):
                    await _apply_auto_action(a)
                    inc["acted"] = True
                    inc["alert"], inc["last_sent"] = a, now
                    await notify_owner(
                        format_alert(a) +
                        "\n(eskalasi: ambang halt sekarang terpenuhi)")
                    log.warning("SEV-%d %s: eskalasi halt %s",
                                a["sev"], a["key"], a["action_mode"])
            for k in [k for k in incidents if k not in fired_keys]:
                inc = incidents.pop(k)
                if not first:
                    a = inc["alert"]
                    dur = int((now - inc["since"]) / 60)
                    await notify_owner(
                        f"✅ PULIH: SEV-{a['sev']} {a['key'].replace('_', ' ')} "
                        f"(berlangsung ~{dur} menit).")
        except Exception as exc:  # noqa: BLE001 — loop harus hidup
            log.warning("sev_watch error: %s", exc)
        first = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=SEV_CHECK_INTERVAL_S)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------- HTTP + CLI

router = APIRouter()


@router.get("/metrics")
async def get_metrics(user: dict = Depends(get_current_user)):
    """Metrics PRD §20.1 untuk dashboard (auth session)."""
    return await collect_metrics()


async def active_alerts(window_s: float = EVENT_WINDOW_S) -> dict:
    """Alert SEV aktif saat ini untuk dashboard (PRD §20.2/§21, UI-D0).

    Read-only, TIDAK menulis state. Tidak ada tabel alert: state insiden
    sev_watch_loop hidup di memori daemon fund2-alerts (proses terpisah,
    tidak bisa dibaca lintas proses), jadi dashboard menghitung ulang dari
    collect_metrics() + evaluate_sev() — evaluator, threshold, dan sumber
    data yang sama dengan /metrics, jadi konsisten by construction.
    SEV-4 (rekap harian) bukan alert aktif dan tidak dihitung di sini.
    """
    m = await collect_metrics(window_s)
    fired = evaluate_sev(m)
    return {
        "alerts": [
            {
                "sev": a["sev"],
                "key": a["key"],
                "what": a["what"],
                "impact": a["impact"],
                "since": a["when"],
                "source": "metrics:evaluate_sev",
            }
            for a in fired
        ],
        "as_of": datetime.now(timezone.utc).isoformat(),
        "window_s": m.get("window_s", window_s),
    }


@router.get("/alerts/active")
async def get_active_alerts(user: dict = Depends(get_current_user)):
    """Alert SEV aktif (read-only) untuk strip dashboard (PRD §21.2).

    Tidak ada alert -> {alerts: []} dengan HTTP 200 (bukan 404).
    """
    return await active_alerts()


def _synthetic_sev_sample() -> list[dict]:
    """Sampel metrics sintetis utk uji kirim SEV-1 & SEV-2 (CLI --send-test)."""
    return [
        {
            "db": {"available": True},
            "risk": {"unprotected_positions": [
                {"ticket_sym": "XAUUSD BUY 0.02", "open_price": 3600.0}],
                "open_positions": 1, "consecutive_failed": 0,
                "daily_drawdown_pct": 0.4},
            "reconciliation": {"mismatch_24h": 1, "orphan_24h": 0,
                               "new": {"mismatch_new": 1, "orphan_new": 0}},
            "ea": {"last_seen_age_s": 5.0, "offline_threshold_s": 60},
            "audit": {"admin_lockouts_new": 0},
            "latency": {"t0_t2_ms": {"p95": 0.041, "n": 12}},
            "spread": {"XAUUSD": {"p95_1h": 0.31, "p50_1h": 0.22}},
            "feed": {"candles": {"XAUUSD:M5": {"age_s": 41.0}}, "gaps_1h": {}},
            "orders": {"stuck_sent_60s": 0},
            "host": {"disk_root_pct": 41.0},
            "backup": {"age_s": 3600.0},
            "strategies": {"runners": {}},
        },
        {
            "db": {"available": True},
            "risk": {"unprotected_positions": [], "open_positions": 2,
                     "consecutive_failed": 4, "daily_drawdown_pct": 0.9},
            "reconciliation": {"mismatch_24h": 0, "orphan_24h": 0,
                               "new": {"mismatch_new": 0, "orphan_new": 0}},
            "ea": {"last_seen_age_s": 145.0, "offline_threshold_s": 60},
            "audit": {"admin_lockouts_new": 0},
            "latency": {"t0_t2_ms": {"p95": 0.05, "n": 12}},
            "spread": {"XAUUSD": {"p95_1h": 0.31, "p50_1h": 0.22}},
            "feed": {"candles": {"XAUUSD:M5": {"age_s": 41.0}}, "gaps_1h": {}},
            "orders": {"stuck_sent_60s": 0},
            "host": {"disk_root_pct": 41.0},
            "backup": {"age_s": 3600.0},
            "strategies": {"runners": {}},
        },
    ]


async def _amain_check() -> int:
    """CLI: collect + evaluate, cetak hasil (tanpa kirim, tanpa auto-action)."""
    await db.init_pool()
    try:
        m = await collect_metrics()
        fired = evaluate_sev(m)
        print(json.dumps(m, indent=2, default=str))
        print(f"\n=== ALERT ({len(fired)}) ===")
        for a in fired:
            print(format_alert(a))
            print()
        return 0
    finally:
        await db.close_pool()


# ---------------------------------------------------------------- daemon integration
# sev_watch_loop dijalankan dari app.alerts._amain (daemon fund2-alerts yang
# sama, sender telegram_bot.notify_owner yang sama) — LIHAT alerts.py.
# TIDAK ada entrypoint daemon terpisah di modul ini (pembatasan Direktur:
# satu pipeline alert, milik t_f2p1b3).


async def _amain_send_test() -> int:
    """CLI: kirim alert [TEST] SEV-1 & SEV-2 ke owner via sender t_f2p1b3.

    Tanpa auto-action (kill-switch live tidak disentuh) — murni uji jalur
    evaluasi -> format -> kirim. Guard TELEGRAM_ALERTS_OFF tetap dihormati.
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_OWNER_ID):
        print("alerts off: TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID tidak diset")
        return 2
    await db.init_pool()
    try:
        for m in _synthetic_sev_sample():
            for a in evaluate_sev(m):
                if a["sev"] in (1, 2):
                    ok = await notify_owner(format_alert(a, test=True))
                    print(f"[test] SEV-{a['sev']} {a['key']}: sent={ok}")
        return 0
    finally:
        await db.close_pool()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--send-test" in sys.argv:
        sys.exit(asyncio.run(_amain_send_test()))
    sys.exit(asyncio.run(_amain_check()))


if __name__ == "__main__":
    main()


