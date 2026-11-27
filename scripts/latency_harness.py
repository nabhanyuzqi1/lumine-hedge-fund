#!/usr/bin/env python3
"""Harness latensi T0..T4 untuk Lumine Fund v2 (PRD v2.1 bagian 6).

Titik ukur (jam monotonic, mikrodetik, satu domain jam pada host yang sama;
EA dan API memakai 127.0.0.1 sehingga clock domain-nya sama):

  T0  API menerima order        (request masuk)
  T1  EA menerima command       (response /bridge/poll berisi command)
  T2  EA memanggil OrderSend    (tepat sebelum pemanggilan)
  T3  OrderSend return          (retcode broker di tangan EA)
  T4  Fill terkonfirmasi di DB  (transisi FILLED ter-commit di order_events)

Kontrak pencatatan (append-only, JSONB order_events.payload):

  payload = {
    "latency": {
      "clock": "mono_us",          # mikrodetik sejak boot: time.monotonic_ns (API)
                                   # atau GetMicrosecondCount (EA MQL5)
      "T0": <int>, ... "T4": <int>,# titik terukur; titik yang hilang boleh absen
      "t0_wall": "<ISO8601 UTC>",  # jam dinding T0, untuk filter periode
      "run": "<label>",            # label run harness
      "order_id": "<uuid>",
      "mode": "harness-synthetic-ea" | "live",
      "terminal_status": "FILLED" | "FAILED" | "REJECTED" | "TIMEOUT",
      "meta": {...}
    }, ...payload lain...
  }

Dua sumber sampel:
  1. Instrumentasi asli (dilakukan hf-backend di P1a): API menulis
     payload.latency pada event terminal (FILLED/FAILED); T1..T3 dari EA
     dikirim lewat field tambahan body /bridge/result.
  2. Mode "measure" harness ini: berperan sebagai client + synthetic EA,
     lalu menyisipkan SATU baris event tambahan per order dengan
     to_status="LATENCY" (from_status NULL), tanpa menyentuh baris transisi.

Laporan: p50/p95/p99 per segmen (T0-T1, T1-T2, T2-T3, T3-T4, T0-T2, T0-T4)
plus verdict SLO internal T0->T2: p95 < 300 ms, p99 < 500 ms, gate dihitung
dari minimal 200 order paper/demo (PRD bagian 6 dan 9).

Pemakaian:
  latency_harness.py report  [--dsn URL] [--run LABEL] [--since ISO]
                             [--until ISO] [--json] [--out FILE] [--gate]
  latency_harness.py measure [--api URL] [--dsn URL] [--n N] [--label RUN]
                             [--pace-s S] [--broker-delay-ms MIN:MAX]
                             [--prep-delay-ms MS] [--t4-poll-ms MS]
                             [--timeout-s S] [--seed N]
  latency_harness.py selftest

Kredensial: --dsn / --api / ADMIN_USER / ADMIN_PASSWORD dibaca dari argumen,
environment, lalu ~/fund2/api/.env (urutan itu). Nilai kredensial tidak
pernah dicetak ke output.

Catatan jam: perbandingan T0..T4 lintas proses hanya valid bila API dan EA
berjalan di host yang sama (memenuhi deployment fund2: bridge lokal).
mono_us() di sisi Python memakai time.monotonic_ns (CLOCK_MONOTONIC),
sisi EA memakai GetMicrosecondCount() MQL5; keduanya monotonic sejak boot.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
except ImportError:  # report/measure butuh psycopg; selftest tidak
    psycopg = None

DEFAULT_API = "http://127.0.0.1:3110"
ENV_FILE = Path(__file__).resolve().parent.parent / "api" / ".env"

SLO_T02_P95_MS = 300.0   # PRD bagian 6: SLO internal mengikat
SLO_T02_P99_MS = 500.0
GATE_MIN_ORDERS = 200    # PRD bagian 6/9: diukur pada >= 200 order paper/demo

TERMINAL_STATUSES = ("FILLED", "FAILED")
LATENCY_STATUS = "LATENCY"   # to_status baris sampel harness (bukan transisi)

# (titik awal, titik akhir, nama segmen, keterangan)
SEGMENTS = [
    ("T0", "T1", "T0-T1 pickup EA", "API -> EA menerima command"),
    ("T1", "T2", "T1-T2 EA pre-send", "EA persiapan sebelum OrderSend"),
    ("T2", "T3", "T2-T3 broker OrderSend", "latensi broker (dilaporkan terpisah)"),
    ("T3", "T4", "T3-T4 konfirmasi DB", "result POST -> commit FILLED"),
    ("T0", "T2", "T0-T2 SLO internal", "SLO p95<300ms p99<500ms"),
    ("T0", "T4", "T0-T4 total", "end to end (dilaporkan terpisah)"),
]
POINTS = ("T0", "T1", "T2", "T3", "T4")


# --------------------------------------------------------------------- util

def mono_us() -> int:
    """Timestamp monotonic dalam mikrodetik sejak boot (satu clock domain)."""
    return time.monotonic_ns() // 1000


def percentile(sorted_vals: list[float], pct: float) -> float | None:
    """Percentile linear interpolation (tipe numpy 'linear')."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def summarize(values_ms: list[float]) -> dict:
    """Statistik ringkas satu segmen dalam milidetik."""
    if not values_ms:
        return {"n": 0}
    s = sorted(values_ms)
    return {
        "n": len(s),
        "p50": percentile(s, 50),
        "p95": percentile(s, 95),
        "p99": percentile(s, 99),
        "min": s[0],
        "max": s[-1],
        "mean": sum(s) / len(s),
    }


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


