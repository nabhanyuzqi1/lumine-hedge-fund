"""Reparasi candle kosong (flat / volume 0) di jendela pasar tutup.

Seed EA mengirim riwayat CopyRates termasuk jeda harian (XAUUSD 05:00-05:59
WIB) dan akhir pekan. Broker mengisi jendela itu dengan harga terakhir:
O=H=L=C, sering volume 0. Bar itu bukan aktivitas pasar, tetapi ikut
ter-rollup ke M5/M15/H1 sehingga histogram chart tampak acak dan sinyal
pembukaan bisa terpicu dari harga palsu.

Skrip ini:
  1. membangun jendela tutup dari tabel `market_sessions` (sumber yang juga
     dipakai gate order),
  2. menambahkan jendela "feed beku": rentetan bar flat berurutan >=
     `--freeze-min` menit (default 30). Ini menangkap jeda historis yang
     tidak lagi cocok dengan jadwal karena broker menggeser jamnya (DST):
     contoh nyata, jeda harian XAUUSD pindah dari 04:00-04:59 menjadi
     05:00-05:59 WIB pada 1 Nov 2026, jadi 31 ribu bar flat lama tidak
     tertangkap jadwal bila hanya memakai aturan "sekarang",
  3. menghapus bar M1 flat di jendela itu dan bar M5/M15/H1 flat yang
     bucket-nya seluruhnya di dalam jendela, dan
  4. membangun ulang rollup dari M1 untuk rentang yang sama.

Default DRY-RUN (hanya menghitung). Pakai `--apply` untuk menulis.

Pekerjaan dipecah per potongan `--chunk-days` (default 14). Rentang besar
(800 hari) dalam satu pernyataan DELETE melampaui `statement_timeout` server,
jadi tiap potongan dihitung, dihapus, dan di-rollup sendiri-sendiri.

Catatan operasional:
  - JIT dimatikan per koneksi: runtime PG bundling tidak membawa libLLVM.
  - Jendela dikirim sebagai array (unnest), bukan temp table dalam satu
    transaksi panjang. Menahan transaksi selama rollup membuat koneksi kena
    `idle_in_transaction_session_timeout`: COMMIT gagal dan seluruh hapusan
    di-rollback tanpa error di baris perintah.

Contoh:
    ./.venv/bin/python scripts/repair_flat_closed_candles.py --days 60
    ./.venv/bin/python scripts/repair_flat_closed_candles.py --days 60 --apply
    ./.venv/bin/python scripts/repair_flat_closed_candles.py --days 800 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, ingest, market_sessions  # noqa: E402

UTC = timezone.utc
DERIVED_TFS = (("M5", 300), ("M15", 900), ("H1", 3600))

# CTE jendela tutup: satu sumber kebenaran untuk hitung, hapus, dan verifikasi.
_WINDOWS = """
    w AS (
        SELECT * FROM unnest(%s::text[], %s::timestamptz[], %s::timestamptz[])
            AS t(symbol, t0, t1)
    )
"""


def _closed_intervals(rows: list[dict], start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Interval [t0, t1) saat simbol tutup, hasil pemindaian per menit."""
    out: list[tuple[datetime, datetime]] = []
    probe = start.replace(second=0, microsecond=0)
    run_start: datetime | None = None
    while probe < end:
        closed = not market_sessions.session_open(rows, probe)[0]
        if closed and run_start is None:
            run_start = probe
        elif not closed and run_start is not None:
            out.append((run_start, probe))
            run_start = None
        probe += timedelta(minutes=1)
    if run_start is not None:
        out.append((run_start, end))
    return out


class _Win:
    """Tiga array paralel siap dikirim ke `unnest`."""

    def __init__(self, windows: list[tuple[str, datetime, datetime]]) -> None:
        self.symbols = [w[0] for w in windows]
        self.t0s = [w[1] for w in windows]
        self.t1s = [w[2] for w in windows]

    def params(self) -> tuple[list[str], list[datetime], list[datetime]]:
        return (self.symbols, self.t0s, self.t1s)


@contextlib.asynccontextmanager
async def _conn():
    """Koneksi autocommit: tiap pernyataan langsung commit, JIT mati."""
    async with db.pool().connection() as conn:
        await conn.set_autocommit(True)
        await conn.execute("SET jit = off")
        await conn.execute("SET statement_timeout = '180s'")
        yield conn


