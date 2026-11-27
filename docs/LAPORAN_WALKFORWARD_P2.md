# Walk-forward london_breakout v1.0.0 (XAUUSD H1)

Run ID: `4ce6f25d-fe31-49f4-9eaf-2d95f80da7a4`
Window: latih 6 bulan / uji 1 bulan, geser 1 bulan [USULAN PRD 5.4]
Biaya: spread 0.5 USD, slippage 0.1 USD per fill; equity awal 10000.0 USD; risiko 0.5% per trade
Grid parameter: 12 kombinasi; total percobaan tercatat di backtest_runs: 52

## Hasil per window uji

| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-08-01 .. 2026-09-01 | 483 | 2 | 0.0 | 0.0 | -45.67 USD / -0.915 R | 91.34 (0.0091) | -91.34 | GAGAL: profit factor 0.0 < 1 setelah biaya |
| 2 | 2026-09-01 .. 2026-10-01 | 504 | 9 | 0.4444 | 1.028 | 0.74 USD / 0.018 R | 131.32 (0.0132) | 6.64 | OK |
| 3 | 2026-10-01 .. 2026-11-01 | 510 | 8 | 0.375 | 1.104 | 3.0 USD / 0.064 R | 181.17 (0.0179) | 23.97 | OK |
| 4 | 2026-11-01 .. 2026-12-01 (parsial) | 345 | 3 | 0.6667 | 2.319 | 21.08 USD / 0.426 R | 47.94 (0.0048) | 63.24 | OK |

## Ringkasan gabungan (ekuiti berantai antar window uji)

- Window uji: 4 (dengan trade: 4, profit: 3)
- Total percobaan parameter: 52 (semua tercatat di backtest_runs)
- Net profit gabungan: 2.51 USD (saldo akhir 10002.51 USD)
- Max drawdown gabungan: 91.34 USD (0.0091)

## Parameter terpilih per window (dari window latih)

| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-02-01 .. 2026-08-01 | buffer=0.3, rr=1.5, min_range=0.5 | -0.227 | 0.619 | 19 |
| 2 | 2026-03-01 .. 2026-09-01 | buffer=0.3, rr=1.5, min_range=0.5 | -0.294 | 0.533 | 21 |
| 3 | 2026-04-01 .. 2026-10-01 | buffer=0.3, rr=2.0, min_range=0.5 | -0.112 | 0.814 | 27 |
| 4 | 2026-05-01 .. 2026-11-01 | buffer=0.3, rr=2.0, min_range=0.5 | -0.07 | 0.879 | 32 |

Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan yang besar relatif terhadap jumlah window uji adalah indikasi overfitting (PRD 5.4). Data H1 terbatas ~10 bulan; ulangi dengan sejarah 2 tahun (DoD P2) begitu crawler mengirimnya.
