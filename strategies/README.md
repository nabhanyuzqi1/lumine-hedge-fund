# Format Skill Strategi: Fund2 (PRD v2.1 §5.3)

Final 22 Nov 2026 (t_f2p2a6). Setiap strategi = **satu skill**: dokumen
`SKILL.md` + satu modul Python murni `decide(context) -> OrderIntent | None`.
Satu `decide()` yang sama dipakai backtest, paper, dan live (PRD §1: hanya
sumber data yang berbeda).

## Layout

| File | Isi |
| --- | --- |
| `strategies/<strategy_id>/SKILL.md` | Doc skill: logika, parameter, risk, hasil backtest, status |
| `api/strategies/<strategy_id>.py` | Modul murni: `decide()` + `OrderIntent` + `StrategyParams` |
| `api/tests/test_<strategy_id>.py` | Test kontrak + test logika strategi |
| `strategies/_template/` | Template strategy-author (SKILL.md + strategy.py + test) |

`<strategy_id>` = snake_case, sama untuk ketiganya, = `STRATEGY_ID` di modul.
SKILL.md wajib mencantumkan path modul + `STRATEGY_VERSION`; modul wajib
mencantumkan path SKILL.md. Keduanya berubah berpasangan (satu commit).

## Kontrak `decide()`

```python
def decide(context: dict, params: StrategyParams | None = None) -> OrderIntent | None
```

- `params=None` → pakai `StrategyParams()` default. Override owner masuk lewat
  settings `strategy_params_<id>` (hanya field yang dikenal yang diterapkan).
- Return `OrderIntent` (SL/TP wajib) atau `None` (tidak entry). `None` adalah
  hasil normal, bukan error.

### Skema `context` (read-only, snapshot per pemanggilan)

| Key | Tipe | Isi |
| --- | --- | --- |
| `symbol` | str | "XAUUSD" / "BTCUSD" |
| `now` | str ISO8601 UTC | waktu snapshot (true UTC, sudah termasuk offset broker) |
| `candles` | list[dict] | bar CLOSED, ascending, `ts` UTC ISO; `{ts, open, high, low, close, volume}` |
| `liquidity` | dict | `{ts, bid, ask, spread, spread_median_15m, fresh}`: snapshot tick terbaru |
| `positions` | list[dict] | posisi OPEN milik strategi ini (read-only) |
| `trades_today` | int | entry yang dibuka hari ini (UTC) |
| `risk` | dict | `{equity, risk_per_trade, max_volume, max_spread}` dari settings (read-only) |

Caller (paper runner / backtest) membangun context baru setiap pemanggilan.
Strategi **wajib memperlakukan context sebagai immutable**: tidak boleh
mutasi (no `sort()` in-place, `pop`, `setdefault`, assignment ke nested dict).
Butuh urutan lain → buat list baru. Inilah yang menjamin dua pemanggilan
dengan context sama menghasilkan output sama (reproduksi penuh, paritas
backtest vs paper).

### Skema `OrderIntent`

`@dataclass(frozen=True)`, didefinisikan di dalam modul strategi (self-contained,
tanpa import lintas strategi). Field wajib: `symbol`, `side` (`BUY`|`SELL`),
`volume` (lot), `sl`, `tp`. Field standar: `strategy`, `reason`,
`sl_distance`, `risk_usd`. **SL tanpa penalty**: risk gate menolak intent
tanpa SL valid (PRD §5.6).

## Regime (PRD v2.2 §6) - opsional

Strategi yang hanya boleh entry pada kondisi pasar tertentu mendeklarasikan
`ALLOWED_REGIMES = ["TREND_UP", ...]` (list pola) di modulnya. Label dari
classifier deterministic `app/regime.py` (lihat `docs/REGIME_v2.2.md`):
`TREND_UP, TREND_DOWN, RANGE, HIGH_VOLATILITY, LOW_LIQUIDITY, UNKNOWN`.

- Gate entry di runner/backtest: label harus ada di `ALLOWED_REGIMES` dan
  bukan `UNKNOWN` (UNKNOWN selalu memblokir - kondisi aman).
