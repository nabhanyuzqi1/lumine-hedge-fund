# SKILL: fund2-strategy-mean-reversion (Strategi #2)

Versi 1.0.0 · Track A · PRD Fund2 P2 · Modul:
`api/strategies/mean_reversion.py` · Test: `api/tests/test_mean_reversion.py`
(format final: `strategies/README.md`)

## Logika

Mean reversion Bollinger dengan trigger re-entry pada XAUUSD M5
(deterministik: tanpa I/O, tanpa jam, tanpa RNG: murni `decide(context)`):

1. Hitung SMA20 + sigma (populasi) dari 20 bar closed terakhir; band = SMA ± 2.5σ.
2. **BUY**: close sebelumnya menembus band bawah lebih dari buffer
   (close ≤ lower − 0.10) dan close terakhir kembali masuk band (≥ lower).
   **SELL**: cermin di band atas.
3. Entry hanya di window 07:00–16:00 UTC (London + NY pagi), 1 trade/hari,
   1 posisi pada satu waktu.
4. **SL**: di luar ekstrem swing 2 bar terakhir (bar pierce + bar trigger)
   ± buffer 0.10: dipilih dari 3 kandidat (swing 10 bar / bar terakhir /
   band-stop) pada backtest M5 riil; bar-terakhir unggul PF 2.01 vs 1.8 vs 1.0.
5. **TP**: di SMA (target reversion ke mean). Trade dilewati bila mean sudah
   di belakang harga atau RR < 0.6.
6. Guard sama dengan strategi #1: spread > max(2×median 15m, 0.50) tolak;
   candle/likuiditas basi > 120 detik tolak; weekend tolak; bar belum closed
   tolak; sigma < 0.50 (pasar mati) atau > 30 (news spike) tolak.

## Parameter (settings `strategy_params_mean_reversion`)

| Param | Default | Arti |
| --- | --- | --- |
| `period` | 20 | window SMA/sigma (bar) |
| `num_std` | 2.5 | lebar band dalam sigma |
| `entry_start_utc` / `entry_end_utc` | 7 / 16 | window entry UTC |
| `force_close_utc` | 16 | time exit engine (E1), sama dengan #1 |
| `reentry_buffer_usd` | 0.10 | kedalaman pierce minimal sebelumnya |
| `sl_lookback` / `sl_buffer_usd` | 2 / 0.10 | swing stop: pierce + trigger |
| `min_rr` | 0.6 | RR minimum ke mean |
| `min_sd_usd` / `max_sd_usd` | 0.50 / 30.0 | guard volatilitas |
| `min_sl_distance_usd` / `max_sl_distance_usd` | 0.50 / 15.00 | batas risk gate |
| `risk_per_trade` / `max_volume` | 0.005 / 0.10 | sizing 0.5% equity, cap 0.10 lot |

## Risk

- SL/TP wajib, divalidasi risk gate (SL < harga < TP untuk BUY, sebaliknya SELL).
- Volume = equity × 0.5% / (jarak SL × 100 USD per lot per USD), floor ke
  step 0.01, cap 0.10 lot: rumus identik strategi #1.
- Sizing, spread filter, staleness, dan 1-trade-per-day identik strategi #1
  agar perbandingan apples-to-apples.

## Hasil backtest (biaya: spread 0.50, slippage 0.10; equity 10.000)

| Periode | Trades | Winrate | PF | Expectancy | Max DD | Net |
| --- | --- | --- | --- | --- | --- | --- |
| M5 27 Okt–20 Nov 2026 (25 hari) | 8 | 50.0% | 1.63 | +14.54 USD / +0.29 R | 144.34 | +116.30 |
| M15 7 Sep–20 Nov 2026 (3.5 bulan) | 5 | 60.0% | 1.89 | +18.16 USD / +0.37 R | 53.04 | +90.80 |

vs Strategi #1 (periode sama): M5 net +43.51 (PF 1.24); M15 net −113.24
(PF 0.88, gagal setelah biaya). Detail: `docs/LAPORAN_P2_PERBANDINGAN_STRATEGI.md`.

- Kapan gagal: tidak trade saat volatilitas sangat rendah (filter sigma ≥
  0.50 USD) dan saat trend kuat tanpa re-entry band. Sampel M15 hanya 5
  trade: belum bisa disimpulkan robust.
- Percobaan parameter tercatat di `backtest_runs` (PRD 5.4 anti-overfit).
  Sampel pendek: bukan validasi walk-forward. Hasil bukan jaminan live.

Paper mode: jalan di paper runner multi-strategi (state `runner_mean_reversion`,
mode `strategy_mode_mean_reversion`). Gerbang live: paper 20 hari (PRD).
