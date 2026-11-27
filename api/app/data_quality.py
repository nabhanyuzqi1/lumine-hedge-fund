"""Data quality checks + laporan (PRD v2.2 §19.2, §4.4; kartu t_f2v22a11).

Sembilan checks §19.2 dijalankan terhadap Postgres (+ parquet tick,
dukascopy historis bila ada), hasilnya:
  - dicetak ke stdout (CLI python -m app.data_quality)
  - ditulis ke data/quality/quality_report.json
  - disimpan ke tabel data_quality_runs (riwayat) + data_versions
    (checksum per series, PRD 19.2 "data version and checksum")
  - opsional dikirim ke owner Telegram (--send)

Status: PASS (sehat) / WARN (perlu dilihat) / FAIL (data rusak atau
guard ledger hilang). Exit code CLI: 0 = tanpa FAIL, 1 = ada FAIL,
2 = DB tidak tersedia.

Daftar check §19.2 -> section laporan:
  completeness              -> candles.completeness
  duplicate rate            -> candles.duplicate_rate
  timestamp monotonicity    -> candles.monotonicity
  gap detection             -> candles.gaps (+ freshness.tick_age)
  spread validity           -> liquidity.spread
  candle OHLC consistency   -> candles.ohlc
  symbol mapping            -> symbols.mapping
  broker-vs-historical      -> broker_vs_historical
  data version & checksum   -> data_versions
Ledger append-only (PRD 19.4) -> ledger (trigger, privilege, event
kompensasi, integritas rantai order_events).

Ambang sengaja konservatif: FAIL hanya untuk kerusakan nyata (OHLC
pecah, spread negatif, guard ledger hilang); kelengkapan rendah dan
gap sedang = WARN karena feed live memang tidak pernah 100%.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, db
from .state_machine import fetchall
from .telegram_bot import notify_owner

log = logging.getLogger("fund2.data_quality")

WIB = timezone(timedelta(hours=7))
DEFAULT_WINDOW_DAYS = 3
QUALITY_DIR = Path(config.TICKS_PARQUET_DIR).parent / "quality"

# ── Ambang (PRD 19.2; nilai default, dijelaskan per check) ──────────────────
DUPLICATE_RATE_WARN = 0.001       # >0.1% duplikat = WARN
COMPLETENESS_WARN = 0.70          # coverage < 70% = WARN
COMPLETENESS_FAIL = 0.30          # coverage < 30% = FAIL (feed mati)
GAP_FAIL_MIN = 240.0              # gap > 4 jam di jam pasar = FAIL
GAP_WARN_MIN = 30.0               # gap 30 menit - 4 jam = WARN
STALE_TICK_WARN_S = 300.0         # tick M1 terakhir > 5 menit = WARN
STALE_TICK_FAIL_S = 1800.0        # > 30 menit = FAIL (feed mati)
SPREAD_ABS_MAX = {"XAUUSD": 0.50, "BTCUSD": 100.00}  # spec settings (A9)
BROKER_HIST_TOL_PCT = 0.005       # beda broker vs dukascopy > 0.5% = mismatch
BROKER_HIST_MISMATCH_WARN = 0.05  # > 5% bar mismatch = WARN
BROKER_HIST_MISMATCH_FAIL = 0.20  # > 20% = FAIL

# Timeframe kanonik -> detik per bar (untuk alignment & gap)
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}

# Jam tutup pasar XAUUSD (UTC, CME): break harian 22:00-23:00, akhir pekan
# Jumat 22:00 -> Minggu 23:00. Toleransi 5 menit di tepi supaya bar tepat
# jam buka/tutup tidak dihitung gap. BTCUSD crypto 24/7.
GOLD_DAILY_BREAK = (22 * 60, 23 * 60)          # menit-dalam-hari UTC
GOLD_WEEKEND = (4, 22 * 60 + 20, 6, 23 * 60 + 20)  # (hari_mulai, menit, hari_akhir, menit)


def _minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def market_closed_minutes(symbol: str, ts: datetime) -> bool:
    """True bila menit ts berada di luar jam pasar spot simbol (UTC)."""
    if symbol.upper() != "XAUUSD":
        return False  # crypto 24/7 (BTCUSD) & simbol lain dianggap buka
    mod = _minute_of_day(ts)
    wd = ts.weekday()  # Senin=0 .. Minggu=6
    start_d, start_m, end_d, end_m = GOLD_WEEKEND
    in_weekend = False
    if start_d <= end_d:
        if start_d < wd < end_d:
            in_weekend = True
        elif wd == start_d and mod >= start_m:
            in_weekend = True
        elif wd == end_d and mod <= end_m:
            in_weekend = True
    if in_weekend:
        return True
    lo, hi = GOLD_DAILY_BREAK
    return lo - 5 <= mod <= hi + 5 and wd not in (4, 5, 6)


def _expected_minutes(symbol: str, start: datetime, end: datetime) -> int:
    """Perkiraan menit pasar terbuka dalam [start, end) untuk M1."""
    total = 0
    cur = start.replace(second=0, microsecond=0)
    while cur < end:
        if not market_closed_minutes(symbol, cur):
            total += 1
        cur += timedelta(minutes=1)
    return total


def _pct(part: float, whole: float) -> float:
    return round(part / whole, 4) if whole else 1.0


# --------------------------------------------------------------------- OHLC
def check_ohlc(rows: list[dict]) -> dict:
    """Konsistensi candle OHLC (PRD 19.2): high >= max(open,close),
    low <= min(open,close), high >= low, semua harga > 0, volume >= 0."""
    violations = []
    for r in rows:
        o, h, l, c = (float(r.get("open", 0)), float(r.get("high", 0)),
                      float(r.get("low", 0)), float(r.get("close", 0)))
        v = float(r.get("volume", 0))
        bad = None
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            bad = "harga <= 0"
        elif v < 0:
            bad = "volume negatif"
        elif h < l:
            bad = "high < low"
        elif h < max(o, c) - 1e-9 or l > min(o, c) + 1e-9:
            bad = "high/close di luar range low-high"
        if bad:
            violations.append({"ts": str(r.get("ts")), "reason": bad,
                               "o": o, "h": h, "l": l, "c": c})
    n = len(rows)
    return {"status": "FAIL" if violations else "PASS",
            "detail": f"{len(violations)}/{n} bar melanggar OHLC",
            "violations": violations[:5], "violation_count": len(violations)}


# --------------------------------------------------------------- monoton/dup
def check_monotonicity(rows: list[dict], timeframe: str) -> dict:
    """Timestamp naik ketat + alignment bucket (PRD 19.2). Bar dari DB sudah
    terurut PK; yang diuji adalah alignment ke bucket TF dan duplicated ts."""
    step = TF_SECONDS.get(timeframe)
    misaligned = 0
    non_monotonic = 0
    prev = None
    for r in rows:
        ts = r.get("ts")
        if isinstance(ts, datetime):
            if prev is not None and ts <= prev:
                non_monotonic += 1
            prev = ts
        if step and step > 60:
            epoch = int(ts.timestamp()) if isinstance(ts, datetime) else None
            if epoch is not None and epoch % step != 0:
                misaligned += 1
    n = len(rows)
    bad = non_monotonic + misaligned
    return {"status": "FAIL" if bad else "PASS",
            "detail": f"{bad}/{n} bar tidak monoton/alignment",
            "non_monotonic": non_monotonic, "misaligned": misaligned}


def check_duplicate_rate(rows: list[dict]) -> dict:
    """Duplicate rate pada kunci series (PRD 19.2). Di Postgres PK
    (symbol,timeframe,ts) menjamin 0; metrik tetap dihitung untuk parquet
    dan sumber legacy."""
    n = len(rows)
    keys = [(r.get("symbol"), r.get("timeframe"), r.get("ts")) for r in rows]
    dup = n - len(set(keys))
    rate = (dup / n) if n else 0.0
    status = "PASS"
    if rate > DUPLICATE_RATE_WARN:
        status = "WARN"
    if rate > 0.10:
        status = "FAIL"
    return {"status": status,
            "detail": f"{dup}/{n} baris duplikat ({rate:.2%})",
            "duplicate_rows": dup, "rows": n, "rate": round(rate, 6)}


def _open_minutes_between(symbol: str, start: datetime, end: datetime) -> int:
    """Jumlah menit pasar BUKA dalam (start, end) — gap diukur hanya di
    jam pasar; akhir pekan & break harian tidak dihitung gap."""
    n = 0
    cur = start + timedelta(minutes=1)
    while cur < end:
        if not market_closed_minutes(symbol, cur):
            n += 1
        cur += timedelta(minutes=1)
    return n


def gap_thresholds(timeframe: str) -> tuple[float, float]:
    """Ambang gap (menit jam pasar) per timeframe: bar H1 berjarak 60 menit
    adalah normal, jadi ambang M1 (30/240) harus diskalakan. Ambang = max(
    konstanta M1, ukuran bar x faktor)."""
    step_min = TF_SECONDS.get(timeframe, 60) / 60.0
    warn = max(GAP_WARN_MIN, step_min * 1.5)
    fail = max(GAP_FAIL_MIN, step_min * 4.0)
    return warn, fail


def check_gaps(rows: list[dict], symbol: str, timeframe: str,
               *, max_report: int = 5) -> dict:
    """Gap detection (PRD 19.2, 4.4): jeda antar bar di jam pasar melebihi
    batas per-timeframe (gap_thresholds). Menit akhir pekan/break harian
    tidak dihitung (XAUUSD), jadi libur akhir pekan bukan gap."""
    warn_min, fail_min = gap_thresholds(timeframe)
    gaps = []
    prev = None
    for r in rows:
        ts = r.get("ts")
        if not isinstance(ts, datetime):
            continue
        if prev is not None and ts > prev:
            open_min = _open_minutes_between(symbol, prev, ts)
            if open_min > warn_min:
                gaps.append({"from": prev.isoformat(), "to": ts.isoformat(),
                             "minutes": open_min})
        prev = ts
    gaps.sort(key=lambda g: -g["minutes"])
    worst = gaps[0]["minutes"] if gaps else 0.0
    status = "PASS"
    if worst > warn_min:
        status = "WARN"
    if worst > fail_min:
        status = "FAIL"
    return {"status": status,
            "detail": (f"{len(gaps)} gap; terbesar {worst:.0f} menit jam pasar "
                       f"(ambang WARN {warn_min:.0f}/FAIL {fail_min:.0f} mnt)"
                       if gaps else "tidak ada gap"),
            "gaps": gaps[:max_report], "gap_count": len(gaps),
            "warn_threshold_min": warn_min, "fail_threshold_min": fail_min}


def check_completeness(rows: list[dict], symbol: str, timeframe: str,
                       window_days: int) -> dict:
    """Data completeness (PRD 19.2): baris aktual vs menit pasar yang
    diharapkan dalam window."""
    step = TF_SECONDS.get(timeframe, 60)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    ts_list = [r.get("ts") for r in rows if isinstance(r.get("ts"), datetime)]
    if not ts_list:
        return {"status": "WARN", "detail": "tidak ada data dalam window",
                "expected": 0, "actual": 0, "coverage": None}
    first = max(min(ts_list), start)
    last = max(ts_list)
    factor = max(1, step // 60)
    expected = max(1, _expected_minutes(symbol, first, last) // factor)
    actual = len({ts for ts in ts_list})
    coverage = _pct(actual, expected)
    status = "PASS"
    if coverage < COMPLETENESS_WARN:
        status = "WARN"
    if coverage < COMPLETENESS_FAIL:
        status = "FAIL"
    return {"status": status,
            "detail": f"coverage {coverage:.1%} ({actual}/{expected} bar "
                      f"{timeframe} dalam window {window_days}h)",
            "expected": expected, "actual": actual,
            "coverage": coverage, "first": first.isoformat(),
            "last": last.isoformat()}


# ------------------------------------------------------------------ checksum
def series_checksum(rows: list[dict]) -> str:
    """Checksum deterministik per series (PRD 19.2 data version). Hash
    kanonik: symbol|timeframe|ts|o|h|l|c|v dengan angka dibulatkan 5 desimal
    dan ts ISO UTC — stabil antar proses."""
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda x: (x.get("ts") or datetime.min.replace(tzinfo=timezone.utc)).isoformat()):
        ts = r.get("ts")
        ts_iso = ts.astimezone(timezone.utc).isoformat() if isinstance(ts, datetime) else str(ts)
        line = "|".join([
            str(r.get("symbol")), str(r.get("timeframe")), ts_iso,
            f"{float(r.get('open', 0)):.5f}", f"{float(r.get('high', 0)):.5f}",
            f"{float(r.get('low', 0)):.5f}", f"{float(r.get('close', 0)):.5f}",
            f"{float(r.get('volume', 0)):.2f}",
        ])
        h.update(line.encode() + b"\n")
    return "sha256:" + h.hexdigest()


# ------------------------------------------------------------ spread/simbol
def check_spread(samples: list[dict], symbol: str) -> dict:
    """Spread validity (PRD 19.2, 4.4): spread negatif, min>max, avg di
    luar spec, tick_count <= 0."""
    bad = []
    spec_max = SPREAD_ABS_MAX.get(symbol.upper())
    for s in samples:
        avg, mn, mx = (float(s.get("spread_avg", 0)), float(s.get("spread_min", 0)),
                       float(s.get("spread_max", 0)))
        cnt = int(s.get("tick_count", 0))
        reason = None
        if mn < 0 or avg < 0 or mx < 0:
            reason = "spread negatif"
        elif mx < mn:
            reason = "spread_max < spread_min"
        elif cnt <= 0:
            reason = "tick_count <= 0"
        elif spec_max is not None and avg > spec_max:
            reason = f"spread_avg {avg} > spec {spec_max}"
        if reason:
            bad.append({"window_start": str(s.get("window_start")),
                        "reason": reason, "avg": avg, "min": mn, "max": mx})
    n = len(samples)
    return {"status": "FAIL" if bad else "PASS",
            "detail": f"{len(bad)}/{n} sampel spread tidak valid ({symbol})",
            "invalid": bad[:5], "invalid_count": len(bad), "samples": n}


def check_symbol_mapping(db_symbols: list[str], settings: dict,
                         known_default: set[str] | None = None) -> dict:
    """Symbol mapping (PRD 19.2): simbol di DB harus kanonik (tanpa #/.,
    suffix broker), dan sinkron dengan settings (allowed_symbols /
    symbol_specs). Simbol di DB yang tidak ada di settings = WARN (settings
    belum diupdate), sebaliknya = INFO."""
    issues = []
    raw_format = [s for s in db_symbols
                  if s.startswith("#") or "." in s or (len(s) > 4 and s[-1] in "cmxiz")]
    if raw_format:
        issues.append({"level": "FAIL",
                       "detail": f"nama simbol broker mentah tersimpan: {raw_format}"})
    allowed = set(settings.get("allowed_symbols") or [])
    specs = set((settings.get("symbol_specs") or {}).keys())
    known = allowed | specs | (known_default or set())
    unmapped = [s for s in db_symbols if s not in known]
    if unmapped:
        issues.append({"level": "WARN",
                       "detail": f"simbol berdata tapi tidak di settings: {unmapped}"})
    ghost = [s for s in allowed - set(db_symbols)
             if s not in (known_default or set())]
    # allowed tanpa data = informasi (feed belum jalan), bukan kegagalan.
    status = "PASS"
    if any(i["level"] == "WARN" for i in issues):
        status = "WARN"
    if any(i["level"] == "FAIL" for i in issues):
        status = "FAIL"
    return {"status": status,
            "detail": "; ".join(i["detail"] for i in issues) or
                      f"{len(db_symbols)} simbol kanonik & sinkron settings",
            "symbols": sorted(db_symbols), "issues": issues}


# --------------------------------------------------------------- broker/hist
def check_broker_vs_historical(broker_rows: list[dict], hist_rows: list[dict],
                               tol_pct: float = BROKER_HIST_TOL_PCT) -> dict:
    """Broker-vs-historical (PRD 19.2): bandingkan close M1 pada window
    overlap. Beda > tol_pct relatif dihitung mismatch. Tidak ada overlap =
    SKIPPED (bukan gagal)."""
    hist = {r["ts"]: float(r["close"]) for r in hist_rows if r.get("ts")}
    diffs = []
    mismatches = 0
    compared = 0
    for r in broker_rows:
        ts = r.get("ts")
        if ts not in hist:
            continue
        compared += 1
        bc, hc = float(r["close"]), hist[ts]
        if hc <= 0:
            continue
        rel = abs(bc - hc) / hc
        diffs.append(rel)
        if rel > tol_pct:
            mismatches += 1
    if compared == 0:
        return {"status": "SKIPPED",
                "detail": "tidak ada overlap window broker vs historis",
                "compared": 0}
    rate = mismatches / compared
    median = sorted(diffs)[len(diffs) // 2] if diffs else 0.0
    p95 = sorted(diffs)[max(0, math.ceil(0.95 * len(diffs)) - 1)] if diffs else 0.0
    status = "PASS"
    if rate > BROKER_HIST_MISMATCH_WARN:
        status = "WARN"
    if rate > BROKER_HIST_MISMATCH_FAIL:
        status = "FAIL"
    return {"status": status,
            "detail": (f"{mismatches}/{compared} bar beda > {tol_pct:.1%} "
                       f"dari historis (median {median:.4%}, p95 {p95:.4%})"),
            "compared": compared, "mismatches": mismatches,
            "mismatch_rate": round(rate, 4),
            "median_rel_diff": round(median, 6), "p95_rel_diff": round(p95, 6)}


# ------------------------------------------------------------------- ledger
def check_ledger(guard: dict, chain: dict) -> dict:
    """Append-only ledger (PRD 19.4): trigger aktif, privilege UPDATE/
    DELETE/TRUNCATE tertutup untuk non-owner, rantai event konsisten."""
    issues = []
    if not guard.get("append_only_trigger"):
        issues.append("trigger append-only order_events TIDAK ada")
    if not guard.get("truncate_trigger"):
        issues.append("trigger anti-TRUNCATE order_events TIDAK ada")
    leaked = guard.get("non_owner_mutate_grants") or []
    if leaked:
        issues.append(f"privilege mutasi bocor ke non-owner: {leaked}")
    orphans = chain.get("orphan_events", 0)
    if orphans:
        issues.append(f"{orphans} event tanpa order induk")
    broken = chain.get("broken_chains", 0)
    if broken:
        issues.append(f"{broken} rantai status patah (from_status tidak nyambung)")
    status = "FAIL" if issues else "PASS"
    detail = "; ".join(issues) or (
        f"ledger aman: {chain.get('events', 0)} event, "
        f"{chain.get('orders', 0)} order, "
        f"{chain.get('compensation_events', 0)} event kompensasi")
    return {"status": status, "detail": detail, **guard, **chain,
            "issues": issues}


# ------------------------------------------------------------- collector DB
async def _collect_candles(conn, window_days: int) -> dict[str, list[dict]]:
    """Candle window terbaru dikelompokkan per (symbol, timeframe)."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = await fetchall(
        conn,
        "SELECT symbol, timeframe, ts, open, high, low, close, volume "
        "FROM candles WHERE ts >= %s ORDER BY symbol, timeframe, ts",
        (since,))
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault((r["symbol"], r["timeframe"]), []).append(r)
    return grouped


