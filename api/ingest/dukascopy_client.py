"""Klien datafeed Dukascopy: fetch bi5 + decode + agregasi M1 (t_3c65f152).

Endpoint tick per jam (bulan 0-indexed!):
  https://datafeed.dukascopy.com/datafeed/<INSTR>/<YYYY>/<MM-1>/<DD>/<HH>h_ticks.bi5
Record 20 byte big-endian setelah LZMA-alone decompress:
  ms_offset(int32), ask(int32), bid(int32), ask_vol(float32), bid_vol(float32)
Harga: 1/1000 USD untuk XAUUSD/BTCUSD (1/100000 untuk forex pair).

Endpoint candle m1 harian (raw yang sudah terunduh, XAUUSD 2 tahun):
  .../<YYYY>/<MM-1>/<DD>/BID_candles_min_1.bi5
Record 24 byte: offset_detik(int32), open/close/low/high(int32, 1/1000),
volume(float32).

OHLC M1 memakai sisi BID; volume = sum(bid_vol) (jutaan unit, konvensi
Dukascopy) — konsisten dengan loader day-m1 existing (paper/dukascopy.py).
"""
from __future__ import annotations

import http.client
import lzma
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

HOST = "datafeed.dukascopy.com"
BASE_PATH = "/datafeed/{sym}/{y}/{m0}/{d}/{h}h_ticks.bi5"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

TICK_REC = struct.Struct(">iiiff")   # ms_offset, ask, bid, ask_vol, bid_vol
DAY_REC = struct.Struct(">iiiiif")   # offset_s, open, close, low, high, volume
PRICE_DIV = {"XAUUSD": 1000.0, "BTCUSD": 1000.0}
DEFAULT_DIV = 100000.0               # forex pair
BACKOFF_S = (5.0, 10.0, 20.0, 40.0, 80.0)  # retry 5x, spesifikasi kartu
HTTP_TIMEOUT = 25.0


def hour_range(start_dt: datetime, end_dt: datetime):
    """Epoch jam UTC [start, end), diselaraskan ke batas jam."""
    h = int(start_dt.timestamp()) // 3600 * 3600
    end = int(end_dt.timestamp()) // 3600 * 3600
    while h < end:
        yield h
        h += 3600


def hour_path(symbol: str, hour_epoch: int) -> str:
    dt = datetime.fromtimestamp(hour_epoch, tz=timezone.utc)
    return BASE_PATH.format(sym=symbol, y=dt.year, m0=dt.month - 1,
                            d=dt.day, h=dt.hour)

DAY_PATH = "/datafeed/{sym}/{y}/{m0}/{d}/BID_candles_min_1.bi5"


def day_path(symbol: str, day_epoch: int) -> str:
    dt = datetime.fromtimestamp(day_epoch, tz=timezone.utc)
    return DAY_PATH.format(sym=symbol, y=dt.year, m0=dt.month - 1, d=dt.day)


def day_range(start_dt: datetime, end_dt: datetime):
    """Epoch hari UTC [start, end), diselaraskan ke batas 00:00."""
    d = int(start_dt.timestamp()) // 86400 * 86400
    end = int(end_dt.timestamp()) // 86400 * 86400
    while d < end:
        yield d
        d += 86400


class KeepAliveClient:
    """Satu koneksi HTTPS persistent (request sekuensial, tanpa paralel).

    urllib membuka koneksi baru per request (TLS handshake tiap jam);
    keep-alive memangkas ~0.2s/jam tanpa mengubah perilaku server.
    """

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
                    "User-Agent": USER_AGENT, "Accept": "*/*"})
                resp = self._conn.getresponse()
                body = resp.read()
                return int(resp.status), body
            except (http.client.HTTPException, OSError) as exc:
                last_exc = exc
                self.close()
                if attempt == 0:
                    continue  # sekali reconnect, lalu serahkan ke pemanggil
        return 0, b""

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None


