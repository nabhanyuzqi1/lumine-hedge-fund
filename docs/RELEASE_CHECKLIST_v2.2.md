# Release Checklist — Fund2 v2.2

Kartu: t_f2v22a17 · Tanggal: 25 Nov 2026 · Referensi: PRD v2.2 §25
Pemilik: hf-ceo (penyusun) · Reviewer: QA + Owner

## Cara pakai

- Setiap butir punya **metode verifikasi** (perintah/endpoint/bukti), **status**, dan **referensi bukti**.
- Status hanya boleh diubah dengan bukti baru yang bisa diukur ulang (bukan laporan lisan).
- Status: `LULUS` · `PENDING` (belum dikerjakan/belum waktunya) · `DEVIASI` (lulus dengan catatan yang disetujui) · `N/A`.
- Keputusan GO/NO-GO ada di bagian akhir. Checklist ini **bukan** pengganti approval tertulis owner (D1, H1).

## Ringkasan status

| Blok | Lulus | Pending/Deviasi |
| --- | --- | --- |
| Product & strategy | 5 | 1 PENDING |
| Execution & risk | 6 | 1 DEVIASI |
| Reliability | 5 | 1 DEVIASI |
| Security | 4 | 1 DEVIASI |
| Release | 0 | 9 PENDING |

**Keputusan saat ini: NO-GO untuk canary/live.** Semua butir engineering inti lulus; seluruh butir blok `Release` masih PENDING dan memang sengaja di-gate (H1: selesaikan wave engineering + P9 lulus + approval owner; live OFF sampai D1 + approval live terpisah). Checklist ini menjadi daftar kerja menuju GO.

## 1. Product & strategy

| # | Butir (PRD §25) | Metode verifikasi | Status | Bukti / catatan |
| --- | --- | --- | --- | --- |
| 1.1 | Scope rilis disetujui | Sprint plan + dispatch Direktur + instruksi owner | **LULUS** | `docs/SPRINT_PLAN.md` (baris a14-a18); Direktur dispatch gelombang 1 (25 Nov 06:02); owner unblock kartu dokumentasi via Telegram (25 Nov 06:22). Kartu live (a14/a15/a16/b1) tetap ter-gate. |
| 1.2 | Strategi dan versi tercatat | Query DB `strategy_versions` / `strategy_approvals` | **LULUS** | Dicek 25 Nov: 3 `strategy_versions` (london_breakout 1.0.0 REVIEW, 1.1.0 APPROVED; ml_gbm 1.0.0 APPROVED), 8 `strategy_approvals`, 2 `deployment_records`. Sistem versioning immutable: `docs/LAPORAN_DOD_VERSIONING_v22.md` (t_f2v22a6). |
| 1.3 | Backtest/walk-forward tersedia | File laporan BT/WF di docs | **LULUS** | `docs/BT_BTCUSD_btc_range_breakout.{json,md}`, `docs/LAPORAN_WALKFORWARD_P2.md`, `docs/LAPORAN_P2_PERBANDINGAN_STRATEGI.md`, `docs/perbandingan_p2*.json`. Catatan H1: kualitas gerbang (1 strategi lolos backtest 2 thn biaya realistis + walk-forward) dinilai BELUM LULUS di verdict `a857d75` — pintu perbaikan tetap terbuka, tidak memblokir kelengkapan artefak. |
| 1.4 | Shadow/paper selesai | Status runner + gerbang P9 | **PENDING** | Shadow runner aktif (`docs/QA_shadow_t_f2v22a4.md`); paper runner aktif sejak 21 Nov 11:59 UTC, balance 10.000 (dicek 25 Nov di `paper_state`). P9 (a14: 20 hari kerja + 100 trade) belum selesai. Catatan: evaluasi gerbang paper sebelumnya gagal (t_f2p5a1) → butuh keputusan owner/Direktur sebelum cutover. |
| 1.5 | Biaya dan asumsi tervalidasi | Laporan kalibrasi + symbol_specs | **LULUS** | `docs/KALIBRASI_BTCUSD.md` (23 Nov); spread profile harian (`fund2-spread-profile.timer`); `symbol_specs` XAUUSD/BTCUSD `spec_verified` via migrasi g007; komisi round-turn masuk perhitungan worst-case loss (portfolio risk). |
| 1.6 | Tidak ada klaim profit terjamin | Review docs | **LULUS** | PRD §0.2 ("Backtest tidak boleh dipromosikan sebagai bukti profitabilitas live") + semua laporan mencantumkan disclaimer bahwa backtest tidak membuktikan profit live. Scan `profit terjamin|guaranteed profit` di docs/ 25 Nov: tidak ada klaim (hanya teks butir checklist ini). |

