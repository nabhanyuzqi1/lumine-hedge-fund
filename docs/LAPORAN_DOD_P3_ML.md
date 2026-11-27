# Laporan DoD P3 — Feature Store + Pipeline Training Offline (ML)

| | |
| --- | --- |
| Tanggal | 2026-11-23 |
| Tugas | t_f2p3a1 [FUND2-P3][OPS] |
| Status | **BERJALAN** — kriteria dideklarasikan sebelum evaluasi dijalankan |
| PRD | `docs/PRD_v2.1_Fund_Core.md` §11 P3 (opsional) |

## 0. Kriteria lolos (DIDEKLARASIKAN SEBELUM RUN — 2026-11-23)

Semua evaluasi memakai: data XAUUSD M5 2 tahun (2024-11-01 .. 2026-11-23,
214.050 bar, kontinuitas bulanan diverifikasi 8064-8928 bar/bulan tanpa bulan
bolong), walk-forward latih 6 bulan / uji 1 bulan geser 1 bulan (18 window uji,
identik dengan run P2), biaya terkalibrasi PRD 5.2 (CostModel Dukascopy×HFM +
haircut 20%, komisi 7 USD/lot round-turn, slippage 0.1 USD/fill), equity awal
10.000 USD, risiko 0.5% per trade, maks 1 trade/hari, force-close 16:00 UTC —
engine, risk gate, dan biaya **sama persis** dengan baseline rule-based.

**ML (walk-forward gabungan, setelah biaya) dinyatakan LOLOS hanya jika SEMUA:**

| # | Kriteria | Ambang |
| --- | --- | --- |
| 1 | Net profit (ekuiti berantai) | > 0 USD |
| 2 | Profit factor | > 1.0 |
| 3 | Expectancy per trade | > 0 USD |
| 4 | Max drawdown | ≤ 10% |
| 5 | Jumlah trade | ≥ 30 |
| 6 | Window uji dengan PF < 1 | ≤ 50% (≤ 9 dari 18) |

**Klaim "mengalahkan baseline rule-based pada metrik yang sama setelah biaya"**
hanya jika ML mengungguli KEDUA baseline rule-based yang di-run ulang sendiri
pada data, window, dan biaya yang sama (mean_reversion M5, london_breakout M5)
pada: net profit, profit factor, expectancy, dan max drawdown.

**Jika tidak lolos**: kode ML diarsipkan (`archived/ml_gbm_<tanggal>/`) +
laporan pembelajaran ditulis. Itu hasil sah sesuai PRD P3.

Anti-overfitting (PRD 5.4): model dilatih HANYA dari window latih; early
stopping memakai 20% terakhir window latih (time-ordered, di dalam data latih);
grid kecil (12 kombinasi = 4 konfigurasi barrier × 3 ambang probabilitas);
seluruh percobaan latih + uji dicatat ke `backtest_runs` dengan run_id yang
sama; seed dan hyperparameter tetap dan tercetak di config run.

## 1. Desain

### Feature store (candle + likuiditas)

Sumber: `candles` XAUUSD M5 (DB, 2 tahun) + spread per menit dari raw
Dukascopy bi5 lokal (`data/dukascopy/m1/raw`, 1.501 hari) untuk fitur
likuiditas historis. Fitur dihitung point-in-time (hanya bar ≤ t). Daftar fitur
lengkap di §2. Tick volume sengaja TIDAK dipakai: runner paper live mengirim
`volume: 0` pada context candle (paper/runner.py `load_candles`), jadi fitur
berbasis volume akan memecah paritas sinyal backtest vs paper. Likuiditas
dari: spread context (live: tick nyata; backtest: model sesi), estimator
Corwin-Schultz dari OHLC, dan kompresi range.

### Label & model

Label triple-barrier per sisi (long/short) dari close bar t: SL = sl_mult ×
ATR14(t), TP = rr × SL, horizon sampai force-close 16:00 UTC hari yang sama;
jika tidak ada barrier tersentuh → label dari tanda (close_1600 - entry).
Aturan konservatif: bar yang menyentuh SL dan TP dihitung SL lebih dulu
(sama dengan PaperBroker). Model: LightGBM binary per sisi per konfigurasi
barrier (4 konfigurasi: sl_mult {1.0, 1.5} × rr {1.0, 1.5}), hyperparameter
tetap teregularisasi (num_leaves 15, min_data_in_leaf 400, lr 0.05, seed 42,
deterministic).

### Strategi (decide, kontrak sama dengan baseline)

`strategies/ml_gbm.py`: guard identik dengan mean_reversion (fresh liquidity,
filter spread max(2×median15m, 0.50), 1 posisi, 1 trade/hari, window entry
07:00-16:00 UTC, hari kerja), fitur dari context candle (CONTEXT_BARS=300,
sama dengan live), p_long/p_short dari model; BUY jika p_long > ambang, SELL
jika p_short > ambang; SL/TP = mult × ATR14; volume = risk 0.5% / jarak SL
(sama dengan baseline); force-close 16:00 UTC.

## 2. Daftar fitur

(diisi setelah implementasi — daftar final tercetak di config run)

## 3. Hasil walk-forward ML

(diisi setelah run)

## 4. Baseline rule-based (run ulang sendiri, biaya sama)

(diisi setelah run)

## 5. Perbandingan & verdict

(diisi setelah run)

## 6. Pembelajaran

(diisi setelah run)