async def _collect_liquidity(conn, window_days: int) -> dict[str, list[dict]]:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = await fetchall(
        conn,
        "SELECT symbol, window_start, spread_avg, spread_min, spread_max, tick_count "
        "FROM liquidity_samples WHERE window_start >= %s ORDER BY symbol, window_start",
        (since,))
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["symbol"], []).append(r)
    return grouped


async def _collect_ledger_guard(conn) -> dict:
    """Guard append-only (PRD 19.4): trigger + privilege + audit table."""
    trigs = await fetchall(
        conn,
        "SELECT tgname FROM pg_trigger "
        "WHERE tgrelid = 'order_events'::regclass AND NOT tgisinternal")
    names = {t["tgname"] for t in trigs}
    grants = await fetchall(
        conn,
        "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'order_events' "
        "AND privilege_type IN ('UPDATE','DELETE','TRUNCATE')")
    # owner selalu punya privilege (dilaporkan, bukan kegagalan); yang dicari
    # adalah grant eksplisit ke role lain.
    owner_rows = await fetchall(
        conn, "SELECT tableowner FROM pg_tables WHERE tablename = 'order_events'")
    owner = owner_rows[0]["tableowner"] if owner_rows else None
    leaked = sorted({f"{g['grantee']}:{g['privilege_type']}" for g in grants
                     if g["grantee"] != owner and g["grantee"] != "PUBLIC"
                     or (g["grantee"] == "PUBLIC")})
    return {
        "append_only_trigger": "order_events_append_only" in names,
        "truncate_trigger": "order_events_no_truncate" in names,
        "non_owner_mutate_grants": leaked,
        "table_owner": owner,
        "triggers": sorted(names),
    }


