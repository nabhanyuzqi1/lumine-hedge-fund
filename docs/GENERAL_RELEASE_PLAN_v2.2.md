# General Release v2.2: Rencana P11 dan 7 Hari Stabilisasi

Kartu: **t_128a9dee** (paket kesiapan operasional) · Tanggal: 25 Nov 2026 (WIB) · Pemilik rencana: hf-devops
Referensi: PRD v2.2 §23.12 (P11), §29.13 (D13), `RELEASE_CHECKLIST_v2.2.md`, `ROLLBACK_PLAN_v2.2.md`, `CANARY_PLAN_v2.2.md`
Eksekusi nanti ditangani kartu **t_f2v22a16** (assignee hf-ceo). Dokumen ini rencana, bukan eksekusi.

> **Tidak ada general release sebelum canary lulus DoD dan owner menyetujui perluasan.** Dokumen ini hanya dipakai setelah keputusan itu.

## 1. Prasyarat masuk

1. Canary (P10) memenuhi seluruh DoD di `CANARY_PLAN_v2.2.md` §8, termasuk tanpa critical incident.
2. Owner menyetujui perluasan secara tertulis, dengan lingkup eksposur target.
3. `RELEASE_CHECKLIST_v2.2.md`: blok Release 5.1-5.8 lulus; 5.5-5.6 dieksekusi di window.
4. Guardrail sesuai `PRASYARAT_LIVE_v2.2.md` §3, terpasang dan terverifikasi.
5. Backup pre-release sukses, tag rilis ada, tree bersih.
6. Rollback teruji penuh (deviasi 3.6 tertutup).

## 2. Freeze artifact dan penamaan

| Item | Aturan |
| --- | --- |
| Commit | Satu commit HEAD bersih (`git status --porcelain` kosong) |
| Tag RC | `fund2-v2.2-rc<N>` pada commit kandidat, digunakan untuk canary |
| Tag rilis | `fund2-v2.2.0` setelah canary lulus, ditandai dari commit yang sama bila tidak ada perubahan |
| Catat | `deployment_records`: versi, env, commit/tag, sha256 arsip, aktor, waktu |
| Arsip | source tar + `frontend/dist` + `deploy/*.service` + checksum sha256 + manifest dependensi |
| Riwayat | Tag hanya dibuat pada commit yang lolos `pytest` penuh dan secret scan |

Prosedur build: `ARTEFAK_RILIS_v2.2.md`.

## 3. Window cutover (D13)

- **Deploy dilakukan saat pasar tutup (weekend).**
- **Aktivasi live pertama awal sesi Asia hari Senin pagi WIB** (ekspresi D13), setelah smoke test lulus dan owner menyetujui aktivasi.
- Dilarang deploy Jumat malam tanpa jendela uji weekend, atau saat rilis data ekonomi besar tanpa checklist.
- Pemegang kunci: DevOps mengeksekusi, QA memverifikasi, owner menyetujui aktivasi.

### 3.1 Urutan hari nol (weekend)

| # | Langkah | Verifikasi |
| --- | --- | --- |
| 1 | `fund2_backup.sh pre-deploy`; verifikasi `status=ok`, `offsite=1`, sha256 | JSON backup |
| 2 | Tag `fund2-v2.2.0`; buat arsip + checksum; catat `deployment_records` | `git tag`, arsip |
| 3 | Deploy sesuai unit systemd; jalankan migrasi forward (`alembic upgrade head`) | `alembic current = l012` |
| 4 | Smoke test read-only: `/health`, `/auth/me`, `/positions`, `/metrics`, dashboard login | output curl |
| 5 | Verifikasi bridge dan snapshot EA: heartbeat, `/bridge/poll`, posisi demo cocok | `order_events`, MT5 |
| 6 | Verifikasi kill-switch berfungsi: activate di demo, release oleh owner 2FA | `kill_switch_events` |
| 7 | Verifikasi alert: `--send-test` 4x terkirim; daemon sehat | log + Telegram |
| 8 | Posisi awal: kill switch `GLOBAL_HALT` sampai owner aktivasi Senin | `/kill-switch` |
| 9 | Owner menyetujui/menolak aktivasi Senin pagi di chat kantor | pesan owner |

