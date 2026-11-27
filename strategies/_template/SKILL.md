---
version: 0.1.0
author: hf-backend
license: internal
name: fund2-strategy-TEMPLATE
description: Template SKILL.md strategi Fund2: salin, isi TODO, jangan ubah struktur.
---

# SKILL: fund2-strategy-{{ID}} ({{NAMA}})

Versi {{X.Y.Z}} · Track {{A|B|C}} · PRD Fund2 {{§}} · Modul:
`api/strategies/{{id}}.py` · Test: `api/tests/test_{{id}}.py`
(format final: `strategies/README.md`)

## Logika

{{Aturan entry/exit langkah demi langkah, deterministik. Contoh:}}

1. {{Hitung indikator dari bar closed terakhir (tanpa look-ahead).}}
2. **BUY**: {{syarat}}. **SELL**: {{cermin}}.
3. Entry hanya di window {{HH}}–{{HH}} UTC, {{n}} trade/hari, 1 posisi.
4. **SL**: {{ struktur / indikator }}. **TP**: {{ rr × SL / mean }}.
5. Guard standar (sama semua strategi): spread > max(2×median 15m, 0.50)
   tolak; candle/likuiditas basi > 120 detik tolak; weekend tolak; bar belum
   closed tolak; {{guard spesifik strategi}}.

## Parameter (settings `strategy_params_{{id}}`)

| Param | Default | Arti |
| --- | --- | --- |
| `{{param}}` | {{nilai}} | {{arti}} |
| `min_sl_distance_usd` / `max_sl_distance_usd` | 0.50 / 15.00 | batas risk gate |
| `risk_per_trade` / `max_volume` | 0.005 / 0.10 | sizing 0.5% equity, cap 0.10 lot |

## Risk

- SL/TP wajib, divalidasi risk gate (SL < harga < TP untuk BUY, sebaliknya SELL).
- Volume = equity × 0.5% / (jarak SL × {{USD-per-lot-per-USD}}), floor ke
  step 0.01, cap 0.10 lot.
- {{Guard/risk spesifik strategi}}.

## Hasil backtest (biaya: spread {{0.50}}, slippage {{0.10}}; equity {{10.000}})

| Periode | Trades | Winrate | PF | Expectancy | Max DD | Net |
| --- | --- | --- | --- | --- | --- | --- |
| {{TF, tanggal}} | {{n}} | {{%}} | {{}} | {{USD / R}} | {{USD}} | {{USD}} |

- Kapan gagal: {{kondisi pasar yang membuat strategi rugi / tidak trade}}.
- Percobaan parameter: {{n}} kombinasi, tercatat di `backtest_runs` (run_id
  {{uuid}}), PRD 5.4 anti-overfit. Walk-forward: {{belum / hasil}}.
- Sampel {{pendek/cukup}}: {{bukan validasi walk-forward}}. Hasil bukan
  jaminan live.

## Status

Paper mode: state `runner_{{id}}`, mode `strategy_mode_{{id}}`. Gerbang live:
paper 20 hari (PRD) + approve owner. {{Tanggal mulai paper / hasil berjalan.}}