async def _collect_ledger_chain(conn) -> dict:
    """Integritas rantai order_events: event tanpa induk, rantai patah,
    jumlah event kompensasi (koreksi PRD 19.4)."""
    orphans = await fetchone_val(
        conn, "SELECT count(*) FROM order_events e "
              "LEFT JOIN orders o ON o.id = e.order_id "
              "WHERE e.order_id IS NOT NULL AND o.id IS NULL")
    events = await fetchone_val(conn, "SELECT count(*) FROM order_events")
    orders = await fetchone_val(conn, "SELECT count(*) FROM orders")
    broken = await fetchone_val(
        conn, """
        WITH ranked AS (
            SELECT order_id, from_status, to_status,
                   lag(to_status) OVER (PARTITION BY order_id ORDER BY id)
                       AS prev_status
            FROM order_events WHERE order_id IS NOT NULL)
        SELECT count(*) FROM ranked
        WHERE prev_status IS NOT NULL AND from_status IS NOT NULL
          AND from_status <> prev_status""")
    comp = await fetchone_val(
        conn, "SELECT count(*) FROM order_events "
              "WHERE to_status ILIKE 'COMPENSAT%%' "
              "OR payload->>'kind' = 'compensation'")
    return {"events": events, "orders": orders, "orphan_events": orphans,
            "broken_chains": broken, "compensation_events": comp}


