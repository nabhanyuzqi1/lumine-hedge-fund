# Walk-forward ml_gbm v1.0.0 (XAUUSD M5) — P3 ML

Run ID: `cab7e9ed-8291-4779-92d9-a75636a1182e`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan (identik run P2)
Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor HFM + haircut 20%; komisi 7.0 USD/lot round-turn; slippage 0.1 USD per fill. Spread akhir: {'asia': 0.506, 'london': 0.432, 'london_newyork': 0.432, 'newyork': 0.432}
equity awal 10000.0 USD; risiko 0.5% per trade; maks 1 trade/hari
Grid: 12 kombinasi (4 barrier x 3 ambang); total percobaan tercatat di backtest_runs: 234
Model: LightGBM per sisi per barrier; params={'objective': 'binary', 'metric': 'binary_logloss', 'learning_rate': 0.05, 'num_leaves': 15, 'max_depth': 5, 'min_data_in_leaf': 400, 'feature_fraction': 0.8, 'bagging_fraction': 0.8, 'bagging_freq': 1, 'lambda_l2': 5.0, 'seed': 42, 'deterministic': True, 'num_threads': 4, 'verbose': -1}; rounds=500 early_stop=50 val=20% time-ordered dalam window latih

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-06-01 .. 2025-07-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 2 | 2025-07-01 .. 2025-08-01 | 8928 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 3 | 2025-08-01 .. 2025-09-01 | 8928 | 16 | 0.5 | 0.76 | -3.89 USD / -0.077 R | 171.16 (0.0169) | -62.25 | GAGAL: profit factor 0.76 < 1 setelah biaya |
| 4 | 2025-09-01 .. 2025-10-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 5 | 2025-10-01 .. 2025-11-01 | 8928 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 6 | 2025-11-01 .. 2025-12-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 7 | 2025-12-01 .. 2026-01-01 | 8928 | 1 | 1.0 | - | 46.99 USD / 0.946 R | 0.0 (0.0) | 46.99 | OK |
| 8 | 2026-01-01 .. 2026-02-01 | 8928 | 11 | 0.8182 | 7.308 | 29.8 USD / 0.589 R | 42.69 (0.0041) | 327.82 | OK |
| 9 | 2026-02-01 .. 2026-03-01 | 8064 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 10 | 2026-03-01 .. 2026-04-01 | 8928 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 11 | 2026-04-01 .. 2026-05-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 12 | 2026-05-01 .. 2026-06-01 | 8928 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 13 | 2026-06-01 .. 2026-07-01 | 8640 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 14 | 2026-07-01 .. 2026-08-01 | 8928 | 12 | 0.5 | 0.75 | -6.29 USD / -0.12 R | 164.97 (0.016) | -75.51 | GAGAL: profit factor 0.75 < 1 setelah biaya |
| 15 | 2026-08-01 .. 2026-09-01 | 8928 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 16 | 2026-09-01 .. 2026-10-01 | 8640 | 3 | 0.6667 | 1.825 | 11.94 USD / 0.235 R | 43.41 (0.0042) | 35.81 | OK |
| 17 | 2026-10-01 .. 2026-11-01 | 8928 | 0 | - | - | None USD / None R | 0.0 (0.0) | 0.0 | GAGAL: tidak ada trade di window uji |
| 18 | 2026-11-01 .. 2026-12-01 (parsial) | 6142 | 8 | 0.5 | 0.91 | -2.05 USD / -0.038 R | 120.81 (0.0117) | -16.36 | GAGAL: profit factor 0.91 < 1 setelah biaya |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 18 (dengan trade: 6, profit: 3, PF<1: 3)
- Total percobaan parameter: 234 (semua tercatat di backtest_runs)
- Trades: 51; winrate 0.5882; PF 1.306; expectancy 5.03 USD/trade
- Net profit gabungan: 256.5 USD (saldo akhir 10256.5 USD)
- Max drawdown gabungan: 75.51 USD (0.0073)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2024-12-01 .. 2025-06-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 2 | 2025-01-01 .. 2025-07-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 3 | 2025-02-01 .. 2025-08-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.193 | 1.978 | 95 |
| 4 | 2025-03-01 .. 2025-09-01 | sl_mult=1.5, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.178 | 1.506 | 43 |
| 5 | 2025-04-01 .. 2025-10-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 6 | 2025-05-01 .. 2025-11-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 7 | 2025-06-01 .. 2025-12-01 | sl_mult=1.5, rr=1.5, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.257 | 2.157 | 32 |
| 8 | 2025-07-01 .. 2026-01-01 | sl_mult=1.5, rr=1.0, threshold=0.6, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.35 | 3.215 | 76 |
| 9 | 2025-08-01 .. 2026-02-01 | sl_mult=1.0, rr=1.0, threshold=0.6, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.626 | None | 8 |
| 10 | 2025-09-01 .. 2026-03-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 11 | 2025-10-01 .. 2026-04-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.337 | 2.44 | 11 |
| 12 | 2025-11-01 .. 2026-05-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 13 | 2025-12-01 .. 2026-06-01 | sl_mult=1.5, rr=1.5, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.648 | 3.371 | 25 |
| 14 | 2026-01-01 .. 2026-07-01 | sl_mult=1.5, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.294 | 2.002 | 97 |
| 15 | 2026-02-01 .. 2026-08-01 | sl_mult=1.5, rr=1.5, threshold=0.65, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 1.004 | 11.784 | 17 |
| 16 | 2026-03-01 .. 2026-09-01 | sl_mult=1.0, rr=1.5, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.858 | 6.168 | 48 |
| 17 | 2026-04-01 .. 2026-10-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | None | None | 0 |
| 18 | 2026-05-01 .. 2026-11-01 | sl_mult=1.0, rr=1.0, threshold=0.55, entry_start_utc=7, entry_end_utc=16, force_close_utc=16, min_sl_distance_usd=0.5, max_sl_distance_usd=15.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=100.0, max_spread_abs=0.5, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0, one_trade_per_day=True, min_bars=250 | 0.364 | 2.528 | 75 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4).
