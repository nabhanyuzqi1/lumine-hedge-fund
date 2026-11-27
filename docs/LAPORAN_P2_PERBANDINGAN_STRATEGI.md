# Perbandingan Strategi #1 vs #2 — P2 (t_f2p2a4)

Tanggal: 22 Nov 2026. Data: XAUUSD candle live DB (HFM ingest).
Engine sama untuk kedua strategi: `decide()` resmi + PaperBroker + risk gate
+ model biaya sama (spread 0.50 USD, slippage 0.10 USD per fill, equity awal
10.000 USD, risiko 0.5% per trade). Context rolling window 300 bar — identik
dengan paper runner, jadi sinyal backtest == sinyal paper.

## Ringkasan

| Periode | Strategi | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M5, 27 Okt–20 Nov (25 hari) | #1 London Breakout | 8 | 50.0% | 1.24 | +5.44 USD (+0.11 R) | 136.76 | +43.51 |
| M5, 27 Okt–20 Nov | #2 Mean Reversion | 8 | 50.0% | 1.63 | +14.54 USD (+0.29 R) | 144.34 | +116.30 |
| M15, 7 Sep–20 Nov (3.5 bulan) | #1 London Breakout | 33 | 39.4% | 0.88 | -3.43 USD (-0.07 R) | 445.97 | -113.24 |
| M15, 7 Sep–20 Nov | #2 Mean Reversion | 5 | 60.0% | 1.89 | +18.16 USD (+0.37 R) | 53.04 | +90.80 |

Detail JSON lengkap (kurva ekuitas, exit mix, entry per jam/hari):
`docs/perbandingan_p2.json` (isi terakhir: M15; M5 ada di riwayat run).

## Bacaan hasil

- **M5 (25 hari):** kedua strategi 8 trade, winrate sama 50%. Mean reversion
  unggul profit factor (1.63 vs 1.24) dan expectancy per trade
  (+14.54 vs +5.44 USD). Net profit +116.30 vs +43.51 USD.
- **M15 (3.5 bulan):** London breakout GAGAL setelah biaya (PF 0.88 < 1,
  net -113.24 USD, max DD 445.97). Mean reversion tetap positif
  (PF 1.89, net +90.80, max DD 53.04) tapi hanya 5 trade — sampel kecil,
  belum bisa disimpulkan robust.
- Kapan gagal: #1 gagal di periode M15 karena winrate 39% dengan RR 1.5 —
  butuh winrate >= 40% untuk balik modal setelah biaya. #2 gagal (tidak
  trade) saat volatilitas sangat rendah (filter sigma >= 0.50 USD) dan saat
  trend kuat tanpa re-entry band.

## Catatan

- Kedua strategi sudah jalan di paper mode (runner multi-strategi, state
  terpisah per strategi: paper_state `runner` dan `runner_mean_reversion`).
- Sampel masih pendek (data HFM M5 baru sejak 27 Okt). Walk-forward 2 tahun
  menyusul begitu crawler P2 kirim sejarah panjang (DoD P2).
- Hasil backtest bukan jaminan performa live.