Bila langkah 4-8 gagal: rollback ke tag sebelumnya sesuai `CHECKLIST_ROLLBACK_v2.2.md`, jangan aktivasi.

## 4. Peningkatan eksposur setelah rilis

Tidak ada lompatan dari canary ke eksposur penuh. Ramp bertahap, tiap tahap butuh approval owner:

| Tahap | Eksposur maksimum | Durasi minimal | Gerbang naik |
| --- | --- | --- | --- |
| Canary | lot terkecil (0,01) | 10 hari kerja | DoD P10 + approval |
| R1 | 25% dari batas D1 | 7 hari stabilisasi | 0 SEV-1, rekonsiliasi harian bersih, owner approval |
| R2 | 50% | 7 hari | idem |
| R3 | 100% (batas D1) | stabil | owner approval final |

Kenaikan tahap tidak otomatis. Bila satu tahap gagal: turun ke tahap sebelumnya atau paper, bukan berhenti di tengah tanpa keputusan.

## 5. 7 hari stabilisasi (wajib §23.12)

Rutinitas harian sama dengan canary (`CANARY_PLAN_v2.2.md` §5), ditambah:

| # | Pemeriksaan tambahan | Ambang |
| --- | --- | --- |
| 1 | Kapasitas: p95 T0-T2 pada volume produksi | < 300 ms |
| 2 | Rekap harian 07:00 dan anomali 07:05 WIB terkirim | 7/7 hari |
| 3 | Backup harian 04:30 UTC sukses + offsite | 7/7 hari |
| 4 | Restore drill ringan (read-only verifikasi manifest) mingguan | lulus |
| 5 | Tidak ada penurunan performa strategi vs paper/backtest | review QA |
| 6 | Tidak ada perubahan guardrail tanpa approval | audit `settings` |
| 7 | Postmortem draf di hari ke-7 | selesai |

**Stop conditions** sama dengan `CANARY_PLAN_v2.2.md` §7; kegagalan pada hari stabilisasi memicu rollback atau penurunan tahap, bukan "diterima karena sudah rilis".

## 6. Rollback di masa rilis

- Trigger: daftar lengkap di `ROLLBACK_PLAN_v2.2.md` §1.
- Eksekusi: `CHECKLIST_ROLLBACK_v2.2.md` (10 langkah, target halt < 1 menit).
- Target RTO: restore DB + API ~21 s (terukur, `DR_v2.2.md`); rollback edge < 5 menit.
- Setelah rollback: incident report, append `INSIDEN_LOG_v2.2.md`, owner keputusan resume.

## 7. Penutupan rilis (post-release)

1. **Postmortem** (tanpa menyalahkan, fokus sistem): timeline, penyebab insiden, corrective action berpemilik + tenggat.
2. **Release notes**: versi, perubahan, bug yang diketahui, batas yang disetujui, parameter risiko final.
3. **Dokumentasi operasional final**: sinkronkan `RUNBOOK_v2.2.md`, `ROLLBACK_PLAN_v2.2.md`, `RELEASE_CHECKLIST_v2.2.md`, `PRASYARAT_LIVE_v2.2.md` dengan angka final.
4. **Owner release acceptance**: tanda tangan pada `RELEASE_CHECKLIST_v2.2.md` §7.
5. **Pekerjaan berikutnya**: daftar backlog (mis. kalibrasi HFM penuh, HMAC bridge, HA), diprioritaskan owner.

## 8. Hal yang tidak boleh dilakukan

- Release saat pasar buka tanpa keputusan owner (D13).
- Kenaikan eksposur otomatis atau tanpa approval.
- Mengubah parameter risiko di hari rilis.
- Menghapus/mengedit log insiden untuk merapikan metrik.
- Menyatakan rilis selesai tanpa postmortem dan acceptance.

## 9. Sign-off

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-devops | 25 Nov 2026 | Kartu t_128a9dee |
| Review | hf-ceo | menunggu | Tahap ramp §4 |
| Review | hf-qa | menunggu | Ambang stabilisasi §5 |
| Approval aktivasi | owner | menunggu | Setelah canary lulus |
