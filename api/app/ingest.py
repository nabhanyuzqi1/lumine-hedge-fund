"""Tick ingest pipeline (PRD 5.1, P1a hari 5-6).

Alur: /bridge/tick -> ring buffer memori -> parquet tiap 60 detik
(BUKAN Postgres mentah). Postgres hanya menerima:
  - candle M1+ (upsert, partisi bulanan)
  - agregat spread per 5 detik (liquidity_samples)

Backpressure (PRD 5.1): jika antrean tulis > 5 detik, buang sampel
likuiditas, JANGAN event order. Order path tidak pernah menunggu tulis
tick: endpoint /bridge/tick tidak menyentuh DB sama sekali (memori +
SSE + antrean), semua tulis DB terjadi di task latar belakang ini.

Event order tidak pernah melewati pipeline ini (ditulis sinkron di
order path sendiri), jadi backpressure tidak mungkin membuang event
order.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from strategies.broker_time import broker_utc_offset_hours

from . import config, db, market_sessions, validate

FLUSH_PARQUET_S = 60      # PRD 5.1: flush parquet tiap 60 detik
DB_FLUSH_S = 5            # cadence tulis liquidity_samples + candles
LIQ_HEAL_INTERVAL_S = 300 # self-heal celah liquidity_samples dari parquet tick
LIQUIDITY_WINDOW_S = 5    # PRD: agregat spread per 5 detik
BACKPRESSURE_S = 5        # PRD: antrean tulis > 5 dtk -> buang sampel likuiditas
RING_MAX = 200_000        # ring buffer ticks (~14 jam pada 4 tick/dtk)

M5_SECONDS = 300              # lebar bar M5
M15_SECONDS = 900             # lebar bar M15 (rollup tingkat lanjut, t_f2mp3)
H1_SECONDS = 3600             # lebar bar H1 (rollup tingkat lanjut, t_f2mp3)
H4_SECONDS = 4 * 3600         # lebar bar H4 (rollup H1->H4)
D1_SECONDS = 24 * 3600        # lebar bar D1 (rollup H4->D1)
# Rantai rollup bertingkat: sumber -> tujuan, URUT dependency (M1 dulu).
# Semua tingkat hanya dibangun dari bar volume>0 (bar datar volume 0 = sampah
# jendela tutup, tidak boleh naik ke timeframe tinggi).
ROLLUP_CHAIN = (
    ("M1", "M5", M5_SECONDS),
    ("M5", "M15", M15_SECONDS),
    ("M5", "H1", H1_SECONDS),
    ("H1", "H4", H4_SECONDS),
    ("H4", "D1", D1_SECONDS),
)
# Timeframe yang candle berjalannya diagregasi langsung dari tick (lihat
# _agg_htf). M1 punya jalur sendiri di _agg_m1; sisanya harus hidup karena EA
# hanya mengirim shift=0 sekali per bucket.
LIVE_HTF = (("M5", M5_SECONDS), ("M15", M15_SECONDS), ("H1", H1_SECONDS),
            ("H4", H4_SECONDS), ("D1", D1_SECONDS))
# Grid bucket H4/D1 mengikuti jam server broker (UTC+2), bukan UTC: bar native
# EA duduk di 01/05/09/13/17/21 (H4) dan 05:00 (D1) = tengah malam broker
# 00:00 UTC+2. Diukur 27 Nov 2026: memotong di grid UTC menyimpan setiap
# periode DUA kali (XAU D1 1114 baris untuk 647 hari) sehingga chart
# menggambar dua seri bersilang. TF <= H1 tidak terpengaruh karena 7200 dtk
# kelipatan bulat dari bucket-nya.
GRID_OFFSET_S = {"H4": -7200, "D1": -7200}


def bucket_epoch(epoch: int, seconds: int, tf: str) -> int:
    """Awal bucket (epoch) untuk tf pada grid broker. TF <= H1 = grid UTC."""
    grid = GRID_OFFSET_S.get(tf, 0)
    return ((epoch - grid) // seconds) * seconds + grid
# Sumber candle: 'legacy' = bar lama sebelum kolom source (migrasi p016),
# 'ea' = bar native/seeding dari EA (atau agregasi tick EA), 'rollup' = hasil
# agregasi server. Bar native EA MENANG atas rollup (upsert rollup tidak
# menimpa baris source='ea').
SOURCE_LEGACY = "legacy"
SOURCE_EA = "ea"
SOURCE_ROLLUP = "rollup"
# 'live' = bar yang sedang berjalan, diagregasi server dari tick. EA hanya
# mengirim bar shift=0 SEKALI tepat setelah bucket berganti (EmitBarsForSlot
# melewati bucket yang sama), jadi tanpa agregasi ini candle berjalan di M5+
# membeku di harga pembukaan bucket: chart memperlihatkan candle datar lalu
# "melompat" ke harga awal setiap refresh, dan high/low bar tidak pernah
# memuat pergerakan nyata (terukur 27 Nov 2026: M5 08:00 high 3560.82
# sementara M1 di jendela yang sama high 3567.15). Bar 'live' selalu
# ditimpa bar 'ea' saat bucket tutup, atau oleh rollup (yang menolak menimpa
# hanya bila source='ea').
SOURCE_LIVE = "live"
CANDLE_SOURCES = (SOURCE_LEGACY, SOURCE_EA, SOURCE_ROLLUP, SOURCE_LIVE)

# jendela sumber M1 rollup berkala (15 menit: bucket berjalan + 2 sebelumnya)
ROLLUP_LOOKBACK_S = 900
FREEZE_TIMEOUT_S = 600.0      # kutipan beku > 10 menit = pasar tutup (tanpa bar)
# Bar M1 baru TIDAK dibuka bila kutipan sudah beku selama ini, walau pasar
# dilaporkan buka. Pembekuan 2 menit adalah tanda feed mengulang harga terakhir
# (bukan pasar sepi): bar menit berikutnya pasti O=H=L=C dan mengotori seri.
# Episode beku 5 menit sebelumnya menghasilkan 5 bar kosong beruntun.
FLAT_BAR_MAX_QUIET_S = 120.0
# Cache jadwal sesi simbol untuk filter candle kosong (refresh berkala).
SESSION_REFRESH_S = 300.0
MAX_QUOTE_JUMP_PCT = 2.0      # loncatan kutipan > 2% dari baseline = tick basi
MAX_JUMP_CONFIRM_TICKS = 5    # level baru dianggap asli setelah N tick beruntun
AUTOHEAL_MAX_LOOKBACK_S = 48 * 3600  # batas auto-heal gap (anti overscroll)

WIB = timezone(timedelta(hours=7))

# Kanonik timeframe (PRD 5.1: candle M1+). Seed EA lama & beberapa sumber
# memakai nama kecil; semua dinormalisasi ke bentuk MT5 standar.
_TF_CANON = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1"}
# Lebar bucket per timeframe kanonik (dipakai menandai bar yang masih berjalan).
_TF_SECONDS = {"M1": 60, "M5": M5_SECONDS, "M15": M15_SECONDS, "H1": H1_SECONDS,
               "H4": H4_SECONDS, "D1": D1_SECONDS}


def _source_of(candle: dict) -> str:
    """Sumber baris candle: 'ea' (default: native/seeding EA) atau 'rollup'.

    Nilai asing DIPAKSA ke 'ea' — bukan 'legacy' — supaya penulis baru tidak
    pernah bisa menyamar sebagai bar lama dan ikut tersembunyi oleh cutover.
    """
    raw = candle.get("source")
    if raw is None:
        return SOURCE_EA
    text = str(raw).strip().lower()
    return text if text in (SOURCE_EA, SOURCE_ROLLUP) else SOURCE_EA


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


# --------------------------------------------------------------------- rollup M1->M5

async def _db_tz_offset_h(conn) -> int:
    """Offset (jam) timezone sesi DB terhadap UTC (Asia/Pontianak = 7)."""
    cur = await conn.execute("SELECT current_setting('TimeZone') AS tz")
    row = await cur.fetchone()
    name = (row or {}).get("tz", "UTC") if row else "UTC"
    try:
        offset = datetime.now(ZoneInfo(name)).utcoffset()
        return int(offset.total_seconds() // 3600) if offset else 0
    except Exception:  # noqa: BLE001 — nama tz tak dikenal: fallback UTC
        return 0


async def _rollup_tf(conn, *, src_tf: str, dst_tf: str, seconds: int,
                     since: datetime, until: datetime | None = None,
                     symbol: str | None = None) -> int:
    """Agregasi bar `<src_tf>` -> `<dst_tf>` server-side (pola rollup M1->M5).

    Kunci ts hasil = bucket true UTC + (offset broker - offset tz DB), sama
    dengan konvensi seed EA/crawler (shift 0 terukur 2026-11-22). Idempotent
    (upsert ON CONFLICT): bar parsial konvergen tiap siklus.

    Dua aturan data (kartu candle pipeline):
    - hanya bar sumber dengan ``volume > 0``: bar datar volume 0 (isi jendela
      pasar tutup) tidak boleh naik ke timeframe tinggi dan membuat histogram
      acak;
    - hasil ditulis dengan ``source='rollup'`` dan TIDAK menimpa bar
      ``source='ea'`` (bar native MT5 selalu menang atas agregasi server).
    """
    until = until or utcnow()
    db_tz = await _db_tz_offset_h(conn)
    shift_h = broker_utc_offset_hours(until) - db_tz
    # Grid bucket H4/D1 mengikuti jam server broker (UTC+2), bukan UTC (lihat
    # GRID_OFFSET_S). Diukur 27 Nov 2026: memotong di grid UTC menyimpan setiap
    # periode dua kali sehingga chart menggambar dua seri bersilang.
    grid_s = GRID_OFFSET_S.get(dst_tf, 0)
    await _ensure_range_partitions(conn, since + timedelta(hours=shift_h),
                                   until + timedelta(hours=shift_h))
    cond = ""
    params: list = [grid_s, seconds, seconds, grid_s, since, until]
    if symbol:
        cond = "AND symbol = %s"
        params.append(symbol)
    params.append(shift_h)
    sql = f"""
        WITH src AS (
            SELECT symbol, ts, open, high, low, close, volume,
                   to_timestamp(floor((extract(epoch FROM ts) - %s) / %s) * %s + %s) AS bucket
            FROM candles
            WHERE timeframe = '{src_tf}' AND ts >= %s AND ts < %s
              AND volume > 0 {cond}
        )
        INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume, source)
        SELECT symbol, '{dst_tf}', bucket + (%s * interval '1 hour'),
               (array_agg(open ORDER BY ts))[1], max(high), min(low),
               (array_agg(close ORDER BY ts DESC))[1], sum(volume), '{SOURCE_ROLLUP}'
        FROM src
        GROUP BY symbol, bucket
        ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, volume = EXCLUDED.volume,
            source = EXCLUDED.source
        WHERE candles.source <> '{SOURCE_EA}'
    """
    cur = await conn.execute(sql, params)
    return max(0, cur.rowcount)


async def rollup_m1_to_m5(conn, *, since: datetime, until: datetime | None = None,
                          symbol: str | None = None) -> int:
    """Agregasi M1 -> M5 server-side (DoD t_86507d65 opsi 1).

    Paper runner 5m tidak lagi bergantung seed EA (yang menyangkut di M1
    sejak 20 Nov 2026). Sumber: baris candle M1 dalam window [since, until)
    — kunci ts-nya true UTC dari pipeline tick.

    Kunci ts M5 hasil rollup = bucket_true + (offset broker - offset tz DB).
    Terukur 2026-11-22: jam server A1 = UTC+7 = tz sesi DB, sehingga
    shift = 0 — seed EA (string jam server) dan crawler sama-sama
    menyimpan candle di kunci true UTC, jadi rollup menyatu dengan series
    tanpa menimpa history, dan dibaca benar oleh paper runner maupun
    engine backtest (stored_to_utc dengan offset yang sama — konvensi
    paritas yang sama).
    """
    return await _rollup_tf(conn, src_tf="M1", dst_tf="M5", seconds=M5_SECONDS,
                            since=since, until=until, symbol=symbol)


async def rollup_m5_to_m15_h1(conn, *, since: datetime, until: datetime | None = None,
                              symbol: str | None = None) -> int:
    """Agregasi M5 -> M15 dan M5 -> H1 (multipair P2, t_f2mp3).

    Seed EA berhenti menyemai ulang M15/H1 sejak 20 Nov 2026 (macet di loop
    M1); strategi BTC H1 butuh series H1 yang hidup. Pola dan konvensi kunci
    sama dengan rollup M1->M5; sumber M5 hasil rollup yang sudah idempotent.
    """
    total = await _rollup_tf(conn, src_tf="M5", dst_tf="M15", seconds=M15_SECONDS,
                             since=since, until=until, symbol=symbol)
    total += await _rollup_tf(conn, src_tf="M5", dst_tf="H1", seconds=H1_SECONDS,
                              since=since, until=until, symbol=symbol)
    return total


async def rollup_cycle(conn) -> int:
    """Satu siklus rollup bertingkat untuk semua simbol, gap-aware.

    M1->M5, M5->M15/H1, H1->H4, H4->D1 (``ROLLUP_CHAIN``, urut dependency).
    Window sumber per simbol & tujuan = sejak max(bar tujuan terakhir) + 1
    bucket (menutup gap feed mati), dibatasi minimal window 15 menit terakhir
    (menjaga bar berjalan & 2 bucket sebelumnya tetap konvergen), dan maksimal
    AUTOHEAL_MAX_LOOKBACK_S ke belakang (anti overscroll saat series kosong).

    Sebelum kartu ini H4/D1 tidak pernah di-rollup: hanya terisi seed EA
    (CopyRates), sehingga series H4/D1 mati begitu EA berhenti menyemai.
    """
    now = utcnow()
    db_tz = await _db_tz_offset_h(conn)
    shift_h = broker_utc_offset_hours(now) - db_tz
    floor_lookback = now - timedelta(seconds=AUTOHEAL_MAX_LOOKBACK_S)
    cur = await conn.execute(
        "SELECT DISTINCT symbol FROM candles WHERE timeframe = 'M1' AND ts >= %s",
        (floor_lookback,),
    )
    symbols = [r["symbol"] for r in await cur.fetchall()]
    total = 0
    for sym in symbols:
        for _src_tf, dst_tf, seconds in ROLLUP_CHAIN:
            cur = await conn.execute(
                "SELECT max(ts) AS m FROM candles WHERE symbol = %s AND timeframe = %s",
                (sym, dst_tf),
            )
            row = await cur.fetchone()
            last_dst = row["m"] if row else None
            if last_dst is not None:
                # bucket berikutnya setelah bar terakhir, dalam basis true UTC
                gap_start = last_dst - timedelta(hours=shift_h) + timedelta(seconds=seconds)
            else:
                gap_start = floor_lookback
            since = min(gap_start, now - timedelta(seconds=ROLLUP_LOOKBACK_S))
            since = max(since, floor_lookback)
            # Selaraskan jendela sumber ke grid bucket sumber. Bar sumber H4/D1
            # dimulai di grid (UTC-2 jam), jadi bar H4 terakhir bisa berumur
            # hampir 4 jam walau baru ditulis: tanpa pembulatan ke bawah,
            # tahap H4->D1 tidak pernah melihatnya dan D1 berhenti terisi.
            src_sec = _TF_SECONDS.get(_src_tf, seconds)
            src_grid = GRID_OFFSET_S.get(_src_tf, 0) - GRID_OFFSET_S.get(dst_tf, 0)
            epoch = since.timestamp()
            since = datetime.fromtimestamp(
                ((epoch - src_grid) // src_sec) * src_sec + src_grid - src_sec,
                tz=timezone.utc)
            total += await _rollup_tf(conn, src_tf=_src_tf, dst_tf=dst_tf,
                                      seconds=seconds, symbol=sym,
                                      since=since, until=now)
    return total


async def _ensure_months(conn, months: set[str], cache: set[str]) -> None:
    """CREATE TABLE IF NOT EXISTS partisi bulanan candles untuk set bulan.

    Deployment dengan `candles` TABEL BIASA (seed legacy, bukan partitioned)
    tidak memakai partisi: pembuatan partisi dilewati dan semua baris tetap
    tersimpan di tabel induk. Tanpa ini, InvalidObjectDefinition
    ('"candles" is not partitioned') mematikan seluruh siklus ingest/rollup
    (insiden 24 Nov 2026: candle M1/M5 berhenti tumbuh sejak restart API).
    """
    row = await conn.execute(
        "SELECT 1 AS ok FROM pg_partitioned_table pt "
        "JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'candles'")
    if (await row.fetchone()) is None:
        cache.update(months)  # tabel biasa: tidak perlu partisi, jangan gagalkan siklus
        return
    for m in sorted(months - cache):
        y, mo = (int(x) for x in m.split("-"))
        start = f"{y:04d}-{mo:02d}-01"
        ny, nm = (y + 1, 1) if mo == 12 else (y, mo + 1)
        end = f"{ny:04d}-{nm:02d}-01"
        await conn.execute(
            f"CREATE TABLE IF NOT EXISTS candles_{y:04d}_{mo:02d} PARTITION OF candles "
            f"FOR VALUES FROM ('{start}') TO ('{end}')",
        )
        cache.add(m)


_ensured_months_rollup: set[str] = set()  # cache partisi jalur rollup (per proses)


async def _ensure_range_partitions(conn, start: datetime, end: datetime) -> None:
    """Pastikan partisi bulanan candles tersedia untuk rentang kunci [start, end)."""
    months: set[str] = {f"{start:%Y-%m}", f"{end:%Y-%m}"}
    # rentang kecil (<= 48 jam): maksimal menyentuh 2 bulan, tapi jaga-jaga
    # bila rentang lebih panjang — jalan per bulan.
    t = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while t <= end:
        months.add(f"{t:%Y-%m}")
        t = (t + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0,
                                             microsecond=0)
    await _ensure_months(conn, months, _ensured_months_rollup)


class IngestPipeline:
    def __init__(self, parquet_dir: str | Path | None = None) -> None:
        self.parquet_dir = Path(parquet_dir) if parquet_dir else Path(config.TICKS_PARQUET_DIR)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self._ticks: deque[dict] = deque(maxlen=RING_MAX)
        self._candles: dict[tuple, dict] = {}          # coalesce per (symbol, timeframe, ts)
        self._m1_current: dict[str, dict] = {}         # bar M1 berjalan per symbol
        self._htf_current: dict[tuple, dict] = {}      # (symbol, tf) -> bar berjalan M5+
        self._liq_open: dict[str, dict] = {}           # jendela 5 dtk per symbol (belum tutup)
        self._liq_ready: dict[tuple, dict] = {}        # jendela tertutup, nunggu tulis DB
        self._ensured_months: set[str] = set()
        self._last_write_duration = 0.0
        self.dropped_samples = 0                       # dibuang karena backpressure
        self.ticks_buffered = 0
        self.ticks_frozen_skipped = 0                  # tick beku: diaudit, tanpa bar
        self.ticks_bad_skipped = 0                     # tick loncatan/basi: diaudit, tanpa bar
        self.parquet_rows_written = 0
        self.samples_written = 0
        self.candles_written = 0
        self.candles_rejected = 0     # ditolak validasi PRD 4.4
        self.rollup_rows_written = 0                    # bar hasil rollup bertingkat (M5/M15/H1)
        self.liquidity_backfilled = 0                   # jendela 5 dtk dipulihkan dari parquet
        self._last_quote: dict[str, tuple[float, float]] = {}
        self._last_quote_change: dict[str, datetime] = {}
        self._quote_moved: set[str] = set()   # simbol yang sudah terlihat bergerak
        self._last_good_bid: dict[str, float] = {}   # baseline anti tick basi
        self._bad_candidate: dict[str, tuple[float, int]] = {}  # (price, count)
        # Bukti feed hidup per simbol: kapan terakhir ada tick yang LOLOS freeze
        # guard (harga benar-benar bergerak). Dipakai market_status sebagai
        # bukti "pasar buka" ketika tidak ada laporan EA dan tidak ada jadwal.
        # Bukan `market.latest` (tick beku tetap masuk store, jadi umurnya
        # selalu kecil walau pasar tutup).
        self._last_live_mono: dict[str, float] = {}
        self.bars_suppressed_closed = 0   # bar datar yang TIDAK dibuat (tutup/gap/beku)
        self.candles_closed_synthetic = 0  # candle kosong di jendela tutup: dibuang
        self._session_rows: dict[str, list[dict]] = {}   # jadwal sesi untuk filter

    # ------------------------------------------------------------- bukti feed
    def feed_age_s(self, symbol: str) -> float | None:
        """Umur (detik) tick terakhir yang lolos freeze guard, atau None.

        None = proses ini belum pernah melihat tick yang bergerak untuk simbol
        itu: tidak ada bukti apa pun, jadi pemanggil tidak boleh menyimpulkan
        "buka" maupun "tutup" dari angka ini.
        """
        last = self._last_live_mono.get(symbol)
        if last is None:
            return None
        return max(0.0, time.monotonic() - last)


    # ------------------------------------------------------------- ingest (tanpa DB)
    def add_tick(self, symbol: str, bid: float, ask: float,
                 spread: float | None = None, ts=None) -> None:
        """Masukkan tick ke ring buffer + agregator likuiditas. Murni memori."""
        now = utcnow()
        if spread is None:
            spread = round(float(ask) - float(bid), 5)
        rec = {
            "ts_utc": f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond // 1000:03d}Z",
            "tick_ts": ts,
            "symbol": symbol,
            "bid": float(bid),
            "ask": float(ask),
            "spread": float(spread),
            "session": session_of(now),
        }
        self._ticks.append(rec)
        self.ticks_buffered += 1
        if self._quote_frozen(symbol, float(bid), float(ask), now):
            self.ticks_frozen_skipped += 1
            return  # tick tetap diaudit di ring buffer, tapi tidak jadi bar
        if self._quote_jumps(symbol, float(bid)):
            self.ticks_bad_skipped += 1
            return  # tick basi/loncatan tidak wajar: audit saja, bukan bar
        # Tick ini lolos freeze guard: bukti feed hidup (market_status).
        self._last_live_mono[symbol] = time.monotonic()
        self._agg_liquidity(symbol, float(spread), now)
        self._agg_m1(symbol, float(bid), now)

    def _quote_jumps(self, symbol: str, bid: float) -> bool:
        """True bila kutipan melompat >MAX_QUOTE_JUMP_PCT dari baseline sehat.

        Kutipan basi EA (insiden 23 Nov 2026: XAUUSD 2001.10 — harga lama
        cache EA — muncul intermiten di tengah harga 3600) mencemari low/high
        bar M1 sehingga range Asia meledak dan strategi menolak sinyal.
        Tick loncatan ditolak; bila level baru bertahan MAX_JUMP_CONFIRM_TICKS
        tick beruntun, level itu dianggap harga baru yang sehat (gap pasar
        asli tetap lewat, kehilangan beberapa tick pertama saja).
        """
        base = self._last_good_bid.get(symbol)
        if base is None or base <= 0:
            self._last_good_bid[symbol] = bid
            return False
        if abs(bid - base) / base <= MAX_QUOTE_JUMP_PCT / 100.0:
            self._last_good_bid[symbol] = bid
            self._bad_candidate.pop(symbol, None)
            return False
        cand = self._bad_candidate.get(symbol)
        if cand is not None and abs(bid - cand[0]) / cand[0] <= 0.001:
            count = cand[1] + 1
            if count >= MAX_JUMP_CONFIRM_TICKS:
                self._last_good_bid[symbol] = bid
                self._bad_candidate.pop(symbol, None)
                return False  # level baru terkonfirmasi: harga sehat kembali
            self._bad_candidate[symbol] = (bid, count)
            return True
        self._bad_candidate[symbol] = (bid, 1)
        return True

    def _quote_frozen(self, symbol: str, bid: float, ask: float, now: datetime) -> bool:
        """True bila kutipan tidak berubah > FREEZE_TIMEOUT_S (pasar tutup).

        EA/bridge mengulang kutipan terakhir ~1x/dtk meski market tutup
        (insiden t_86507d65: 35 ribu tick XAUUSD beku di harga close Jumat
        sepanjang akhir pekan, exchange_ts tetap berjalan). Tick beku boleh
        dicatat untuk audit, tapi tidak boleh jadi bar: bar flat buatan
        bisa memicu sinyal palsu di pembukaan dan M5-nya mengotori seri.

        Kutipan pertama yang terlihat proses BELUM diverifikasi bergerak:
        diagregasi hanya setelah perubahan harga pertama teramati. Tanpa
        ini, ~FREEZE_TIMEOUT_S tick beku pasca-restart jadi bar flat
        (insiden nyata 22 Nov 18:05 UTC: bar flat XAUUSD muncul tiap
        restart API di akhir pekan). Biaya: bar M1 pertama pasca-restart
        live kehilangan tick sebelum perubahan harga pertama (sub-detik
        di pasar aktif) — jauh lebih murah daripada bar palsu.
        """
        prev = self._last_quote.get(symbol)
        if prev is None:
            self._last_quote[symbol] = (bid, ask)
            self._last_quote_change[symbol] = now
            return True  # belum pernah lihat harga bergerak: tahan dulu
        if prev != (bid, ask):
            self._last_quote[symbol] = (bid, ask)
            self._last_quote_change[symbol] = now
            self._quote_moved.add(symbol)
            return False
        if symbol not in self._quote_moved:
            return True  # kutipan belum pernah berubah sejak proses start
        changed = self._last_quote_change.get(symbol, now)
        return (now - changed).total_seconds() > FREEZE_TIMEOUT_S

    def _agg_liquidity(self, symbol: str, spread: float, now: datetime) -> None:
        window_start = int(now.timestamp() // LIQUIDITY_WINDOW_S) * LIQUIDITY_WINDOW_S
        w = self._liq_open.get(symbol)
        if w is not None and w["window_start"] != window_start:
            self._close_window(symbol, w)
            w = None
        if w is None:
            w = {"window_start": window_start, "session": session_of(now),
                 "spreads": []}
            self._liq_open[symbol] = w
        w["spreads"].append(spread)

    def _close_window(self, symbol: str, w: dict) -> None:
        key = (symbol, w["window_start"])
        spreads = w["spreads"]
        self._liq_ready[key] = {
            "symbol": symbol,
            "window_start": datetime.fromtimestamp(w["window_start"], tz=timezone.utc),
            "session": w["session"],
            "spread_avg": round(sum(spreads) / len(spreads), 5),
            "spread_min": min(spreads),
            "spread_max": max(spreads),
            "tick_count": len(spreads),
        }

    def _agg_m1(self, symbol: str, bid: float, now: datetime) -> None:
        """Agregasi tick -> candle M1 (PRD 5.1: Postgres hanya candle M1+).

        OHLC dari bid (konvensi MT5), volume = jumlah tick. Bar berjalan
        di-coalesce ke antrean setiap tick sehingga candle live ter-upsert
        tiap flush DB (5 dtk); saat menit berganti, bar selesai ditulis
        final sebelum bar baru dimulai.

        Anti bar datar (kartu candle pipeline): bar BARU hanya dibuka bila
        tick membawa sesuatu yang baru. Kutipan yang tidak berubah (volume
        "tick-gap filler") TIDAK membuka bar baru ketika pasar tutup menurut
        EA maupun jadwal sesi, ketika jarak ke bar terakhir sudah
        >= FREEZE_TIMEOUT_S, atau ketika harga sudah beku
        >= FLAT_BAR_MAX_QUIET_S. Akibatnya bar terakhir sebelum tutup
        dibiarkan utuh dan bar berikutnya baru lahir dari tick pertama sesi
        buka — bukan dari pengulangan harga beku sepanjang akhir pekan.
        """
        minute = (int(now.timestamp()) // 60) * 60
        ts = datetime.fromtimestamp(minute, tz=timezone.utc)
        cur = self._m1_current.get(symbol)
        if cur is not None and cur["ts"] != ts and self._suppress_new_bar(
                symbol, cur, float(bid), ts, now):
            return
        if cur is None or cur["ts"] != ts:
            if cur is not None:
                self._candles[(cur["symbol"], cur["timeframe"], cur["ts"])] = dict(cur)
            cur = {"symbol": symbol, "timeframe": "M1", "ts": ts,
                   "open": bid, "high": bid, "low": bid, "close": bid,
                   "volume": 0, "source": SOURCE_EA}
            self._m1_current[symbol] = cur
        if bid > cur["high"]:
            cur["high"] = bid
        if bid < cur["low"]:
            cur["low"] = bid
        cur["close"] = bid
        cur["volume"] += 1
        self._candles[(symbol, "M1", ts)] = dict(cur)

        # Bar berjalan M5+ ikut tick yang sama. Tanpa ini candle berjalan
        # hanya berisi detik-detik pertama bucket (EA mengirim shift=0 sekali
        # per bucket), sehingga chart menampilkan candle datar lalu melompat
        # ke harga pembukaan setiap refresh.
        self._agg_htf(symbol, bid, ts)

    def _agg_htf(self, symbol: str, bid: float, m1_ts: datetime) -> None:
        """Agregasi tick -> bar BERJALAN M5/M15/H1/H4/D1 (source='live').

        Kunci ts = bucket dari kunci M1 (ruang kunci yang sama dengan bar EA
        dan rollup, sehingga upsert saling menimpa tanpa bar ganda). Saat
        bucket tutup, bar 'live' digantikan bar final dari EA (shift=1) atau
        rollup M1->M5 (upsert hanya menolak menimpa source='ea').

        Volume dihitung sebagai jumlah tick, sama seperti bar M1 berjalan;
        bar final dari EA membawa volume tick MT5 yang sebenarnya.
        """
        epoch = int(m1_ts.timestamp())
        for tf, seconds in LIVE_HTF:
            bucket = datetime.fromtimestamp(bucket_epoch(epoch, seconds, tf),
                                            tz=timezone.utc)
            key = (symbol, tf)
            cur = self._htf_current.get(key)
            if cur is None or cur["ts"] != bucket:
                if cur is not None:
                    self._candles[(symbol, tf, cur["ts"])] = dict(cur)
                cur = {"symbol": symbol, "timeframe": tf, "ts": bucket,
                       "open": bid, "high": bid, "low": bid, "close": bid,
                       "volume": 0, "source": SOURCE_LIVE}
                self._htf_current[key] = cur
            if bid > cur["high"]:
                cur["high"] = bid
            if bid < cur["low"]:
                cur["low"] = bid
            cur["close"] = bid
            cur["volume"] += 1
            self._candles[(symbol, tf, bucket)] = dict(cur)

    def set_session_rows(self, rows: dict[str, list[dict]]) -> None:
        """Pasang cache jadwal sesi simbol (dipakai filter candle kosong)."""
        self._session_rows = {str(k).upper(): v for k, v in (rows or {}).items() if v}

    def _schedule_closed(self, symbol: str, ts: datetime) -> bool:
        """True bila `ts` jatuh di luar jadwal sesi simbol.

        Fail-open: simbol tanpa baris jadwal (atau ts tanpa tz) bukan bukti
        tutup, jadi kembalikan False. Dipakai untuk menolak candle kosong dari
        seed EA di jendela pasar tutup (jeda harian 05:00-05:59, akhir pekan),
        bukan untuk gate order.
        """
        rows = self._session_rows.get(str(symbol).upper())
        if not rows:
            return False
        if ts.tzinfo is None:
            return False
        try:
            return not market_sessions.session_open(rows, ts)[0]
        except Exception:  # noqa: BLE001 - jadwal rusak tidak boleh menjatuhkan ingest
            return False

    async def refresh_session_rows(self) -> int:
        """Muat ulang jadwal sesi dari DB (read-only, toleran gagal)."""
        try:
            async with db.pool().connection() as conn:
                rows = await market_sessions.load_all(conn)
        except Exception as exc:  # noqa: BLE001 - pakai cache lama bila DB down
            print(f"[ingest] jadwal sesi gagal dimuat (cache lama dipakai): {exc!r}",
                  flush=True)
            return 0
        self.set_session_rows(rows)
        return len(rows)

    def _suppress_new_bar(self, symbol: str, cur: dict, bid: float,
                          ts: datetime, now: datetime | None = None) -> bool:
        """True bila tick ini TIDAK boleh membuka bar M1 baru (bar datar palsu).

        Syarat supresi: harga tidak berubah dari close bar terakhir DAN salah
        satu dari:
        - EA melaporkan pasar tutup, atau jadwal sesi bilang `ts` di luar jam;
        - jarak ke bar terakhir >= FREEZE_TIMEOUT_S (feed mati lama);
        - harga sudah beku >= FLAT_BAR_MAX_QUIET_S (feed mengulang kutipan
          terakhir walau baru 2 menit: bar berikutnya pasti kosong).
        Tick dengan harga baru selalu menang: pembukaan sesi tidak pernah
        kehilangan bar pertamanya.
        """
        try:
            unchanged = abs(bid - float(cur.get("close"))) < 1e-9
        except (TypeError, ValueError):
            return False
        if not unchanged:
            return False
        gap_s = (ts - cur["ts"]).total_seconds()
        try:
            from . import market_status

            closed = market_status.closed_flag(symbol)
        except Exception:  # noqa: BLE001 - registry belum ada: pakai bukti gap saja
            closed = False
        if not closed:
            closed = self._schedule_closed(symbol, ts)
        quiet_s = 0.0
        changed = self._last_quote_change.get(symbol)
        if changed is not None and now is not None:
            quiet_s = (now - changed).total_seconds()
        if closed or gap_s >= FREEZE_TIMEOUT_S or quiet_s >= FLAT_BAR_MAX_QUIET_S:
            self.bars_suppressed_closed += 1
            return True
        return False

    def _synthetic_in_closed(self, candle: dict, ts: datetime) -> bool:
        """True bila candle kosong (flat atau volume 0) di jendela pasar tutup.

        Seed EA mengirim riwayat termasuk jendela tutup (jeda harian dan akhir
        pekan) dengan harga terakhir broker: O=H=L=C dan sering volume 0.
        Bar seperti itu bukan aktivitas pasar, jadi tidak boleh masuk series.
        Bar yang benar-benar bergerak tetap diterima walau jadwal bilang tutup
        (jadwal bisa salah; data nyata menang).
        """
        try:
            hi = float(candle.get("high") or 0)
            lo = float(candle.get("low") or 0)
            vol = float(candle.get("volume") or 0)
        except (TypeError, ValueError):
            return False
        if hi != lo and vol > 0:
            return False
        return self._schedule_closed(str(candle.get("symbol", "")), ts)

    def add_candles(self, candles: list[dict]) -> int:
        """Antrean candle (coalesce per key; tulis DB di background).

        Nama timeframe dinormalisasi ke kanonik PRD (1m->M1, 5m->M5, ...)
        supaya seed EA lama, crawler, dan agregasi tick memakai satu seri.

        Validasi PRD 4.4: candle rusak (OHLC konsisten, harga <= 0, volume
        negatif, ts masa depan) DITOLAK — tidak masuk antrean. Candle KOSONG
        (flat/volume 0) yang jatuh di jendela pasar tutup menurut jadwal sesi
        juga dibuang: itu jejak seed EA di jeda harian/akhir pekan, bukan
        aktivitas pasar. Return jumlah candle ditolak (respons /bridge/tick
        "flagged").
        """
        validator = validate.get_validator()
        rejected_n = 0
        for c in candles:
            tf = _TF_CANON.get(str(c.get("timeframe", "")), str(c.get("timeframe", "")))
            issues = validator.check_candle(
                c.get("symbol", ""), tf, c.get("ts"),
                c.get("open", 0), c.get("high", 0), c.get("low", 0),
                c.get("close", 0), c.get("volume", 0))
            if validate.rejected(issues):
                rejected_n += 1
                print(f"[ingest] candle ditolak: {[i.code for i in issues]} "
                      f"({c.get('symbol')} {tf} {c.get('ts')})", flush=True)
                continue
            ts_dt, _kind = validate._parse_ts(c.get("ts"))
            if ts_dt is not None and self._synthetic_in_closed(c, ts_dt):
                rejected_n += 1
                self.candles_closed_synthetic += 1
                print(f"[ingest] candle kosong di pasar tutup dibuang "
                      f"({c.get('symbol')} {tf} {ts_dt.isoformat()})", flush=True)
                continue
            row = {**c, "timeframe": tf, "source": _source_of(c)}
            # Bar yang ts-nya masih bucket BERJALAN adalah bar parsial
            # (EA mengirim shift=0 sekali per bucket). Menyimpannya sebagai
            # 'ea' membuatnya kebal terhadap rollup (upsert rollup menolak
            # menimpa source='ea'), sehingga bar membeku di harga pembukaan
            # sampai bucket tutup. Simpan sebagai 'live' supaya agregasi M1
            # (rollup) atau tick di server boleh menyegarkannya; saat bucket
            # tutup EA mengirim bar final untuk ts yang sama dan kembali
            # menjadi 'ea'.
            if (ts_dt is not None
                    and _source_of(c) == SOURCE_EA
                    and tf in _TF_SECONDS
                    and ts_dt <= utcnow() < ts_dt + timedelta(seconds=_TF_SECONDS[tf])):
                row["source"] = SOURCE_LIVE
            key = (c["symbol"], tf, c["ts"])
            self._candles[key] = row
        self.candles_rejected += rejected_n
        return rejected_n

    # ------------------------------------------------------------- background loop
    async def run(self, stop: asyncio.Event) -> None:
        # Auto-heal M1->M5 saat start (DoD t_86507d65): isi ulang bar M5 yang
        # hilang saat feed mati (insiden 20 Nov 2026) tanpa menunggu seed EA.
        # Non-fatal: kegagalan tidak boleh mematikan pipeline.
        try:
            async with db.pool().connection() as conn:
                healed = await rollup_cycle(conn)
            if healed:
                print(f"[ingest] auto-heal M1->M5: {healed} bar ditulis", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[ingest] auto-heal M5 gagal (dilewati): {exc!r}", flush=True)

        last_parquet = time.monotonic()
        last_db = time.monotonic()
        last_sched = 0.0   # 0 = muat jadwal sesi segera setelah start
        last_heal = 0.0    # 0 = pulihkan celah likuiditas segera setelah start
        while not stop.is_set():
            await asyncio.sleep(1.0)  # tanpa wait_for: timeout tidak boleh mematikan task
            # tutup jendela likuiditas yang sudah lewat (tick berhenti pun
            # jendela terakhir tetap tersimpan)
            now_ts = time.time()
            for symbol, w in list(self._liq_open.items()):
                if now_ts >= w["window_start"] + LIQUIDITY_WINDOW_S:
                    self._close_window(symbol, w)
                    del self._liq_open[symbol]
            now = time.monotonic()
            if now - last_sched >= SESSION_REFRESH_S:
                await self.refresh_session_rows()
                last_sched = time.monotonic()
            if now - last_db >= DB_FLUSH_S:
                await self._flush_db()
                last_db = time.monotonic()
            if now - last_parquet >= FLUSH_PARQUET_S:
                await self._flush_parquet()
                last_parquet = time.monotonic()
            if now - last_heal >= LIQ_HEAL_INTERVAL_S:
                await self._heal_liquidity()
                last_heal = time.monotonic()
        # shutdown: flush terakhir
        await self.flush_now()

    async def _heal_liquidity(self) -> None:
        """Rekonstruksi celah `liquidity_samples` dari parquet tick sendiri.

        Celah lahir dari restart, backpressure, atau event loop tersendat.
        Dipanggil di loop: sekali tepat setelah start, lalu tiap
        LIQ_HEAL_INTERVAL_S. Tidak pernah melempar: kegagalan hanya warning.
        """
        from .liquidity_heal import heal_liquidity_gaps

        try:
            async with db.pool().connection() as conn:
                filled = await heal_liquidity_gaps(conn, parquet_dir=self.parquet_dir)
            if filled:
                self.liquidity_backfilled += filled
                print(f"[ingest] self-heal likuiditas: {filled} jendela dipulihkan")
        except Exception as exc:  # noqa: BLE001 — pemeliharaan data tak boleh mematikan ingest
            print(f"[ingest] self-heal likuiditas dilewati: {exc}")

    async def flush_now(self) -> None:
        """Tulis semua yang tertahan (dipakai test + shutdown)."""
        # tutup jendela likuiditas yang masih terbuka
        now = time.time()
        for symbol, w in list(self._liq_open.items()):
            if now >= w["window_start"] + LIQUIDITY_WINDOW_S:
                self._close_window(symbol, w)
                del self._liq_open[symbol]
        await self._flush_parquet()
        await self._flush_db()

    # ------------------------------------------------------------- parquet
    def _write_parquet_sync(self) -> int:
        import pandas as pd

        if not self._ticks:
            return 0
        rows = [self._ticks.popleft() for _ in range(len(self._ticks))]
        df = pd.DataFrame(rows)
        written = 0
        for day, g in df.groupby(df["ts_utc"].str[:10]):
            p = self.parquet_dir / f"ticks_{day}.parquet"
            if p.exists():
                g = pd.concat([pd.read_parquet(p), g], ignore_index=True)
            g.to_parquet(p, index=False, compression="snappy")
            written += len(g)
        return written

    async def _flush_parquet(self) -> None:
        if not self._ticks:
            return
        try:
            written = await asyncio.to_thread(self._write_parquet_sync)
            self.parquet_rows_written += written
        except Exception as exc:  # noqa: BLE001
            # parquet gagal (mis. disk penuh): buffer dipertahankan, coba lagi
            # di siklus berikutnya; ring buffer membatasi memori.
            print(f"[ingest] flush parquet gagal: {exc!r}", flush=True)

    # ------------------------------------------------------------- DB
    async def _ensure_candle_partitions(self, conn, candles: list[dict]) -> None:
        months = set()
        for c in candles:
            try:
                ts = c["ts"]
                if isinstance(ts, str):
                    # dukung ISO ("2026-11-21T10:00:00") dan format EA
                    # TimeToString ("2026.11.21 10:00")
                    m = ts[:7].replace(".", "-")  # "2026-11"
                else:
                    m = f"{ts.year:04d}-{ts.month:02d}"
                months.add(m)
            except Exception:
                continue
        months.add(f"{utcnow():%Y-%m}")
        await _ensure_months(conn, months, self._ensured_months)

    async def _flush_db(self) -> None:
        t0 = time.monotonic()
        # Backpressure PRD: siklus tulis sebelumnya > 5 dtk -> buang sampel
        # likuiditas siklus ini (bukan event order; event order tidak pernah
        # melewati pipeline ini).
        if self._last_write_duration > BACKPRESSURE_S and self._liq_ready:
            self.dropped_samples += len(self._liq_ready)
            print(f"[ingest] backpressure {self._last_write_duration:.1f}s > "
                  f"{BACKPRESSURE_S}s: buang {len(self._liq_ready)} sampel likuiditas",
                  flush=True)
            self._liq_ready.clear()

        try:
            async with db.pool().connection() as conn:
                if self._liq_ready:
                    rows = list(self._liq_ready.values())
                    cur = conn.cursor()
                    await cur.executemany(
                        """
                        INSERT INTO liquidity_samples (symbol, window_start, session,
                                                       spread_avg, spread_min, spread_max,
                                                       tick_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, window_start) DO UPDATE SET
                            session = EXCLUDED.session,
                            spread_avg = EXCLUDED.spread_avg, spread_min = EXCLUDED.spread_min,
                            spread_max = EXCLUDED.spread_max, tick_count = EXCLUDED.tick_count
                        """,
                        [(r["symbol"], r["window_start"], r["session"], r["spread_avg"],
                          r["spread_min"], r["spread_max"], r["tick_count"]) for r in rows],
                   )
                    await cur.close()
                    self._liq_ready.clear()
                    self.samples_written += len(rows)

                if self._candles:
                    candles = list(self._candles.values())
                    await self._ensure_candle_partitions(conn, candles)
                    cur = conn.cursor()
                    await cur.executemany(
                        """
                        INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
                            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                            close = EXCLUDED.close, volume = EXCLUDED.volume,
                            source = EXCLUDED.source
                        """,
                        [(c["symbol"], c["timeframe"], c["ts"], c["open"], c["high"],
                          c["low"], c["close"], c.get("volume", 0),
                          c.get("source") or SOURCE_EA) for c in candles],
                    )
                    await cur.close()
                    self._candles.clear()
                    self.candles_written += len(candles)

                # Rollup M1->M5 server-side (DoD t_86507d65 opsi 1): paper
                # runner 5m tidak lagi bergantung seed EA. Sumber = bar M1
                # window terbaru (kunci true UTC pipeline); kunci M5 =
                # bucket true (server A1 = UTC+7 = tz DB, shift 0) sehingga
                # menyatu dengan series seed EA/crawler & dibaca benar runner.
                self.rollup_rows_written += await rollup_cycle(conn)
        except Exception as exc:  # noqa: BLE001
            # Tulis DB gagal (mis. partisi/liga/schema): buffer DIPERTAHANKAN,
            # dicoba lagi siklus berikutnya; task background tidak boleh mati
            # (flusher mati = candle & liquidity_samples berhenti terisi).
            print(f"[ingest] flush DB gagal (buffer dipertahankan, retry): {exc!r}",
                  flush=True)

        self._last_write_duration = time.monotonic() - t0


# --------------------------------------------------------------------- global
_pipeline: IngestPipeline | None = None


def get_pipeline() -> IngestPipeline:
    """Pipeline aktif; dibuat lazily bila belum ada (mis. saat test)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestPipeline()
    return _pipeline


def reset_pipeline(parquet_dir: str | Path | None = None) -> IngestPipeline:
    """Ganti pipeline global (dipakai test untuk parquet dir sementara)."""
    global _pipeline
    _pipeline = IngestPipeline(parquet_dir=parquet_dir)
    return _pipeline
