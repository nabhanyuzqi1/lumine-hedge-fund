# VERDICT RELEASE P1 — Lumine-Hedge-Fund v2 (Fund Core)

Tanggal: 22 Nov 2026 · Koordinator: hf-ceo (t_f2co_p1) · Rujukan: PRD_v2.1_Fund_Core.md P1a–P1b
Verdict diterbitkan dari konsolidasi hasil QA sesuai DoD tambahan Direktur (butir b).

## Verdict: LULUS — direkomendasikan untuk approval rilis P1

Semua DoD P1a + P1b terpenuhi dan terverifikasi live/Direktur. Live trading tetap OFF sampai D1 (modal live + batas kerugian) diisi owner + approval live terpisah; paper mode berjalan.

## DoD P1a

| Butir | Bukti | Status |
| --- | --- | --- |
| 1 order demo E2E tercatat T0..T4 di event log | 53/53 order FILLED, chain `RECEIVED→RISK_PASS→SENT→FILLED` di `order_events` live DB (QA paritas core t_55fb2608, head e792011). Live EA v5.03 (c260da6): O1 b826a62c & O2 4c362755 `RECEIVED→RISK_PASS→SENT→FILLED→FILLED_THEN_CLOSED` dari result EA sungguhan (BUKTI_E2E_V503.md) | PASS |
| Risk gate menolak semua kasus uji | test_kill_switch.py 32/32 PASS (Direktur jalankan ulang); kill-switch manual+auto 17/17 (QA_P1b); bukti live: 2 order ditolak 422 saat owner aktifkan kill-switch manual | PASS |
| T0→T2 p95 < 300 ms pada ≥ 50 order | p95 135.5 ms, p99 149.5 ms pada 53 order (T0→T1 127.5, T0→T4 121.3) | PASS |
| Auto-halt drawdown teruji | daily drawdown → GLOBAL_HALT + audit (32/32 kill-switch, 17/17 QA P1b) | PASS |
| DoD tambahan (a): latensi API < 300 ms p95 | Terpenuhi (135.5 ms) | PASS |

## DoD P1b

| Butir | Bukti | Status |
| --- | --- | --- |
| Disconnect 10/10 | 10/10 rekonsiliasi benar (QA_P1b + test_dod_disconnect_10x_reconciliation, commit 752de1a) — diverifikasi Direktur | PASS |
| UI 4 halaman desktop + mobile | Login/Dashboard/StrategyLab/History di 1440×900 + 390×844 browser nyata; fix F-UI-1..3 (c8f9521) LULUS approve Direktur; screenshot di kartu t_854560b4 | PASS |
| Strategi #1 paper mode | London Breakout decide() + paper broker, 40/40 PASS (t_f2p1b2, diverifikasi Direktur) | PASS |
| Paper trading dimulai | paper_state `runner` aktif sejak 21 Nov 11:59 UTC, balance 10.000 — hari ke-0 dimulai sesuai DoD | PASS |

## Penopang lintas kartu

- **3 P0 fix E2E BTCUSD** selesai + approve Direktur: t_93a6f9dd pytest isolation (777a1f1), t_7e7dc1c1 EA result queue v5.03 (c260da6, 404 di-drop tanpa head-of-line), t_736acb4f race T4 (71e006e).
- **Owner decisions**: KEPUTUSAN_OWNER.md ter-commit (cd4319d), "SETUJU SEMUA", D1 DEFER → live OFF.
- **QA P1b**: 32 cek = 28 pass, 0 fail, 4 deviasi terdokumentasi (cookie `Secure` & HMAC digated, wajib saat cutover).
- **Alert Telegram**: fund2-alerts active, E2E live 6/6 kasus 200 OK (t_f2p1b3, diverifikasi Direktur).
- **Service live 22 Nov**: fund2-api health `{ok:true,subscribers:1}`, fund2-alerts, fund2-edge-proxy, fund2-postgres, fund2-hfm-recorder semuanya active.

## Deviasi / follow-up non-blocking P1

- Cookie `Secure` belum diset di dev — wajib saat cutover produksi.
- Poller perintah Telegram butuh bot khusus fund2 (token sekarang dipakai Hermes gateway, 409) — keputusan owner.
- t_cfa14c43: akar restart XFCE (4014 whitelist) — kartu devops terpisah.
