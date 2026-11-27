# Indeks Dokumentasi & Artefak Rilis: Fund2 v2.2

Dokumen ini adalah pintu masuk resmi `~/fund2/docs/`. Ia memetakan **setiap artefak wajib Lampiran B**
ke path, status, dan buktinya, lalu mengindeks bukti pendukung. Diperbarui: **26 Nov 2026** oleh hf-ceo
(kartu `t_f2v22a18`).

Aturan indeks ini: satu artefak wajib = satu baris dengan path yang benar-benar ada. Status yang
ditulis di sini harus sama dengan isi dokumennya; bila berbeda, dokumennya yang benar dan indeks wajib
diperbaiki.

## 1. Artefak wajib Lampiran B (14 butir)

| # | Artefak | Path | Status 26 Nov 2026 | Bukti / catatan |
| --- | --- | --- | --- | --- |
| 1 | PRD disetujui | `PRD_v2.2_End_to_End.md`, `KEPUTUSAN_OWNER.md` | **ADA** (baseline disetujui 21 Nov; D1 DEFER) | Lampiran B di PRD §Lampiran B |
| 2 | Architecture diagram + ADR | `ARCHITECTURE_v2.2.md`, `ADR_v2.2.md` | **ADA (baru, final)** | 15 ADR; topologi diverifikasi dari host |
| 3 | Threat model | `THREAT_MODEL_v2.2.md` (+ `RISK_REGISTER_v2.2.md`) | **ADA (baru, final)**; penerimaan risiko owner **BELUM** | 14 STRIDE + 5 ancaman AI + RR-1..RR-6 |
| 4 | Data dictionary | `DATA_DICTIONARY_v2.2.md` (+ `SCHEMA_v2.2.md`) | **ADA (baru, digenerate dari DB)** | 40 relasi, generator `gen_data_dictionary.py` |
| 5 | API/EA protocol spec | `API_EA_PROTOCOL_SPEC_v2.2.md` (+ `../ea/HMAC_CONTRACT.md`) | **ADA (baru, final)** | 65 path, kontrak EA v5.03 |
| 6 | Risk policy disetujui owner | `RISK_POLICY_v2.2.md` (+ `KEPUTUSAN_OWNER.md`) | **ADA**; baseline disetujui, amendemen angka **BELUM** | §3 memuat drift yang masih terbuka |
| 7 | Test plan + evidence | `TEST_PLAN_v2.2.md`, `TEST_EVIDENCE_pytest_*.log` | **ADA (baru)**; exit criteria E-1/E-5/E-6/E-8/E-9 **BELUM** | 1.347 lulus / 1 gagal (drift migrasi) |
| 8 | Backtest/walk-forward report | `LAPORAN_DOD_P2.md`, `LAPORAN_WALKFORWARD_P2.md`, `wf2_*.md`, `wf_baseline_*.md`, `BT_BTCUSD_btc_range_breakout.md` | **ADA** | `backtest_runs` 1.432 baris |
| 9 | Paper/shadow report | `PAPER_SHADOW_REPORT_v2.2.md`, `EVIDENCE_paper_gate_llm_20261126T0140.md`, `EVIDENCE_shadow_gate_*` | **ADA (diukur ulang 26 Nov)**; verdict **BELUM LULUS** | Paper PF 1,09; shadow 0 sinyal |
| 10 | Security review | `qa_security_v22_attempts.json`, `qa_p1b_rerun.log`, `pentest.py`, `QA_P1b.md` | **ADA** | 0 fail, 4 deviasi non-kritis |
| 11 | Backup/restore evidence | `DR_v2.2.md` + `~/fund2-backups/manifest.tsv` + `logs/backup-*.json` | **ADA** | 3/3 drill LULUS; RTO ~21 s; offsite WARN 1x |
| 12 | Runbook + incident playbook | `RUNBOOK_v2.2.md`, `RUNBOOK_v2.2_UJI.md`, `INCIDENT_PLAYBOOK_v2.2.md`, `INSIDEN_LOG_v2.2.md` | **ADA** (diuji pihak lain) | 2 simulasi insiden LULUS |
| 13 | Release notes | `RELEASE_NOTES_v2.2.md` | **ADA (baru)**; rilis **NO-GO** | 10 masalah diketahui didokumentasikan |
| 14 | Rollback plan | `ROLLBACK_PLAN_v2.2.md`, `CHECKLIST_ROLLBACK_v2.2.md`, `ROLLBACK_P5.md` | **ADA**; drill aplikasi penuh **BELUM** | langkah 1-10 siap diuji |
| 15 | Owner release approval | `OWNER_RELEASE_APPROVAL_v2.2.md` | **ADA (formulir)**; tanda tangan **BELUM** | A-01..A-14; semua BELUM = NO-GO |

Catatan: Lampiran B menyebut 14 butir; di atas dipecah menjadi 15 baris karena "data dictionary" dan
"API/EA protocol spec" adalah dua dokumen terpisah yang keduanya wajib ada.