_FILE_ENV = load_env_file(ENV_FILE)


def resolve(name: str, cli_value: str | None, default: str = "") -> str:
    """Prioritas: argumen CLI > environment > api/.env > default."""
    return cli_value or os.environ.get(name) or _FILE_ENV.get(name, default)


# ------------------------------------------------------------------- traces

def fetch_latency_samples(conn, run: str | None = None) -> list[dict]:
    """Ambil semua sampel latensi dari order_events.payload->'latency'.

    Satu baris = satu kandidat sampel. Order dengan lebih dari satu baris
    latensi (mis. harness + instrumentasi asli) dipilih di build_traces.
    """
    sql = ("SELECT order_id::text, payload, created_at FROM order_events "
           "WHERE payload ? 'latency' OR payload ? 'T0'")
    params: list = []
    if run:
        sql += " AND (payload->'latency'->>'run' = %s OR payload->>'run' = %s)"
        params.extend([run, run])
    sql += " ORDER BY id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    samples = []
    for order_id, payload, created_at in rows:
        lat = (payload or {}).get("latency")
        if lat is None and isinstance(payload, dict) and "T0" in payload:
            # Bentuk lama (pre-wrap): titik latensi langsung di payload.
            lat = payload
        if isinstance(lat, dict):
            samples.append({
                "order_id": order_id,
                "latency": lat,
                "created_at": created_at,
            })
    return samples


def trace_points(lat: dict) -> dict[str, int]:
    """Ambil titik T0..T4 yang valid (int) dari satu objek latensi."""
    out = {}
    for p in POINTS:
        v = lat.get(p)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[p] = int(v)
    return out


def build_traces(samples: list[dict]) -> dict[str, dict]:
    """Gabungkan sampel per order: pilih objek latensi dengan titik terlengkap.

    Tie: sampel dengan terminal_status jelas menang, lalu yang terbaru.
    """
    best: dict[str, dict] = {}
    rank: dict[str, tuple] = {}
    for s in samples:
        oid = s["order_id"]
        pts = trace_points(s["latency"])
        terminal = 1 if s["latency"].get("terminal_status") in TERMINAL_STATUSES else 0
        created = s.get("created_at")
        key = (len(pts), terminal, 1 if created else 0)
        if oid not in rank or key >= rank[oid]:
            rank[oid] = key
            best[oid] = s["latency"]
    return best


