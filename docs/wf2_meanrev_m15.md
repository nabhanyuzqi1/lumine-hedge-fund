cost model: {
 "source": "dukascopy_m1+hfm_liquidity_samples",
 "duka_spread_by_session": {
  "asia": 0.75,
  "london": 0.62,
  "london_newyork": 0.64,
  "newyork": 0.64
 },
 "hfm_spread_by_session": {
  "asia": 0.43,
  "london": 0.43,
  "london_newyork": 0.43,
  "newyork": 0.43
 },
 "factor_by_session": {
  "asia": 0.5733,
  "london": 0.6935,
  "london_newyork": 0.6719,
  "newyork": 0.6719
 },
 "filter_spread_by_session": {
  "asia": 0.43,
  "london": 0.43,
  "london_newyork": 0.43,
  "newyork": 0.43
 },
 "spread_by_session": {
  "asia": 0.516,
  "london": 0.516,
  "london_newyork": 0.516,
  "newyork": 0.516
 },
 "haircut": 0.2,
 "commission_per_lot_round_usd": 7.0,
 "slippage_usd_per_fill": 0.1,
 "notes": [
  "basis Dukascopy: 1080000 menit spread (2024-11-01 .. 2026-11-21)"
 ]
}
backtest_runs: 234 baris ditulis (run_id 4c0d9fd9-d943-42df-8797-3f52d2e1f2b6)
# Walk-forward mean_reversion v1.0.0 (XAUUSD M15)