**Kesimpulan indeks: semua artefak kini ADA sebagai dokumen. Yang belum adalah persetujuan owner
(risiko residual, angka guardrail final, D1, approval live), plus bukti yang memang harus menunggu
(P9 paper, tag rilis, drill rollback).**

## 2. Dokumen keputusan & kebijakan

| Path | Isi | Status |
| --- | --- | --- |
| `KEPUTUSAN_OWNER.md` | Baseline risk policy + amendemen F1/G1/H1 | disetujui owner |
| `RISK_POLICY_v2.2.md` | Konsolidasi kebijakan + status implementasi | final dokumen |
| `PRASYARAT_LIVE_v2.2.md` | 3 gerbang terpisah, drift guardrail, prasyarat G3 | acuan gate |
| `PRD_v2.1_Fund_Core.md`, `PRD_v2.2_End_to_End.md` | PRD | acuan |
| `RELEASE_CHECKLIST_v2.2.md` | Checklist 6 blok + GO/NO-GO | NO-GO live |
| `RELEASE_PACKET_v2.2.md`, `ARTEFAK_RILIS_v2.2.md` | Paket kesiapan + manifes artefak/tag | acuan rilis |
| `GENERAL_RELEASE_PLAN_v2.2.md`, `CANARY_PLAN_v2.2.md` | Rencana rilis umum & canary | menunggu gate |
| `PLAN_UI_AUDIT.md`, `SPRINT_PLAN.md` | Rencana kerja | historis |

## 3. Arsitektur, data & operasional

| Path | Isi |
| --- | --- |
| `ARCHITECTURE_v2.2.md` | Topologi, komponen, alur T0-T4, trust boundary, batasan |
| `ADR_v2.2.md` | 15 ADR (DB native, single service, long-poll, append-only, dsb.) |
| `DATA_DICTIONARY_v2.2.md` + `gen_data_dictionary.py` | Kamus kolom hasil introspeksi DB |
| `SCHEMA_v2.2.md` | Tabel logical, retensi, partisi, governance |
| `API_EA_PROTOCOL_SPEC_v2.2.md` | Kontrak REST + EA (HMAC, poll, tick, positions, heartbeat) |
| `OBSERVABILITY_v2.2.md` | Metrik, alert SEV-1..SEV-4, pemicu |
| `REGIME_v2.2.md` | Deteksi regime deterministik |
| `MODEL_CHAIN.md` | Rantai model LLM + fallback |
| `RUNBOOK_v2.2.md`, `RUNBOOK_v2.2_UJI.md` | Prosedur operasi + bukti uji runbook |
| `INCIDENT_PLAYBOOK_v2.2.md`, `INSIDEN_LOG_v2.2.md` | Playbook insiden + log insiden nyata |
| `DR_v2.2.md` | Backup, restore drill, RTO/RPO |
| `ROLLBACK_PLAN_v2.2.md`, `CHECKLIST_ROLLBACK_v2.2.md`, `ROLLBACK_P5.md` | Rollback |

## 4. Risiko, keamanan, kepatuhan

| Path | Isi |
| --- | --- |
| `RISK_REGISTER_v2.2.md` | 14 risiko (R-01..R-14) + matriks prioritas |
| `THREAT_MODEL_v2.2.md` | STRIDE TM-01..TM-14, AI-01..AI-05, skenario S1-S5 |
| `qa_security_v22_attempts.json`, `qa_security_r2.json` | Bukti probe keamanan |
| `qa_p1b_rerun.log`, `QA_P1b.md`, `QA_P1b_UI_R2.md` | Hasil uji keamanan/UI P1b |
| `pentest.py` | Skrip pentest sederhana (read-only) |

## 5. Bukti pengujian

| Path | Isi | Hasil |
| --- | --- | --- |
| `TEST_PLAN_v2.2.md` | Rencana uji + exit criteria | acuan |
| `TEST_EVIDENCE_pytest_20261126T012510.log` | Full suite 26 Nov | 1.347 lulus / 1 gagal (drift `m013`) |
| `QA_v22_pytest_25nov_fix_run2.log` | Full suite hijau 25 Nov | 1.127 lulus |
| `QA_v22_pytest_25nov.log` | Sebelum perbaikan | 6 gagal (sudah ditutup `90e4c1e`) |
| `QA_P5_cutover.md` | 7 gerbang cutover + latensi | p95 182,8 ms (n=207) |
| `LOAD_SOAK_v2.2.md`, `QA_v22_soak_extended_*.json` | Load & soak | 0 error 5xx |
| `QA_P2_paritas.md`, `LAPORAN_P2_PERBANDINGAN_STRATEGI.md` | Paritas & perbandingan strategi | tercatat |
| `QA_F2LLM3_plan_uji_injection.md` | Rencana uji prompt injection | guard lulus |
| `QA_F2LLM4_kriteria_gerbang.md`, `QA_F2LLM4_eval_gerbang_minggu1.md`, `QA_F2LLM4_eval_run355.md`, `QA_eval_gerbang_llm.md`, `QA_F2LLM4_smoke_london_breakout.md`, `qa_p5_gate5_london_breakout.md` | Kriteria & evaluasi gerbang LLM/paper | gate paper belum lulus |
| `QA_shadow_t_f2v22a4.md`, `EVIDENCE_shadow_gate_lb-base_20261126T0140.md`, `EVIDENCE_shadow_gate_mr-base_20261126T0140.md`, `EVIDENCE_shadow_gate_btc-base_20261126T0140.md` | Shadow (3 label) | sinyal tidak cukup |
| `EVIDENCE_paper_gate_llm_20261126T0140.md` | Gerbang paper (ukur ulang) | PF 1,09, 30 trade |
| `QA_UI_D4_ops.md`, `QA_UI_D6_endtoend.md`, `QA_MP5.md` | QA UI & multipair | tercatat |
| `SIMULASI_INSIDEN_20261124234036.md`, `SIMULASI_INSIDEN_20261124235320.md`, `simulasi_insiden_evidence_*.json` | Drill insiden | 2x LULUS |