def compute_segments(traces: dict[str, dict]) -> dict[str, list[float]]:
    """Hitung nilai segmen (ms) dari trace per order.

    Segmen dihitung selama kedua titiknya ada, tanpa syarat kelengkapan
    titik lain; laporan mencantumkan n per segmen secara eksplisit.
    """
    seg: dict[str, list[float]] = {name: [] for _, _, name, _ in SEGMENTS}
    for lat in traces.values():
        pts = trace_points(lat)
        for a, b, name, _ in SEGMENTS:
            if a in pts and b in pts:
                ms = (pts[b] - pts[a]) / 1000.0
                if ms >= 0:
                    seg[name].append(ms)
    return seg


def completeness(traces: dict[str, dict]) -> dict:
    counts = {"complete": 0, "partial": 0, "terminal": {}}
    for lat in traces.values():
        pts = trace_points(lat)
        if all(p in pts for p in POINTS):
            counts["complete"] += 1
        else:
            counts["partial"] += 1
        st = lat.get("terminal_status", "?")
        counts["terminal"][st] = counts["terminal"].get(st, 0) + 1
    return counts


# ------------------------------------------------------------------ laporan

def render_report(traces: dict[str, dict], run_label: str | None,
                  period: str = "semua") -> str:
    seg = compute_segments(traces)
    comp = completeness(traces)
    n_samples = len(traces)
    lines: list[str] = []
    lines.append("# Laporan Latensi Fund2 (T0..T4)")
    lines.append("")
    lines.append(f"- Run: {run_label or 'semua run'}")
    lines.append(f"- Periode (t0_wall): {period}")
    lines.append(f"- Sumber: order_events.payload->'latency' (clock mono_us)")
    lines.append(f"- Sampel order: {n_samples} "
                 f"(lengkap T0..T4: {comp['complete']}, parsial: {comp['partial']})")
    if comp["terminal"]:
        dist = ", ".join(f"{k}={v}" for k, v in sorted(comp["terminal"].items()))
        lines.append(f"- Status terminal: {dist}")
    lines.append("")
    lines.append("| Segmen | n | p50 | p95 | p99 | min | max | mean |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, _, name, desc in SEGMENTS:
        st = summarize(seg[name])
        if st["n"] == 0:
            lines.append(f"| {name} ({desc}) | 0 | - | - | - | - | - | - |")
        else:
            lines.append(
                f"| {name} ({desc}) | {st['n']} "
                f"| {st['p50']:.1f} | {st['p95']:.1f} | {st['p99']:.1f} "
                f"| {st['min']:.1f} | {st['max']:.1f} | {st['mean']:.1f} |"
            )
    lines.append("")
    lines.append(_slo_lines(seg, n_samples))
    lines.append("")
    lines.append("Satuan milidetik. T2-T3 (broker) dan T0-T4 (total) dilaporkan "
                 "terpisah tanpa SLO keras (PRD bagian 6).")
    return "\n".join(lines)


def _slo_lines(seg: dict[str, list[float]], n_samples: int) -> str:
    st = summarize(seg["T0-T2 SLO internal"])
    if st["n"] == 0:
        return "SLO T0-T2: tidak ada sampel."
    ok95 = st["p95"] < SLO_T02_P95_MS
    ok99 = st["p99"] < SLO_T02_P99_MS
    lines = [
        f"SLO T0-T2 (PRD bagian 6): "
        f"p95 {st['p95']:.1f} ms < {SLO_T02_P95_MS:.0f} ms -> {'PASS' if ok95 else 'FAIL'}; "
        f"p99 {st['p99']:.1f} ms < {SLO_T02_P99_MS:.0f} ms -> {'PASS' if ok99 else 'FAIL'}",
        f"Gate sampel: {n_samples}/{GATE_MIN_ORDERS} order "
        f"({'memenuhi' if n_samples >= GATE_MIN_ORDERS else 'BELUM memenuhi'} "
        f"syarat >= {GATE_MIN_ORDERS} order untuk keputusan gate).",
    ]
    return "\n".join(lines)


def report_json(traces: dict[str, dict], run_label: str | None) -> str:
    seg = compute_segments(traces)
    out = {
        "run": run_label,
        "samples": len(traces),
        "completeness": completeness(traces),
        "segments_ms": {name: summarize(seg[name]) for _, _, name, _ in SEGMENTS},
        "slo": {
            "metric": "T0-T2",
            "p95_ms_target": SLO_T02_P95_MS,
            "p99_ms_target": SLO_T02_P99_MS,
            "gate_min_orders": GATE_MIN_ORDERS,
        },
    }
    return json.dumps(out, indent=2, ensure_ascii=False)


def connect_db(dsn: str):
    if psycopg is None:
        print("ERROR: modul psycopg tidak ada. Jalankan dengan python api venv:",
              "~/fund2/api/.venv/bin/python scripts/latency_harness.py ...", file=sys.stderr)
        sys.exit(2)
    try:
        return psycopg.connect(dsn)
    except Exception as exc:
        print(f"ERROR: tidak bisa konek DB: {exc.__class__.__name__}", file=sys.stderr)
        sys.exit(2)


def fetch_reference_price(conn, symbol: str = "XAUUSD") -> float | None:
    """Harga referensi dari candle 1m terakhir di DB (None bila belum ada).

    Dipakai agar SL/TP dan tick sintetis mengikuti harga pasar saat ini;
    SL/TP hardcode akan ditolak risk gate begitu harga bergeser.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT close::float FROM candles "
            "WHERE symbol = %s AND timeframe = 'M1' "
            "ORDER BY ts DESC LIMIT 1",
            (symbol,))
        row = cur.fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------- HTTP

class Http:
    """Client HTTP kecil dengan cookie jar untuk sesi login."""

    def __init__(self) -> None:
        import http.cookiejar
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, method: str, url: str, body=None, headers=None,
                timeout: float = 30.0):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw.decode(errors="replace")[:200]
            return exc.code, parsed


# ------------------------------------------------------------- mode: report

def cmd_report(args) -> int:
    dsn = resolve("DATABASE_URL", args.dsn)
    if not dsn:
        print("ERROR: DATABASE_URL tidak ditemukan (--dsn / env / api/.env)",
              file=sys.stderr)
        return 2
    with connect_db(dsn) as conn:
        samples = fetch_latency_samples(conn, args.run)

    def in_period(lat: dict) -> bool:
        wall = lat.get("t0_wall")
        if not wall:
            return True
        try:
            t = datetime.fromisoformat(str(wall))
        except ValueError:
            return True
        if args.since:
            if t < datetime.fromisoformat(args.since):
                return False
        if args.until:
            if t > datetime.fromisoformat(args.until):
                return False
        return True

    traces = build_traces([s for s in samples if in_period(s["latency"])])
    period = f"{args.since or 'awal'} .. {args.until or 'sekarang'}"
    if args.json:
        out = report_json(traces, args.run)
    else:
        out = render_report(traces, args.run, period)
    print(out)
    if args.out:
        Path(args.out).write_text(out + "\n")
        print(f"\nDitulis: {args.out}")
    if args.gate:
        seg = compute_segments(traces)
        st = summarize(seg["T0-T2 SLO internal"])
        ok = (st["n"] > 0 and st["p95"] < SLO_T02_P95_MS
              and st["p99"] < SLO_T02_P99_MS
              and len(traces) >= GATE_MIN_ORDERS)
        return 0 if ok else 3
    return 0


# ------------------------------------------------------------ mode: measure

class SyntheticEA(threading.Thread):
    """Pengganti EA untuk QA: poll command, simulasi OrderSend, kirim result.

    T1 = response /bridge/poll diterima; T2 = sebelum "OrderSend";
    T3 = setelah "OrderSend" return. Delay disimulasikan agar distribusi
    latensi tidak degenerate; ganti dengan EA asli untuk data broker nyata.
    """

    def __init__(self, api: str, token: str, prep_ms: float,
                 broker_min_ms: float, broker_max_ms: float, seed: int | None,
                 fill_price: float = 2650.10):
        super().__init__(daemon=True, name="synthetic-ea")
        self.api = api
        self.token = token
        self.prep_s = prep_ms / 1000.0
        self.broker_min_ms = broker_min_ms
        self.broker_max_ms = broker_max_ms
        self.fill_price = fill_price
        self.rng = random.Random(seed)
        self.stop = threading.Event()
        self.marks: dict[str, dict] = {}
        self.http = Http()

    def run(self) -> None:
        headers = {"Authorization": f"Bearer {self.token}"}
        while not self.stop.is_set():
            try:
                status, body = self.http.request(
                    "GET", f"{self.api}/bridge/poll?timeout_s=2",
                    headers=headers, timeout=12.0)
                if status == 200 and isinstance(body, dict) and body.get("command_id"):
                    self._handle(body, headers)
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.2)

    def _handle(self, cmd: dict, headers: dict) -> None:
        oid = cmd.get("order_id") or cmd["command_id"]
        t1 = mono_us()
        time.sleep(self.prep_s)
        t2 = mono_us()
        # "OrderSend": dipanggil di sini; delay = latensi broker tersimulasi
        time.sleep(self.rng.uniform(self.broker_min_ms, self.broker_max_ms) / 1000.0)
        t3 = mono_us()
        price = self.fill_price
        status, resp = self.http.request(
            "POST", f"{self.api}/bridge/result",
            body={"command_id": cmd["command_id"], "status": "FILLED",
                  "ticket": self.rng.randint(10**6, 10**7), "price": price},
            headers=headers)
        self.marks[oid] = {
            "T1": t1, "T2": t2, "T3": t3,
            "result_http": status,
        }


def _tick_loop(api: str, token: str, stop: threading.Event,
               bid: float, ask: float) -> None:
    """Jaga tick tetap segar (risk gate menolak tick > 10 detik)."""
    http = Http()
    headers = {"Authorization": f"Bearer {token}"}
    while not stop.is_set():
        try:
            http.request("POST", f"{api}/bridge/tick",
                         body={"symbol": "XAUUSD", "bid": bid, "ask": ask},
                         headers=headers, timeout=10.0)
        except Exception:
            pass
        stop.wait(3.0)


def cmd_measure(args) -> int:
    dsn = resolve("DATABASE_URL", args.dsn)
    api = resolve("FUND2_API", args.api, DEFAULT_API)
    user = resolve("ADMIN_USER", args.username, "admin")
    password = resolve("ADMIN_PASSWORD", args.password)
    if args.password_file:
        p = Path(args.password_file)
        if not p.exists():
            print(f"ERROR: password file tidak ada: {p}", file=sys.stderr)
            return 2
        password = p.read_text().strip()
    if not dsn or not password:
        print("ERROR: butuh DATABASE_URL dan ADMIN_PASSWORD "
              "(--dsn/--password, env, atau api/.env)", file=sys.stderr)
        return 2

    with connect_db(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM settings")
            settings = {k: v for k, v in cur.fetchall()}
        token = settings.get("bridge_token")
        if not token:
            print("ERROR: settings.bridge_token kosong (API belum di-boot?)",
                  file=sys.stderr)
            return 2
        max_per_min = int(settings.get("max_orders_per_min", 10))
        ref_price = fetch_reference_price(conn)

    http = Http()
    status, body = http.request("POST", f"{api}/auth/login",
                                body={"username": user, "password": password})
    if status != 200:
        print(f"ERROR: login gagal (http {status})", file=sys.stderr)
        return 2
    status, me = http.request("GET", f"{api}/auth/me")
    csrf = (me or {}).get("csrf_token")
    if status != 200 or not csrf:
        print("ERROR: tidak dapat csrf token", file=sys.stderr)
        return 2

    pace = args.pace_s
    if pace is None:
        pace = max(0.5, 60.0 / max(max_per_min, 1) + 0.5)

    # Harga mengikuti pasar (candle 1m terakhir); SL/TP hardcode akan
    # ditolak risk gate ('BUY requires SL < price < TP') begitu harga geser.
    if ref_price:
        # SL/TP 5.0 USD (di atas min stop broker); order dipecah jadi burst
        # kecil + flatten antar burst oleh driver QA agar limit stress
        # portofolio tidak terlampaui saat posisi menumpuk.
        order_sl = round(ref_price - 5.0, 2)
        order_tp = round(ref_price + 5.0, 2)
        tick_bid = round(ref_price - 0.075, 2)
        tick_ask = round(ref_price + 0.075, 2)
    else:
        order_sl, order_tp = 2648.00, 2653.50
        tick_bid, tick_ask = 2650.00, 2650.15
    label = args.label or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S")

    # Koneksi khusus refresh harga: harga mengikuti pasar (candle M1 terakhir
    # dari feed real), SL/TP dihitung ulang tiap order agar tidak berbeda
    # dengan tick live yang dipakai risk gate.
    price_conn = connect_db(dsn)

    def current_sl_tp() -> tuple[float, float, float] | None:
        ref = fetch_reference_price(price_conn)
        if not ref:
            return None
        return round(ref - 5.0, 2), round(ref + 5.0, 2), ref

    stop_tick = threading.Event()
    threading.Thread(target=_tick_loop, args=(api, token, stop_tick,
                                              tick_bid, tick_ask),
                     daemon=True, name="tick-keepalive").start()

    ea = SyntheticEA(api, token, args.prep_delay_ms,
                     *args.broker_delay_ms, seed=args.seed,
                     fill_price=tick_ask)
    ea.start()

    pending: dict[str, dict] = {}   # order_id -> {"t0":, "wall":}
    terminal: dict[str, tuple[str, int]] = {}
    term_lock = threading.Lock()
    stop_watch = threading.Event()
    rejected = 0

    def watch_terminal() -> None:
        """Pantau commit FILLED/FAILED di DB berjalan concurren dengan order."""
        conn = connect_db(dsn)
        try:
            while not stop_watch.is_set():
                with term_lock:
                    todo = [oid for oid in pending if oid not in terminal]
                if todo:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id::text, status FROM orders "
                                    "WHERE id::text = ANY(%s)", (todo,))
                        for oid, st in cur.fetchall():
                            if st in TERMINAL_STATUSES:
                                with term_lock:
                                    terminal[oid] = (st, mono_us())
                stop_watch.wait(args.t4_poll_ms / 1000.0)
        finally:
            conn.close()

    watcher = threading.Thread(target=watch_terminal, daemon=True,
                               name="t4-watch")
    watcher.start()
    print(f"Measure run '{label}': {args.n} order, pace {pace:.2f}s, api {api}")

    for i in range(args.n):
        t0 = mono_us()
        wall = datetime.now(timezone.utc).isoformat()
        sl_tp = current_sl_tp()
        if sl_tp:
            order_sl, order_tp, ref_now = sl_tp
        status, body = http.request(
            "POST", f"{api}/orders",
            body={"symbol": "XAUUSD", "side": "BUY", "volume": 0.01,
                  "sl": order_sl, "tp": order_tp},
            headers={"x-csrf-token": csrf})
        if status == 201 and isinstance(body, dict) and body.get("id"):
            with term_lock:
                pending[body["id"]] = {"t0": t0, "wall": wall}
        else:
            rejected += 1
            reason = (body or {}).get("rejected_reasons") if isinstance(body, dict) else body
            print(f"  order {i + 1}/{args.n} ditolak (http {status}): {reason}")
        time.sleep(pace)

    deadline = time.monotonic() + args.timeout_s
    while len(terminal) < len(pending) and time.monotonic() < deadline:
        time.sleep(0.02)
    stop_watch.set()
    watcher.join(timeout=2.0)
    stop_tick.set()
    ea.stop.set()

    samples = []
    for oid, p in pending.items():
        marks = ea.marks.get(oid, {})
        st, t4 = terminal.get(oid, ("TIMEOUT", None))
        lat = {
            "clock": "mono_us",
            "T0": p["t0"],
            "t0_wall": p["wall"],
            "run": label,
            "order_id": oid,
            "mode": "harness-synthetic-ea",
            "terminal_status": st,
            "meta": {
                "n": args.n, "pace_s": round(pace, 3),
                "prep_delay_ms": args.prep_delay_ms,
                "broker_delay_ms": list(args.broker_delay_ms),
                "t4_poll_ms": args.t4_poll_ms,
                "result_http": marks.get("result_http"),
                "ref_price": ref_price, "sl": order_sl, "tp": order_tp,
            },
        }
        for point in ("T1", "T2", "T3"):
            if point in marks:
                lat[point] = marks[point]
        if t4 is not None:
            lat["T4"] = t4
        samples.append((oid, lat))

    if samples:
        with connect_db(dsn) as conn:
            with conn.transaction():
                for oid, lat in samples:
                    # Kontrak pembacaan report: payload = {"latency": {...}}
                    conn.execute(
                        "INSERT INTO order_events (order_id, from_status, to_status, "
                        "payload) VALUES (%s, NULL, %s, %s)",
                        (oid, LATENCY_STATUS, json.dumps({"latency": lat})))

    ok = sum(1 for _, lat in samples
             if all(p in lat for p in POINTS))
    reached = sum(1 for _, lat in samples
                  if lat.get("terminal_status") in TERMINAL_STATUSES)
    print(f"Selesai: {len(samples)} sampel ditulis ke order_events "
          f"(terminal T4: {reached}, lengkap T0..T4: {ok}, ditolak: {rejected}, "
          f"timeout: {len(pending) - len(terminal)})")

    with connect_db(dsn) as conn:
        traces = build_traces(fetch_latency_samples(conn, label))
    print()
    print(render_report(traces, label))
    # Skeleton: T1-T3 baru lengkap setelah instrumentasi EA (P1a). Run
    # dianggap sukses bila semua order mencapai status terminal (T4 tercatat)
    # dan tidak ada yang ditolak risk gate.
    return 0 if reached == len(pending) and not rejected else 1


# ----------------------------------------------------------- mode: selftest

def cmd_selftest(_args) -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    print("selftest: percentile")
    vals = list(range(1, 101))
    check("p50 dari 1..100 = 50.5", percentile(vals, 50) == 50.5)
    check("p95 dari 1..100 = 95.05", abs(percentile(vals, 95) - 95.05) < 1e-9)
    check("p99 dari 1..100 = 99.01", abs(percentile(vals, 99) - 99.01) < 1e-9)
    check("p0 = min", percentile(vals, 0) == 1)
    check("p100 = max", percentile(vals, 100) == 100)
    check("satu nilai", percentile([7], 95) == 7)
    check("kosong -> None", percentile([], 50) is None)

    print("selftest: mono_us")
    a, b = mono_us(), mono_us()
    check("monotonic naik", b >= a)
    check("tipe int", isinstance(a, int))

    print("selftest: trace")
    lat_full = {"clock": "mono_us", "T0": 1000, "T1": 2000, "T2": 3000,
                "T3": 5000, "T4": 6000, "terminal_status": "FILLED"}
    lat_partial = {"T0": 1000, "T1": 2100}
    samples = [
        {"order_id": "o1", "latency": lat_partial, "created_at": None},
        {"order_id": "o1", "latency": lat_full, "created_at": "x"},
        {"order_id": "o2", "latency": {"T0": 0, "T4": 9000}, "created_at": None},
    ]
    traces = build_traces(samples)
    check("pilih sampel terlengkap per order",
          trace_points(traces["o1"]).get("T3") == 5000)
    seg = compute_segments(traces)
    check("T0-T1 ms", seg["T0-T1 pickup EA"] == [1.0])
    check("T2-T3 ms", seg["T2-T3 broker OrderSend"] == [2.0])
    check("T3-T4 ms", seg["T3-T4 konfirmasi DB"] == [1.0])
    check("T0-T2 ms", seg["T0-T2 SLO internal"] == [2.0])
    check("T0-T4 ms", seg["T0-T4 total"] == [5.0, 9.0])
    comp = completeness(traces)
    check("lengkap = 1, parsial = 1",
          comp["complete"] == 1 and comp["partial"] == 1)

    print("selftest: laporan")
    text = render_report(traces, "unit-test")
    check("tabel p50/p95/p99", all(k in text for k in ("p50", "p95", "p99")))
    check("verdict SLO tampil", "SLO T0-T2" in text)
    check("gate 200 tampil", "/200 order" in text)
    js = json.loads(report_json(traces, "unit-test"))
    check("json valid + segmen ada",
          "T0-T2 SLO internal" in js["segments_ms"])
    check("nilai json sama dengan render",
          abs(js["segments_ms"]["T0-T2 SLO internal"]["p50"] - 2.0) < 1e-9)

    print(f"\nselftest: {len(failures)} gagal")
    return 1 if failures else 0


# ---------------------------------------------------------------------- CLI

def _pair(v: str) -> tuple[float, float]:
    a, b = v.split(":")
    return float(a), float(b)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Harness latensi T0..T4 Fund2 (PRD v2.1 bagian 6)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("report", help="laporan p50/p95/p99 dari order_events")
    p.add_argument("--dsn", default=None, help="Postgres DSN (default: api/.env)")
    p.add_argument("--run", default=None, help="filter label run")
    p.add_argument("--since", default=None, help="ISO8601, filter t0_wall")
    p.add_argument("--until", default=None, help="ISO8601, filter t0_wall")
    p.add_argument("--json", action="store_true", help="output JSON")
    p.add_argument("--out", default=None, help="tulis laporan ke file")
    p.add_argument("--gate", action="store_true",
                   help="exit 3 bila SLO/gate tidak terpenuhi (untuk CI)")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("measure",
                       help="dorong N order lewat API + synthetic EA, tulis sampel")
    p.add_argument("--api", default=None, help="base URL API (default 3110)")
    p.add_argument("--dsn", default=None, help="Postgres DSN (default: api/.env)")
    p.add_argument("--n", type=int, default=10, help="jumlah order")
    p.add_argument("--label", default=None, help="label run (default: run-<ts>)")
    p.add_argument("--pace-s", type=float, default=None,
                   help="jarak antar order (default: ikut max_orders_per_min)")
    p.add_argument("--broker-delay-ms", type=_pair, default=(100.0, 250.0),
                   help="delay OrderSend tersimulasi MIN:MAX (default 100:250)")
    p.add_argument("--prep-delay-ms", type=float, default=2.0)
    p.add_argument("--t4-poll-ms", type=float, default=5.0,
                   help="interval pantau commit FILLED di DB")
    p.add_argument("--timeout-s", type=float, default=120.0)
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None,
                   help="hindari: gunakan --password-file agar kredensial "
                        "tidak lewat command line")
    p.add_argument("--password-file", default=None,
                   help="baca password admin dari file ( direkomendasikan)")
    p.add_argument("--seed", type=int, default=None)
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("selftest", help="uji internals tanpa DB/API")
    p.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