## 2. Execution & risk

| # | Butir (PRD §25) | Metode verifikasi | Status | Bukti / catatan |
| --- | --- | --- | --- | --- |
| 2.1 | Risk gate tests lulus | `pytest` suite API | **DEVIASI** | Run penuh 25 Nov 2026 (`docs/QA_v22_pytest_25nov.log`): **1115 lulus, 6 gagal** dari 1121 test (15 m 07 d). Klasifikasi: (a) 4× `test_llm_risk` (kuota/burst) = flakiness isolasi test — state in-memory `_ea_seen_mono` dari test bridge sebelumnya + suite lambat membuat gate menolak order dengan "EA offline 72s" (perilaku fail-closed yang BENAR); lulus 20/20 saat sendiri dan 61/61 dalam grup file llm. (b) 2× `test_regime` = kontrak test kadaluarsa — test (t_f2v22a2, `9a2d864`) masih mengharapkan label `REGIME_OFF` saat filter mati, padahal kode (t_f2v22a19, `8ff9c54`) kini selalu melabel regime sesuai PRD §8.3 "hasil per regime"; gagal deterministik. Bukan bug produk; kartu tindak lanjut dibuat untuk perbaikan test. Test risk gate inti (`test_risk.py` + `test_portfolio_risk.py`) 93/93 lulus. |
| 2.2 | Portfolio exposure tests lulus | pytest + laporan DoD | **LULUS** | `docs/LAPORAN_DOD_PORTFOLIO_RISK_v22.md`: 43 test; race dua sinyal simultan dicegah `pg_advisory_xact_lock` (tidak bisa oversubscribe). |
| 2.3 | Idempotency lulus | pytest test_bridge + P1 E2E | **LULUS** | `POST /bridge/result` idempotent; state machine RECEIVED→RISK_PASS→SENT→FILLED/FAILED/STUCK; semua transisi append `order_events`. |
| 2.4 | Partial fill/rejection lulus | pytest state machine | **LULUS** | Test rejection/partial di `test_orders_api.py` + `test_bridge.py`; FAILED tetap tercatat di event log. |
| 2.5 | Kill-switch lulus | pytest + bukti produksi | **LULUS** | `test_kill_switch.py` (30+ test, termasuk auto-trigger dan anti-auto-flatten). **Bukti nyata (2x)**: auto `GLOBAL_HALT` ter-fire 24 Nov 22:05 UTC (`auto:ea_offline`, "EA offline 63s, 2 posisi terbuka", event id 98) dan 25 Nov 06:45 WIB (`auto:ea_offline`, "1 posisi terbuka", id 138) — keduanya ter-audit di `kill_switch_events`, halt menolak entry sesuai desain (lihat `INSIDEN_LOG_v2.2.md` INS-20261124-01, INS-20261125-03). |
| 2.6 | Reconciliation lulus | QA P1b + rerun | **LULUS** | `docs/QA_P1b.md` 10/10 disconnect reconciliation; rerun 25 Nov 05:39 `docs/qa_p1b_rerun.log`; auto-reconcile order STUCK >15 menit via posisi target (commit `1e6361d`). |
| 2.7 | SL broker-side diverifikasi | E2E live P1 + risk gate SL/TP wajib | **LULUS** | E2E live EA v5.03 O1 `b826a62c` & O2 `4c362755` T0..T4 lengkap di `order_events` live (verdict P1, 22 Nov). SL/TP wajib dan valid di risk gate. Verifikasi ulang wajib saat canary live. |

## 3. Reliability

