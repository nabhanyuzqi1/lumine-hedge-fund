"""Klien Bitstamp v2 OHLC: candle M1 BTC/USD untuk backtest (t_3c65f152).

Latar: datafeed lama Dukascopy (datafeed.dukascopy.com) TIDAK menyediakan
crypto sama sekali - BTCUSD/ETHUSD/LTCUSD 404 nginx di semua tahun yang
diuji (2018-2025), termasuk BID_candles_min_1.bi5. Mirror S3
(cfg-public-proper-wallaby) mewajibkan AWS requester-pays. dukascopy-node
(jetta.dukascopy.com/v1/candles) kena WAF 403. Alternatif gratis tanpa
API key yang reachable dari host ini: Bitstamp (BTC/USD asli, bukan USDT),
OKX, Coinbase Exchange. Bitstamp dipilih: 1000 bar/request (paling hemat)
+ riwayat penuh.

Endpoint: GET https://www.bitstamp.net/api/v2/ohlc/<pair>/
          ?step=60&limit=1000&start=<unix_s>
Response: {"data": {"pair": "BTC/USD", "ohlc": [
            {"timestamp": "1719699960", "open": "60876.00", ...}, ...]}}
Bar ascending per timestamp; timestamp = awal menit (UTC).
Volume = base volume (BTC), bukan jutaan unit konvensi Dukascopy.
"""
from __future__ import annotations

import http.client
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

HOST = "www.bitstamp.net"
OHLC_PATH = "/api/v2/ohlc/{pair}/?"
STEP_S = 60
MAX_LIMIT = 1000
PAIR = {"BTCUSD": "btcusd"}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BACKOFF_S = (5.0, 10.0, 20.0, 40.0, 80.0)
HTTP_TIMEOUT = 25.0


class BitstampClient:
    """Satu koneksi HTTPS persistent, request sekuensial."""

    def __init__(self, host: str = HOST, timeout: float = HTTP_TIMEOUT):
        self.host = host
        self.timeout = timeout
        self._conn: http.client.HTTPSConnection | None = None

    def get(self, path: str) -> tuple[int, bytes]:
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                if self._conn is None:
                    self._conn = http.client.HTTPSConnection(
                        self.host, timeout=self.timeout)
                self._conn.request("GET", path, headers={
                    "User-Agent": USER_AGENT, "Accept": "application/json"})
                resp = self._conn.getresponse()
                body = resp.read()
                return int(resp.status), body
            except (http.client.HTTPException, OSError) as exc:
                last_exc = exc
                self.close()
                if attempt == 0:
                    continue
        raise OSError(f"Bitstamp connection gagal 2x: {last_exc!r}")

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None


def fetch_ohlc(client: BitstampClient, symbol: str, start_s: int,
               *, limit: int = MAX_LIMIT, attempts: int = 5) -> list[dict]:
    """Ambil candle M1 mulai start_s (unix, inklusif), max `limit` bar.

    Retry 5x backoff eksponensial untuk 429/5xx/timeout (endpoint tetangga
    sama flakiness-nya dengan datafeed Dukascopy). Return list bar ascending.
    """
    pair = PAIR.get(symbol, symbol.lower())
    path = OHLC_PATH.format(pair=pair) + urlencode(
        {"step": STEP_S, "limit": limit, "start": start_s})
    code = 0
    for attempt in range(attempts):
        try:
            code, body = client.get(path)
        except OSError:
            time.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
            continue
        if code == 200:
            try:
                payload = json.loads(body)
                rows = payload["data"]["ohlc"]
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Bitstamp payload tak terduga: {exc!r} "
                                 f"body[:120]={body[:120]!r}") from exc
            out = []
            for r in rows:
                ts = int(r["timestamp"])
                out.append({
                    "ts": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "open": float(r["open"]), "high": float(r["high"]),
                    "low": float(r["low"]), "close": float(r["close"]),
                    "volume": float(r["volume"]),
                })
            return out
        if code == 404:          # pair tidak dikenal / tidak ada data
            return []
        # 429/5xx/ lainnya: backoff lalu coba lagi
        time.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
    raise RuntimeError(f"Bitstamp {symbol} gagal {attempts}x: HTTP {code}")


def ohlc_range(client: BitstampClient, symbol: str, start_dt: datetime,
               end_dt: datetime, *, delay: float = 0.15,
               attempts: int = 5):
    """Generator seluruh bar M1 [start_dt, end_dt) UTC, paginasi maju.

    Bitstamp mengembalikan bar hanya untuk menit yang ada transaksi; menit
    tanpa transaksi dilewati (jarang untuk BTC - preflight akan menghitung
    gap-nya). Bar dengan ts >= end_dt dibuang.
    """
    start = int(start_dt.timestamp()) // 60 * 60
    end = int(end_dt.timestamp()) // 60 * 60
    cur = start
    while cur < end:
        bars = fetch_ohlc(client, symbol, cur, attempts=attempts)
        if not bars:
            return
        for b in bars:
            if b["ts"].timestamp() >= end:
                return
            yield b
        last = int(bars[-1]["timestamp"]) if "timestamp" in bars[-1] else \
            int(bars[-1]["ts"].timestamp())
        nxt = last + STEP_S
        if nxt <= cur:            # safety: server diam-diam mengulang data
            raise RuntimeError(f"Bitstamp paginasi macet di {cur}")
        cur = nxt
        time.sleep(delay)
