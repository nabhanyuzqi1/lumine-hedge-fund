# QA — Shadow Strategy (t_f2v22a4, PRD v2.2 §9)

Tanggal: 25 Nov 2026. Assignee: hf-backend.

## DoD

1. **Shadow jalan** — `fund2-shadow-runner.service` (systemd --user) aktif,
   MODE=SHADOW, 3 versi strategi bersamaan (lb-base, mr-base, btc-base),
   label + params_hash + code_commit tercatat per run (shadow_runs).
2. **Sinyal tercatat** — baris `shadow_signals` lengkap: harga referensi
   (ref_bid/ref_ask), spread + spread_median_15m, timestamp, regime
   (label + confidence), alasan (reason/detail), strategy_version, label,
   params_hash, code_commit, sim_status (FILLED/REJECTED/REGIME_BLOCKED),
   sim_fill_price, sim_cost_usd, is_simulation=TRUE.
   Bukti live: replay lb-base 25 Nov 08:20-08:45 UTC (window breakout live
   08:30 UTC) menghasilkan sinyal SELL 08:30, sim_status REJECTED dengan
   alasan risk gate (kill-switch GLOBAL_HALT aktif) — perilaku benar:
   sinyal tetap dicatat lengkap meski entry ditolak gate.
3. **Shadow tidak bisa kirim order (teruji negatif)** —
   - Test AST (test_shadow_isolation): modul shadow tidak meng-import
     app.bridge/app.worker/kill-switch dan tidak menulis ke
     orders/bridge_commands/paper_orders.
   - Test isolasi E2E: setelah tick_once, count orders/bridge_commands/
     paper_orders tetap 0.
   - Tripwire runtime (OrderLedgerTripwire): hanya memantau baris yang
     dapat diatribusikan ke shadow (strategy = strategy_id spec atau
     berawalan 'shadow'), exit code 9 bila dilanggar; order strategi lain
     (llm/manual/paper) yang sah tidak memicu false positive.
   - Tripwire OK pada semua replay + runner live.

## Simulasi fill konservatif

`shadow/fill.py`: slippage + komisi per lot round-turn dari settings,
exit price konservatif melawan sisi, P&L dicatat sebagai SIMULASI
(is_simulation=TRUE, saldo sim_balance), bukan realized P&L.

## Gerbang promosi shadow→paper (PRD 9.3)

Evaluasi out-of-sample: `python -m shadow.replay --label X --from .. --to ..`
memutar data live terekam melalui jalur produksi yang sama (supervisor
sandbox, regime classifier, risk gate, fill konservatif). Kriteria gate:
tanpa error kritis, perilaku sesuai spec, out-of-sample + biaya masuk akal,
tanpa indikasi data leakage, owner setuju. Endpoint API shadow hanya
read-only (`/shadow/runs`, `/shadow/signals`, dsb.).

## Perbaikan saat task ini

1. **Tripwire false positive** — tripwire lama menghitung SELURUH tabel
   orders, sehingga order sah strategi llm/manual memicu pelanggaran
   (runner crash-loop, 35x restart). Sekarang hanya baris shadow yang
   dihitung.
2. **Timeframe spec salah** — default XAUUSD `5m` tidak ada di DB (kanonik
   `M5`, lihat t_fbdb7329) → replay selalu 0 candle → strategi tak pernah
   sinyal. Diperbaiki di shadow/specs.py + shadow/replay.py.
3. **load_candles replay** — paper.runner.load_candles mengambil N candle
   terbaru global lalu menyaring "still forming"; pada replay historis
   semua candle tersaring. shadow/replay.py kini memakai
   load_candles_until dengan cutoff SQL berdasarkan `now` replay (tanpa
   mengubah paper/runner.py).

## Test

`api/.venv/bin/python -m pytest tests/test_shadow.py tests/test_shadow_api.py
tests/test_shadow_isolation.py tests/test_shadow_replay.py
tests/test_eval_gate_shadow.py` → **23 passed**.
