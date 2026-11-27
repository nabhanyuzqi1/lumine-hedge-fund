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
backtest_runs: 234 baris ditulis (run_id c6fb1cd2-1a42-4089-b5e9-1b1c5c8224f3)
# Walk-forward london_breakout v1.0.0 (XAUUSD M5)

Run ID: `c6fb1cd2-1a42-4089-b5e9-1b1c5c8224f3`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan [USULAN PRD 5.4]
Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor HFM/Duka + haircut 20%; komisi 7.0 USD/lot round-turn; slippage 0.1 USD per fill.
Spread akhir per sesi (USD): {'asia': 0.516, 'london': 0.516, 'london_newyork': 0.516, 'newyork': 0.516}
Catatan kalibrasi: basis Dukascopy: 1080000 menit spread (2024-11-01 .. 2026-11-21)
equity awal 10000.0 USD; risiko 0.5% per trade
Grid parameter: 12 kombinasi; total percobaan tercatat di backtest_runs: 234

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-06-01 .. 2025-07-01 | 8640 | 13 | 0.2308 | 0.276 | -22.7 USD / -0.459 R | 344.25 (0.0343) | -295.11 | GAGAL: profit factor 0.276 < 1 setelah biaya |
| 2 | 2025-07-01 .. 2025-08-01 | 8928 | 18 | 0.1667 | 0.245 | -17.55 USD / -0.367 R | 315.95 (0.0326) | -315.95 | GAGAL: profit factor 0.245 < 1 setelah biaya |
| 3 | 2025-08-01 .. 2025-09-01 | 8928 | 15 | 0.2667 | 0.681 | -6.41 USD / -0.135 R | 188.51 (0.02) | -96.12 | GAGAL: profit factor 0.681 < 1 setelah biaya |
| 4 | 2025-09-01 .. 2025-10-01 | 8640 | 14 | 0.2857 | 0.596 | -10.74 USD / -0.231 R | 247.54 (0.0265) | -150.4 | GAGAL: profit factor 0.596 < 1 setelah biaya |
| 5 | 2025-10-01 .. 2025-11-01 | 8928 | 16 | 0.625 | 1.405 | 5.42 USD / 0.119 R | 174.09 (0.0189) | 86.74 | OK |
| 6 | 2025-11-01 .. 2025-12-01 | 8640 | 13 | 0.3077 | 0.381 | -17.71 USD / -0.387 R | 230.27 (0.025) | -230.27 | GAGAL: profit factor 0.381 < 1 setelah biaya |
| 7 | 2025-12-01 .. 2026-01-01 | 8928 | 11 | 0.4545 | 1.835 | 15.51 USD / 0.346 R | 68.66 (0.0074) | 170.65 | OK |
| 8 | 2026-01-01 .. 2026-02-01 | 8928 | 7 | 0.2857 | 0.618 | -11.11 USD / -0.24 R | 203.5 (0.0221) | -77.77 | GAGAL: profit factor 0.618 < 1 setelah biaya |
| 9 | 2026-02-01 .. 2026-03-01 | 8064 | 7 | 0.4286 | 1.132 | 3.07 USD / 0.071 R | 94.91 (0.0103) | 21.51 | OK |
| 10 | 2026-03-01 .. 2026-04-01 | 8928 | 9 | 0.3333 | 0.95 | -1.42 USD / -0.027 R | 213.89 (0.0234) | -12.81 | GAGAL: profit factor 0.95 < 1 setelah biaya |
| 11 | 2026-04-01 .. 2026-05-01 | 8640 | 14 | 0.2143 | 0.5 | -16.97 USD / -0.375 R | 343.46 (0.0374) | -237.64 | GAGAL: profit factor 0.5 < 1 setelah biaya |
| 12 | 2026-05-01 .. 2026-06-01 | 8928 | 13 | 0.3077 | 0.751 | -7.62 USD / -0.169 R | 304.32 (0.0336) | -99.12 | GAGAL: profit factor 0.751 < 1 setelah biaya |
| 13 | 2026-06-01 .. 2026-07-01 | 8640 | 14 | 0.2857 | 0.672 | -10.21 USD / -0.231 R | 229.34 (0.0259) | -142.93 | GAGAL: profit factor 0.672 < 1 setelah biaya |
| 14 | 2026-07-01 .. 2026-08-01 | 8928 | 10 | 0.4 | 1.047 | 1.01 USD / 0.026 R | 49.56 (0.0057) | 10.1 | OK |
| 15 | 2026-08-01 .. 2026-09-01 | 8928 | 13 | 0.2308 | 0.409 | -18.31 USD / -0.427 R | 257.17 (0.0298) | -237.98 | GAGAL: profit factor 0.409 < 1 setelah biaya |
| 16 | 2026-09-01 .. 2026-10-01 | 8640 | 20 | 0.45 | 0.999 | -0.03 USD / 0.003 R | 219.23 (0.026) | -0.51 | GAGAL: profit factor 0.999 < 1 setelah biaya |
| 17 | 2026-10-01 .. 2026-11-01 | 8592 | 14 | 0.2857 | 0.439 | -14.83 USD / -0.356 R | 286.63 (0.0338) | -207.56 | GAGAL: profit factor 0.439 < 1 setelah biaya |
| 18 | 2026-11-01 .. 2026-12-01 (parsial) | 4140 | 12 | 0.4167 | 0.82 | -4.25 USD / -0.101 R | 186.25 (0.0225) | -50.98 | GAGAL: profit factor 0.82 < 1 setelah biaya |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 18 (dengan trade: 18, profit: 4)
- Total percobaan parameter: 234 (semua tercatat di backtest_runs)
- Net profit gabungan: -1866.15 USD (saldo akhir 8133.85 USD)
- Max drawdown gabungan: 1866.15 USD (0.1866)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2024-12-01 .. 2025-06-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.016 | 0.957 | 84 |
| 2 | 2025-01-01 .. 2025-07-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.08 | 0.815 | 87 |
| 3 | 2025-02-01 .. 2025-08-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.073 | 0.836 | 84 |
| 4 | 2025-03-01 .. 2025-09-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.091 | 0.807 | 80 |
| 5 | 2025-04-01 .. 2025-10-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.191 | 0.534 | 83 |
| 6 | 2025-05-01 .. 2025-11-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.141 | 0.625 | 90 |
| 7 | 2025-06-01 .. 2025-12-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.172 | 0.655 | 90 |
| 8 | 2025-07-01 .. 2026-01-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.057 | 0.871 | 88 |
| 9 | 2025-08-01 .. 2026-02-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.007 | 0.979 | 77 |
| 10 | 2025-09-01 .. 2026-03-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.032 | 1.058 | 69 |
| 11 | 2025-10-01 .. 2026-04-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.052 | 1.091 | 63 |
| 12 | 2025-11-01 .. 2026-05-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.125 | 0.79 | 61 |
| 13 | 2025-12-01 .. 2026-06-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.039 | 0.929 | 60 |
| 14 | 2026-01-01 .. 2026-07-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.5, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.071 | 0.867 | 63 |
| 15 | 2026-02-01 .. 2026-08-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.5, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.062 | 0.881 | 66 |
| 16 | 2026-03-01 .. 2026-09-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.5, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.123 | 0.784 | 73 |
| 17 | 2026-04-01 .. 2026-10-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.5, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.089 | 0.835 | 84 |
| 18 | 2026-05-01 .. 2026-11-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.5, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.098 | 0.819 | 84 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4). Run gate DoD P2 (23 Nov 2026): data 2 tahun kontinu, biaya terkalibrasi PRD 5.2; catatan kalibrasi dan provenance data lihat LAPORAN_DOD_P2.md.