Run ID: `4c0d9fd9-d943-42df-8797-3f52d2e1f2b6`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan [USULAN PRD 5.4]
Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor HFM/Duka + haircut 20%; komisi 7.0 USD/lot round-turn; slippage 0.1 USD per fill.
Spread akhir per sesi (USD): {'asia': 0.516, 'london': 0.516, 'london_newyork': 0.516, 'newyork': 0.516}
Catatan kalibrasi: basis Dukascopy: 1080000 menit spread (2024-11-01 .. 2026-11-21)
equity awal 10000.0 USD; risiko 0.5% per trade
Grid parameter: 12 kombinasi; total percobaan tercatat di backtest_runs: 234

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-06-01 .. 2025-07-01 | 2880 | 4 | 0.5 | 0.51 | -12.24 USD / -0.244 R | 78.14 (0.0078) | -48.96 | GAGAL: profit factor 0.51 < 1 setelah biaya |
| 2 | 2025-07-01 .. 2025-08-01 | 2976 | 5 | 0.6 | 0.998 | -0.04 USD / 0.001 R | 94.79 (0.0095) | -0.21 | GAGAL: profit factor 0.998 < 1 setelah biaya |
| 3 | 2025-08-01 .. 2025-09-01 | 2976 | 1 | 0.0 | 0.0 | -33.33 USD / -0.67 R | 33.33 (0.0033) | -33.33 | GAGAL: profit factor 0.0 < 1 setelah biaya |
| 4 | 2025-09-01 .. 2025-10-01 | 2880 | 11 | 0.1818 | 0.149 | -27.01 USD / -0.551 R | 300.45 (0.0303) | -297.06 | GAGAL: profit factor 0.149 < 1 setelah biaya |
| 5 | 2025-10-01 .. 2025-11-01 | 2976 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 6 | 2025-11-01 .. 2025-12-01 | 2880 | 1 | 0.0 | 0.0 | -49.46 USD / -1.028 R | 49.46 (0.0051) | -49.46 | GAGAL: profit factor 0.0 < 1 setelah biaya |
| 7 | 2025-12-01 .. 2026-01-01 | 2976 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 8 | 2026-01-01 .. 2026-02-01 | 2976 | 2 | 0.0 | 0.0 | -50.2 USD / -1.052 R | 100.41 (0.0105) | -100.41 | GAGAL: profit factor 0.0 < 1 setelah biaya |
| 9 | 2026-02-01 .. 2026-03-01 | 2688 | 11 | 0.4545 | 1.982 | 20.81 USD / 0.44 R | 93.39 (0.0096) | 228.87 | OK |
| 10 | 2026-03-01 .. 2026-04-01 | 2976 | 9 | 0.2222 | 0.522 | -16.97 USD / -0.349 R | 169.88 (0.0175) | -152.73 | GAGAL: profit factor 0.522 < 1 setelah biaya |
| 11 | 2026-04-01 .. 2026-05-01 | 2880 | 8 | 0.125 | 0.308 | -25.87 USD / -0.545 R | 299.09 (0.031) | -206.98 | GAGAL: profit factor 0.308 < 1 setelah biaya |
| 12 | 2026-05-01 .. 2026-06-01 | 2976 | 12 | 0.25 | 0.549 | -14.7 USD / -0.314 R | 255.87 (0.0274) | -176.45 | GAGAL: profit factor 0.549 < 1 setelah biaya |
| 13 | 2026-06-01 .. 2026-07-01 | 2880 | 13 | 0.2308 | 0.547 | -15.0 USD / -0.327 R | 222.89 (0.0243) | -194.98 | GAGAL: profit factor 0.547 < 1 setelah biaya |
| 14 | 2026-07-01 .. 2026-08-01 | 2976 | 11 | 0.6364 | 1.946 | 15.51 USD / 0.346 R | 89.52 (0.0098) | 170.59 | OK |
| 15 | 2026-08-01 .. 2026-09-01 | 2976 | 5 | 0.4 | 0.593 | -7.6 USD / -0.165 R | 91.88 (0.01) | -38.0 | GAGAL: profit factor 0.593 < 1 setelah biaya |
| 16 | 2026-09-01 .. 2026-10-01 | 2880 | 4 | 0.75 | 4.356 | 36.79 USD / 0.806 R | 43.85 (0.0047) | 147.15 | OK |
| 17 | 2026-10-01 .. 2026-11-01 | 2864 | 3 | 0.6667 | 0.992 | -0.12 USD / -0.001 R | 44.59 (0.0048) | -0.35 | GAGAL: profit factor 0.992 < 1 setelah biaya |
| 18 | 2026-11-01 .. 2026-12-01 (parsial) | 1380 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 18 (dengan trade: 15, profit: 3)
- Total percobaan parameter: 234 (semua tercatat di backtest_runs)
- Net profit gabungan: -752.31 USD (saldo akhir 9247.69 USD)
- Max drawdown gabungan: 1031.7 USD (0.1032)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2024-12-01 .. 2025-06-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.285 | 1.904 | 19 |
| 2 | 2025-01-01 .. 2025-07-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.195 | 1.556 | 23 |
| 3 | 2025-02-01 .. 2025-08-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.154 | 1.427 | 26 |
| 4 | 2025-03-01 .. 2025-09-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.095 | 1.21 | 67 |
| 5 | 2025-04-01 .. 2025-10-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.464 | 3.143 | 5 |
| 6 | 2025-05-01 .. 2025-11-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.464 | 3.143 | 5 |
| 7 | 2025-06-01 .. 2025-12-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.464 | 3.143 | 5 |
| 8 | 2025-07-01 .. 2026-01-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.268 | 0.447 | 15 |
| 9 | 2025-08-01 .. 2026-02-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.264 | 0.554 | 76 |
| 10 | 2025-09-01 .. 2026-03-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.192 | 0.674 | 73 |
| 11 | 2025-10-01 .. 2026-04-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.165 | 0.728 | 70 |
| 12 | 2025-11-01 .. 2026-05-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.207 | 0.669 | 61 |
| 13 | 2025-12-01 .. 2026-06-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.178 | 0.713 | 58 |
| 14 | 2026-01-01 .. 2026-07-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.163 | 0.746 | 60 |
| 15 | 2026-02-01 .. 2026-08-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.02 | 0.957 | 20 |
| 16 | 2026-03-01 .. 2026-09-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.038 | 0.92 | 23 |
| 17 | 2026-04-01 .. 2026-10-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.134 | 1.294 | 26 |
| 18 | 2026-05-01 .. 2026-11-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.15 | 1.36 | 24 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4). Run gate DoD P2 (23 Nov 2026): data 2 tahun kontinu, biaya terkalibrasi PRD 5.2; catatan kalibrasi dan provenance data lihat LAPORAN_DOD_P2.md.