async def _freeze_runs(conn, sym: str, start: datetime, end: datetime, min_len: int) -> list[tuple[str, datetime, datetime]]:
    """Rentetan bar flat berurutan >= min_len menit: jejak feed beku, bukan pasar.

    Dijadikan jendela tambahan karena jadwal sesi berlaku untuk "sekarang":
    broker yang menggeser jam (DST) memindahkan jeda harian satu jam lebih
    awal, jadi jeda historis tidak tertangkap jadwal.
    """
    if min_len <= 0:
        return []
    cur = await conn.execute(
        """WITH f AS (
               SELECT ts,
                      ts - (row_number() OVER (ORDER BY ts)) * interval '1 minute' AS grp
               FROM candles
               WHERE symbol = %s AND timeframe = 'M1' AND high = low
                 AND ts >= %s AND ts < %s
           )
           SELECT min(ts) t0, max(ts) + interval '1 minute' t1, count(*) n
           FROM f GROUP BY grp HAVING count(*) >= %s ORDER BY 1""",
        (sym, start, end, min_len))
    return [(sym, r["t0"], r["t1"]) for r in await cur.fetchall()]


async def _count(conn, win: _Win, start: datetime, end: datetime) -> tuple[list[dict], list[tuple[str, str, int]], list[dict]]:
    """Hitung (flat M1, bucket turunan penuh, M1 bergerak) dalam satu potongan."""
    wp = win.params()
    cur = await conn.execute(
        f"""WITH {_WINDOWS}
        SELECT c.symbol, count(*) AS n
        FROM candles c JOIN w ON c.symbol = w.symbol
         AND c.ts >= w.t0 AND c.ts < w.t1
        WHERE c.timeframe = 'M1' AND c.high = c.low
          AND c.ts >= %s AND c.ts < %s
        GROUP BY 1 ORDER BY 1""",
        (*wp, start, end))
    m1_plan = list(await cur.fetchall())

    derived: list[tuple[str, str, int]] = []
    for tf, secs in DERIVED_TFS:
        cur = await conn.execute(
            f"""WITH {_WINDOWS}
            SELECT c.symbol, count(*) AS n
            FROM candles c JOIN w ON c.symbol = w.symbol
             AND c.ts >= w.t0
             AND c.ts + (%s * interval '1 second') <= w.t1
            WHERE c.timeframe = %s AND c.high = c.low
              AND c.ts >= %s AND c.ts < %s
            GROUP BY 1 ORDER BY 1""",
            (*wp, secs, tf, start, end))
        derived.extend((r["symbol"], tf, int(r["n"])) for r in await cur.fetchall())

    cur = await conn.execute(
        f"""WITH {_WINDOWS}
        SELECT c.symbol, count(*) AS n
        FROM candles c JOIN w ON c.symbol = w.symbol
         AND c.ts >= w.t0 AND c.ts < w.t1
        WHERE c.timeframe = 'M1' AND c.high <> c.low
          AND c.ts >= %s AND c.ts < %s
        GROUP BY 1 ORDER BY 1""",
        (*wp, start, end))
    moving = list(await cur.fetchall())
    return m1_plan, derived, moving


async def _delete(conn, win: _Win, start: datetime, end: datetime) -> dict[str, int]:
    """Hapus M1 flat + bucket turunan penuh di jendela tutup, hanya dalam potongan."""
    wp = win.params()
    out: dict[str, int] = {}
    cur = await conn.execute(
        f"""WITH {_WINDOWS}
        DELETE FROM candles c USING w
        WHERE c.symbol = w.symbol AND c.timeframe = 'M1'
          AND c.ts >= w.t0 AND c.ts < w.t1
          AND c.high = c.low
          AND c.ts >= %s AND c.ts < %s""",
        (*wp, start, end))
    out["M1"] = cur.rowcount
    for tf, secs in DERIVED_TFS:
        cur = await conn.execute(
            f"""WITH {_WINDOWS}
            DELETE FROM candles c USING w
            WHERE c.symbol = w.symbol AND c.timeframe = %s
              AND c.high = c.low
              AND c.ts >= w.t0
              AND c.ts + (%s * interval '1 second') <= w.t1
              AND c.ts >= %s AND c.ts < %s""",
            (*wp, tf, secs, start, end))
        out[tf] = cur.rowcount
    return out


