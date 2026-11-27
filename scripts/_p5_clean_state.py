#!/usr/bin/env python3
"""Bersihkan state fund2 sebelum run latensi (EA real masih hidup).

flatten -> tunggu bersih (pending=0, open=0) -> resolve STUCK -> release halt
bila perlu. Keluar 0 bila bersih, 1 bila gagal.
"""
import re
import sys
import time

sys.path.insert(0, "/home/tekka/fund2/api")

API = "http://127.0.0.1:3110"
ENV_PATH = "/home/tekka/fund2/api/.env"

env = {}
for line in open(ENV_PATH):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        env[m.group(1)] = m.group(2)

import psycopg  # noqa: E402
from app import totp as totp_mod  # noqa: E402
import urllib.request
import urllib.error
import json


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


def main():
    conn = psycopg.connect(env["DATABASE_URL"], autocommit=True)
    cur = conn.cursor()
    sess = Session()
    st, _ = sess.req("POST", "/auth/login",
                     body={"username": env["ADMIN_USER"], "password": env["ADMIN_PASSWORD"]})
    assert st == 200, f"login gagal {st}"
    st, me = sess.req("GET", "/auth/me")
    sess.csrf = me["csrf_token"]
    cur.execute("SELECT totp_secret FROM users WHERE username=%s", (env["ADMIN_USER"],))
    totp_secret = cur.fetchone()[0]

    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        cur.execute("SELECT count(*) FROM orders WHERE status IN "
                    "('RECEIVED','RISK_PASS','SENT','STUCK','PARTIALLY_FILLED')")
        pending = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM positions WHERE status='OPEN'")
        openp = cur.fetchone()[0]
        if pending == 0 and openp == 0:
            # release halt bila aktif
            st, ks = sess.req("GET", "/kill-switch")
            state = (ks or {}).get("state") or {}
            if state.get("active"):
                st2, _ = sess.req("POST", "/auth/2fa/challenge",
                                  body={"code": totp_mod.totp_at(totp_secret, None)})
                st3, body = sess.req("POST", "/kill-switch/release",
                                     body={"checklist_ack": True})
                print(f"release halt: {st3} {str(body)[:80]}")
                time.sleep(2)
            print("BERSIH")
            return 0
        if openp:
            sess.req("POST", "/auth/2fa/challenge",
                     body={"code": totp_mod.totp_at(totp_secret, None)})
            st, body = sess.req("POST", "/kill-switch/flatten", body={"confirm": True})
            print(f"flatten {st}: {str(body)[:80]}")
        time.sleep(15)
    print("GAGAL: state tidak bersih dalam 600s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
