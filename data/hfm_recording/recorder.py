#!/usr/bin/env python3
"""Fund2 P0 — HFM spread/slippage recorder.

Menyambung ke SSE fund2-api (http://127.0.0.1:3110/stream) sebagai
svc-recorder, menangkap setiap event tick (bid/ask/spread, XAUUSD dan
BTCUSD) dan event order (fill), lalu menyimpan ke:

  parquet/ticks_<SYMBOL>_YYYY-MM-DD.parquet  per simbol, flush 60 detik
                                             (PRD 5.1, t_f2mp4)
  parquet/fills_YYYY-MM-DD.parquet           raw material slippage (PRD 5.2)
  log/ticks_YYYY-MM-DD.jsonl                 append per tick (crash-safe,
                                             campur simbol, ada kolom symbol)
  log/fills_YYYY-MM-DD.jsonl

Tidak menyentuh config/profil MT5, tanpa Docker, jalan sebagai systemd
user service (non-root). Restart aman: buffer < 60 detik hanya hilang
dari parquet, JSONL tetap lengkap.
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
PARQUET_DIR = BASE / "parquet"
LOG_DIR = BASE / "log"
STATE_DIR = BASE / "state"

API_HOST = "127.0.0.1"
API_PORT = 3110
FLUSH_S = 60        # PRD 5.1: flush parquet tiap 60 detik
STALL_S = 90        # reconnect bila tidak ada byte selama 90 dtk
RECONNECT_S = 5

for d in (PARQUET_DIR, LOG_DIR, STATE_DIR):
    d.mkdir(parents=True, exist_ok=True)

WIB = timezone(timedelta(hours=7))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm_exchange_ts(v):
    """Normalisasi exchange_ts ke string epoch-ms atau None.

    Payload SSE EA v5 mengirim int epoch ms; EA lama mengirim string MT5
    ("2026.11.20 23:59:59"); baris lama bisa null. Kolom buffer juga bisa
    ter-upcast ke float64 saat bercampur dengan None, maka float utuh
    dikembalikan ke int agar tidak muncul akhiran ".0".
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def session_of(dt: datetime) -> str:
    """Jendela sesi pasar (UTC): asia 21-07, london 07-12,
    london_newyork 12-16, newyork 16-21."""
    h = dt.hour
    if h < 7 or h >= 21:
        return "asia"
    if h < 12:
        return "london"
    if h < 16:
        return "london_newyork"
    return "newyork"


def load_env() -> dict:
    env = {}
    p = BASE / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("FUND2_")})
    return env


ENV = load_env()
API_USER = ENV.get("FUND2_RECORDER_USER", "svc-recorder")
API_PASS = ENV.get("FUND2_RECORDER_PASSWORD", "")