async def fetchone_val(conn, sql: str, params: tuple = ()):
    """Ambil nilai kolom pertama (row factory dict_row -> ambil value pertama)."""
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    if not row:
        return 0
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


async def _collect_freshness(conn) -> dict:
    """Tick age (PRD 20.1): umur bar M1 terakhir per simbol + EA heartbeat."""
    rows = await fetchall(
        conn, "SELECT symbol, max(ts) AS last FROM candles "
              "WHERE timeframe = 'M1' GROUP BY symbol")
    now = datetime.now(timezone.utc)
    out = {}
    for r in rows:
        age = (now - r["last"]).total_seconds() if r["last"] else None
        out[r["symbol"]] = {"last_m1": r["last"].isoformat() if r["last"] else None,
                            "age_s": round(age) if age is not None else None}
    return out


def _load_history_parquet(path: Path) -> list[dict]:
    """Muat candle M1 historis (dukascopy) untuk perbandingan broker."""
    if not path.exists():
        return []
    import pandas as pd
    df = pd.read_parquet(path)
    out = []
    for _, r in df.iterrows():
        ts = r["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        out.append({"ts": ts, "close": float(r["close"])})
    return out


# ----------------------------------------------------------------- orkestra
async def run_quality_checks(window_days: int = DEFAULT_WINDOW_DAYS,
                             history_parquet: Path | None = None) -> dict:
    """Jalankan seluruh check §19.2 + §4.4 + ledger §19.4. Return dict
    laporan (JSON-serializable)."""
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
        "sections": {},
    }
    async with db.pool().connection() as conn:
        grouped = await _collect_candles(conn, window_days)
        liq = await _collect_liquidity(conn, window_days)
        guard = await _collect_ledger_guard(conn)
        chain = await _collect_ledger_chain(conn)
        freshness = await _collect_freshness(conn)
        settings = await db.get_settings()

    # ---- candles: ohlc / monotonic / dup / gap / completeness per series
    candle_sections = {}
    all_candle_rows = []
    for (symbol, tf), rows in sorted(grouped.items()):
        all_candle_rows.extend(rows)
        candle_sections[f"{symbol}/{tf}"] = {
            "ohlc": check_ohlc(rows),
            "monotonicity": check_monotonicity(rows, tf),
            "duplicate_rate": check_duplicate_rate(rows),
            "gaps": check_gaps(rows, symbol, tf),
            "completeness": check_completeness(rows, symbol, tf, window_days),
        }
    # ringkas status candle per series
    worst = "PASS"
    for name, sec in candle_sections.values() and candle_sections.items():
        for check in sec.values():
            if check["status"] == "FAIL":
                worst = "FAIL"
            elif check["status"] == "WARN" and worst != "FAIL":
                worst = "WARN"
    report["sections"]["candles"] = {
        "status": worst,
        "detail": f"{len(candle_sections)} series diperiksa",
        "series": candle_sections,
    }

    # ---- liquidity: spread validity
    liq_sections = {}
    liq_worst = "PASS"
    for symbol, samples in sorted(liq.items()):
        sec = check_spread(samples, symbol)
        liq_sections[symbol] = sec
        if sec["status"] == "FAIL":
            liq_worst = "FAIL"
        elif sec["status"] == "WARN" and liq_worst != "FAIL":
            liq_worst = "WARN"
    report["sections"]["liquidity"] = {
        "status": liq_worst,
        "detail": f"{sum(len(v) for v in liq.values())} sampel diperiksa",
        "by_symbol": liq_sections,
    }

    # ---- symbol mapping
    db_symbols = sorted({s for (s, _tf) in grouped} | set(liq.keys()))
    report["sections"]["symbols"] = check_symbol_mapping(db_symbols, settings)

    # ---- freshness (tick age, PRD 20.1/4.4)
    fresh_worst = "PASS"
    for symbol, info in freshness.items():
        age = info.get("age_s")
        if age is None:
            continue
        if age > STALE_TICK_WARN_S:
            fresh_worst = "WARN"
        if age > STALE_TICK_FAIL_S:
            fresh_worst = "FAIL"
    report["sections"]["freshness"] = {
        "status": fresh_worst,
        "detail": "; ".join(f"{s}: age {i['age_s']}s"
                            for s, i in freshness.items()) or "tidak ada data M1",
        "by_symbol": freshness,
    }

    # ---- broker vs historical (dukascopy bila ada)
    hist_path = history_parquet or (
        Path(config.TICKS_PARQUET_DIR).parent / "dukascopy" / "snapshot"
        / "xauusd_m1_bid.parquet")
    hist_rows = await asyncio.to_thread(_load_history_parquet, hist_path)
    broker_m1 = [r for r in all_candle_rows if r["timeframe"] == "M1"]
    report["sections"]["broker_vs_historical"] = check_broker_vs_historical(
        broker_m1, hist_rows)

    # ---- ledger append-only (PRD 19.4)
    report["sections"]["ledger"] = check_ledger(guard, chain)

    # ---- data version & checksum (PRD 19.2)
    versions = {}
    for (symbol, tf), rows in sorted(grouped.items()):
        versions[f"{symbol}/{tf}"] = {
            "rows": len(rows),
            "checksum": series_checksum(rows),
        }
    report["sections"]["data_versions"] = {
        "status": "PASS",
        "detail": f"{len(versions)} series checksum",
        "versions": versions,
    }

    # ---- rekap status
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIPPED": 0}
    for sec in report["sections"].values():
        counts[sec["status"]] = counts.get(sec["status"], 0) + 1
    report["counts"] = counts
    if counts["FAIL"]:
        report["status"] = "FAIL"
    elif counts["WARN"]:
        report["status"] = "WARN"
    else:
        report["status"] = "PASS"
    return report


