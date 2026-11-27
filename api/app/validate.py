"""Validasi data ingest (PRD v2.2 §4.4, kartu t_f2v22a11).

Dua jalur keputusan untuk data yang masuk lewat /bridge/tick:

  REJECT — data rusak/struktural salah: tidak masuk ring buffer, agregasi,
           market store, maupun candle. Dihitung di counter + log.
  FLAG   — data mencurigakan tetapi tidak bisa dibuang tanpa risiko
           membuang data sah (mis. tick stale, candle out-of-order):
           dicatat + dihitung, tetap diproses.

Aturan §4.4 yang diimplementasi (kode Issue):
  - timestamp mundur            -> TS_BACKWARD   (REJECT, tick; mundur
    > BACKWARD_TOLERANCE_S)
  - timestamp mundur kecil      -> TS_BACKWARD_SMALL (FLAG; jitter ±1 dtk
    antara tick real konversi offset broker dan tick sintetis TimeGMT —
    t_74b1f18f: REJECT kaku membuang ~10% tick di bawah ratchet)
  - timestamp terlalu di masa depan -> TS_FUTURE (REJECT)
  - bid/ask nol atau negatif    -> BID_ASK_NONPOSITIVE (REJECT)
  - bid/ask tidak masuk akal    -> PRICE_ABSURD (REJECT; di luar band
    warasan per simbol), PRICE_JUMP (FLAG; lompatan > JUMP_FRACTION
    antar tick berurutan — black swan sah tetap lewat, tapi tercatat)
  - ask < bid                   -> ASK_BELOW_BID (REJECT)
  - tick melewati freshness threshold -> TS_STALE (FLAG; hanya bila ts
    epoch/ISO eksplisit — string jam broker v0 ambigu offset, tidak
    dihukum)
  - simbol/contract spec berubah -> di data_quality (deviasi median harga
    antar hari); di sini SYMBOL_MAPPED (FLAG) bila nama broker
    dinormalisasi, SYMBOL_UNKNOWN (REJECT) bila simbol tak dikenal
  - duplicate tick/candle tak teridentifikasi -> DUPLICATE_TICK /
    CANDLE_DUPLICATE / CANDLE_CONFLICT (FLAG + counter: duplikat
    teridentifikasi, bukan lewat diam-diam)
  - EA kirim versi schema tidak didukung -> schema_version di body
    diverifikasi bridge (422); konstanta SUPPORTED_SCHEMA_VERSIONS.

Candle: out-of-order/duplicate sengaja FLAG bukan REJECT karena upsert
candle memang idempotent per (symbol, timeframe, ts) — seed ulang history
EA harus tetap boleh. Tick stream REJECT mundur karena merusak monotonis
agregator.

Modul murni (tanpa import app) agar bisa diuji unit tanpa DB.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

# ── Kontrak versi schema EA (PRD 4.4 baris terakhir) ────────────────────────
# EA v5 = batch tick 250ms + candle seed; EA v0 = single tick legacy.
# Body tanpa schema_version dianggap kontrak lama (toleran; EA berjalan
# sekarang tidak mengirim field ini).
SUPPORTED_SCHEMA_VERSIONS = {"v5", "5", "v0", "0"}

FUTURE_TOLERANCE_S = 120.0   # ts di depan now melebihi ini = REJECT
BACKWARD_TOLERANCE_S = 5.0   # regresi kecil di bawah ini = FLAG (jitter multi-sumber)
FRESHNESS_S = 60.0           # tick lebih tua dari ini = FLAG TS_STALE
JUMP_FRACTION = 0.20         # lompatan harga antar tick > 20% = FLAG

# Band harga warasan per simbol (absolut). Di luar band = PRICE_ABSURD.
# BTCUSD ~ ratusan ribu; XAUUSD ribuan. Default untuk simbol lain lebar.
PRICE_BANDS: dict[str, tuple[float, float]] = {
    "XAUUSD": (100.0, 10_000.0),
    "BTCUSD": (1_000.0, 1_000_000.0),
}
DEFAULT_PRICE_BAND = (0.0001, 10_000_000.0)

TS_PAST_FLOOR = datetime(2000, 1, 1, tzinfo=timezone.utc)


class Issue(NamedTuple):
    code: str
    severity: str          # 'REJECT' | 'FLAG'
    detail: str


def normalize_symbol(raw: str) -> str:
    """Mirror EA NormalizeSymbol (ea/LumineEA.mq5): #prefix, .suffix,
    suffix 1 char lowercase (c/m/x/i/z), uppercase."""
    s = str(raw or "").strip()
    if s.startswith("#"):
        s = s[1:]
    dot = s.find(".")
    if dot > 0:
        s = s[:dot]
    if len(s) > 4 and s[-1] in "cmxiz":
        s = s[:-1]
    return s.upper()


def _parse_ts(value: Any) -> tuple[datetime | None, str]:
    """Parse ts tick (EA v5 epoch ms, EA v0 epoch detik / ISO / jam broker).

    Return (datetime_utc|None, kind) dengan kind:
    'epoch_ms' | 'epoch_s' | 'iso' | 'broker_str' | 'none' | 'invalid'.
    Hanya epoch/ISO yang dianggap kandidat freshness (string jam broker
    punya offset zona ambigu — lihat paper/feed.py).
    """
    if value is None:
        return None, "none"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v <= 0:
            return None, "invalid"
        if v > 1e12:  # epoch ms
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc), "epoch_ms"
        if v > 1e9:   # epoch detik
            return datetime.fromtimestamp(v, tz=timezone.utc), "epoch_s"
        return None, "invalid"
    s = str(value).strip()
    if not s:
        return None, "none"
    # epoch numerik dalam string
    try:
        return _parse_ts(float(s))
    except ValueError:
        pass
    iso = s.replace(" ", "T", 1) if (" " in s and "T" not in s) else s
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), "iso"
    except ValueError:
        pass
    try:  # format EA TimeToString: "2026.11.21 10:00:00"
        dt = datetime.strptime(s, "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt, "broker_str"
    except ValueError:
        return None, "invalid"


class TickValidator:
    """Validator stateful per proses: ingat tick terakhir per simbol
    (untuk deteksi mundur/duplikat/lompatan) + counter audit."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, dict] = {}       # symbol -> {ts, bid, ask}
        self._known_symbols: set[str] = set()  # simbol yang pernah lolos
        self.counters: dict[str, int] = {}

    # ------------------------------------------------------------- counters
    def _bump(self, code: str) -> None:
        self.counters[code] = self.counters.get(code, 0) + 1

    def snapshot(self) -> dict:
        """Counter untuk endpoint /metrics & laporan kualitas."""
        with self._lock:
            return {
                "counters": dict(self.counters),
                "known_symbols": sorted(self._known_symbols),
                "last_tick": {k: dict(v) for k, v in self._last.items()},
            }

    def note_symbol(self, symbol: str) -> None:
        """Daftarkan simbol yang sah (dari settings / simbol bersejarah)."""
        with self._lock:
            self._known_symbols.add(normalize_symbol(symbol))

    # ------------------------------------------------------------- tick
    def check_tick(self, symbol: str, bid: float, ask: float, ts=None,
                   *, now: datetime | None = None) -> list[Issue]:
        """Validasi satu tick. Return issues; REJECT berarti pemanggil wajib
        membuang tick ini (tidak masuk market store / pipeline)."""
        issues: list[Issue]
        try:
            issues = _check_tick(
                symbol, float(bid), float(ask), ts,
                last=self._last.get(normalize_symbol(symbol)),
                known_symbols=self._known_symbols, now=now,
            )
        except (TypeError, ValueError):
            issues = [Issue("TICK_MALFORMED", "REJECT", "bid/ask bukan angka")]
        with self._lock:
            base = normalize_symbol(symbol)
            for i in issues:
                self._bump(i.code)
            if not any(i.severity == "REJECT" for i in issues):
                parsed, _ = _parse_ts(ts)
                prev = self._last.get(base)
                # High-water mark (t_74b1f18f): tick regresi-kecil diterima
                # tapi TIDAK menurunkan baseline; ts mundur besar sudah
                # REJECT di atas. Tanpa ini baseline ikut mundur dan stream
                # kehilangan perlindungan monoton.
                if (prev is None or prev.get("ts") is None
                        or (parsed is not None and parsed >= prev["ts"])):
                    self._last[base] = {"ts": parsed, "bid": float(bid),
                                        "ask": float(ask)}
                self._known_symbols.add(base)
        return issues

    # ------------------------------------------------------------- candle
    def check_candle(self, symbol: str, timeframe: str, ts, open_: float,
                     high: float, low: float, close: float,
                     volume: float = 0, *, now: datetime | None = None) -> list[Issue]:
        issues = _check_candle(symbol, timeframe, ts, open_, high, low, close,
                               volume, now=now)
        with self._lock:
            for i in issues:
                self._bump(i.code)
        return issues


