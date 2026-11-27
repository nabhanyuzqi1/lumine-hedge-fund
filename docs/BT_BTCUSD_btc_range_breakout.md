# Walk-forward btc_range_breakout v1.0.0 (BTCUSD H1)

Run ID: `1179a486-aa15-4830-b9f7-a50df18645d8`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan [USULAN PRD 5.4]
Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor HFM/Duka + haircut 20%; komisi 7.0 USD/lot round-turn; slippage 0.1 USD per fill.
Spread akhir per sesi (USD): {'asia': 48.0, 'london': 47.04, 'newyork': 47.04, 'london_newyork': 47.04}
Catatan kalibrasi: window overlap 2026-11-20 00:00..2026-11-22 23:59 UTC; 13542 sampel HFM 5-detik
equity awal 10000.0 USD; risiko 0.5% per trade
Grid parameter: 12 kombinasi; total percobaan tercatat di backtest_runs: 13

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-01 .. 2026-12-01 (parsial) | 515 | 12 | 0.4167 | 1.299 | 8.22 USD / 0.168 R | 134.0 (0.0133) | 98.63 | OK |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 1 (dengan trade: 1, profit: 1)
- Total percobaan parameter: 13 (semua tercatat di backtest_runs)
- Net profit gabungan: 98.63 USD (saldo akhir 10098.63 USD)
- Max drawdown gabungan: 0.0 USD (0.0)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-05-01 .. 2026-11-01 | range_lookback=48, breakout_buffer_usd=50.0, atr_period=14, atr_min_usd=150.0, atr_max_usd=900.0, atr_sl_mult=1.0, rr=2.0, max_trades_per_day=1, reject_weekend=False, force_close_utc=None, min_sl_distance_usd=100.0, max_sl_distance_usd=1000.0, risk_per_trade=0.005, max_volume=0.1, min_volume=0.01, volume_step=0.01, usd_per_lot_per_usd=1.0, max_spread_abs=100.0, spread_median_multiplier=2.0, max_candle_age_s=120.0, max_liquidity_age_s=120.0 | -0.047 | 0.914 | 101 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4). Data H1 terbatas ~10 bulan; ulangi dengan sejarah 2 tahun (DoD P2) begitu crawler mengirimnya.
