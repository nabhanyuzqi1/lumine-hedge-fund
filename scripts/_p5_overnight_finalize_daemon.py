#!/usr/bin/env python3
"""Finalizer daemon run latensi P5 (detached).

Tunggu status p5_latency_v10_status.json phase=done && samples>=200 (maks 4
jam), lalu: restore bridge_token asli -> start service MT5 -> hitung statistik
latensi -> patch placeholder {{...}} di docs/QA_P5_cutover.md -> tulis marker
scripts/p5_overnight_done.log. Idempoten: bila marker sudah ada, keluar.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/tekka/fund2/scripts")

BASE = "/home/tekka/fund2"
STATUS = f"{BASE}/scripts/p5_latency_v10_status.json"
DONE_MARKER = f"{BASE}/scripts/p5_overnight_done.log"
LOG = f"{BASE}/scripts/p5_overnight.log"
PY = f"{BASE}/api/.venv/bin/python"
REPORT = f"{BASE}/docs/QA_P5_cutover.md"


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[finalize {time.strftime('%H:%M:%S')}] {msg}\n")


def main():
    if os.path.exists(DONE_MARKER):
        log("sudah selesai sebelumnya; keluar")
        return 0
    deadline = time.monotonic() + 4 * 3600
    done = False
    st = {}
    while time.monotonic() < deadline:
        try:
            st = json.load(open(STATUS))
        except Exception:
            st = {}
        if st.get("phase") == "done" and st.get("samples_total", 0) >= 200:
            done = True
            break
        if st.get("phase") == "preflight_failed":
            log("pre-flight gagal; hentikan finalizer")
            return 1
        time.sleep(60)
    if not done:
        log("TIMEOUT menunggu run selesai (4 jam); keluar tanpa finalisasi")
        return 1
    log(f"run selesai: {st}")

    # 1. restore token asli (EA real kembali bisa poll)
    r = subprocess.run([PY, f"{BASE}/scripts/_p5_bridge_token.py", "restore"],
                       capture_output=True, text=True)
    log(f"restore token: {r.stdout.strip()} {r.stderr.strip()[:200]}")

    # 2. start MT5
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{os.getuid()}/bus"
    r = subprocess.run(["systemctl", "--user", "start", "lumine-hedge-fund-mt5.service"],
                       capture_output=True, text=True)
    time.sleep(8)
    log(f"start mt5: rc={r.returncode} {r.stderr.strip()[:200]}")

    # 3. statistik latensi
    r = subprocess.run([PY, f"{BASE}/scripts/_p5_latency_stats.py"],
                       capture_output=True, text=True)
    log(f"stats:\n{r.stdout.strip()}\n{r.stderr.strip()[:400]}")

    # 4. patch placeholder laporan dari stats JSON
    try:
        stats = json.load(open(f"{BASE}/scripts/p5_latency_v10_stats.json"))
        t02 = stats["segments"]["T0-T2"]
        rep = open(REPORT).read()
        verdict = "LULUS" if t02["p95"] < 300 else "GAGAL"
        repl = {
            "{{T02_P50}}": f"{t02['p50']:.1f}",
            "{{T02_P95}}": f"{t02['p95']:.1f}",
            "{{T02_P99}}": f"{t02['p99']:.1f}",
            "{{T02_MAX}}": f"{t02['max']:.1f}",
            "{{T02_VERDICT}}": verdict,
            "{{REJECTED}}": str(st.get("rejected_total", "-")),
            "{{TIMEOUT}}": str(stats.get("terminal_status", {}).get("TIMEOUT", 0)),
        }
        for k, v in repl.items():
            rep = rep.replace(k, v)
        with open(REPORT, "w") as f:
            f.write(rep)
        log(f"laporan dipatch: T0-T2 p95={t02['p95']} -> {verdict}")
    except Exception as e:
        log(f"patch laporan GAGAL: {e}")

    with open(DONE_MARKER, "w") as f:
        f.write(f"selesai {time.strftime('%F %T')}\n{json.dumps(st)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