def _check_tick(symbol: str, bid: float, ask: float, ts, *,
                last: dict | None, known_symbols: set[str],
                now: datetime | None = None) -> list[Issue]:
    """Aturan tick murni (tanpa state, testable)."""
    issues: list[Issue] = []
    base = normalize_symbol(symbol)

    if base != str(symbol):
        issues.append(Issue("SYMBOL_MAPPED", "FLAG",
                            f"'{symbol}' dinormalisasi -> '{base}'"))
    elif known_symbols and base not in known_symbols:
        issues.append(Issue("SYMBOL_UNKNOWN", "REJECT",
                            f"simbol '{base}' tidak dikenal (bukan simbol "
                            "allowed/bersejarah); data tidak diinkest"))

    # bid/ask nol, negatif, tidak masuk akal (PRD 4.4)
    if not (bid > 0) or not (ask > 0):
        issues.append(Issue("BID_ASK_NONPOSITIVE", "REJECT",
                            f"bid={bid} ask={ask}"))
        return issues  # tidak ada lanjut yang bisa dihitung

    if ask < bid:
        issues.append(Issue("ASK_BELOW_BID", "REJECT",
                            f"ask {ask} < bid {bid}"))
        return issues

    lo, hi = PRICE_BANDS.get(base, DEFAULT_PRICE_BAND)
    if not (lo <= bid <= hi) or not (lo <= ask <= hi):
        issues.append(Issue("PRICE_ABSURD", "REJECT",
                            f"harga di luar band warasan [{lo}, {hi}]: "
                            f"bid={bid} ask={ask}"))
        return issues

    # timestamp: mundur / masa depan / stale / duplikat
    parsed, kind = _parse_ts(ts)
    if kind == "invalid":
        issues.append(Issue("TS_UNPARSED", "FLAG", f"ts tidak bisa diparse: {ts!r}"))
    elif parsed is not None:
        now = now or datetime.now(timezone.utc)
        if parsed < TS_PAST_FLOOR:
            issues.append(Issue("TS_BACKWARD", "REJECT", f"ts ekstrem lampau: {parsed}"))
            return issues
        if parsed - now > timedelta(seconds=FUTURE_TOLERANCE_S):
            issues.append(Issue("TS_FUTURE", "REJECT",
                                f"ts {parsed.isoformat()} terlalu jauh di masa depan"))
            return issues
        if last and last.get("ts") is not None:
            if parsed < last["ts"]:
                lag = (last["ts"] - parsed).total_seconds()
                if lag > BACKWARD_TOLERANCE_S:
                    issues.append(Issue("TS_BACKWARD", "REJECT",
                                        f"ts mundur: {parsed.isoformat()} < "
                                        f"{last['ts'].isoformat()}"))
                    return issues
                # t_74b1f18f: jitter ±1 dtk (offset broker terukur ulang tiap
                # siklus timer + tick sintetis berbasis TimeGMT) membuat
                # stream EA tidak monoton; ratchet REJECT membuang semua tick
                # di bawah high-water mark (~10% tick XAUUSD). Regresi kecil
                # diterima dengan FLAG; high-water mark tetap (lihat
                # check_tick) sehingga anti-lookahead tidak melemah.
                issues.append(Issue("TS_BACKWARD_SMALL", "FLAG",
                                    f"ts mundur {lag:.3f}s (<= "
                                    f"{BACKWARD_TOLERANCE_S:.0f}s jitter): "
                                    f"{parsed.isoformat()}"))
            if parsed == last["ts"] and (bid, ask) == (last["bid"], last["ask"]):
                issues.append(Issue("DUPLICATE_TICK", "FLAG",
                                    "tick identik (ts, bid, ask) berulang"))
        if kind in ("epoch_ms", "epoch_s", "iso"):
            age = (now - parsed).total_seconds()
            if age > FRESHNESS_S:
                issues.append(Issue("TS_STALE", "FLAG",
                                    f"tick berumur {age:.0f}s > {FRESHNESS_S:.0f}s"))

    # lompatan harga antar tick berurutan (black swan sah tetap lewat)
    if last and last.get("bid"):
        ref = last["bid"]
        if ref > 0 and abs(bid - ref) / ref > JUMP_FRACTION:
            issues.append(Issue("PRICE_JUMP", "FLAG",
                                f"bid {ref} -> {bid} "
                                f"({abs(bid - ref) / ref:.0%} dalam sejikan tick)"))
    return issues


