# QA P2 — Paritas Sinyal: Backtest vs Paper (t_f2p2a5)

**Tanggal:** 22 Nov 2026, ~21:00 WIB · **Verifier:** hf-qa · **PRD:** PRD_v2.1_Fund_Core.md §P2 (baris 292, 294)

## Verdict

**LULUS untuk paritas sinyal (100% ≥ target 99%) pada replay terkontrol — dengan 3 temuan kritis yang wajib ditutup sebelum paritas LIVE bisa dibuktikan.**

| # | Uji | Hasil |
| --- | --- | --- |
| T1 | Identitas fungsi `decide()` | **PASS** — backtest & paper memakai objek fungsi yang sama |
| T2 | Replay paritas sinyal (5000 bar M5, 27 Okt–20 Nov) | **PASS 100%** — 8/8 sinyal identik (side, volume, SL, TP, bar waktu) |
| T3 | Divergensi model spread (live vs backtest) | **BELUM TERUKUR** — data spread live baru 15 jam (weekend); band divergensi ada by construction |
| T4 | Kondisi operasional paper live | **GAGAL** — M5 feed mati sejak 20 Nov 16:55 UTC, runner crash saat sinyal pertama, runner tidak berjalan |

Paritas **by construction** (satu `decide()`) terverifikasi benar. Yang belum terbukti adalah paritas pada data live, karena jalur paper saat ini tidak bisa menghasilkan sinyal sama sekali (F-1..F-3 di bawah).

## 1. Metode

### T1 — Identitas `decide()`
`paper.backtest.decide is strategies.london_breakout.decide` → `True`; `paper.runner.decide is strategies.london_breakout.decide` → `True`.

### T2 — Replay paritas (bukti utama)
Seri candle **yang sama** (5000 bar M5 XAUUSD dari DB live, 2026-10-27 17:20 .. 2026-11-20 21:55 UTC, konversi broker-time→UTC sama dengan engine) dilewatkan ke **dua jalur asli**:

- **Jalur A (backtest):** `paper.backtest.run_backtest()` — engine sungguhan, `decide()` di-instrumentasi (wrapper perekam, logika tidak diubah).
- **Jalur B (paper):** `paper.runner.run_iteration()` — jalur keputusan paper sungguhan (build context → `decide()` → risk gate → persist), mode `dry=False` pada DB test buangan `fund2_test_parity_*` (dihapus setelah run; DB live hanya READ).

Kedua jalur diberi konteks tick sintetis **identik** (spread 0.50, median None, fresh) sehingga satu-satunya perbedaan yang mungkin berasal dari *context builder* dan *state handling*, bukan dari data pasar. Sinyal dibandingkan per bar: `opened_at`, `side`, `volume`, `sl`, `tp`. Repro:

```
cd ~/fund2/api && TELEGRAM_ALERTS_OFF=1 .venv/bin/python <workspace>/parity_replay.py
```

Kode yang diuji dipin (sha256-16): `london_breakout.py d60866d27a8371fe`, `paper/backtest.py 28297943ef1d7980`, `paper/runner.py c95190a17d99cb3d`, `paper/store.py deacdb1e686def5f`, `paper/broker.py 0e245ffb05954853`, `paper/feed.py 19521cfeaab29771`, `app/risk.py e86547ed436128f3` (HEAD 3ae9806 + edit P2 berjalan: STRATEGY_VERSION, canonical_tf, guard sharpe — none menyentuh `decide()`).

### T3 — Model spread
Agregat `liquidity_samples` live dibandingkan dengan model backtest (konstanta 0.50, median None → threshold absolut 0.50) vs paper live (threshold `max(2×median_15m, 0.50)`).

### T4 — Kondisi operasional
Inspeksi `candles`, `paper_orders`, `paper_state`, proses, dan log EA.

## 2. Hasil

### T2 — Paritas sinyal: 8/8 = **100.00%**

| Waktu sinyal (UTC) | Side | Vol | SL | TP | A | B |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-29 07:50 | SELL | 0.10 | 4024.06 | 4018.94 | ✓ | ✓ |
| 2026-10-30 11:15 | SELL | 0.08 | 3967.35 | 3951.72 | ✓ | ✓ |
| 2026-11-02 08:20 | SELL | 0.08 | 3898.07 | 3883.14 | ✓ | ✓ |
| 2026-11-03 07:15 | SELL | 0.10 | 3912.98 | 3906.15 | ✓ | ✓ |
| 2026-11-04 08:10 | BUY | 0.06 | 4026.07 | 4045.47 | ✓ | ✓ |
| 2026-11-10 09:05 | SELL | 0.03 | 4113.35 | 4077.42 | ✓ | ✓ |
| 2026-11-12 07:15 | SELL | 0.10 | 3965.29 | 3954.91 | ✓ | ✓ |
| 2026-11-18 07:05 | SELL | 0.08 | 3777.70 | 3762.45 | ✓ | ✓ |

