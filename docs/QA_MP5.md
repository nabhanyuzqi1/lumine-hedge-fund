# QA Multipair XAUUSD+BTCUSD - Laporan

Task: t_f2mp5 · Tanggal: 2026-11-23 · QA: hf-qa
Rujukan: PRD v2.2 multipair, task body [FUND2-MP] QA multipair

## Ringkasan

| Area | Hasil |
| --- | --- |
| E2E live demo kedua simbol (T0..T4) | **PASS** - XAUUSD + BTCUSD chain lengkap di `order_events` live |
| Risk gate lintas simbol (eksposur agregat, order/menit, SL per simbol) | **PASS** |
| Kill-switch global kedua simbol | **PASS** |
| Reconciler snapshot 2 simbol + orphan adopt per simbol | **PASS** (1 finding, lihat bawah) |
| Recorder XAUUSD tidak terganggu aktivitas BTCUSD | **PASS** |
| Suite QA multipair (`qa_mp5.py`, in-process, DB `fund2_qa_mp5`) | **43 cek: 42 pass, 0 fail, 1 finding** - direproduksi 2× (run8, run9) identik |
| Regresi penuh suite P1b (`qa_p1b_v2.py`, 32 cek) | **0 fail** (28 pass + 4 deviasi terdokumentasi, identik ronde 1) |

## 1. E2E live kedua simbol (T0..T4 di order_events live)

Skrip `qa_mp5_live.py` ke fund2-api live (127.0.0.1:3110), user QA `e2e_mp5`
(dihapus setelahnya, baris order audit dipertahankan dengan user_id NULL).
Bukti: `qa_mp5_live_results.json` (workspace t_f2mp5); diverifikasi ulang
langsung ke DB live oleh QA ronde ini:

- **XAUUSD** `3b6dc980`: RECEIVED 10:44:07 → RISK_PASS → SENT → FILLED
  10:44:07.97 → **FILLED_THEN_CLOSED** 10:45:57 (ditutup broker SL, close
  3605.18, profit -2.84).
- **BTCUSD** `e0e8a26d`: RECEIVED 10:44:07 → RISK_PASS → SENT → FILLED
  10:44:08.58 → **FILLED_THEN_CLOSED** 10:50:51 (ditutup flatten SELL
  `8167e4e4`, FILLED 10:50:51).

Order LIVE_E2E: **PASS**. T0..T4 lengkap untuk kedua simbol.

## 2. Risk gate lintas simbol

- Eksposur agregat: gabungan XAUUSD+BTCUSD melebihi `exposure_max_usd`
  → **422** `open exposure 22591.05 exceeds max 21000.00`; boundary pass 201.
- Order/menit agregat lintas simbol: order ke-3 → **422**
  `order rate limit exceeded`.
- SL per simbol: min/max jarak SL dievaluasi per spec (BTCUSD min 10 / max
  1000; XAUUSD sesuai spec) → pelanggaran ditolak 422 dengan alasan eksplisit.
- Spread & volume per simbol, fail-closed tanpa spec, risk per trade lintas
  simbol: PASS.

## 3. Kill-switch GLOBAL

- STOP_NEW_ORDERS: order baru XAUUSD **dan** BTCUSD sama-sama ditolak 422
  `kill-switch aktif`; baris audit tetap dibuat (status FAILED).
- GLOBAL_HALT: blokir kedua simbol; release tanpa checklist → 400, dengan
  checklist → 200.
- Flatten: 2 posisi (730001 XAUUSD, 730002 BTCUSD) → CLOSE command → CLOSED.
- PAUSE_STRATEGY scoped per strategi (bukan per simbol): breakout 422, manual 201.
- Auto-trigger streak FAILED campur simbol → STOP_NEW_ORDERS ter-arm.

## 4. Reconciler multipair

- Snapshot reconnect mencakup posisi kedua simbol (740001 XAUUSD 0.02,
  740002 BTCUSD 0.03): PASS.
- Orphan adopt per simbol (741001 XAUUSD, 741002 BTCUSD, event symbol benar):
  PASS.
- Orphan BTCUSD tanpa SL → emergency SL diqueue: PASS.
- Order hilang per simbol terjelaskan (FILLED_THEN_CLOSED) tanpa kill-switch
  palsu: PASS; BTC FAILED tak terjelaskan → flag + GLOBAL_HALT ter-audit: PASS.

**Finding 1 (deviasi, bukan fail)** - `recon/finding_emergency_sl_not_per_symbol`:
SL darurat orphan masih memakai `EMERGENCY_SL_DISTANCE` global 15.0 (untuk
BTCUSD 61269 = 0.025% harga - derau biasa; spec XAUUSD sl_max=15.0).
SL darurat seharusnya per-simbol. Dibuat kartu follow-up backend.

## 5. Recorder XAUUSD vs flood BTCUSD

- Backpressure >5s membuang **sampel likuiditas** (4/4 dibuang, 0 baris
  `liquidity_samples`), candle tetap dibangun, `order_events` tidak pernah
  masuk pipeline recorder (sentinel utuh).
- Flood 5000 tick BTCUSD: ring buffer XAUUSD utuh (100), jendela likuiditas
  independen, candle M1 XAUUSD tetap terbangun, parquet kedua simbol benar
  (xau_rows=100, btc_rows=5000; setelah flush 10000 BTC ticks).
- Order events recorder tidak pernah dibuang (fills ord-2500/5000/7500).

## 6. Regresi P1b (32 cek)

`qa_p1b_v2.py` dijalankan ulang penuh pada build current (23 Nov): **32 cek
= 28 pass, 0 fail, 4 deviasi** - identik dengan hasil terdokumentasi
`QA_P1b.md` ronde 1 (disconnect 10/10, kill-switch, security). DoD "0 fail"
terpenuhi. Catatan teknis: skrip v2 ditulis sebelum trigger append-only
`order_events` (PRD 19.4); re-run memakai salinan `qa_p1b_v2_rerun.py` dengan
workaround `session_replication_role = replica` di DB `fund2_test` terisolasi
(pola conftest pytest) - tidak mengubah asersi test apa pun.

## Guardrail akhir (23 Nov ~11:00 WIB)

- `/health` → `{"ok":true,"subscribers":1}`; kill-switch live **inactive**;
  `max_spread` kembali 0.5; `allowed_symbols=[XAUUSD,BTCUSD]`.
- Recorder hidup: ticks JSONL & parquet ter-update saat verifikasi.
- User QA `e2e_mp5` dihapus (0 baris tersisa); order baris audit dipertahankan
  dengan user_id NULL.
- Tidak ada order live baru setelah E2E di atas; tidak ada state live yang
  tertinggal dari test.