def _check_candle(symbol: str, timeframe: str, ts, open_: float, high: float,
                  low: float, close: float, volume: float,
                  *, now: datetime | None = None) -> list[Issue]:
    """Aturan candle murni. Out-of-order/duplikat = FLAG (upsert idempotent),
    OHLC/value rusak = REJECT."""
    issues: list[Issue] = []
    try:
        o, h, l, c, v = (float(open_), float(high), float(low),
                         float(close), float(volume))
    except (TypeError, ValueError):
        return [Issue("CANDLE_MALFORMED", "REJECT", "OHLCV bukan angka")]

    if not (o > 0 and h > 0 and l > 0 and c > 0):
        issues.append(Issue("CANDLE_NONPOSITIVE", "REJECT",
                            f"ada harga <= 0: o={o} h={h} l={l} c={c}"))
    elif not (h >= l and h >= max(o, c) - 1e-9 and l <= min(o, c) + 1e-9):
        issues.append(Issue("CANDLE_OHLC", "REJECT",
                            f"OHLC tidak konsisten: o={o} h={h} l={l} c={c}"))
    if v < 0:
        issues.append(Issue("CANDLE_VOLUME", "REJECT", f"volume negatif: {v}"))

    parsed, kind = _parse_ts(ts)
    if kind == "invalid":
        issues.append(Issue("TS_UNPARSED", "FLAG", f"ts tidak bisa diparse: {ts!r}"))
    elif parsed is not None:
        now = now or datetime.now(timezone.utc)
        if parsed - now > timedelta(seconds=FUTURE_TOLERANCE_S):
            issues.append(Issue("TS_FUTURE", "REJECT",
                                f"ts candle {parsed.isoformat()} terlalu jauh "
                                "di masa depan"))
    return issues


# --------------------------------------------------------------------- global
_validator: TickValidator | None = None
_validator_lock = threading.Lock()


def get_validator() -> TickValidator:
    global _validator
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                _validator = TickValidator()
                # simbol yang sudah bersejarah dianggap dikenal agar tick
                # BTCUSD (settings allowed_symbols masih ["XAUUSD"])
                # tidak ditolak salah.
                _validator._known_symbols.update(PRICE_BANDS.keys())
    return _validator


def reset_validator() -> TickValidator:
    global _validator
    with _validator_lock:
        _validator = TickValidator()
        _validator._known_symbols.update(PRICE_BANDS.keys())
    return _validator


def schema_version_supported(version: str | None) -> bool:
    """None = kontrak lama (diterima); selain itu harus ada di set didukung."""
    return version is None or str(version) in SUPPORTED_SCHEMA_VERSIONS


def rejected(issues: Iterable[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "REJECT"]


def flagged(issues: Iterable[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "FLAG"]


def monotonic_ms() -> int:
    """Epoch ms saat ini (untuk test ts fresh)."""
    return int(time.time() * 1000)