| # | Butir (PRD §25) | Metode verifikasi | Status | Bukti / catatan |
| --- | --- | --- | --- | --- |
| 3.1 | API/DB/EA restart tests lulus | QA P1b reconnect + DR | **LULUS** | QA_P1b 10/10 reconnect-reconciliation; DR_v2.2 §4: start API 12 s terukur, MT5/EA start ~2-3 menit. |
| 3.2 | Backup dan restore lulus | Restore drill | **LULUS** | `docs/DR_v2.2.md`: 3x drill LULUS (23 Nov, 9-10 s per drill, DB 64 MB), staging terisolasi penuh; backup harian `fund2-backup.timer` 04:30 UTC + `pre-deploy`; offsite R2 terverifikasi. |
| 3.3 | Disk alert lulus | test_metrics | **LULUS** | `test_metrics.py` (24 test) mencakup disk ≥ 80%; ambang di `app/metrics.py`. Catatan: host satu disk — salinan lokal backup berada di disk yang sama, mitigasi via offsite R2. |
| 3.4 | Monitoring dan Telegram alert lulus | Daemon aktif + alert nyata | **LULUS** | `fund2-alerts.service` aktif; SEV-1 alert nyata terkirim saat auto GLOBAL_HALT 24 Nov; anti-spam dedup 300 s; `docs/OBSERVABILITY_v2.2.md`. |
| 3.5 | Runbook tersedia | Dokumen | **LULUS** | `docs/DR_v2.2.md` §5 (recovery sequence) + `docs/ROLLBACK_PLAN_v2.2.md` (kartu ini) + `docs/INCIDENT_PLAYBOOK_v2.2.md`. |
| 3.6 | Rollback teruji | Drill rollback | **DEVIASI** | Teruji: rollback versi strategi di staging (t_f2v22a6, 17 test), restore DB dari backup terenkripsi (3x drill LULUS), jalur release kill-switch + snapshot + reconcile di simulasi 25 Nov (`docs/SIMULASI_INSIDEN_*.md`) — drill dijalankan 2x (23:40 UTC & 23:53 UTC / 06:53 WIB), keduanya **LULUS** semua langkah, reproducible. Belum di-drill: rollback aplikasi penuh (git checkout commit sebelumnya + restart + reconcile E2E). Wajib di-drill sebelum canary (lihat ROLLBACK_PLAN §4). |

## 4. Security

| # | Butir (PRD §25) | Metode verifikasi | Status | Bukti / catatan |
| --- | --- | --- | --- | --- |
| 4.1 | RBAC dan auth lulus | Pentest + rerun | **LULUS** | `docs/qa_p1b_rerun.log` (25 Nov): 33 checks, 29 pass, 0 fail, 4 deviasi. Mencakup admin-only RBAC, CSRF, lockout, Argon2id, rate limit. |
| 4.2 | Secret scan bersih | pentest.py + scan secret repo | **LULUS** | `docs/qa_security_r2.json` check `secret_env_not_in_repo`: 0 secret di file repo (di luar `.env`), perm `.env` 0600 (22 Nov); semua probe keamanan DITOLAK (`docs/qa_security_v22_attempts.json`, 23 Nov); secret tidak ikut backup (DR §2.2). Jalankan ulang scan + `pentest.py` sebelum release window. |
| 4.3 | HMAC/replay test lulus | pytest + QA security | **DEVIASI** | 2FA anti-replay (counter reuse ditolak) LULUS. Deviasi tercatat: bridge masih Bearer (EA v5.03), kontrak HMAC baru ada di dummy_bridge — `DEV` di qa_p1b_rerun.log, dinilai non-kritis (loopback/docker internal). Keputusan lanjut HMAC = kartu terpisah. |
| 4.4 | Tidak ada critical/high finding terbuka | qa_security | **LULUS** | 0 fail; 4 deviasi non-kritis. Wajib: flip cookie `Secure` saat cutover domain (catatan DEV qa_p1b_rerun.log). |
| 4.5 | Hermes access boundary terbukti | Injection guard + sandbox | **LULUS** | Injection guard fase B: 27 kasus agent-side lulus (commit `c6e0b58`); research sandbox terisolasi (`docs/LAPORAN_DOD_RESEARCH_v22.md`); LLM risk gate + circuit breaker (commit `4facfc8`). |

## 5. Release