async def _rebuild(conn, symbols: list[str], start: datetime, end: datetime) -> int:
    """Rollup ulang dengan margin 1 hari di kedua sisi agar bucket batas utuh."""
    pad = timedelta(days=1)
    total = 0
    for sym in symbols:
        for src_tf, dst_tf, secs in ingest.ROLLUP_CHAIN:
            total += await ingest._rollup_tf(
                conn, src_tf=src_tf, dst_tf=dst_tf, seconds=secs,
                since=start - pad, until=end + pad, symbol=sym)
    return total


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hapus candle kosong di jendela pasar tutup")
    ap.add_argument("--symbols", default="", help="dipisah koma; default semua simbol berjadwal")
    ap.add_argument("--days", type=int, default=60, help="rentang ke belakang (hari)")
    ap.add_argument("--chunk-days", type=int, default=14, help="ukuran potongan kerja (hari)")
    ap.add_argument("--freeze-min", type=int, default=30,
                    help="hapus juga rentetan flat berurutan >= N menit (0 = nonaktif)")
    ap.add_argument("--apply", action="store_true", help="tulis perubahan (default dry-run)")
    ap.add_argument("--no-rebuild", action="store_true", help="jangan rollup ulang setelah hapus")
    args = ap.parse_args(argv)

    await db.init_pool()
    try:
        async with _conn() as conn:
            all_rows = await market_sessions.load_all(conn)
            wanted = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
            symbols = wanted or sorted(all_rows)
            now = datetime.now(UTC).replace(second=0, microsecond=0)
            since = now - timedelta(days=max(1, args.days))
            chunk = timedelta(days=max(1, args.chunk_days))
            print(f"rentang {since.isoformat()} .. {now.isoformat()} | simbol {symbols} | "
                  f"potongan {args.chunk_days} hari | mode {'APPLY' if args.apply else 'dry-run'}")

            missing = [s for s in symbols if not all_rows.get(s)]
            for s in missing:
                print(f"{s}: tidak ada jadwal sesi, dilewati")
            symbols = [s for s in symbols if all_rows.get(s)]
            if not symbols:
                print("tidak ada simbol berjadwal: selesai")
                return 0

            tot_m1 = tot_der = tot_rebuilt = 0
            grand_left = 0
            grand_moving = 0
            start = since
            while start < now:
                end = min(start + chunk, now)
                windows: list[tuple[str, datetime, datetime]] = []
                for sym in symbols:
                    windows.extend((sym, a, b) for a, b in _closed_intervals(all_rows[sym], start, end))
                if args.freeze_min > 0:
                    for sym in symbols:
                        windows.extend(await _freeze_runs(conn, sym, start, end, args.freeze_min))

                if not windows:
                    print(f"{start:%Y-%m-%d}: 0 jendela tutup, dilewati")
                    start = end
                    continue

                win = _Win(windows)
                m1_plan, derived, moving = await _count(conn, win, start, end)
                n_m1 = sum(int(r["n"]) for r in m1_plan)
                n_der = sum(n for _, _, n in derived)
                per_sym = ", ".join(f"{r['symbol']}={int(r['n'])}" for r in m1_plan) or "-"
                line = (f"{start:%Y-%m-%d}..{end:%Y-%m-%d}: {len(windows):>3} jendela | "
                        f"M1 flat {n_m1:>6} ({per_sym}) | turunan {n_der:>6}")
                grand_moving += sum(int(r["n"]) for r in moving)

                if args.apply:
                    removed = await _delete(conn, win, start, end)
                    rebuilt = 0
                    if not args.no_rebuild:
                        rebuilt = await _rebuild(conn, symbols, start, end)
                    tot_m1 += removed["M1"]
                    tot_der += sum(v for k, v in removed.items() if k != "M1")
                    tot_rebuilt += rebuilt
                    line += (f" | hapus M1 {removed['M1']:>6}, turunan "
                             f"{sum(v for k, v in removed.items() if k != 'M1'):>6}, "
                             f"rollup {rebuilt:>6}")
                print(line, flush=True)
                start = end

            if grand_moving:
                print(f"catatan: {grand_moving} bar M1 BERGERAK di jendela tutup DIPERTAHANKAN "
                      f"(data nyata menang atas jadwal)")

            if not args.apply:
                print("\ndry-run: tidak ada yang diubah. Ulangi dengan --apply.")
                return 0

            # Verifikasi ulang per potongan supaya tidak menabrak statement_timeout.
            start = since
            while start < now:
                end = min(start + chunk, now)
                windows = []
                for sym in symbols:
                    windows.extend((sym, a, b) for a, b in _closed_intervals(all_rows[sym], start, end))
                if windows:
                    win = _Win(windows)
                    m1_plan, _, _ = await _count(conn, win, start, end)
                    grand_left += sum(int(r["n"]) for r in m1_plan)
                start = end

            print(f"\ntotal dihapus: M1 {tot_m1}, turunan {tot_der}, rollup ditulis ulang {tot_rebuilt}")
            print("verifikasi: M1 flat tersisa di jendela tutup =",
                  grand_left if grand_left else "0 (bersih)")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
