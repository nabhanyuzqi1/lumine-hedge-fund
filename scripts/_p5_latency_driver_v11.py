#!/usr/bin/env python3
"""Driver QA latensi P5 v11 (rerun gerbang 2 pasca-fix poll 0.05s): burst x 8
order demo sampai >= 200 sampel valid T0-T2, label v11.

Turunan _p5_latency_driver_v9.py (pola run v10); perubahan hanya label,
EVENT_SOURCE, dan kap BURSTS (headroom; driver berhenti di 200 sampel).

Perbaikan atas v8/v7 (yang jalurnya terkontaminasi):
  SyntheticEA persisten driver ikut bersaing menerima /bridge/poll sehingga
  mayoritas command diproses EA persisten, bukan EA harness -> sampel tanpa
  T1/T2/T3 (hanya T0+T4) -> T0-T2 tidak terukur. v7 dibuang (8 sampel).

Desain v9:
  - EA persisten HANYA hidup di antara burst (flatten + tunggu bersih +
    release halt). Sebelum burst: EA di-stop + join, lalu sleep window rate
    limit, baru harness measure --n 8 (EA harness menerima SEMUA command,
    T0..T4 lengkap untuk tiap order).
  - Resume: hitung sampel berlabel p5-latency-gate-v8% di order_events;
    lanjut burst berikutnya; selesai bila >= 200 sampel.
  - Dijalankan di bawah supervisor bash yang me-restart bila proses mati
    mendadak (scripts/_p5_latency_supervisor.sh).

TOTP digenerate in-process dari secret di DB; tidak pernah dicetak/log.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, "/home/tekka/fund2/api")
API = "http://127.0.0.1:3110"
ENV_PATH = "/home/tekka/fund2/api/.env"
LABEL_PREFIX = "p5-latency-gate-v11"
# Event driver ditandai source 'kanban:<card>' agar alerts watcher
# melewatinya (anti-spam Telegram owner, lihat app/alerts.py).
EVENT_SOURCE = "kanban:t_baeb3ce4"
BURSTS = 40
PER_BURST = 8
TARGET_SAMPLES = 200
HARNESS = "/home/tekka/fund2/scripts/latency_harness.py"
PY = "/home/tekka/fund2/api/.venv/bin/python"
RESOLVE_STUCK = "/home/tekka/fund2/scripts/_p5_resolve_stuck.py"
STATUS_FILE = "/home/tekka/fund2/scripts/p5_latency_v11_status.json"

env = {}
for line in open(ENV_PATH):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)
DSN = env["DATABASE_URL"]
# t_4651d431 (insiden 25 Nov 2026): driver QA WAJIB login pakai user QA
# khusus ber-role 'qa' (svc-qa-driver), BUKAN admin -- order dari user QA
# dikecualikan dari metrik anomaly harian (app/anomaly.py). Kredensial ada
# di api/.env (QA_DRIVER_USER / QA_DRIVER_PASSWORD); tanpa itu driver
# berhenti keras -- tidak ada fallback ke admin.
QA_USER = env["QA_DRIVER_USER"]
QA_PASSWORD = env["QA_DRIVER_PASSWORD"]

import psycopg  # noqa: E402
from app import totp as totp_mod  # noqa: E402

sys.path.insert(0, "/home/tekka/fund2/scripts")
import latency_harness as lh  # noqa: E402


def write_status(**kw):
    kw["ts"] = time.strftime("%H:%M:%S")
    with open(STATUS_FILE, "w") as f:
        json.dump(kw, f)


class Session:
    def __init__(self):
        self.cookies = {}
        self.csrf = None

    def _headers(self, extra=None):
        h = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}
        if self.csrf:
            h["x-csrf-token"] = self.csrf
        if extra:
            h.update(extra)
        return h

    def req(self, method, path, body=None, timeout=30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **self._headers()})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read().decode()
        else:
            status, raw = resp.status, resp.read().decode()
            for hdr in resp.headers.get_all("Set-Cookie") or []:
                kv = hdr.split(";", 1)[0]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    self.cookies[k.strip()] = v.strip()
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = raw
        return status, parsed


def totp_code(conn):
    cur = conn.cursor()
    cur.execute("SELECT totp_secret FROM users WHERE username=%s", (QA_USER,))
    row = cur.fetchone()
    assert row and row[0], "totp_secret user QA tidak ditemukan"
    return totp_mod.totp_at(row[0], None)


_2fa_ok_until = 0.0


def ensure_2fa(sess, conn):
    global _2fa_ok_until
    if time.time() < _2fa_ok_until - 30:
        return True
    for attempt in range(6):
        st, body = sess.req("POST", "/auth/2fa/challenge", body={"code": totp_code(conn)})
        if st == 200:
            _2fa_ok_until = time.time() + 4 * 60
            return True
        if st == 429:
            detail = str(body)
            m = re.search(r"retry in ([\d.]+)", detail)
            wait = float(m.group(1)) + 1 if m else 20
            print(f"  2fa 429, tunggu {wait:.0f}s", flush=True)
            time.sleep(wait)
        else:
            time.sleep(6)
    raise SystemExit("2fa challenge gagal berulang")


def count_samples(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM order_events "
                "WHERE payload->'latency'->>'run' LIKE %s", (LABEL_PREFIX + "%",))
    return cur.fetchone()[0]


def counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM orders WHERE status IN "
                "('RECEIVED','RISK_PASS','SENT','STUCK','PARTIALLY_FILLED')")
    pending = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM positions WHERE status='OPEN'")
    openp = cur.fetchone()[0]
    return pending, openp


def wait_clean(conn, timeout=240, label=""):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pending, openp = counts(conn)
        if pending == 0 and openp == 0:
            return True
        print(f"  [{label}] belum bersih (pending={pending}, open={openp}); tunggu 15s", flush=True)
        time.sleep(15)
    pending, openp = counts(conn)
    return pending == 0 and openp == 0


def flatten(sess, conn):
    ensure_2fa(sess, conn)
    st, body = sess.req("POST", "/kill-switch/flatten",
                        body={"confirm": True, "source": EVENT_SOURCE})
    n = (body or {}).get("flatten", {}).get("requested") if isinstance(body, dict) else None
    print(f"[{time.strftime('%H:%M:%S')}] flatten http {st} requested={n}", flush=True)
    return st


def halt_active(sess):
    st, ks = sess.req("GET", "/kill-switch")
    if st != 200 or not isinstance(ks, dict):
        return None
    state = ks.get("state") or ks
    if isinstance(state, dict):
        return bool(state.get("active"))
    return None


def release_halt(sess, conn):
    """Release kill-switch bila aktif; hanya bila state sudah bersih."""
    if not halt_active(sess):
        return True
    if not wait_clean(conn, timeout=20, label="pre-release"):
        print("  halt aktif tapi belum bersih; tidak di-release", flush=True)
        return False
    ensure_2fa(sess, conn)
    st, body = sess.req("POST", "/kill-switch/release",
                        body={"checklist_ack": True, "source": EVENT_SOURCE})
    print(f"[{time.strftime('%H:%M:%S')}] release kill-switch http {st} "
          f"{str(body)[:120]}", flush=True)
    time.sleep(2)
    return not halt_active(sess)


def ensure_clean_and_released(sess, conn, max_rounds=4):
    """flatten + resolve_stuck + wait_clean + release, sampai benar-benar siap."""
    for rounds in range(max_rounds):
        subprocess.run([PY, RESOLVE_STUCK], capture_output=True, text=True)
        pending, openp = counts(conn)
        if openp:
            flatten(sess, conn)
            time.sleep(8)
        if wait_clean(conn, timeout=200, label=f"r{rounds + 1}"):
            if release_halt(sess, conn):
                return True
        print(f"  rounds {rounds + 1}/{max_rounds} belum siap; ulangi flatten", flush=True)
    return False


def main():
    conn = psycopg.connect(DSN, autocommit=True)
    sess = Session()
    st, body = sess.req("POST", "/auth/login",
                        body={"username": QA_USER, "password": QA_PASSWORD})
    assert st == 200, f"login user QA gagal {st}"
    st, me = sess.req("GET", "/auth/me")
    if not (st == 200 and isinstance(me, dict) and me.get("csrf_token")):
        raise SystemExit(f"csrf gagal: {st} {me}")
    sess.csrf = me["csrf_token"]
    print(f"[{time.strftime('%H:%M:%S')}] login ok, csrf ok", flush=True)

    # Resume: sampel v11 yang sudah ada dihitung dari order_events.
    existing = count_samples(conn)
    print(f"[{time.strftime('%H:%M:%S')}] resume: {existing} sampel v11 existing", flush=True)
    if existing >= TARGET_SAMPLES:
        write_status(phase="done", bursts_done=min(existing // PER_BURST, BURSTS),
                     samples_total=existing, rejected_total=0, note="resume: target tercapai")
        print("SELESAI: target sampel sudah tercapai", flush=True)
        return

    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='bridge_token'")
    row = cur.fetchone()
    token = row[0] if row else None
    cur.execute("SELECT close_price FROM positions ORDER BY open_time DESC LIMIT 1")
    row = cur.fetchone()
    fill_price = float(row[0]) if row and row[0] else 3554.0

    def start_ea():
        ea = lh.SyntheticEA(API, token, 2.0, 100.0, 250.0, seed=None, fill_price=fill_price)
        ea.start()
        return ea

    # EA persisten HANYA untuk fase antar burst (flatten).
    ea = start_ea()
    print(f"[{time.strftime('%H:%M:%S')}] synthetic EA antar-burst start", flush=True)

    # pre-flight: pastikan mulai dari state bersih + halt released
    if not ensure_clean_and_released(sess, conn):
        write_status(phase="preflight_failed", samples_total=existing)
        raise SystemExit("pre-flight gagal: state tidak kunjung bersih / halt tak ter-release")
    write_status(phase="running", bursts_done=existing // PER_BURST, samples_total=existing)
    print(f"[{time.strftime('%H:%M:%S')}] pre-flight OK; "
          f"lanjut burst {existing // PER_BURST + 1}/{BURSTS}", flush=True)

    t_start = time.time()
    total_samples = existing
    total_rejected = 0
    full_reject = 0
    bursts_done = existing // PER_BURST
    deadline = t_start + 150 * 60  # batas total 150 menit per proses
    b = bursts_done
    while total_samples < TARGET_SAMPLES and b < BURSTS:
        if time.monotonic() > deadline:
            print("BATAS WAKTU total tercapai; berhenti (supervisor akan melanjutkan)", flush=True)
            break
        b += 1
        label = f"{LABEL_PREFIX}-b{b:02d}"
        if not ensure_clean_and_released(sess, conn):
            print(f"[{time.strftime('%H:%M:%S')}] burst {b}: state tidak siap; lewati", flush=True)
            full_reject += 1
            if full_reject >= 3:
                print("ABORT: 3 siklus gagal bersih", flush=True)
                break
            continue
        # EA persisten di-stop: selama burst, SATU-SATunya consumer /bridge/poll
        # harus EA harness agar T1/T2/T3 tercatat untuk semua order.
        ea.stop.set()
        ea.join(timeout=10)
        # order close dari flatten ikut dihitung rate limit; tunggu window bersih
        time.sleep(65)
        # Harness resolve kredensial dari env ADMIN_USER/ADMIN_PASSWORD
        # (kontrak latency_harness.py); diisi kredensial user QA agar order
        # yang dibuat harness tercatat sebagai user QA (bukan admin).
        child_env = dict(os.environ)
        child_env["ADMIN_USER"] = QA_USER
        child_env["ADMIN_PASSWORD"] = QA_PASSWORD
        r = subprocess.run(
            [PY, HARNESS, "measure", "--n", str(PER_BURST), "--label", label],
            capture_output=True, text=True, timeout=600, cwd="/home/tekka/fund2",
            env=child_env)
        out = r.stdout.strip().splitlines()
        done = [l for l in out if l.startswith("Selesai:")]
        print(f"[{time.strftime('%H:%M:%S')}] burst {b}/{BURSTS} ({label}) exit={r.returncode} "
              f"{done[0] if done else 'TANPA RINGKASAN'}", flush=True)
        m = re.search(r"ditolak:\s*(\d+)", done[0]) if done else None
        sampel = re.search(r"(\d+) sampel ditulis", done[0]) if done else None
        nsamp = int(sampel.group(1)) if sampel else 0
        nrej = int(m.group(1)) if m else PER_BURST
        total_samples = count_samples(conn)
        total_rejected += nrej
        bursts_done = b
        write_status(phase="running", bursts_done=b, samples_total=total_samples,
                     rejected_total=total_rejected)
        print(f"   total sampel v11: {total_samples}/{TARGET_SAMPLES}", flush=True)
        if m and nrej >= PER_BURST and nsamp == 0:
            full_reject += 1
            print(f"   burst {b} SEMUA order ditolak ({nrej}/{PER_BURST}); "
                  f"strike {full_reject}/2", flush=True)
            if full_reject >= 2:
                print("ABORT: gate memblokir semua order -- stop, jangan spam.", flush=True)
                break
        else:
            full_reject = 0
        if r.returncode != 0:
            for l in out:
                if "ditolak" in l:
                    print("   ", l, flush=True)
            if r.stderr.strip():
                print("STDERR:", r.stderr.strip()[-500:], flush=True)
        # EA baru untuk flatten sesudah burst
        ea = start_ea()
        flatten(sess, conn)

    ea.stop.set()
    final_samples = count_samples(conn)
    print(f"SELESAI total waktu {time.time()-t_start:.0f}s; "
          f"burst={bursts_done} sampel={final_samples} ditolak={total_rejected}", flush=True)
    write_status(phase="done" if final_samples >= TARGET_SAMPLES else "incomplete",
                 bursts_done=bursts_done, samples_total=final_samples,
                 rejected_total=total_rejected,
                 elapsed_s=round(time.time() - t_start))


if __name__ == "__main__":
    main()