| # | Butir (PRD §25) | Metode verifikasi | Status | Bukti / catatan |
| --- | --- | --- | --- | --- |
| 5.1 | UAT owner lulus | Sesi UAT + berita acara | **PENDING** | Jadwalkan sebelum canary: owner jalankan alur login → dashboard → kill-switch (mode) → release (2FA) di staging/paper. |
| 5.2 | Paper gate lulus | Evaluasi gerbang paper | **PENDING** | Paper berjalan sejak 21 Nov; P9 (a14: 20 hari kerja + 100 trade) belum selesai. Evaluasi sebelumnya gagal (t_f2p5a1) → keputusan owner/Direktur diperlukan. |
| 5.3 | QA sign-off | Kartu QA | **PENDING** | Handoff QA (t_f2v22a13) masih review; TEST_PLAN.md ditunda sampai review. |
| 5.4 | Owner approval tertulis | Dokumen persetujuan | **PENDING** | Live OFF sampai D1 (modal + batas kerugian) + approval live terpisah (H1; Direktur 25 Nov). Agent tidak berhak mengisi (garis merah PRD 5.9). |
| 5.5 | Backup pre-release | `fund2_backup.sh pre-deploy` | **PENDING** | Prosedur siap; wajib dijalankan di awal release window (sebelum tag & deploy). |
| 5.6 | Release artifact dan commit tag | `git tag` + arsip | **PENDING** | Belum ada tag di repo. Saat P9 lulus: buat tag `fund2-v2.2-rc<N>` pada commit terverifikasi + catat di `deployment_records`. |
| 5.7 | Canary plan dan rollback plan | Dokumen | **PENDING** | Rollback plan: **LULUS** — `docs/ROLLBACK_PLAN_v2.2.md` (kartu ini). Canary plan: PENDING — kartu P10/a15 (usulan D10: min. 10 hari kerja, ≥ 30 trade, exposure terkecil, review harian). |
| 5.8 | Monitoring pasca-rilis | Window monitoring + alert | **PENDING** | Alerts + metrics + dashboard aktif; rencana window monitoring ketat pasca-canary mengikuti canary plan. |
| 5.9 | Guardrail runtime sesuai policy final | `validate_release_packet.py` gate `guardrails_sesuai_policy` | **LULUS** | Angka final di `KEPUTUSAN_OWNER.md` §I; runtime disamakan 26 Nov 2026 06:39 WIB lewat `PUT /admin/risk-settings` (2FA + password ulang, kartu `t_bf4b85f9`, `KEPUTUSAN_OWNER.md` §I.4). Nilai sekarang: `max_volume` 0,10; order/menit 5; DD harian 3,0% + `max_daily_drawdown` 292,02 (= 3% x 9.733,86); DD total 8,0%; FAILED beruntun 3; `ea_offline_seconds` 6,0; `ea_offline_halt_seconds` 60,0; `max_tick_age_s` 3,0. Bukti: `settings_audit` #356-#359, `audit_log` #716 (`CONFIG_CHANGED`), `docs/VALIDASI_PAKET_RILIS_20261126T063940Z.json` gate `guardrails_sesuai_policy = true` (`guardrail_drift` kosong, `guardrail_open` kosong). Rincian: `docs/BUKTI_GUARDRAIL_PARITY_t_bf4b85f9.md`. |

## 6. Keputusan GO/NO-GO

- **NO-GO canary/live** per 25 Nov 2026. Syarat menjadi GO:
  1. Blok Release 5.1-5.4 lulus (UAT, paper gate P9, QA sign-off, approval tertulis owner termasuk D1).
  2. Butir 5.5-5.6 dieksekusi di release window (pre-deploy backup, tag).
  3. Drill rollback aplikasi penuh lulus (menutup deviasi 3.6).
  4. Re-run `pentest.py` + pytest penuh di release window; hasil dilampirkan ke kartu.
  5. 6 kegagalan pytest 25 Nov (butir 2.1) dituntaskan: kontrak test regime diperbarui ke PRD §8.3 + isolasi `_ea_seen_mono` antar-test diperbaiki — kartu tindak lanjut `t_ec261999`.
  6. Butir 5.9 lulus: nilai guardrail runtime = `KEPUTUSAN_OWNER.md` §I dan gate `guardrails_sesuai_policy` PASS (penerapan lewat `PUT /admin/risk-settings` + `PUT /kill-switch/triggers`, bukan `psql`).
- **GO untuk melanjutkan P9/paper** (fase sekarang): ya — semua butir engineering inti lulus (test risk gate inti 93/93; 6 kegagalan terklasifikasi sebagai test debt, bukan bug produk) dan tidak ada critical/high terbuka.

## 7. Sign-off

| Peran | Nama | Keputusan | Tanggal | Catatan |
| --- | --- | --- | --- | --- |
| Penyusun | hf-ceo | Checklist disusun | 25 Nov 2026 | Kartu t_f2v22a17 |
| QA | hf-qa | (menyusul) | | |
| Owner | owner | (menyusul) | | Approval live terpisah (H1) |
