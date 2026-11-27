# Disaster Recovery Plan & Laporan — Fund2 v2.2

Tanggal: 2026-11-23 (WIB). Referensi: PRD v2.2 §17 (Backup, Restore drill,
RTO/RPO, Recovery sequence).

## 1. Ringkasan

| Item | Nilai |
| --- | --- |
| Backup harian | `fund2-backup.timer`, 04:30 UTC (11:30 WIB), `Persistent=true` |
| Backup pre-deployment | `fund2_backup.sh pre-deploy` (manual, sebelum deploy besar) |
| Isi backup | DB (pg_dump -Fc + globals), config non-secret, Parquet + manifest sha256 |
| Enkripsi | age (X25519); private key TIDAK di host (offline, akses terbatas) |
| Akses terbatas | `/home/tekka/fund2-backups` mode 0700; arsip 0600 |
| Salinan beda lokasi | Offsite Cloudflare R2 `r2:lumine-backups/fund2-v22` (verified) |
| Retensi | 30 hari (lokal + offsite), usulan PRD §17.2 |
| Restore drill | LULUS, 3x berulang, 9-10 detik per drill (DB 64 MB) |
| RPO (usulan awal) | maks 24 jam (backup harian); pre-deploy backup mempersempit |
| RTO (usulan awal) | 4 jam; terukur: DB restore 9 s + API start 12 s ≈ **21 s** |

## 2. Backup pipeline (`scripts/fund2_backup.sh`)

1. **DB**: `pg_dump -Fc` (custom, terkompresi) + `pg_dumpall --globals-only`
   (roles/tablespace). Sanity check TOC: `order_events`, `candles`, `users`
   wajib ada.
2. **Config non-secret**: Caddyfile, unit systemd user, alembic.ini + versions,
   `.env.example`, EA settings (mq5/ini/set), deploy scripts, pin `git_commit`.
   Secret TIDAK ikut (kebijakan secret terpisah).
3. **Dataset Parquet**: ingest ticks, HFM recorder, dukascopy historis.
   Manifest `sha256` untuk seluruh file dataset (`datasets-<ts>.sha256`).
4. **Pack + encrypt**: tar -> age encrypt -> `/home/tekka/fund2-backups/db/
   fund2-<ts>.tar.age` (mode 0600 via umask dir 0700).
5. **Manifest global**: `manifest.tsv` (path, sha256, bytes, label, ts),
   append dengan `flock`.
6. **Offsite**: `rclone copyto` ke R2 + verifikasi size; gagal upload TIDAK
   membatalkan backup lokal (WARN).
7. **Retensi**: hapus arsip > 30 hari lokal & offsite; staging dibersihkan.
8. **Result JSON**: `logs/backup-<ts>.json` (status, sha256, bytes, offsite,
   duration) — dipakai alert Telegram.

Verifikasi mandiri: `fund2_backup.sh --verify-only` memeriksa ulang sha256
semua arsip di manifest.

## 3. Restore drill (`scripts/fund2_restore_drill.sh`)

Drill ke staging **terisolasi penuh**: instance PostgreSQL terpisah
(socket `/tmp`, port 5599, user `drill`, DB `fund2_drill`). Tidak menyentuh
produksi (:5433), tidak ada koneksi ke broker live, tidak mengirim order.

8 tahap verifikasi (PRD §17.3), semua otomatis:

1. Dekripsi age + ekstrak tar; verifikasi sha256 arsip.
2. Init PostgreSQL staging terisolasi (port 5599).
3. `pg_restore` schema + data.
4. Verifikasi schema/migration: `alembic_version` = `c003`, >= 50 tabel.
5. Jumlah baris & rentang timestamp 9 tabel kunci **identik dengan sumber**
   (dipotong pada waktu backup, `mtime` dump — DB live terus bertambah).
6. Checksum dataset: 1527 file Parquet, sha256 semua match.
7. Query integritas: 0 order tanpa event (ledger orphan), trigger append-only
   `order_events` aktif, konsistensi OHLC candle.
8. Bandingkan state: `settings`, `paper_state`, `kill_switch` identik sumber.

### Hasil drill (2026-11-23)

| Drill | Arsip | Durasi total | pg_restore | Status |
| --- | --- | --- | --- | --- |
| 20261123T050648Z | fund2-20261123T050211Z.tar.age | 10 s | 4 s | LULUS |
| 20261123T051045Z | fund2-20261123T050211Z.tar.age | 9 s | 4 s | LULUS |
| 20261123T051441Z | fund2-20261123T051421Z.tar.age (terbaru) | 9 s | 4 s | LULUS |

