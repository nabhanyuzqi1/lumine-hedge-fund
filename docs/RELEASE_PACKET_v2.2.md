# Release Readiness Packet v2.2: Fund2

Kartu: **t_128a9dee** (Lengkapi paket kesiapan operasional dan rollback rilis) · Tanggal: 25 Nov 2026 (WIB)
Penyusun: hf-devops · Status paket: **LENGKAP SEBAGAI DOKUMEN** · Keputusan rilis: **NO-GO untuk canary/live**

> **Tidak ada deployment dan tidak ada perubahan live trading pada kartu ini.** Semua verifikasi bersifat read-only kecuali pembuatan dokumen dan eksekusi uji terisolasi (soak pada DB sekali buangan, `TELEGRAM_ALERTS_OFF=1`). Live trading tetap **OFF** sesuai `KEPUTUSAN_OWNER.md` (F2, H1).

## 1. Keputusan

| Pertanyaan | Jawaban |
| --- | --- |
| Apakah paket release readiness v2.2 lengkap? | Ya, seluruh komponen wajib kini ada dokumennya (§2) |
| Apakah boleh canary live sekarang? | **TIDAK** (NO-GO). Prasyarat G1/G2/G3 belum lulus (§3) |
| Apakah boleh general release sekarang? | **TIDAK** (belum canary) |
| Apakah live trading aktif? | **TIDAK**. `env=demo`, kill switch nonaktif, runner paper, `halted=false` |
| Apa yang memblokir? | P9, D1 + approval live, guardrail drift, rollback drill, artifact freeze (§5) |

## 2. Isi paket (9 komponen wajib)

| # | Komponen | Dokumen | Kartu sumber | Status |
| --- | --- | --- | --- | --- |
| 1 | Rencana canary live terbatas | `CANARY_PLAN_v2.2.md` | baru (t_128a9dee) | **ADA** |
| 2 | Rencana general release + 7 hari stabilisasi | `GENERAL_RELEASE_PLAN_v2.2.md` | baru (t_128a9dee) | **ADA** |
| 3 | Rollback plan + checklist | `ROLLBACK_PLAN_v2.2.md`, `CHECKLIST_ROLLBACK_v2.2.md` | a17 + baru | **ADA** (drill penuh belum) |
| 4 | Artefak dan build yang akan dirilis | `ARTEFAK_RILIS_v2.2.md` | baru (t_128a9dee) | **ADA** (tag belum) |
| 5 | Risk register + threat model | `RISK_REGISTER_v2.2.md` | a20 | **ADA** (DRAFT, review owner) |
| 6 | Hasil load/soak | `LOAD_SOAK_v2.2.md`, `QA_v22_soak_extended_*.json` | b1 + baru | **ADA** (batas §5 LOAD_SOAK) |
| 7 | Observability | `OBSERVABILITY_v2.2.md`, `RUNBOOK_v2.2.md` | a10, b2 | **ADA** (F1/F2 terbuka) |
| 8 | Runbook operasional + incident playbook | `RUNBOOK_v2.2.md`, `RUNBOOK_v2.2_UJI.md`, `INCIDENT_PLAYBOOK_v2.2.md` | b2, a17 | **ADA** (diuji pihak lain) |
| 9 | Prasyarat live terpisah (D1, kill switch, guardrail, approval) | `PRASYARAT_LIVE_v2.2.md` | baru (t_128a9dee) | **ADA** |

Dokumen pendukung: `RELEASE_CHECKLIST_v2.2.md` (gate resmi), `DR_v2.2.md` (backup/restore), `QA_P5_cutover.md` (7 gerbang cutover), `SCHEMA_v2.2.md`, `ea/HMAC_CONTRACT.md`.

## 3. Status prasyarat live (G1/G2/G3)

| Gerbang | Isi | Status 25 Nov 2026 | Bukti |
| --- | --- | --- | --- |
| G1 Kesiapan teknik | engineering v2.2 + P9 + QA sign-off + rollback teruji | **BELUM** | `t_f2llm4` berjalan (paper LLM); P9: 8/20 hari, 8/100 trade, PF 1,211, DD 1,38% (`qa_p5_gate5_london_breakout.md`); rollback penuh belum di-drill |
| G2 D1 | modal live + batas kerugian absolut | **DEFER** | `KEPUTUSAN_OWNER.md` bagian E |
| G3 Approval live | persetujuan tertulis terpisah dari H1 | **BELUM ADA** | tidak ada catatan approval |