async def persist_report(report: dict) -> None:
    """Simpan laporan ke data_quality_runs + upsert data_versions."""
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO data_quality_runs (status, report, checks_failed, "
            "checks_warned) VALUES (%s, %s, %s, %s)",
            (report["status"], json.dumps(report),
             report["counts"].get("FAIL", 0),
             report["counts"].get("WARN", 0)))
        for key, v in report["sections"]["data_versions"]["versions"].items():
            symbol, tf = key.split("/", 1)
            await conn.execute(
                "INSERT INTO data_versions (symbol, timeframe, row_count, "
                "checksum, updated_at) VALUES (%s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol, timeframe) DO UPDATE SET "
                "row_count = EXCLUDED.row_count, checksum = EXCLUDED.checksum, "
                "updated_at = now()",
                (symbol, tf, v["rows"], v["checksum"]))


def write_report_file(report: dict, path: Path | None = None) -> Path:
    path = path or (QUALITY_DIR / "quality_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str))
    return path


def render_text(report: dict) -> str:
    """Ringkasan human-readable untuk stdout/Telegram."""
    lines = [f"*Data quality report* — {report['status']} "
             f"({report['generated_at'][:19]}Z, window {report['window_days']}h)"]
    for name, sec in report["sections"].items():
        mark = {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL",
                "SKIPPED": "skip"}[sec["status"]]
        lines.append(f"[{mark}] {name}: {sec['detail']}")
    return "\n".join(lines)


async def _amain(window_days: int, json_path: Path | None, send: bool) -> int:
    await db.init_pool()
    try:
        report = await run_quality_checks(window_days)
        print(render_text(report))
        path = write_report_file(report, json_path)
        print(f"laporan: {path}")
        try:
            await persist_report(report)
        except Exception as exc:  # noqa: BLE001 — tabel belum termigrasi?
            print(f"[data_quality] persist gagal: {exc!r}", flush=True)
        if send and report["status"] != "PASS":
            await notify_owner(render_text(report))
        return 1 if report["status"] == "FAIL" else 0
    finally:
        await db.close_pool()


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Fund2 data quality checks (PRD 19.2)")
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--json", type=Path, default=None,
                    help="path laporan JSON (default data/quality/quality_report.json)")
    ap.add_argument("--send", action="store_true",
                    help="kirim ke owner Telegram bila status != PASS")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_amain(args.window_days, args.json, args.send)))


if __name__ == "__main__":
    main()