- Tanpa `ALLOWED_REGIMES` (= `[]`): tidak ada syarat regime, gate no-op.
- Regime TIDAK mengubah risk limit (PRD §6.4) - hanya filter kelayakan.
- Backtest: `run_backtest(..., regime_filter=True)` memakai classifier yang
  sama; dampak vs baseline dilaporkan out-of-sample sebelum strategi
  regime-aware dipromosikan (PRD §6.5).

## Aturan kemurnian (purity)

`decide()` tidak boleh: I/O (DB, file, HTTP), jam (`datetime.now`, `time.time`),
RNG (`random`), atau state global mutable. Semua input lewat `context`/`params`.
Pelanggaran = strategi tidak reproducible = tolak di review.

## Guard standar (wajib ada, template sudah menyediakan)

1. Weekend tolak; bar belum closed tolak; candle basi > `max_candle_age_s` tolak.
2. Likuiditas tidak `fresh` atau basi > `max_liquidity_age_s` tolak.
3. Spread filter PRD §5.2: tolak bila `spread > max(2 × median 15m, ambang_absolut)`.
4. Sudah ada posisi (milik strategi) tolak; `trades_today` melebihi batas tolak.
5. Sizing risk-based: `volume = equity × risk% / (jarak_SL × USD-per-lot-per-USD)`,
   floor ke `volume_step`, cap `max_volume` (0.10 lot, PRD §5.6).
6. SL distance di luar [0.50, 15.00] USD → tidak entry (batas risk gate).

XAUUSD: 1.0 lot = 100 oz → 1.00 USD pergerakan harga = 100 USD/lot.

## Struktur `SKILL.md` (wajib, urutan tetap)

1. **Header**: `# SKILL: fund2-strategy-<id>` + versi, track (A rule-based /
   B ML / C RL), PRD, path modul + test.
2. **Logika**: aturan entry/exit langkah demi langkah, deterministik.
3. **Parameter**: tabel `Param | Default | Arti`: harus sama dengan
   `StrategyParams` di modul.
4. **Risk**: SL/TP, sizing, guard, posisi di risk gate.
5. **Hasil backtest**: periode, timeframe, biaya (spread/slippage), trades,
   winrate, PF, expectancy, Max DD, net; catatan kapan strategi GAGAL;
   percobaan parameter tercatat di `backtest_runs` (PRD §5.4 anti-overfit).
   Sampel pendek diberi label eksplisit, bukan validasi walk-forward.
6. **Status**: mode paper/live, state key, gerbang live (paper 20 hari).

## Test wajib (strategi baru)

- Kontrak: context tidak dimutasi; dua pemanggilan → hasil identik; return
  `None` atau `OrderIntent` valid (SL/TP/volume/side).
- Logika: entry fire / tidak fire (buffer, window, guard), SL/TP position,
  sizing, masing-masing guard standar.
- Jalankan: `cd ~/fund2/api && env -u DATABASE_URL TELEGRAM_ALERTS_OFF=1 \
  .venv/bin/python -m pytest -q tests/test_<strategy_id>.py`

## Alur strategi baru (pakai template)

1. Salin `strategies/_template/` → `api/strategies/<id>.py` +
   `strategies/<id>/SKILL.md` + `api/tests/test_<id>.py` (ikuti penanda TODO).
2. Isi logika entry + parameter spesifik; jangan ubah guard/sizing standar.
3. Test kontrak + logika hijau.
4. Backtest dengan biaya terkalibrasi (PRD §5.2) + walk-forward bila data
   cukup; semua percobaan parameter tercatat di `backtest_runs`.
5. Isi bagian Hasil Backtest di SKILL.md dari hasil run (bukan angka manual).
6. Register di `api/paper/runner.py` (`STRATEGIES`) + mode
   `strategy_mode_<id>` default `paper`. Live butuh approve owner (PRD garis
   merah); gerbang: paper 20 hari + QA.

Checklist DoD satu strategi: modul + SKILL.md + test konsisten (id, versi,
parameter), test hijau, backtest tercatat, entri registry paper runner.
