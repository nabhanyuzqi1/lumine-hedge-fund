# SKILL: fund2-strategy-btc-range-breakout (Strategi #3)

Versi 1.0.0 · Track A · PRD Fund2 §5.3 (P2 multipair) · Modul:
`api/strategies/btc_range_breakout.py` · Test:
`api/tests/test_btc_range_breakout.py` (format final: `strategies/README.md`)

## Logika

Breakout channel Donchian + filter volatilitas pada BTCUSD H1, 24/7
(deterministik: tanpa I/O, tanpa jam, tanpa RNG: murni `decide(context)`).
Khas crypto: sesi Asia/London/NY tidak dipakai, weekend tidak ditolak, tanpa
time exit harian (posisi ditutup SL/TP oleh broker kertas):

1. Channel Donchian `range_lookback` bar H1 closed terakhir (excluding bar
   pemicu): high tertinggi / low terendah.
2. **BUY**: close bar terakhir menembus atas channel + buffer 50 USD, dan
   close sebelumnya masih di dalam channel (breakout pertama). **SELL**:
   cermin di bawah channel.
3. Filter volatilitas: ATR14 harus dalam [150, 900] USD — pasar mati atau
   ekstrem tidak entry.
4. 1 trade/hari, 1 posisi pada satu waktu.
5. **SL**: `atr_sl_mult × ATR` (struktur volatilitas; SL ratusan USD juga
   aman dari stops level broker BTCUSD ~50 USD, lihat
   `docs/VERIFIKASI_t_f2mp1.md`), di-clamp ke batas jarak SL risk gate
   [100, 1000] USD.
6. **TP**: `rr × jarak SL`.
7. Guard standar: spread > max(2×median 15m, 100) tolak; candle basi > 120
   detik dari close tolak; likuiditas tidak fresh > 120 detik tolak; bar
   belum closed tolak; posisi terbuka tolak; trades_today >= 1 tolak.
   Weekend TIDAK ditolak (`reject_weekend=False`).

## Parameter (settings `strategy_params_btc_range_breakout`)

| Param | Default | Arti |
| --- | --- | --- |
| `tf_seconds` | 3600 | timeframe H1 |
| `range_lookback` | 24 | channel Donchian 24 bar H1 (1 hari) |
| `breakout_buffer_usd` | 50.0 | kedalaman tembus minimal |
| `atr_period` / `atr_min_usd` / `atr_max_usd` | 14 / 150 / 900 | filter volatilitas |
| `atr_sl_mult` | 1.5 | SL = mult × ATR |
| `rr` | 1.5 | TP = rr × jarak SL |
| `max_trades_per_day` | 1 | batas harian |
| `reject_weekend` | False | crypto 24/7 |
| `force_close_utc` | None | tanpa time exit harian |
| `min_sl_distance_usd` / `max_sl_distance_usd` | 100 / 1000 | batas risk gate A2 BTCUSD |
| `risk_per_trade` / `max_volume` | 0.005 / 0.10 | sizing 0.5% equity, cap 0.10 lot |
| `max_spread_abs` | 100.0 | ambang spread absolut A9 BTCUSD |

## Risk

- SL/TP wajib, divalidasi risk gate (SL < harga < TP untuk BUY, sebaliknya
  SELL; jarak SL dalam [100, 1000] USD).
- Kontrak BTCUSD (t_f2mp1, verifikasi 8 deal live): 1.0 lot = 1 BTC, jadi
  pergerakan harga 1.00 USD = 1 USD/lot.
- Volume = equity × 0.5% / (jarak SL × 1 USD per lot per USD), floor ke step
  0.01, cap 0.10 lot.
- Guard identik strategi lain kecuali adaptasi 24/7 di atas, agar
  perbandingan apples-to-apples.
- Engine backtest/runner memberi `CONTEXT_BARS=64` bar sejarah lintas hari
  ke `decide()` (Donchian 24 bar H1 tidak muat dalam candle hari berjalan).

## Hasil backtest (walk-forward, biaya terkalibrasi PRD 5.2)

Cost model BTCUSD (t_f2mp4, settings `backtest_cost_calibration_BTCUSD`):
spread per sesi 47.04–48.00 USD, komisi 7.0 USD/lot round-turn, slippage
0.1 USD/fill, haircut 20%. Equity 10.000, risiko 0.5%/trade.

Walk-forward latih 6 bulan / uji 1 bulan (run_id `1179a486`, 13 baris di
`backtest_runs` = 12 kombinasi latih + 1 uji):

| Window | Trades | Winrate | PF | Expectancy | Max DD | Net |
| --- | --- | --- | --- | --- | --- | --- |
| Latih Mei–Okt 2026 (param terpilih: lookback 48, SL 1.0×ATR, RR 2.0) | 101 | - | 0.914 | −0.047 R | - | - |
| Uji 1–22 Nov 2026 | 12 | 41.7% | 1.299 | +8.22 USD / +0.168 R | 134.0 (1.3%) | +98.63 |

- Catatan jujur: window latih PF < 1 (belum ada edge setelah biaya pada
  sampel ini); window uji positif dengan hanya 12 trade. Sampel pendek —
  bukan bukti profitabilitas. Ulangi dengan sejarah 2 tahun (DoD P2) begitu
  crawler mengirimnya.
- Grid 12 kombinasi (atr_sl_mult × rr × range_lookback) — semua percobaan
  tercatat di `backtest_runs` (anti-overfitting PRD 5.4).

Paper mode: jalan di paper runner multi-simbol (state
`runner_btc_range_breakout`, mode `strategy_mode_btc_range_breakout`).
Gerbang live: paper 20 hari + QA (PRD) dan approve owner terpisah.
