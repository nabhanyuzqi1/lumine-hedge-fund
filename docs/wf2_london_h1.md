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
backtest_runs: 234 baris ditulis (run_id 4245e9cb-848e-4980-9821-dc0fe4e387c8)
# Walk-forward london_breakout v1.0.0 (XAUUSD H1)

Run ID: `4245e9cb-848e-4980-9821-dc0fe4e387c8`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan [USULAN PRD 5.4]
Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor HFM/Duka + haircut 20%; komisi 7.0 USD/lot round-turn; slippage 0.1 USD per fill.
Spread akhir per sesi (USD): {'asia': 0.516, 'london': 0.516, 'london_newyork': 0.516, 'newyork': 0.516}
Catatan kalibrasi: basis Dukascopy: 1080000 menit spread (2024-11-01 .. 2026-11-21)
equity awal 10000.0 USD; risiko 0.5% per trade
Grid parameter: 12 kombinasi; total percobaan tercatat di backtest_runs: 234

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-06-01 .. 2025-07-01 | 720 | 8 | 0.25 | 0.616 | -13.7 USD / -0.272 R | 285.57 (0.0283) | -109.62 | GAGAL: profit factor 0.616 < 1 setelah biaya |
| 2 | 2025-07-01 .. 2025-08-01 | 744 | 12 | 0.5 | 1.467 | 11.59 USD / 0.237 R | 105.51 (0.0104) | 139.12 | OK |
| 3 | 2025-08-01 .. 2025-09-01 | 744 | 12 | 0.25 | 0.422 | -19.61 USD / -0.393 R | 244.77 (0.0244) | -235.33 | GAGAL: profit factor 0.422 < 1 setelah biaya |
| 4 | 2025-09-01 .. 2025-10-01 | 720 | 12 | 0.3333 | 0.453 | -16.14 USD / -0.331 R | 231.54 (0.0235) | -193.72 | GAGAL: profit factor 0.453 < 1 setelah biaya |
| 5 | 2025-10-01 .. 2025-11-01 | 744 | 8 | 0.25 | 0.271 | -25.16 USD / -0.527 R | 238.6 (0.0248) | -201.25 | GAGAL: profit factor 0.271 < 1 setelah biaya |
| 6 | 2025-11-01 .. 2025-12-01 | 720 | 7 | 0.1429 | 0.128 | -33.05 USD / -0.71 R | 231.33 (0.0246) | -231.33 | GAGAL: profit factor 0.128 < 1 setelah biaya |
| 7 | 2025-12-01 .. 2026-01-01 | 744 | 6 | 0.6667 | 1.879 | 12.24 USD / 0.268 R | 45.54 (0.0049) | 73.46 | OK |
| 8 | 2026-01-01 .. 2026-02-01 | 635 | 4 | 0.25 | 0.321 | -21.95 USD / -0.475 R | 129.22 (0.0139) | -87.79 | GAGAL: profit factor 0.321 < 1 setelah biaya |
| 9 | 2026-02-01 .. 2026-03-01 | 458 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 10 | 2026-03-01 .. 2026-04-01 | 491 | 2 | 0.5 | 0.839 | -3.44 USD / -0.074 R | 42.86 (0.0047) | -6.88 | GAGAL: profit factor 0.839 < 1 setelah biaya |
| 11 | 2026-04-01 .. 2026-05-01 | 483 | 3 | 0.3333 | 1.019 | 0.53 USD / 0.016 R | 83.09 (0.0091) | 1.58 | OK |
| 12 | 2026-05-01 .. 2026-06-01 | 481 | 4 | 0.25 | 0.268 | -23.46 USD / -0.513 R | 128.31 (0.014) | -93.86 | GAGAL: profit factor 0.268 < 1 setelah biaya |
| 13 | 2026-06-01 .. 2026-07-01 | 503 | 3 | 0.3333 | 0.43 | -14.97 USD / -0.33 R | 78.82 (0.0087) | -44.91 | GAGAL: profit factor 0.43 < 1 setelah biaya |
| 14 | 2026-07-01 .. 2026-08-01 | 526 | 4 | 0.5 | 2.969 | 20.02 USD / 0.445 R | 40.15 (0.0044) | 80.08 | OK |
| 15 | 2026-08-01 .. 2026-09-01 | 483 | 2 | 0.0 | 0.0 | -44.59 USD / -0.983 R | 89.19 (0.0098) | -89.19 | GAGAL: profit factor 0.0 < 1 setelah biaya |
| 16 | 2026-09-01 .. 2026-10-01 | 504 | 3 | 0.6667 | 3.687 | 40.93 USD / 0.91 R | 45.69 (0.005) | 122.78 | OK |
| 17 | 2026-10-01 .. 2026-11-01 | 506 | 5 | 0.2 | 0.469 | -15.99 USD / -0.349 R | 150.65 (0.0165) | -79.93 | GAGAL: profit factor 0.469 < 1 setelah biaya |
| 18 | 2026-11-01 .. 2026-12-01 (parsial) | 345 | 3 | 0.6667 | 3.308 | 32.08 USD / 0.71 R | 41.69 (0.0046) | 96.23 | OK |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 18 (dengan trade: 17, profit: 6)
- Total percobaan parameter: 234 (semua tercatat di backtest_runs)
- Net profit gabungan: -860.56 USD (saldo akhir 9139.44 USD)
- Max drawdown gabungan: 1029.14 USD (0.1026)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2024-12-01 .. 2025-06-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.07 | 0.875 | 67 |
| 2 | 2025-01-01 .. 2025-07-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.118 | 0.805 | 63 |
| 3 | 2025-02-01 .. 2025-08-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.135 | 0.782 | 58 |
| 4 | 2025-03-01 .. 2025-09-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.182 | 0.656 | 60 |
| 5 | 2025-04-01 .. 2025-10-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.22 | 0.604 | 52 |
| 6 | 2025-05-01 .. 2025-11-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.217 | 0.609 | 56 |
| 7 | 2025-06-01 .. 2025-12-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.245 | 0.574 | 61 |
| 8 | 2025-07-01 .. 2026-01-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.3, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.191 | 0.653 | 56 |
| 9 | 2025-08-01 .. 2026-02-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.314 | 0.478 | 51 |
| 10 | 2025-09-01 .. 2026-03-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.344 | 0.448 | 38 |
| 11 | 2025-10-01 .. 2026-04-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.279 | 0.606 | 28 |
| 12 | 2025-11-01 .. 2026-05-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.159 | 0.695 | 23 |
| 13 | 2025-12-01 .. 2026-06-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.092 | 0.808 | 19 |
| 14 | 2026-01-01 .. 2026-07-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=1.5, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | -0.208 | 0.659 | 16 |
| 15 | 2026-02-01 .. 2026-08-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.12 | 1.22 | 16 |
| 16 | 2026-03-01 .. 2026-09-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.003 | 0.998 | 18 |
| 17 | 2026-04-01 .. 2026-10-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.113 | 1.2 | 19 |
| 18 | 2026-05-01 .. 2026-11-01 | asia_start_utc=0, asia_end_utc=7, london_start_utc=7, london_end_utc=12, force_close_utc=16, min_asia_coverage=0.6, min_range_usd=0.5, max_range_usd=150.0, breakout_buffer_usd=0.1, rr=2.0, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True | 0.051 | 1.084 | 21 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4). Run gate DoD P2 (23 Nov 2026): data 2 tahun kontinu, biaya terkalibrasi PRD 5.2; catatan kalibrasi dan provenance data lihat LAPORAN_DOD_P2.md.