Prasyarat rinci dan daftar periksa A-01..A-14: `PRASYARAT_LIVE_v2.2.md` §4.

## 4. Kondisi runtime terverifikasi (25 Nov 2026, ±22:00 WIB, read-only)

| Pemeriksaan | Hasil |
| --- | --- |
| `GET /health` | `{"ok": true, "subscribers": 1, "env": "demo"}` |
| Layanan inti | `fund2-api`, `fund2-postgres`, `fund2-alerts`, `fund2-paper-runner`, `fund2-llm-agent`, `fund2-hfm-recorder`, `fund2-shadow-runner`, `fund2-candle-rollup`: semua `active` |
| Kill switch | `active: false`, `mode: null`, `halted: false` |
| Auto-trigger | 25 Nov 22:00: `ea_offline` 60 s, DD harian 10%, DD total 15%, FAILED beruntun 100 (F-03). **Sejak 26 Nov 06:39 WIB (§I.4, `t_bf4b85f9`): `ea_offline_seconds` 6 s, `ea_offline_halt_seconds` 60 s, DD harian 3%, DD total 8%, FAILED beruntun 3** |
| Skema | Alembic head `l012`, DB `l012` (sinkron) |
| Git | HEAD `f39c60f` (master), tree kotor (fix AUDIT-B + file QA baru), **belum ada tag** |
| Backup terakhir | `backup-20261125T043315Z.json`: `status=ok`, `offsite=1`, 122 MB, sha256 tercatat |
| Pytest penuh | **1127 passed, 1 warning, 0 failed** (12 m 53 s, `QA_v22_pytest_25nov_fix_run2.log`, run terbaru) |
| Soak extended | 32.848 request / 360 s, 0 error 5xx, RSS +5,9%, p95 220,8 ms (lulus) |
| Alert daemon | `fund2-alerts` active sejak 07:42 WIB (restart), kirim `sendMessage 200 OK` terakhir 19:46 WIB |
| Spread profile service | `failed` sejak 07:15 WIB (lihat F-10) |
| MT5/EA | `lumine-hedge-fund-mt5` active sejak 19:42 WIB; 2 insiden `auto:ea_offline` pagi ini + 1 offline 19:40 (6 m, akibat stop/start QA latensi) |

## 5. Temuan (urut dampak)

