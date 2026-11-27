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
backtest_runs: 234 baris ditulis (run_id d9706373-3353-4f50-a3e9-951306e9192f)
# Walk-forward mean_reversion v1.0.0 (XAUUSD M5)

Run ID: `d9706373-3353-4f50-a3e9-951306e9192f`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan [USULAN PRD 5.4]
Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor HFM/Duka + haircut 20%; komisi 7.0 USD/lot round-turn; slippage 0.1 USD per fill.
Spread akhir per sesi (USD): {'asia': 0.516, 'london': 0.516, 'london_newyork': 0.516, 'newyork': 0.516}
Catatan kalibrasi: basis Dukascopy: 1080000 menit spread (2024-11-01 .. 2026-11-21)
equity awal 10000.0 USD; risiko 0.5% per trade
Grid parameter: 12 kombinasi; total percobaan tercatat di backtest_runs: 234

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-06-01 .. 2025-07-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 2 | 2025-07-01 .. 2025-08-01 | 8928 | 20 | 0.45 | 1.571 | 8.0 USD / 0.16 R | 89.12 (0.0088) | 159.93 | OK |
| 3 | 2025-08-01 .. 2025-09-01 | 8928 | 18 | 0.4444 | 1.322 | 4.55 USD / 0.091 R | 137.78 (0.0133) | 81.94 | OK |
| 4 | 2025-09-01 .. 2025-10-01 | 8640 | 20 | 0.3 | 0.595 | -9.51 USD / -0.186 R | 279.01 (0.0272) | -190.28 | GAGAL: profit factor 0.595 < 1 setelah biaya |
| 5 | 2025-10-01 .. 2025-11-01 | 8928 | 6 | 0.3333 | 0.806 | -5.37 USD / -0.104 R | 147.37 (0.0145) | -32.24 | GAGAL: profit factor 0.806 < 1 setelah biaya |
| 6 | 2025-11-01 .. 2025-12-01 | 8640 | 7 | 0.4286 | 1.558 | 12.57 USD / 0.254 R | 66.56 (0.0066) | 88.02 | OK |
| 7 | 2025-12-01 .. 2026-01-01 | 8928 | 6 | 0.3333 | 0.347 | -21.43 USD / -0.425 R | 175.41 (0.0173) | -128.6 | GAGAL: profit factor 0.347 < 1 setelah biaya |
| 8 | 2026-01-01 .. 2026-02-01 | 8928 | 7 | 0.4286 | 1.649 | 15.47 USD / 0.313 R | 85.95 (0.0085) | 108.32 | OK |
| 9 | 2026-02-01 .. 2026-03-01 | 8064 | 7 | 0.2857 | 0.25 | -26.01 USD / -0.518 R | 201.98 (0.02) | -182.07 | GAGAL: profit factor 0.25 < 1 setelah biaya |
| 10 | 2026-03-01 .. 2026-04-01 | 8928 | 7 | 0.0 | 0.0 | -46.08 USD / -0.944 R | 322.59 (0.0326) | -322.59 | GAGAL: profit factor 0.0 < 1 setelah biaya |
| 11 | 2026-04-01 .. 2026-05-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 12 | 2026-05-01 .. 2026-06-01 | 8928 | 20 | 0.55 | 1.274 | 5.75 USD / 0.122 R | 259.94 (0.0268) | 114.99 | OK |
| 13 | 2026-06-01 .. 2026-07-01 | 8640 | 20 | 0.3 | 0.676 | -9.46 USD / -0.193 R | 321.21 (0.0331) | -189.2 | GAGAL: profit factor 0.676 < 1 setelah biaya |
| 14 | 2026-07-01 .. 2026-08-01 | 8928 | 22 | 0.3636 | 0.94 | -1.46 USD / -0.028 R | 352.94 (0.0361) | -32.03 | GAGAL: profit factor 0.94 < 1 setelah biaya |
| 15 | 2026-08-01 .. 2026-09-01 | 8928 | 20 | 0.25 | 0.302 | -23.14 USD / -0.498 R | 469.85 (0.0495) | -462.71 | GAGAL: profit factor 0.302 < 1 setelah biaya |
| 16 | 2026-09-01 .. 2026-10-01 | 8640 | 2 | 1.0 | - | 50.7 USD / 1.122 R | 0.0 (0.0) | 101.41 | OK |
| 17 | 2026-10-01 .. 2026-11-01 | 8592 | 2 | 1.0 | - | 97.09 USD / 2.123 R | 0.0 (0.0) | 194.17 | OK |
| 18 | 2026-11-01 .. 2026-12-01 (parsial) | 4140 | 1 | 0.0 | 0.0 | -42.71 USD / -0.918 R | 42.71 (0.0046) | -42.71 | GAGAL: profit factor 0.0 < 1 setelah biaya |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 18 (dengan trade: 16, profit: 7)
- Total percobaan parameter: 234 (semua tercatat di backtest_runs)
- Net profit gabungan: -733.65 USD (saldo akhir 9266.35 USD)
- Max drawdown gabungan: 1228.39 USD (0.1199)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2024-12-01 .. 2025-06-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.141 | 0.637 | 7 |
| 2 | 2025-01-01 .. 2025-07-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.169 | 0.616 | 117 |
| 3 | 2025-02-01 .. 2025-08-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.128 | 0.708 | 116 |
| 4 | 2025-03-01 .. 2025-09-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.12 | 0.726 | 116 |
| 5 | 2025-04-01 .. 2025-10-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.034 | 1.071 | 40 |
| 6 | 2025-05-01 .. 2025-11-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.103 | 1.236 | 39 |
| 7 | 2025-06-01 .. 2025-12-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.155 | 1.379 | 37 |
| 8 | 2025-07-01 .. 2026-01-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.138 | 1.314 | 27 |
| 9 | 2025-08-01 .. 2026-02-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.177 | 1.379 | 29 |
| 10 | 2025-09-01 .. 2026-03-01 | period=20, num_std=2.5, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.3, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.054 | 1.098 | 33 |
| 11 | 2025-10-01 .. 2026-04-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.422 | 2.054 | 5 |
| 12 | 2025-11-01 .. 2026-05-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.032 | 0.932 | 110 |
| 13 | 2025-12-01 .. 2026-06-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.06 | 1.127 | 117 |
| 14 | 2026-01-01 .. 2026-07-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.012 | 1.018 | 115 |
| 15 | 2026-02-01 .. 2026-08-01 | period=20, num_std=2.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.019 | 0.956 | 118 |
| 16 | 2026-03-01 .. 2026-09-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.523 | 3.596 | 5 |
| 17 | 2026-04-01 .. 2026-10-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=0.6, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.665 | 4.974 | 6 |
| 18 | 2026-05-01 .. 2026-11-01 | period=20, num_std=3.0, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sd_usd=0.5, max_sd_usd=30.0, reentry_buffer_usd=0.1, sl_lookback=2, sl_buffer_usd=0.1, min_rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 1.585 | None | 5 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4). Run gate DoD P2 (23 Nov 2026): data 2 tahun kontinu, biaya terkalibrasi PRD 5.2; catatan kalibrasi dan provenance data lihat LAPORAN_DOD_P2.md.

