# SKILL: fund2-strategy-london-breakout (Strategi #1)

Versi 1.0.0 · Track A · PRD Fund2 §5.3 · Modul:
`api/strategies/london_breakout.py` · Test: `api/tests/test_london_breakout.py`
(format final: `strategies/README.md`)

## Logika

Breakout sesi London + filter spread pada XAUUSD M5 (deterministik: tanpa
I/O, tanpa jam, tanpa RNG: murni `decide(context)`):

1. Hitung rentang Asia 00:00–07:00 UTC dari bar M5 closed hari itu (minimal
   60% bar terisi; guard pasar mati `range < 0.50` atau sanity
   `range > 150` tolak).
2. **BUY**: close bar terakhir (dalam window London 07:00–12:00 UTC) menembus
   atas rentang Asia + buffer 0.10, dan close sebelumnya masih di dalam
   rentang. **SELL**: cermin di bawah rentang.
3. 1 trade/hari, 1 posisi pada satu waktu.
4. **SL**: di luar candle breakout (structure stop), di-clamp ke batas
   jarak SL risk gate [0.50, 15.00] USD.
5. **TP**: 1.5 × jarak SL (RR 1.5).
6. Guard standar: spread > max(2×median 15m, 0.50) tolak; candle/likuiditas
   basi > 120 detik tolak; weekend tolak; bar belum closed tolak.

## Parameter (settings `strategy_params_london_breakout`)

| Param | Default | Arti |
| --- | --- | --- |
| `tf_seconds` | 300 | timeframe M5 |
| `asia_start_utc` / `asia_end_utc` | 0 / 7 | window rentang Asia |
| `london_start_utc` / `london_end_utc` | 7 / 12 | window entry London |
| `force_close_utc` | 16 | time exit engine (E1) |
| `min_asia_coverage` | 0.6 | fraksi minimal bar Asia |
| `min_range_usd` / `max_range_usd` | 0.50 / 150.00 | guard rentang Asia |
| `breakout_buffer_usd` | 0.10 | kedalaman tembus minimal |
| `rr` | 1.5 | TP = rr × jarak SL |
| `min_sl_distance_usd` / `max_sl_distance_usd` | 0.50 / 15.00 | batas risk gate |
| `risk_per_trade` / `max_volume` | 0.005 / 0.10 | sizing 0.5% equity, cap 0.10 lot |

## Risk

- SL/TP wajib, divalidasi risk gate (SL < harga < TP untuk BUY, sebaliknya SELL).
- Volume = equity × 0.5% / (jarak SL × 100 USD per lot per USD), floor ke
  step 0.01, cap 0.10 lot.
- Sizing, spread filter, staleness, dan 1-trade-per-day identik strategi #2
  agar perbandingan apples-to-apples.

## Hasil backtest (biaya: spread 0.50, slippage 0.10; equity 10.000)

| Periode | Trades | Winrate | PF | Expectancy | Max DD | Net |
| --- | --- | --- | --- | --- | --- | --- |
| M5 27 Okt–20 Nov 2026 (25 hari) | 8 | 50.0% | 1.24 | +5.44 USD / +0.11 R | 136.76 | +43.51 |
| M15 7 Sep–20 Nov 2026 (3.5 bulan) | 33 | 39.4% | 0.88 | −3.43 USD / −0.07 R | 445.97 | −113.24 |

- Kapan gagal: M15: winrate 39% dengan RR 1.5 (butuh ≥ 40% untuk balik
  modal setelah biaya) → PF 0.88, GAGAL setelah biaya. Trade-off buffer/RR
  sedang dieksplorasi lewat walk-forward.
- Percobaan parameter: grid 12 kombinasi (buffer × rr × min_range)
  tercatat di `backtest_runs`: detail `docs/LAPORAN_WALKFORWARD_P2.md`.
  Walk-forward penuh menunggu sejarah M5/M15 lebih panjang (crawler P2).
- Sampel pendek: bukan validasi walk-forward. Hasil bukan jaminan live.

Paper mode: jalan di paper runner multi-strategi (state `runner`, mode
`strategy_mode_london_breakout`). Gerbang live: paper 20 hari (PRD).