| ID | Temuan | Severity | Status | Pemilik | Tindakan |
| --- | --- | --- | --- | --- | --- |
| F-01 | P9 belum lulus: 8/20 hari kerja, 8/100 trade, PF 1,211 < 1,3, DD 1,38% (verdict `DATA_BELUM_CUKUP`) | BLOCKER | terbuka | hf-ceo/QA (`t_f2v22a14`) | Lanjutkan akumulasi paper; evaluasi ulang; `t_f2llm4` jalan |
| F-02 | D1 DEFER dan approval live tertulis belum ada | BLOCKER | terbuka | Owner | Isi D1 + approval G3 (`PRASYARAT_LIVE_v2.2.md` §1, §4) |
| F-03 | Guardrail runtime longgar dari policy: `max_volume` 1,0 vs 0,10; order/menit 10 vs 5; DD harian 10% (dan `max_daily_drawdown` 100) vs 3%; DD total 15% vs 8%; FAILED beruntun 100 vs 3; `ea_offline_seconds` 60 s vs A12 6 s; SL distance dan tick age belum terpetakan | BLOCKER (live) | **TERTUTUP (26 Nov 2026 06:39 WIB)** | hf-ceo (`t_bf4b85f9`) | Angka final `KEPUTUSAN_OWNER.md` §I. Runtime disamakan lewat kanal resmi `PUT /admin/risk-settings` (sesi 2FA + password ulang): `max_volume` 0,10; order/menit 5; DD harian 3,0%; `max_daily_drawdown` 292,02 (= 3% x 9.733,86); DD total 8,0%; FAILED beruntun 3; `ea_offline_seconds` 6,0; `ea_offline_halt_seconds` 60,0. Bukti: `settings_audit` #356-#359, `audit_log` #716 (`CONFIG_CHANGED`), gate `guardrails_sesuai_policy = true` (`docs/VALIDASI_PAKET_RILIS_20261126T063940Z.json`), `/metrics` proses berjalan `ea.offline_threshold_s` 6 vs `ea.offline_halt_threshold_s` 60. Rincian: `docs/BUKTI_GUARDRAIL_PARITY_t_bf4b85f9.md`; aturan paritas dev/staging: `KEPUTUSAN_OWNER.md` §I.4 |
| F-04 | Drill rollback aplikasi penuh belum dijalankan (deviasi `RELEASE_CHECKLIST` 3.6) | BLOCKER canary | terbuka | hf-devops | Drill: tag sehat -> inject orphan -> langkah 1-10 -> resume-ready; catat durasi |
| F-05 | Tree kotor: fix AUDIT-B (`api/app/routes.py`, 64 baris) belum di-commit; `api/tests/test_orders_reasons.py` belum di-track; belum ada tag rilis | BLOCKER rilis | terbuka | pemilik fix AUDIT-B + hf-devops | Selesaikan + pytest + commit, lalu tag `fund2-v2.2-rc1` pada commit bersih |
| F-06 | Pipeline alert: F1 daemon beku saat Postgres belum siap (`db.pool().connection()` tanpa timeout) dan F2 teks `paper_state` tidak di-escape (400 `can't parse entities`). Mitigasi restart 07:42 WIB; akar belum diperbaiki | HIGH | terbuka | hf-devops + pemilik `t_f2p1b3`/`t_f2v22a10` | Tambah timeout/retry/urutan start; escape `_md_escape`; uji ulang `--send-test` |
| F-07 | MT5/EA tidak stabil: 2x `auto:ea_offline` pagi ini (05:05, 06:45) akar koneksi terminal belum diketahui; 19:40 offline 6 menit akibat stop/start QA latensi | HIGH | terbuka | hf-devops/hf-backend | Investigasi terminal/wine/network; wajib 24 jam stabil sebelum canary |
| F-08 | Bukti load/soak belum produksi-grade: in-process, 6 menit, tanpa EA paralel, tanpa recovery di tengah beban | HIGH | terbuka | hf-devops | Jalankan S-1..S-5 di `LOAD_SOAK_v2.2.md` §5.1 |
| F-09 | Artefak Lampiran B belum lengkap: architecture diagram + ADR, release notes, UAT owner, owner release approval | MEDIUM | terbuka | hf-ceo (`t_f2v22a18`), QA, owner | Tutup sebelum tag rilis |
| F-10 | `fund2-spread-profile.service` failed sejak 07:15 WIB; profil XAUUSD terakhir 24 Nov 00:15 UTC; jurnal unit sudah terotasi sehingga error aslinya tidak terbaca | MEDIUM | terbuka | hf-devops | Inspeksi ulang dengan jurnal aktif (jalankan manual pada jendela aman), perbaiki, jalankan ulang kalibrasi; verifikasi ambang spread |
| F-11 | Bridge produksi masih Bearer (EA v5.03), kontrak HMAC baru ada di dummy_bridge (deviasi non-kritis 4.3) | MEDIUM | terbuka | hf-backend | Kartu terpisah HMAC; jangan blok rilis kecuali owner minta |
| F-12 | Angka ambang tidak sinkron antar dokumen: `ROLLBACK_PLAN` §1 (5%/8%/3), `KEPUTUSAN_OWNER` (3%/8%), DB (10%/15%/100) | MEDIUM | **TERTUTUP (26 Nov 2026)** | hf-ceo | Satu sumber kebenaran: `KEPUTUSAN_OWNER.md` §I. `ROLLBACK_PLAN` §1 (T7/T9 + paragraf ambang), `RELEASE_CHECKLIST` 5.9, dan `PRASYARAT_LIVE` §3 sudah disinkronkan ke angka §I. Drift DB tersisa dilacak sebagai F-03 |

## 6. Delta terhadap `RELEASE_CHECKLIST_v2.2.md`

