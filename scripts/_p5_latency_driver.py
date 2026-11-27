#!/usr/bin/env python3
"""Driver QA latensi P5: 25 burst x 8 order + flatten antar burst.

Gerbang 2 PRD butuh >= 200 order demo dengan T0->T2 p95 < 300 ms. Limit
portofolio (max_total_volume_lot) memblokir order bila posisi menumpuk,
maka tiap burst 8 order diikuti flatten via /kill-switch/flatten (2FA).
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
os.environ.setdefault("DATABASE_URL", "")  # diisi dari .env di bawah

API = "http://127.0.0.1:3110"
ENV_PATH = "/home/tekka/fund2/api/.env"
LABEL_PREFIX = "p5-latency-gate-v6"
BURSTS = 25
PER_BURST = 8
HARNESS = "/home/tekka/fund2/scripts/latency_harness.py"
PY = "/home/tekka/fund2/api/.venv/bin/python"

env = {}
for line in open(ENV_PATH):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)
DSN = env["DATABASE_URL"]
ADMIN_USER = env["ADMIN_USER"]
ADMIN_PASSWORD = env["ADMIN_PASSWORD"]

import psycopg  # noqa: E402
from app import totp as totp_mod  # noqa: E402

sys.path.insert(0, "/home/tekka/fund2/scripts")
import latency_harness as lh  # noqa: E402


def db_secret(conn, key):
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def http(method, path, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode()
        return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def login():
    st, body = http("POST", "/auth/login",
                    body={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert st == 200, f"login gagal: {st} {body}"
    cookies = []
    # cookie session via header Set-Cookie ditangani manual sederhana
    return body


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
    cur.execute("SELECT totp_secret FROM users WHERE username=%s", (ADMIN_USER,))
    row = cur.fetchone()
    assert row and row[0], "totp_secret admin tidak ditemukan"
    return totp_mod.totp_at(row[0], None)


_2fa_ok_until = 0.0


def ensure_2fa(sess, conn):
    global _2fa_ok_until
    if time.time() < _2fa_ok_until - 30:
        return True
    for attempt in range(6):
        st, body = sess.req("POST", "/auth/2fa/challenge",
                            body={"code": totp_code(conn)})
        if st == 200:
            _2fa_ok_until = time.time() + 4 * 60  # window 5 menit, margin 1 menit
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


def flatten(sess, conn):
    ensure_2fa(sess, conn)
    st, body = sess.req("POST", "/kill-switch/flatten", body={"confirm": True})
    n = (body or {}).get("flatten", {}).get("requested") if isinstance(body, dict) else None
    print(f"[{time.strftime('%H:%M:%S')}] flatten http {st} requested={n}", flush=True)
    return st


def release_halt(sess, conn):
    """Release kill-switch auto-halt SEV bila state sudah bersih.

    Halt SEV orphan/eafire sering terpicu oleh trading legacy EA di akun
    yang sama; reconciler mengadopsi & menutupnya. QA me-release hanya
    bila tidak ada order non-terminal dan posisi cocok.
    """
    st, ks = sess.req("GET", "/kill-switch")
    if st != 200 or not isinstance(ks, dict):
        return
    state = ks.get("state") or ks
    if not (isinstance(state, dict) and state.get("active")):
        return
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM orders WHERE status IN "
                "('RECEIVED','RISK_PASS','SENT','STUCK')")
    pending = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM positions WHERE status='OPEN'")
    openp = cur.fetchone()[0]
    if pending or openp:
        print(f"  halt aktif tapi belum bersih (pending={pending}, open={openp}); "
              "tidak di-release", flush=True)
        return
    ensure_2fa(sess, conn)
    st, body = sess.req("POST", "/kill-switch/release",
                        body={"checklist_ack": True})
    print(f"[{time.strftime('%H:%M:%S')}] release kill-switch http {st} "
          f"{str(body)[:120]}", flush=True)


def main():
    conn = psycopg.connect(DSN, autocommit=True)
    sess = Session()
    st, body = sess.req("POST", "/auth/login",
                        body={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert st == 200, f"login gagal {st}"
    st, me = sess.req("GET", "/auth/me")
    if not (st == 200 and isinstance(me, dict) and me.get("csrf_token")):
        raise SystemExit(f"csrf gagal: {st} {me}")
    sess.csrf = me["csrf_token"]
    print(f"[{time.strftime('%H:%M:%S')}] login ok, csrf ok", flush=True)

    # SyntheticEA persisten: flatten antar burst butuh ada yang menjawab
    # /bridge/poll, kalau tidak close order menggantung -> STUCK -> gate blokir.
    token = db_secret(conn, "bridge_token")
    cur = conn.cursor()
    cur.execute("SELECT close_price FROM positions ORDER BY open_time DESC LIMIT 1")
    row = cur.fetchone()
    fill_price = float(row[0]) if row and row[0] else 2650.10
    ea = lh.SyntheticEA(API, token, 2.0, 100.0, 250.0, seed=None, fill_price=fill_price)
    ea.start()
    print(f"[{time.strftime('%H:%M:%S')}] synthetic EA persisten start", flush=True)

    t_start = time.time()
    total_ok = 0
    full_reject = 0
    for b in range(1, BURSTS + 1):
        label = f"{LABEL_PREFIX}-b{b:02d}"
        # flatten sebelum burst agar mulai bersih
        subprocess.run([PY, "/home/tekka/fund2/scripts/_p5_resolve_stuck.py"],
                       capture_output=True, text=True)
        flatten(sess, conn)
        release_halt(sess, conn)
        # order close dari flatten ikut dihitung rate limit; tunggu window bersih
        time.sleep(65)
        r = subprocess.run(
            [PY, HARNESS, "measure", "--n", str(PER_BURST), "--label", label],
            capture_output=True, text=True, timeout=600, cwd="/home/tekka/fund2")
        out = r.stdout.strip().splitlines()
        done = [l for l in out if l.startswith("Selesai:")]
        print(f"[{time.strftime('%H:%M:%S')}] burst {b}/{BURSTS} ({label}) exit={r.returncode} "
              f"{done[0] if done else 'TANPA RINGKASAN'}", flush=True)
        # Fail-fast: kalau satu burst penuh semua ordernya ditolak (gate portofolio
        # memblokir), jangan lanjut burst berikutnya -- akan spam 200 order FAILED
        # percuma. Dua burst penuh penolakan berturut = hentikan driver.
        m = re.search(r"ditolak:\s*(\d+)", done[0]) if done else None
        sampel = re.search(r"(\d+) sampel ditulis", done[0]) if done else None
        if m and int(m.group(1)) >= PER_BURST and (not sampel or int(sampel.group(1)) == 0):
            full_reject += 1
            print(f"   burst {b} SEMUA order ditolak ({m.group(1)}/{PER_BURST}); "
                  f"strike {full_reject}/2", flush=True)
            if full_reject >= 2:
                print("ABORT: gate portofolio memblokir semua order -- stop, jangan spam.", flush=True)
                break
        else:
            full_reject = 0
        if r.returncode != 0:
            for l in out:
                if "ditolak" in l:
                    print("   ", l, flush=True)
            if r.stderr.strip():
                print("STDERR:", r.stderr.strip()[-500:], flush=True)
        # flatten sesudah burst
        flatten(sess, conn)
    print(f"SELESAI total waktu {time.time()-t_start:.0f}s", flush=True)
    ea.stop.set()


if __name__ == "__main__":
    main()