## 6. Riset, backtest, walk-forward

| Path | Isi |
| --- | --- |
| `LAPORAN_DOD_P2.md` | DoD backtest engine + walk-forward |
| `LAPORAN_WALKFORWARD_P2.md` | Ringkasan walk-forward P2 |
| `wf2_london_m5.md`, `wf2_london_h1.md`, `wf2_meanrev_m5.md`, `wf2_meanrev_m15.md` | WF per strategi/timeframe |
| `wf2_prafill_*.json`, `walkforward_p2.json` | Data mentah WF |
| `wf_baseline_london_breakout_m5.md`, `wf_baseline_mean_reversion_m5.md`, `wf_ml_gbm_m5.md` | Baseline WF |
| `wf_selfimprove_r1_probe.json` | Probe self-improve |
| `BT_BTCUSD_btc_range_breakout.md` (+ `.json`) | Backtest BTCUSD |
| `KALIBRASI_BTCUSD.md` | Kalibrasi biaya BTCUSD |
| `LAPORAN_DOD_RESEARCH_v22.md`, `LAPORAN_DOD_P3_ML.md` | Riset & ML |
| `LAPORAN_DOD_PORTFOLIO_RISK_v22.md`, `LAPORAN_DOD_VERSIONING_v22.md` | Portfolio risk & versioning |
| `backtest_p2_equity_*.svg` | Kurva ekuitas |

## 7. Laporan DoD per fase

`LAPORAN_DOD_P0.md`, `LAPORAN_DOD_P1a2_KILLSWITCH.md`, `LAPORAN_DOD_P1B_REKONSILIASI.md`,
`LAPORAN_DOD_P1B3_TELEGRAM.md`, `LAPORAN_DOD_P2.md`, `LAPORAN_DOD_P3_ML.md`, `LAPORAN_DOD_P4_APPROVE.md`,
`LAPORAN_GERBANG_P4.md`, `LAPORAN_DOD_DATAPIPE_v22.md`, `VERDICT_RELEASE_P1.md`, `VERIFIKASI_t_f2mp1.md`.

## 8. Aset & referensi lain

- `ui-references/` (16 screenshot + 1 HTML referensi), `qa_d6_shots/` (screenshot QA UI).
- `selfimprove/`, `selfimprove_proposals.json` (proposal perbaikan + keputusan).
- `snapshot.py`, `after.json`, `before.json` (snapshot state untuk verifikasi perubahan).
- `QA_P4_garis_merah.html`, `qa_p4_attempts.json` (uji garis merah LLM).
- `MODEL_CHAIN.md`, `QA_eval_gerbang_llm.*`.

## 9. Konvensi penamaan

| Awalan | Arti |
| --- | --- |
| `ARTEFAK_`, `RELEASE_`, `OWNER_` | artefak rilis & approval |
| `ARCHITECTURE_`, `ADR_`, `THREAT_MODEL_`, `DATA_DICTIONARY_`, `API_EA_PROTOCOL_SPEC_` | dokumen teknis rilis |
| `RISK_`, `PRASYARAT_`, `KEPUTUSAN_` | risiko, prasyarat, keputusan owner |
| `QA_`, `qa_` | bukti pengujian (huruf besar = laporan, kecil = data mentah) |
| `EVIDENCE_` | bukti yang diukur khusus untuk rilis ini (tanggal di nama file) |
| `LAPORAN_DOD_` | laporan Definition of Done per fase |
| `wf2_`, `wf_`, `BT_` | walk-forward & backtest |
| `SIMULASI_INSIDEN_` | drill insiden dengan timestamp |

## 10. Aturan pemeliharaan indeks

1. Setiap artefak baru di `docs/` wajib ditambahkan ke tabel yang sesuai di file ini.
2. Status di indeks tidak boleh lebih optimis daripada dokumen yang dirujuk.
3. Dokumen bertanggal (mis. `EVIDENCE_*_<ts>`) tidak dihapus; superseded dengan file baru.
4. Angka di dokumen rilis wajib menyebut sumber (path log/JSON) dan tanggal pengukuran.