| Butir | Status di checklist | Kondisi sekarang | Catatan |
| --- | --- | --- | --- |
| 2.1 Risk gate tests | DEVIASI (1115 lulus, 6 gagal) | **LULUS**: 1127 passed, 0 failed | Fix run terbaru `QA_v22_pytest_25nov_fix_run2.log`; kontrak regime + isolasi `_ea_seen_mono` sudah dituntaskan |
| 3.6 Rollback teruji | DEVIASI | masih DEVIASI | F-04 |
| 5.7 Canary plan | PENDING (rollout plan LULUS) | **plan ADA** | `CANARY_PLAN_v2.2.md`; status tetap PENDING sampai approval owner |
| 5.8 Monitoring pasca-rilis | PENDING | plan ADA | `GENERAL_RELEASE_PLAN_v2.2.md` §5 |
| 5.1-5.4, 5.6 | PENDING | masih PENDING | UAT, P9, QA sign-off, approval, tag |
| (baru) | - | **temuan F-03** | Guardrail drift tidak tercantum di checklist; wajib masuk blok Release |

Checklist resmi tetap milik hf-ceo; kartu ini tidak mengubah statusnya. Perubahan status hanya dengan bukti baru yang bisa diukur ulang.

## 7. Urutan menuju GO (ringkas)

1. Tutup F-05 (commit fix AUDIT-B, pytest, tree bersih).
2. Tutup F-04 (drill rollback penuh) dan F-06 (alert F1/F2).
3. Jalankan S-1..S-5 (F-08) dan stabilisasi MT5 24 jam (F-07).
4. P9 lulus + QA sign-off (F-01).
5. Angka guardrail final sudah ditetapkan (`KEPUTUSAN_OWNER.md` §I) dan diterapkan ke runtime (§I.4; F-03/F-12 tertutup, gate `guardrails_sesuai_policy` PASS). Sisa keputusan owner: D1 + approval live tertulis (F-02).
6. Tag `fund2-v2.2-rc1` pada commit bersih, backup pre-release.
7. Owner menulis approval live (G3).
8. Canary sesuai `CANARY_PLAN_v2.2.md`; setelah DoD, general release sesuai `GENERAL_RELEASE_PLAN_v2.2.md`.

Langkah 1-3 dan 6-8 dieksekusi di window rilis, bukan oleh kartu dokumentasi ini.

## 8. Validasi paket

Validator read-only: `scripts/validate_release_packet.py`. Ia memeriksa keberadaan dokumen, marker isi, state git, `env=demo`, layanan inti, live OFF, guardrail vs policy, sinkron skema, umur backup, bukti pytest, dan hasil soak. Hasil: `docs/VALIDASI_PAKET_RILIS_latest.json` dan `docs/VALIDASI_PAKET_RILIS_20261125T220446Z.json`.

Hasil run 25 Nov 2026 22:04 WIB: `paket_dokumen`, `runtime_demo_env`, `layanan_inti_aktif`, `live_off`, `schema_sync`, `backup_segar`, `pytest_penuh_lulus`, `soak_extended_lulus` = PASS. Dua gate gagal sengaja menandai kesiapan rilis, bukan kegagalan dokumentasi: `git_bersih_dan_tag` (tree kotor, belum ada tag) dan `guardrails_sesuai_policy` (drift F-03). Verdict validator: **PAKET BELUM SIAP RILIS**.

Run 26 Nov 2026 06:39 WIB (`docs/VALIDASI_PAKET_RILIS_20261126T063940Z.json`): `guardrails_sesuai_policy` **PASS** setelah F-03 ditutup (`settings_actual` = angka §I, `guardrail_drift` kosong, `guardrail_open` kosong). Satu-satunya gate gagal kini `git_bersih_dan_tag` (F-05). Verdict tetap **PAKET BELUM SIAP RILIS** karena F-01, F-02, F-04, F-05 masih terbuka.

## 9. Larangan kartu ini

- Tidak melakukan deploy ke akun live, tidak mengubah `FUND2_ENV`, tidak mengaktifkan auto-trading live.
- Tidak mengubah `settings` risiko, kill switch, atau konfigurasi Caddy.
- Tidak membuat tag, tidak meng-commit kode milik kartu lain.
- Tidak mengedit log insiden, `order_events`, `kill_switch_events`.

## 10. Sign-off

| Peran | Nama | Tanggal | Keputusan | Catatan |
| --- | --- | --- | --- | --- |
| Penyusun | hf-devops | 25 Nov 2026 | Paket lengkap, NO-GO live | Kartu `t_128a9dee` |
| Review QA | hf-qa | menunggu | | Verifikasi bukti dan temuan |
| Review rilis | hf-ceo | menunggu | | Koordinasi kartu gate `t_f2gate_rel` |
| Approval live | owner | menunggu | | G3, terpisah dari H1 |
