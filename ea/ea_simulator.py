#!/usr/bin/env python3
"""Simulator EA v0 — replika lapisan HTTP LumineEA.mq5 v5.00 (P0).

Bukan produk: alat verifikasi kontrak untuk dummy_bridge.py saat runtime
MT5 tidak tersedia (live terminal tidak boleh disentuh dari kartu ini).
Meniru persis:
  - canonical string & header HMAC (sama dengan SignHeaders di MQL5)
  - heartbeat tiap heartbeat_sec detik (default 2, PRD 5.5)
  - tick batch: tiap tick masuk buffer, di-flush tiap tick_batch_ms
    (default 250, PRD 5.1) atau saat buffer penuh; tiap item berisi
    {ts(ms), bid, ask, spread=ask-bid}
  - poll GET /bridge/poll?timeout_s=0 tiap poll_ms (default 100)

Pemakaian:
  python3 ea_simulator.py --url http://127.0.0.1:3199/bridge \
      --secret <hex> --duration 8
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request

TS_TOLERANCE_S = 5

# Mirror konstanta anti head-of-line di LumineEA.mq5 (v5.02):
# transient (5xx/-1/401/403) retry backoff 1s..30s; permanen (404/422/409) drop.
RESULT_RETRY_BASE_MS = 1000
RESULT_RETRY_MAX_MS = 30000
RESULT_QUEUE_MAX = 128
# Mirror konstanta anti seed-loop di LumineEA.mq5 (v5.03):
# transient (5xx/-1/401/403) retry backoff 1s..30s; permanen (4xx) drop TF.
SEED_RETRY_BASE_MS = 1000
SEED_RETRY_MAX_MS = 30000


def sign_request(secret: str, method: str, path_with_query: str, body: bytes) -> dict:
    """Header HMAC — referensi Python dari SignHeaders() di LumineEA.mq5.

    string_to_sign = ts \\n nonce \\n METHOD \\n path \\n sha256_hex(body)
    """
    ts = str(int(time.time()))
    nonce = "%032x" % random.getrandbits(128)
    sts = "\n".join([ts, nonce, method, path_with_query,
                     hashlib.sha256(body).hexdigest()]).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), sts, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Fund2-Timestamp": ts,
        "X-Fund2-Nonce": nonce,
        "X-Fund2-Signature": sig,
    }


class EaSim:
    """EA v0 dalam bentuk thread Python (cadence & contract identik)."""

    def __init__(self, url: str, secret: str, symbol: str = "XAUUSD",
                 heartbeat_sec: float = 2.0, tick_batch_ms: float = 250.0,
                 poll_ms: float = 100.0, base_price: float = 2650.0):
        # Terima base dengan atau tanpa "/bridge"; simpan TANPA "/bridge"
        # karena path yang ditandatangani/dikirim sudah memuat "/bridge/...".
        url = url.rstrip("/")
        if url.endswith("/bridge"):
            url = url[: -len("/bridge")]
        self.url = url
        self.secret = secret
        self.symbol = symbol
        self.heartbeat_sec = heartbeat_sec
        self.tick_batch_ms = tick_batch_ms
        self.poll_ms = poll_ms
        self.base_price = base_price
        self.running = False
        self.thread: threading.Thread | None = None
        # buffer tick seperti EA
        self.tick_buf: list[dict] = []
        self.buf_lock = threading.Lock()
        self.stats = {"heartbeats_sent": 0, "tick_batches_sent": 0,
                      "ticks_sent": 0, "polls_sent": 0, "http_200": 0,
                      "http_other": 0, "errors": 0,
                      "results_sent": 0, "results_dropped": 0,
                      "result_failures": 0}
        # Antrean result (mirror FlushOneResult/QueueResult LumineEA v5.02):
        # FIFO; gagal permanen (404/422/409) di-drop, transient di-retry dgn
        # backoff eksponensial 1s..30s. Anti poison-pill head-of-line blocking.
        self.result_queue: list[str] = []
        self.result_log: list[str] = []
        self._last_result_try_ms = 0.0
        self._result_retry_ms = 0
        # Seed state (mirror SeedNextChunk/SeedAdvanceTf LumineEA v5.03):
        # anti seed-loop — "total=N bars" sekali per TF; transient backoff
        # 1s..30s; 4xx drop TF.
        self.seed_log: list[str] = []
        self._seed_sym = "XAUUSD"
        self._seed_tf = "1m"
        self._seed_offset = 0
        self._seed_total = 5000
        self._seed_retry_ms = 0
        self._last_seed_try_ms = 0.0
        self._seed_total_printed = False

    # ── transport ────────────────────────────────────────────────────────
    def _request(self, method: str, path_with_query: str, body: bytes) -> int:
        headers = sign_request(self.secret, method, path_with_query, body)
        req = urllib.request.Request(self.url + path_with_query,
                                     data=body if body else None,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
                code = resp.status
        except urllib.error.HTTPError as e:
            e.read()
            code = e.code
        except Exception:
            self.stats["errors"] += 1
            return -1
        if code == 200:
            self.stats["http_200"] += 1
        else:
            self.stats["http_other"] += 1
        return code

    # ── EA behaviours ────────────────────────────────────────────────────
    def send_heartbeat(self) -> int:
        bid = round(self.base_price + random.uniform(-0.5, 0.5), 5)
        ask = round(bid + random.uniform(0.10, 0.35), 5)  # spread XAUUSD realistis
        body = json.dumps({
            "ts": int(time.time()), "symbol": self.symbol,
            "bid": bid, "ask": ask, "spread": round(ask - bid, 5), "ea": "v0",
        }, separators=(",", ":")).encode()
        code = self._request("POST", "/bridge/heartbeat", body)
        if code == 200:
            self.stats["heartbeats_sent"] += 1
        return code

    def capture_tick(self) -> None:
        """OnTick: 1 tick masuk buffer (dengan spread)."""
        bid = round(self.base_price + random.uniform(-0.5, 0.5), 5)
        ask = round(bid + random.uniform(0.10, 0.35), 5)
        with self.buf_lock:
            self.tick_buf.append({
                "ts": int(time.time() * 1000), "bid": bid, "ask": ask,
                "spread": round(ask - bid, 5),
            })
            if len(self.tick_buf) > 512:  # TICK_BUF_MAX + backpressure
                self.tick_buf = self.tick_buf[-256:]

    def flush_tick_batch(self) -> int:
        with self.buf_lock:
            ticks, self.tick_buf = self.tick_buf, []
        if not ticks:
            return 200
        body = json.dumps({"symbol": self.symbol, "ticks": ticks},
                          separators=(",", ":")).encode()
        code = self._request("POST", "/bridge/tick", body)
        if code == 200:
            self.stats["tick_batches_sent"] += 1
            self.stats["ticks_sent"] += len(ticks)
        else:
            with self.buf_lock:  # gagal: taruh kembali (sisa backpressure EA)
                self.tick_buf = ticks[-256:] + self.tick_buf
        return code

    def poll(self) -> int:
        code = self._request("GET", "/bridge/poll?timeout_s=0", b"")
        if code == 200:
            self.stats["polls_sent"] += 1
        return code

    # ── result queue (mirror LumineEA v5.02) ─────────────────────────────
    @staticmethod
    def _extract_json_string(json_str: str, key: str) -> str:
        """Mirror ExtractJsonString() MQL5: cari \"key\":\"value\"."""
        pattern = f'"{key}":"'
        start = json_str.find(pattern)
        if start == -1:
            return ""
        start += len(pattern)
        end = json_str.find('"', start)
        if end == -1:
            return ""
        return json_str[start:end]

    def queue_result(self, obj) -> None:
        """QueueResult: FIFO 128 slot; penuh -> buang tertua (sama dengan EA)."""
        json_str = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
        if len(self.result_queue) >= RESULT_QUEUE_MAX:
            self.result_log.append("result queue FULL, dropping oldest")
            self.result_queue.pop(0)
        self.result_queue.append(json_str)

    def flush_one_result(self, force: bool = False, now_ms: float | None = None):
        """FlushOneResult: mirror persis klasifikasi status di LumineEA v5.02.

        200            -> pop + reset backoff
        404/422/409    -> pop (drop permanen, anti poison-pill) + reset backoff
        5xx/-1/401/403 -> retry dengan backoff 1s,2s,4s,...,max 30s
        force=True     -> abaikan backoff gate (dipakai OnDeinit)
        Return: "backoff" | "empty" | kode http.
        """
        if not self.result_queue:
            return "empty"
        if now_ms is None:
            now_ms = time.time() * 1000.0
        if (not force and self._result_retry_ms > 0
                and now_ms - self._last_result_try_ms < self._result_retry_ms):
            return "backoff"
        self._last_result_try_ms = now_ms

        json_str = self.result_queue[0]
        res = self._request("POST", "/bridge/result", json_str.encode())

        if res == 200:
            self.result_queue.pop(0)
            self._result_retry_ms = 0
            self.stats["results_sent"] += 1
            self.result_log.append(
                f"result terkirim (sisa antrean={len(self.result_queue)})")
            return res

        if res in (404, 422, 409):
            cid = self._extract_json_string(json_str, "command_id")
            self.result_log.append(
                f"result DROPPED http={res} command_id={cid} "
                f"(permanen, tidak di-retry) — sisa antrean={len(self.result_queue) - 1}")
            self.result_queue.pop(0)
            self._result_retry_ms = 0
            self.stats["results_dropped"] += 1
            return res

        # transient: 5xx, -1 (jaringan), 401/403 (auth bisa pulang), lainnya
        self._result_retry_ms = (
            RESULT_RETRY_BASE_MS if self._result_retry_ms <= 0
            else min(RESULT_RETRY_MAX_MS, self._result_retry_ms * 2))
        self.stats["result_failures"] += 1
        self.result_log.append(
            f"result gagal http={res} — retry dalam {self._result_retry_ms} ms "
            f"(isi antrean={len(self.result_queue)})")
        return res

    # ── seed (mirror SeedNextChunk v5.03) ────────────────────────────────
    def _seed_advance_tf(self) -> None:
        """SeedAdvanceTf: TF berikutnya; wrap -> simbol berikutnya."""
        order = ["1m", "5m", "15m", "1h", "4h", "1d"]
        idx = order.index(self._seed_tf) + 1
        if idx >= len(order):
            idx = 0
            self._seed_sym = "BTCUSD" if self._seed_sym == "XAUUSD" else "XAUUSD"
        self._seed_tf = order[idx]
        self._seed_offset = 0
        self._seed_total = 5000   # di MQL5 di-recompute dari iBars saat offset==0
        self._seed_total_printed = False

    def _seed_backoff(self) -> None:
        """SeedBackoff: 1,2,4,...,max 30s (mirror persis MQL5)."""
        self._seed_retry_ms = (
            SEED_RETRY_BASE_MS if self._seed_retry_ms <= 0
            else min(SEED_RETRY_MAX_MS, self._seed_retry_ms * 2))

    def seed_next_chunk(self, res: int, got: int = 500,
                        now_ms: float | None = None) -> str:
        """Mirror persis klasifikasi POST chunk seed di LumineEA v5.03.

        200            -> offset maju + reset backoff; TF selesai -> advance
        401/403        -> transient (auth bisa pulang): backoff
        4xx lain       -> permanen: drop TF + log
        -1/5xx/lainnya -> transient: backoff + log tiap gagal
        "total=N bars" hanya dicetak sekali per TF (bukan tiap retry).
        Return: "sent" | "drop-tf" | "transient" | "backoff-gate".
        """
        if now_ms is None:
            now_ms = time.time() * 1000.0
        if now_ms - self._last_seed_try_ms < self._seed_retry_ms:
            return "backoff-gate"
        self._last_seed_try_ms = now_ms
        if self._seed_offset == 0 and not self._seed_total_printed:
            self.seed_log.append(
                f"seed {self._seed_sym} {self._seed_tf} "
                f"total={self._seed_total} bars")
            self._seed_total_printed = True
        if res == 200:
            self._seed_offset += got
            self._seed_retry_ms = 0
            if self._seed_offset >= self._seed_total:
                self._seed_advance_tf()
            return "sent"
        if res in (401, 403):
            self._seed_backoff()
            return "transient"
        if 400 <= res < 500:
            self.seed_log.append(
                f"seed chunk DITOLAK http={res} {self._seed_sym} "
                f"{self._seed_tf} offset={self._seed_offset} — "
                f"skip TF (permanen, tidak di-retry)")
            self._seed_advance_tf()
            self._seed_retry_ms = 0
            return "drop-tf"
        self._seed_backoff()
        self.seed_log.append(
            f"seed chunk gagal http={res} {self._seed_sym} {self._seed_tf} "
            f"offset={self._seed_offset} — retry dalam {self._seed_retry_ms} ms")
        return "transient"

    # ── loop utama (meniru OnTimer 100ms) ────────────────────────────────
    def _run(self, duration: float) -> None:
        ev = getattr(self, "_started", None)
        if ev is not None:
            ev.set()  # loop benar-benar jalan (anti-race dgn stop())
        deadline = time.time() + duration
        next_hb = time.time() + self.heartbeat_sec
        next_poll = time.time() + self.poll_ms / 1000.0
        last_flush = time.time()
        tick_interval = 0.05  # feed tick ~20/s (XAUUSD aktif)
        next_tick = time.time() + tick_interval
        while time.time() < deadline and self.running:
            now = time.time()
            if now >= next_hb:
                next_hb = now + self.heartbeat_sec
                self.send_heartbeat()
            if now >= next_poll:
                next_poll = now + self.poll_ms / 1000.0
                self.poll()
            if now >= next_tick:
                next_tick = now + tick_interval
                self.capture_tick()
            with self.buf_lock:
                buffered = len(self.tick_buf)
            if buffered and (now - last_flush >= self.tick_batch_ms / 1000.0
                             or buffered >= 100):
                last_flush = now
                self.flush_tick_batch()
            time.sleep(0.01)

    def start(self, duration: float) -> None:
        self._started = threading.Event()
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(duration,), daemon=True)
        self.thread.start()

    def stop(self, cancel: bool = False) -> None:
        """Tunggu thread selesai (default: biarkan berjalan sampai duration).

        cancel=True: hentikan lebih awal — tunggu loop mulai dulu (anti-race:
        tanpa ini running=False bisa terpasang sebelum thread masuk while).
        """
        if self.thread:
            if cancel:
                self._started.wait(timeout=5)
                self.running = False
            self.thread.join(timeout=30)


def main() -> int:
    ap = argparse.ArgumentParser(description="EA v0 simulator (HMAC)")
    ap.add_argument("--url", default="http://127.0.0.1:3110/bridge")
    ap.add_argument("--secret", default=os.environ.get("FUND2_HMAC_SECRET", ""))
    ap.add_argument("--duration", type=float, default=8.0)
    ap.add_argument("--heartbeat-sec", type=float, default=2.0)
    ap.add_argument("--tick-batch-ms", type=float, default=250.0)
    ap.add_argument("--poll-ms", type=float, default=100.0)
    args = ap.parse_args()
    if not args.secret:
        print("ERROR: --secret atau env FUND2_HMAC_SECRET wajib", file=sys.stderr)
        return 2
    sim = EaSim(args.url, args.secret, heartbeat_sec=args.heartbeat_sec,
                tick_batch_ms=args.tick_batch_ms, poll_ms=args.poll_ms)
    sim.start(args.duration)
    sim.stop()
    print(json.dumps(sim.stats, indent=2))
    return 0 if sim.stats["errors"] == 0 and sim.stats["http_other"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
