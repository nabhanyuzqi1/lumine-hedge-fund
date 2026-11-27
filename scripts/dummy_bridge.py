#!/usr/bin/env python3
"""Dummy bridge untuk EA v0 (kartu FUND2-P0: heartbeat + tick batch + HMAC).

Stand-in ringan fund2-api di http://127.0.0.1:3110/bridge khusus P0:
menerima request EA v0 yang ditandatangani HMAC-SHA256, mencatat
heartbeat & tick (spread) ke file JSONL, dan menyediakan /_stats untuk
inspeksi. TIDAK untuk produksi: tanpa DB, tanpa order, tanpa TLS.

Auth (PRD v2.1 §7, sama dengan EA v0 LumineEA.mq5):
  Header:
    X-Fund2-Timestamp : unix epoch detik, toleransi +-5 dtk dari server
    X-Fund2-Nonce     : hex acak, wajib unik (dipakai sekali)
    X-Fund2-Signature : hex HMAC-SHA256(secret, string_to_sign)
  string_to_sign:
    ts \\n nonce \\n METHOD \\n path-with-query \\n sha256_hex(body)
  Secret diambil dari env FUND2_HMAC_SECRET (atau --secret), BUKAN repo.

Endpoint:
  GET  /health                 -> liveness, tanpa auth
  GET  /_stats                 -> counter + data terakhir (debug, loopback)
  GET  /bridge/poll            -> "null" (dummy tidak punya command)
  POST /bridge/heartbeat       -> catat heartbeat
  POST /bridge/tick            -> catat tick batch (symbol, ts, bid, ask, spread)
  POST /bridge/result          -> terima & catat (tanpa proses)
  POST /bridge/positions       -> terima & catat (tanpa proses)

Output default: <out-dir>/{heartbeats,ticks,rejected}.jsonl
(out-dir default: ~/fund2/data/ea_v0 — di luar git? tidak, masih di repo;
 gunakan --out-dir lain bila tidak ingin tercatat di repo. File jsonl
 ditambahkan ke .gitignore fund2 untuk data runtime.)

Contoh:
  FUND2_HMAC_SECRET=$(openssl rand -hex 32) python3 scripts/dummy_bridge.py
  python3 scripts/dummy_bridge.py --port 3199 --secret <hex32>
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TS_TOLERANCE_S = 5          # PRD §7: toleransi jam 5 detik
NONCE_TTL_S = 2 * TS_TOLERANCE_S + 1  # replay window > toleransi
MAX_BODY = 4 * 1024 * 1024


class BridgeState:
    def __init__(self, secret: str, out_dir: str):
        self.secret = secret.encode("utf-8")
        self.out_dir = out_dir
        self.lock = threading.Lock()
        self.nonces: dict[str, float] = {}
        self.started = time.time()
        self.counters = {
            "heartbeats": 0, "ticks": 0, "tick_batches": 0,
            "results": 0, "positions": 0, "polls": 0, "rejected": 0,
        }
        self.last_heartbeat: dict | None = None
        self.last_ticks: list[dict] = []
        self.rejected_log: list[dict] = []

    # ── recording ────────────────────────────────────────────────────────
    def _append(self, name: str, obj: dict) -> None:
        path = os.path.join(self.out_dir, name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")

    def record_heartbeat(self, body: dict) -> None:
        rec = {"received_at": round(time.time(), 3), **body}
        with self.lock:
            self.counters["heartbeats"] += 1
            self.last_heartbeat = rec
        self._append("heartbeats.jsonl", rec)

    def record_ticks(self, symbol: str, ticks: list[dict], candles: int) -> None:
        now = round(time.time(), 3)
        with self.lock:
            self.counters["tick_batches"] += 1
            self.counters["ticks"] += len(ticks)
            for t in ticks:
                self.last_ticks.append({"symbol": symbol, "received_at": now, **t})
            self.last_ticks = self.last_ticks[-50:]
        for t in ticks:
            self._append("ticks.jsonl", {"symbol": symbol, "received_at": now, **t})
        if candles:
            self._append("ticks.jsonl", {"symbol": symbol, "received_at": now,
                                         "candles_only": candles})

    def record_raw(self, kind: str, body: dict) -> None:
        with self.lock:
            self.counters[kind] += 1
        self._append(f"{kind}.jsonl", {"received_at": round(time.time(), 3), **body})

    def record_poll(self) -> None:
        with self.lock:
            self.counters["polls"] += 1

    def record_rejected(self, reason: str, path: str) -> dict:
        rec = {"received_at": round(time.time(), 3), "path": path, "reason": reason}
        with self.lock:
            self.counters["rejected"] += 1
            self.rejected_log.append(rec)
            self.rejected_log = self.rejected_log[-50:]
        self._append("rejected.jsonl", rec)
        return rec

    # ── HMAC validation ──────────────────────────────────────────────────
    def check_hmac(self, method: str, path: str, body: bytes, headers) -> str | None:
        """Return None bila valid, else alasan penolakan."""
        ts = headers.get("X-Fund2-Timestamp", "")
        nonce = headers.get("X-Fund2-Nonce", "")
        sig = headers.get("X-Fund2-Signature", "")
        if not ts or not nonce or not sig:
            return "missing X-Fund2-* headers"
        try:
            ts_val = int(ts)
        except ValueError:
            return "timestamp not an integer"
        if abs(time.time() - ts_val) > TS_TOLERANCE_S:
            return "timestamp outside +-5s tolerance"
        if not (8 <= len(nonce) <= 64) or any(c not in "0123456789abcdef" for c in nonce.lower()):
            return "nonce not hex"
        now = time.time()
        with self.lock:
            # purge expired nonces lazily
            if len(self.nonces) > 4096:
                self.nonces = {n: exp for n, exp in self.nonces.items() if exp > now}
            if nonce in self.nonces and self.nonces[nonce] > now:
                return "nonce replayed"
            self.nonces[nonce] = now + NONCE_TTL_S
        body_hash = hashlib.sha256(body).hexdigest()
        sts = "\n".join([ts, nonce, method, path, body_hash]).encode("utf-8")
        expected = hmac.new(self.secret, sts, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig.lower()):
            return "bad signature"
        return None

    def stats(self) -> dict:
        with self.lock:
            return {
                "ok": True,
                "started_at": round(self.started, 3),
                "uptime_s": round(time.time() - self.started, 1),
                **self.counters,
                "last_heartbeat": self.last_heartbeat,
                "last_ticks": self.last_ticks[-5:],
                "recent_rejected": self.rejected_log[-5:],
            }


def make_handler(state: BridgeState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "fund2-dummy-bridge/0.1"

        def log_message(self, format, *args):  # noqa: A002 — signature base class
            sys.stdout.write("[dummy] %s\n" % (format % args))
            sys.stdout.flush()

        def _send(self, code: int, obj) -> None:
            payload = obj if isinstance(obj, (bytes, str)) else json.dumps(obj)
            data = payload.encode("utf-8") if isinstance(payload, str) else payload
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return b""
            if length > MAX_BODY:
                raise ValueError("body too large")
            return self.rfile.read(length)

        # ── GET ──────────────────────────────────────────────────────────
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/health":
                self._send(200, {"ok": True, "service": "dummy-bridge"})
                return
            if path == "/_stats":
                self._send(200, state.stats())
                return
            if path == "/bridge/poll":
                err = state.check_hmac("GET", self.path, b"", self.headers)
                if err:
                    self._send(401, {"ok": False, "error": err})
                    state.record_rejected(err, self.path)
                    return
                state.record_poll()
                self._send(200, "null")
                return
            self._send(404, {"ok": False, "error": "not found"})

        # ── POST ─────────────────────────────────────────────────────────
        def do_POST(self):
            path = self.path.split("?")[0]
            try:
                body = self._read_body()
            except ValueError:
                self._send(413, {"ok": False, "error": "body too large"})
                return
            err = state.check_hmac("POST", self.path, body, self.headers)
            if err:
                state.record_rejected(err, self.path)
                self._send(401, {"ok": False, "error": err})
                return
            try:
                parsed = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"ok": False, "error": "invalid JSON body"})
                return

            if path == "/bridge/heartbeat":
                state.record_heartbeat(parsed if isinstance(parsed, dict) else {"value": parsed})
                self._send(200, {"ok": True})
            elif path == "/bridge/tick":
                if not isinstance(parsed, dict):
                    self._send(400, {"ok": False, "error": "tick body must be object"})
                    return
                ticks = parsed.get("ticks") or []
                candles = parsed.get("candles") or []
                state.record_ticks(parsed.get("symbol", ""), ticks, len(candles))
                self._send(200, {"ok": True, "recorded": len(ticks), "candles": len(candles)})
            elif path == "/bridge/result":
                state.record_raw("results", parsed if isinstance(parsed, dict) else {})
                self._send(200, {"ok": True, "duplicate": False})
            elif path == "/bridge/positions":
                state.record_raw("positions", parsed if isinstance(parsed, dict) else {})
                self._send(200, {"ok": True})
            else:
                self._send(404, {"ok": False, "error": "not found"})

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="Dummy bridge EA v0 (HMAC, P0)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3110)
    ap.add_argument("--secret", default=os.environ.get("FUND2_HMAC_SECRET", ""),
                    help="default: env FUND2_HMAC_SECRET")
    ap.add_argument("--out-dir",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "data", "ea_v0"))
    args = ap.parse_args()

    if not args.secret:
        print("ERROR: secret kosong. Set env FUND2_HMAC_SECRET atau --secret.",
              file=sys.stderr)
        return 2
    if len(args.secret) < 16:
        print("ERROR: secret terlalu pendek (min 16 char).", file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    state = BridgeState(args.secret, out_dir)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"[dummy] bridge listening on http://{args.host}:{args.port}/bridge "
          f"(out: {out_dir})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[dummy] shutdown", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