- `A-only`: 0 · `B-only`: 0 · union 8 → **paritas 100.00%** (target ≥99%).
- Risk gate: 0 penolakan di kedua jalur (keputusan identik).
- `decide()` dipanggil 3630× (A) vs 4945× (B); 1315 panggilan ekstra B semuanya `None` (B tidak punya pre-filter `trades_today`, pembatasan ditegakkan di dalam `decide()` — hasil sama).
- Perbedaan konteks: **39/3630 (1.07%)**, seluruhnya di bar batas hari (00:00/00:05/23:05 UTC) akibat reset `today_bars` di jalur A vs window 300 bar di jalur B; `decide()` menyaring bar Asia per tanggal sehingga **nol dampak sinyal** (jam tersebut di luar jendela London 07:00–12:00).
- Selisih saldo akhir (A 10.043,51 vs B 10.049,81) murni model fill: backtest menambahkan slippage 0.10 pada entry, `run_iteration` entry di ask/bid polos. Bukan selisih sinyal.

## 3. Temuan

### F-1 (KRITIS) — Paper runner crash pada sinyal pertama
`paper/runner.py:171` memanggil `store.insert_order(mode=..., ...)` **tanpa argumen `conn`**, padahal `store.insert_order(conn, *, ...)` mewajibkannya → `TypeError` tepat saat order paper pertama mau disimpan. Terbukti saat replay (traceback asli, tanpa perubahan kode). Latent selama ini karena paper belum pernah punya sinyal live (weekend). Harness memakai shim khusus untuk meneruskan `conn`; logika lain tidak disentuh. **Wajib fix + regression test sebelum paper trading dinyatakan jalan.**

### F-2 (KRITIS) — Feed candle M5 mati; paper runner (5m) tidak akan pernah sinyal
- M5: **0 bar** setelah 2026-11-20 16:55 UTC (bar terakhir 20 Nov 23:55 WIB).
- M1: hidup sampai 22 Nov (535 bar sejak 20 Nov 17:00 UTC) — pipeline tick hanya mengagregasi M1 (`ingest._agg_m1`); tidak ada agregasi M1→M5.
- Sumber M5 sebelumnya adalah seed EA (`g_seedTfs` M1..D1), tapi log EA (`/tmp/mql5_today.log`) menunjukkan loop seed **M1 tiap ~1 detik** — seed loop menyangkut di M1 sehingga M5/M15/... tidak pernah disemai ulang.
- Akibat: sejak paper runner start (21 Nov 11:59 UTC), `decide()` selalu melihat candle M5 terakhir >120 detik (staleness guard) → tanpa sinyal, selamanya, sampai M5 mengalir. Ini juga membusukkan DoD P2 "backtest 2 tahun data" di TF M5.

### F-3 (KRITIS, ops) — Paper runner tidak berjalan
Tidak ada proses `paper.runner` saat verifikasi; `paper_state` terakhir disimpan 21 Nov 22:42 UTC (`days_observed` masih kosong, `broker_offset_h` None — konsisten: market tutup sepanjang weekend sejak start Sabtu). Tidak ada unit systemd/cron untuk runner (deploy/ hanya fund2-alerts & fund2-api). Butuh supervisi + auto-start.

### F-4 (SEDANG) — Divergensi threshold spread by construction
Backtest: spread konstanta 0.50, median `None` → threshold 0.50 absolut. Paper live: threshold `max(2×median_15m, 0.50)` ≥ 0.50 → paper bisa menerima spread di band (0.50, 2×median] yang backtest tolak. Belum bisa dikuantifikasi: `liquidity_samples` baru mencakup 15 jam weekend (spread stabil 0.43 < 0.50, 0 sampel divergen). Rekomendasi: catat `spread_median_15m` di alasan order paper, dan ukur ulang setelah ≥1 minggu data London hidup; jika perlu, samakan aturan threshold di kedua jalur.

### Catatan non-paritas
- `max_daily_drawdown` backtest hardcode 100 vs settings live default 300 — hanya relevan bila rugi harinya ≤ -100 (1 trade/hari, risiko ~50 USD); samakan agar gate identik.
- Live polling 15 detik + flush candle 5 detik bisa menggeser evaluasi ±1 bar dalam jendela staleness 120 detik; guard `last_close_ts > now` menutup celah entry prematur. Terlihat aman secara analisis; bukti live menyusul setelah F-1..F-3 ditutup.

## 4. Kesimpulan

1. **Paritas sinyal backtest vs paper: LULUS 100%** pada periode yang sama (replay 5000 bar M5, 27 Okt–20 Nov 2026), melebihi target ≥99%.
2. Paritas **live** belum dapat dibuktikan: jalur paper saat ini mati (F-1, F-2, F-3). Tiga kartu follow-up dibuat; paritas live diulang sebagai QA setelah ketiganya ditutup dan market London hidup ≥1 hari.
3. Laporan ini menguji kode pada HEAD 3ae9806 + hash pin di atas; repo sedang diedit konkuren oleh pekerja P2 lain (walk-forward) — hash menandai exactly what was verified.

## Lampiran — artefak verifikasi

| File | Isi |
| --- | --- |
| `parity_replay.py` | Harness T1+T2 (reproducible; DB test buangan, live read-only) |
| `parity_result.json` | Hasil terpin: sinyal, mismatch list, hash pin |
| `parity_run.log` | Log eksekusi final |
| `spread_divergence.py` / `.json` | Analisis T3 |
| `db_inspect.py` | Inspeksi read-only DB live |