Laporan per drill: `/home/tekka/fund2-backups/drill/<ts>/restore-drill-<ts>.md`
+ `result.json`. Drill terakhir membuktikan backup harian yang baru jadi
benar-benar dapat di-restore.

## 4. RTO / RPO terukur

- **RPO**: backup harian 04:30 UTC -> window kehilangan maksimum ~24 jam
  (sesuai usulan awal PRD §17.4). Backup pre-deployment mempersempit window
  untuk risiko deploy. RPO aktual = `now - ts backup terakhir` (lihat
  `manifest.tsv` / log JSON).
- **RTO** (komponen terukur di VPS ini, DB 64 MB):
  - Restore DB: **9 s** (dekripsi 1 s + pg_restore 4 s + verifikasi 4 s).
  - Start API: **12 s** (uvicorn siap melayani, diukur via restart).
  - Total DB + API: **~21 s** — jauh di bawah target RTO 4 jam.
  - Belum termasuk: recovery host/OS (di luar lingkup DR aplikasi), propagasi
    DNS, dan langkah manual reconciliation broker (§17.5 langkah 5-10).
- RTO bridge/rekonsiliasi: ditetapkan terpisah (sesuai PRD), bergantung
  waktu start MT5/EA (~2-3 menit pada host ini) dan review manual owner.

## 5. Recovery sequence runbook (PRD §17.5)

1. **Sumber masalah & keamanan host**: pastikan penyebab (disk, DB, API,
   kompromi). Host tidak aman -> jangan restore ke host yang sama.
2. **Trading halt**: pastikan kill-switch aktif
   (`POST /api/kill-switch {mode}` + CSRF) atau cabut koneksi EA.
3. **Pulihkan API/DB dari sumber tervalidasi**: pilih arsip dari
   `manifest.tsv` (sha256 cocok, label jelas), lalu
   `fund2_restore_drill.sh <arsip.tar.age> restore-prod` untuk restore ke
   staging, atau pg_restore langsung ke DB produksi baru dari arsip
   terverifikasi. Jangan pernah restore dari sumber yang checksum-nya tidak
   cocok.
4. **Verifikasi integritas ledger**: jalankan kembali query integritas drill
   (0 order tanpa event, append-only trigger aktif).
5. **Nyalakan MT5/EA TANPA mengirim order baru**: start terminal, login, EA
   dalam mode non-trading (disable auto-trading / EA input read-only).
6. **Ambil broker snapshot**: catat posisi, pending order, balance, equity,
   margin dari terminal broker.
7. **Jalankan reconciliation**: bandingkan snapshot broker vs DB
   (`positions`, `orders`, `order_events`); selisih dicatat sebagai event
   kompensasi, tidak mengedit ledger.
8. **Review posisi & pending orders**: owner + backend review hasil
   reconciliation; keputusan keep/close/revise per posisi.
9. **Uji heartbeat & command channel di demo/staging**: EA demo menerima
   command via bridge, heartbeat masuk, T0->T2 sehat.
10. **Owner menyetujui resume**: approval eksplisit sebelum auto-trading
    dinyalakan kembali.

## 6. Verifikasi cepat (operasional harian)

```bash
# status timer
systemctl --user list-timers fund2-backup.timer

# backup manual / pre-deploy
~/fund2/scripts/fund2_backup.sh pre-deploy

# verifikasi checksum semua arsip di manifest
~/fund2/scripts/fund2_backup.sh --verify-only

# restore drill (staging terisolasi, ~10 detik)
~/fund2/scripts/fund2_restore_drill.sh --latest

# cek offsite
rclone ls r2:lumine-backups/fund2-v22
```

## 7. Keterbatasan & catatan

- Host punya **satu disk** (sda1); salinan lokal berada di disk yang sama.
  Salinan beda lokasi dipenuhi via **offsite R2** (beda penyedia/region).
  Salinan kedua di volume lokal berbeda bisa ditambah bila anggaran
  mengizinkan (usulan PRD "bila memungkinkan").
- **Private key age tidak di host** — restore butuh key offline
  (`~/backups/lumine-router-secrets-20261122/keys/backup-age.key`, 0600,
  lokasi terpisah dari fund2-backups). Pastikan key dapat diakses saat DR.
- Backup DB bersifat **point-in-time logis** (pg_dump), bukan PITR WAL.
  RPO 24 jam sesuai desain ini; PITR bisa menyempitkan RPO bila diperlukan.
- Retensi 30 hari adalah **usulan**; owner dapat menetapkan lebih panjang.
- Live trading saat ini OFF (paper only); drill tidak pernah menyentuh
  broker live.
