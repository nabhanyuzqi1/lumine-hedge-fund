#!/usr/bin/env python3
"""Statistik latensi gabungan run p5-latency-gate-v7 (semua burst).

Membaca order_events.payload->'latency' untuk run berprefix p5-latency-gate-v7,
menggabungkan per order (sampel terlengkap menang, sama dengan build_traces),
lalu menghitung p50/p95/p99/max per segmen T0-T1, T1-T2, T2-T3, T3-T4, T0-T2,
T0-T4 dalam ms. Output JSON + tabel markdown siap tempel ke laporan.
"""
import json
import re
import statistics
import sys

env = {}
for line in open("/home/tekka/fund2/api/.env"):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)

import psycopg

# PREFIX opsional via argv[1]; default v10 (kompatibilitas mundur).
# Contoh: .venv/bin/python scripts/_p5_latency_stats.py p5-latency-gate-v11
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "p5-latency-gate-v10"
STATS_FILE = "/home/tekka/fund2/scripts/p5_latency_%s_stats.json" % PREFIX.replace(
    "p5-latency-gate-", "")
TERMINAL = {"FILLED", "FAILED", "REJECTED", "CLOSED"}


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


conn = psycopg.connect(env["DATABASE_URL"], autocommit=True)
cur = conn.cursor()
cur.execute(
    "SELECT payload->'latency' AS lat FROM order_events "
    "WHERE payload->'latency'->>'run' LIKE %s ORDER BY created_at", (PREFIX + "%",))
rows = [r[0] for r in cur.fetchall()]

best = {}
for lat in rows:
    oid = lat["order_id"]
    pts = sum(1 for p in ("T0", "T1", "T2", "T3", "T4") if p in lat)
    term = 1 if lat.get("terminal_status") in TERMINAL else 0
    key = (pts, term)
    if oid not in best or key >= best[oid][0]:
        best[oid] = (key, lat)

# Gabungkan titik yang hilang dari rekaman lain untuk order yang sama
# (mis. T1/T2/T3 tercatat EA lain) -- T0/T4 selalu dari rekaman terlengkap.
samples = []
for oid in best:
    recs = [lat for lat in rows if lat["order_id"] == oid]
    primary = best[oid][1]
    merged = dict(primary)
    for r in recs:
        for p in ("T1", "T2", "T3", "T4"):
            if p not in merged and p in r:
                merged[p] = r[p]
    samples.append(merged)
print(f"orders unik: {len(samples)}")

seg_names = [("T0", "T1"), ("T1", "T2"), ("T2", "T3"), ("T3", "T4"),
             ("T0", "T2"), ("T0", "T4")]
out = {}
for a, b in seg_names:
    vals = []
    for lat in samples:
        if a in lat and b in lat:
            vals.append((lat[b] - lat[a]) / 1000.0)  # us -> ms
    vals.sort()
    if not vals:
        continue
    seg = {
        "n": len(vals),
        "p50": round(pct(vals, 50), 1),
        "p95": round(pct(vals, 95), 1),
        "p99": round(pct(vals, 99), 1),
        "max": round(vals[-1], 1),
        "mean": round(statistics.mean(vals), 1),
    }
    out[f"{a}-{b}"] = seg
    print(f"{a}-{b}: n={seg['n']} p50={seg['p50']} p95={seg['p95']} "
          f"p99={seg['p99']} max={seg['max']} mean={seg['mean']}")

t02 = out.get("T0-T2", {})
verdict = "PASS" if t02 and t02["p95"] < 300 else "FAIL"
print(f"T0-T2 p95 {t02.get('p95')} ms < 300 ms -> {verdict}")

term_status = {}
for lat in samples:
    st = lat.get("terminal_status", "TIMEOUT")
    term_status[st] = term_status.get(st, 0) + 1
print("terminal_status:", term_status)

with open(STATS_FILE, "w") as f:
    json.dump({"prefix": PREFIX, "orders": len(samples), "segments": out,
               "t02_verdict": verdict, "terminal_status": term_status}, f, indent=1)
print("ditulis:", STATS_FILE)