def fetch_hour(client: KeepAliveClient, symbol: str, hour_epoch: int,
               *, attempts: int = 5) -> tuple[str, bytes]:
    """Unduh satu file jam. Return (status, raw_ticks).

    status: ok | empty (404 konsisten = tidak ada tick) | fail (habis retry).
    503/429/timeout: backoff eksponensial 5/10/20/40/80 sesuai spesifikasi.
    404 di-verifikasi 3x (node kadang 404 sesaat sebelum 200).
    """
    return _fetch_path(client, hour_path(symbol, hour_epoch),
                       attempts=attempts)


def fetch_day(client: KeepAliveClient, symbol: str, day_epoch: int,
              *, attempts: int = 5) -> tuple[str, bytes]:
    """Unduh candle m1 harian (BID_candles_min_1.bi5), 1 request/hari."""
    return _fetch_path(client, day_path(symbol, day_epoch), attempts=attempts)


def _fetch_path(client: KeepAliveClient, path: str,
                *, attempts: int = 5) -> tuple[str, bytes]:
    not_found = 0
    for attempt in range(attempts):
        code, body = client.get(path)
        if code == 200:
            if not body:
                return "empty", b""
            try:
                return "ok", lzma.decompress(body, format=lzma.FORMAT_ALONE)
            except lzma.LZMAError:
                pass  # body korup -> perlakukan sebagai error
        elif code == 404:
            not_found += 1
            if not_found >= 3:
                return "empty", b""
            time.sleep(1.5 * not_found)  # node kadang 404 sesaat (load balancer)
        else:  # 503/429/5xx/0 (network/timeout)
            time.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
    return "fail", b""


def ticks_to_m1(hour_epoch: int, raw: bytes, div: float = 1000.0) -> list[dict]:
    """Tick satu jam -> bar M1 sisi BID (ts UTC, o/h/l/c, volume sum bid_vol)."""
    base_ms = hour_epoch * 1000
    buckets: dict[int, list] = {}
    for i in range(0, len(raw) - len(raw) % TICK_REC.size, TICK_REC.size):
        ms, _ask, bid, _av, bv = TICK_REC.unpack_from(raw, i)
        minute = (base_ms + ms) // 60000
        price = bid / div
        b = buckets.get(minute)
        if b is None:
            buckets[minute] = [price, price, price, price, float(bv)]
        else:
            if price > b[1]:
                b[1] = price
            elif price < b[2]:
                b[2] = price
            b[3] = price
            b[4] += bv
    return [{"ts": datetime.fromtimestamp(m * 60, tz=timezone.utc),
             "open": b[0], "high": b[1], "low": b[2], "close": b[3],
             "volume": round(b[4], 6)} for m, b in sorted(buckets.items())]


def day_bytes_to_m1(day_epoch: int, raw: bytes, div: float = 1000.0) -> list[dict]:
    """Raw candle m1 harian (24 byte) -> bar M1 langsung (sudah OHLCV)."""
    day0 = day_epoch
    out = []
    for i in range(0, len(raw) - len(raw) % DAY_REC.size, DAY_REC.size):
        off, o, c, l, h, v = DAY_REC.unpack_from(raw, i)
        out.append({"ts": datetime.fromtimestamp(day0 + off, tz=timezone.utc),
                    "open": o / div, "high": h / div, "low": l / div,
                    "close": c / div, "volume": round(float(v), 6)})
    return out


def day_file_to_m1(path: Path, div: float = 1000.0) -> list[dict]:
    """File candle m1 harian (24 byte) -> bar M1 langsung (sudah OHLCV)."""
    raw = lzma.decompress(path.read_bytes(), format=lzma.FORMAT_ALONE)
    day = datetime.strptime(path.stem[:10], "%Y-%m-%d").replace(
        tzinfo=timezone.utc)
    return day_bytes_to_m1(int(day.timestamp()), raw, div)