class Recorder:
    def __init__(self) -> None:
        self.tick_buf: list[dict] = []
        self.fill_buf: list[dict] = []
        self.cookie: str | None = None
        self.stop = False
        self.last_flush = time.time()
        self.ticks_total = 0
        self.fills_total = 0

    # ------------------------------------------------------------- persistence
    def _append_jsonl(self, kind: str, rec: dict) -> None:
        p = LOG_DIR / f"{kind}_{utcnow():%Y-%m-%d}.jsonl"
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")

    def flush(self) -> None:
        now = utcnow()
        day = f"{now:%Y-%m-%d}"
        # Tick: parquet per simbol (t_f2mp4) — BTCUSD tidak lagi tercampur
        # XAUUSD dalam satu file.
        by_symbol: dict[str, list[dict]] = {}
        for rec in self.tick_buf:
            by_symbol.setdefault(str(rec.get("symbol") or "UNKNOWN"), []).append(rec)
        for symbol, rows in by_symbol.items():
            df = pd.DataFrame(rows)
            p = PARQUET_DIR / f"ticks_{symbol}_{day}.parquet"
            if p.exists():
                df = pd.concat([pd.read_parquet(p), df], ignore_index=True)
            if "exchange_ts" in df.columns:
                # EA v5 kirim exchange_ts int (epoch ms); EA lama string MT5,
                # dan baris lama bisa null. Samakan ke string (skema parquet
                # large_string) tanpa mengubah null menjadi "None": kolom
                # buffer bisa ter-upcast ke float64 (int + None), maka
                # bulatkan nilai float utuh kembali ke int sebelum di-str-kan.
                df["exchange_ts"] = df["exchange_ts"].map(_norm_exchange_ts)
            df.to_parquet(p, index=False, compression="snappy")
            print(f"[flush] {len(rows)} ticks {symbol} -> {p.name} "
                  f"(total {df.shape[0]} rows)", flush=True)
        self.tick_buf.clear()
        if self.fill_buf:
            df = pd.DataFrame(self.fill_buf)
            p = PARQUET_DIR / f"fills_{day}.parquet"
            if p.exists():
                df = pd.concat([pd.read_parquet(p), df], ignore_index=True)
            df.to_parquet(p, index=False, compression="snappy")
            print(f"[flush] {len(self.fill_buf)} fills -> {p.name} "
                  f"(total {df.shape[0]} rows)", flush=True)
            self.fill_buf.clear()
        self.last_flush = time.time()

    # ------------------------------------------------------------- auth
    def login(self) -> None:
        body = json.dumps({"username": API_USER, "password": API_PASS}).encode()
        conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=10)
        try:
            conn.request("POST", "/auth/login", body, {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            })
            resp = conn.getresponse()
            data = resp.read()
            if resp.status != 200:
                raise RuntimeError(f"login gagal: {resp.status} {data[:200]!r}")
            raw = resp.getheader("Set-Cookie") or ""
            token = raw.split("fund2_session=")[1].split(";")[0]
        finally:
            conn.close()
        self.cookie = f"fund2_session={token}"
        (STATE_DIR / "session.json").write_text(json.dumps({
            "user": API_USER, "cookie": self.cookie,
            "ts": utcnow().isoformat()}))
        print("[auth] login ok (session 24h)", flush=True)

    # ------------------------------------------------------------- SSE
    def handle(self, event: str, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        now = utcnow()
        ts = f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond // 1000:03d}Z"
        if event == "tick":
            rec = {
                "ts_utc": ts,
                "tick_ts": data.get("ts"),
                "exchange_ts": data.get("exchange_ts"),
                "symbol": data.get("symbol"),
                "bid": data.get("bid"),
                "ask": data.get("ask"),
                "spread": data.get("spread"),
                "session": session_of(now),
            }
            self.tick_buf.append(rec)
            self.ticks_total += 1
            self._append_jsonl("ticks", rec)
        elif event == "order":
            rec = {
                "ts_utc": ts,
                "order_id": data.get("order_id"),
                "status": data.get("status"),
                "ticket": data.get("ticket"),
                "price": data.get("price"),
            }
            self.fill_buf.append(rec)
            self.fills_total += 1
            self._append_jsonl("fills", rec)

    def stream_once(self) -> None:
        conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=STALL_S)
        try:
            headers = {"Accept": "text/event-stream"}
            if self.cookie:
                headers["Cookie"] = self.cookie
            conn.request("GET", "/stream", headers=headers)
            resp = conn.getresponse()
            if resp.status == 401:
                print("[auth] session kedaluwarsa, login ulang", flush=True)
                conn.close()
                time.sleep(2)
                self.login()
                return
            if resp.status != 200:
                raise RuntimeError(
                    f"GET /stream: {resp.status} {resp.read()[:200]!r}")
            print("[sse] tersambung ke /stream", flush=True)
            event: str | None = None
            while not self.stop:
                line = resp.readline()
                if not line:
                    break
                s = line.decode("utf-8", "replace").strip()
                if not s:
                    event = None
                    continue
                if s.startswith(":"):
                    continue
                if s.startswith("event:"):
                    event = s.split(":", 1)[1].strip()
                elif s.startswith("data:") and event:
                    self.handle(event, s.split(":", 1)[1].strip())
                if time.time() - self.last_flush >= FLUSH_S:
                    try:
                        self.flush()
                    except Exception as exc:  # noqa: BLE001
                        # Flush gagal tidak boleh mematikan koneksi SSE:
                        # buffer dipertahankan dan di-retry pada baris
                        # berikutnya, tick terus diproses.
                        print(f"[warn] flush gagal, buffer dipertahankan: "
                              f"{exc!r}", flush=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def run(self) -> None:
        if not API_PASS:
            print("FUND2_RECORDER_PASSWORD kosong — cek .env", file=sys.stderr)
            sys.exit(2)
        while not self.stop:
            try:
                if self.cookie is None:
                    self.login()
                self.stream_once()
                if not self.stop:
                    print("[sse] stream terputus, reconnect", flush=True)
                    time.sleep(RECONNECT_S)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] {exc!r} — reconnect dalam {RECONNECT_S}s",
                      flush=True)
                time.sleep(RECONNECT_S)
        self.flush()


def main() -> int:
    rec = Recorder()

    def _term(signum, frame):  # noqa: ANN001
        print(f"[sig] signal {signum}, flush & keluar", flush=True)
        rec.stop = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    rec.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
