# Canary Live Terbatas v2.2: Rencana P10

Kartu: **t_128a9dee** (paket kesiapan operasional) · Tanggal: 25 Nov 2026 (WIB) · Pemilik rencana: hf-devops
Referensi: PRD v2.2 §23.11 (P10 canary), §29.10 (D10), `KEPUTUSAN_OWNER.md` (D1, D9, D10, D15, F1)
Eksekusi nanti ditangani kartu **t_f2v22a15** (assignee hf-devops). Kartu ini hanya rencana, bukan pelaksanaan.

> **Canary adalah uang nyata.** Pelaksanaan hanya setelah seluruh prasyarat di `PRASYARAT_LIVE_v2.2.md` (G1, G2, G3) lulus, termasuk D1 terisi owner dan approval live tertulis. Sampai itu, rencana ini hanya dokumen.

## 1. Tujuan dan batas

- Membuktikan jalur order end-to-end (sinyal, risk gate, bridge, EA, broker, rekonsiliasi) dengan modal paling kecil.
- Membuktikan operasional: alert sampai owner, rekonsiliasi harian, kill switch siap, rollback bisa dieksekusi.
- **Bukan** target profit. Tidak ada klaim profitabilitas dari canary.

Di luar canary: menaikkan eksposur otomatis, menambah strategi kedua, multipair BTCUSD live, mengubah parameter risiko tanpa approval.

## 2. Prasyarat masuk (semua wajib)

1. G1: engineering v2.2 selesai, P9 lulus (20 hari kerja, 100 trade, PF >= 1,3, DD <= 5%), QA sign-off.
2. G2: D1 terisi owner (modal + batas kerugian absolut + lot + exposure).
3. G3: approval live tertulis owner, terpisah dari H1.
4. Guardrail G-01..G-06, G-11, G-12 di `PRASYARAT_LIVE_v2.2.md` disetujui dan terpasang.
5. Drill rollback aplikasi penuh lulus (menutup deviasi `RELEASE_CHECKLIST` 3.6).
6. Drill kill switch oleh owner (aktivasi dan release dengan 2FA) tercatat.
7. Pipeline alert sehat (temuan F1/F2 `RUNBOOK_v2.2_UJI.md` ditutup).
8. Release artifact ter-tag dan backup pre-release sukses (offsite).
9. MT5/EA stabil minimal 24 jam tanpa `auto:ea_offline` sebelum hari pertama.
10. UAT owner lulus.

Bila satu saja belum lulus: canary ditunda, tidak ada pengecualian lisan.

## 3. Parameter canary (dikunci saat mulai)

| Parameter | Nilai | Dasar |
| --- | --- | --- |
| Strategi | `london_breakout` versi 1.1.0 (status APPROVED), hanya 1 strategi | D9, D15, `strategy_versions` |
| Simbol | XAUUSD saja | F1: XAUUSD instrumen live utama |
| Lot per order | **0,01 lot** (terkecil yang sah menurut contract spec broker) | §23.11; final setelah contract spec diverifikasi |
| Eksposur total maksimum | 0,30 lot (agregat, dari D1/owner) | A4, D1 |
| Risiko per trade | 0,5% equity | A5 |
| Drawdown harian | 3% auto-halt (angka final owner) | A6, D1 |
| Drawdown total | 8% auto-halt (angka final owner) | A7, D1 |
| Order per menit | 5 (angka final owner) | A8 |
| Durasi canary | **min. 10 hari kerja** | D10 |
| Jumlah trade minimum | **>= 30 trade** | D10 |
| Auto-exposure | **TIDAK ADA** peningkatan otomatis | §23.11 |
| Review | Harian owner + QA, jadwal tetap | D10 |
| Budget loss canary | Batas kerugian absolut dari D1; sentuh = stop permanen canary | D1 |

Perubahan parameter di tengah canary butuh persetujuan tertulis owner dan reset perhitungan durasi (keputusan owner; disarankan ulang dari hari 1).

## 4. Hari nol: pre-flight checklist (dieksekusi di window, bukan sekarang)

| # | Langkah | Bukti |
| --- | --- | --- |
| 1 | Jalankan `fund2_backup.sh pre-deploy`, verifikasi status `ok`, offsite `1` | `logs/backup-<ts>.json` |
| 2 | Verifikasi tag rilis pada commit bersih: `git status --porcelain` kosong, `git tag --list 'fund2-v2.2*'` | output git |
| 3 | Verifikasi guardrail: jalankan `scripts/validate_release_packet.py`, gate `guardrails` PASS | JSON validasi |
| 4 | Verifikasi `FUND2_ENV`, `GET /health`, mode kill switch nonaktif, alembic `l012` | curl + alembic |
| 5 | Uji alert: `python -m app.metrics --send-test` 4x sent=True, owner konfirmasi terima | log + Telegram |
| 6 | Uji kill switch demo: activate (admin) dan release (owner + 2FA), catat event id | `kill_switch_events` |
| 7 | Verifikasi EA heartbeat dan SL/TP broker-side pada posisi demo terakhir | MT5 + `/positions` |
| 8 | Uji bridge demo: `/bridge/poll` dan `/bridge/result` idempotent, latensi T0-T2 < 300 ms | `order_events` |
| 9 | Kunci parameter canary di §3 (catat di tiket + chat kantor) | snapshot `settings` |
| 10 | owner menyetujui GO hari pertama di chat kantor | pesan owner |

Bila langkah 3-8 gagal: batal hari nol, tidak ada live.

## 5. Rutinitas harian (owner + QA, 15 menit)

Setiap hari kerja canary, setelah rekap 07:05 WIB:

1. **Posisi**: `GET /positions` dan snapshot MT5 cocok; semua posisi punya SL broker-side.
2. **Rekonsiliasi**: 0 mismatch/orphan baru di `order_events`; `reconciliation_runs` terbaru.
3. **Eksekusi**: slippage median dan p95 24 jam vs kalibrasi (XAUUSD p95 spread 0,43 USD, gate 0,50); latensi p95 T0-T2 < 300 ms; rejection < 20%.
4. **Risiko**: DD harian dan total vs ambang; jumlah order per menit; tidak ada order di atas lot canary.
5. **Kill switch**: daftar `kill_switch_events` 24 jam; semua ACTIVATE punya sumber jelas; tidak ada RELEASE oleh pihak tak berhak.
6. **Alert**: `journalctl --user -u fund2-alerts` 24 jam; tidak ada `notify_owner gagal` atau `can't parse entities`.
7. **Keputusan harian** (owner): `LANJUT`, `PAUSE` (stop entry, posisi dikelola), atau `STOP` (rollback). Keputusan dicatat di tiket canary.
8. **Log bukti**: isi tabel §6 di `docs/CANARY_LOG_v2.2.md` (dibuat di hari nol).

## 6. Template log harian canary

```
| Hari | Tanggal | Trade (kum) | PF (kum) | DD harian | DD total | Slippage p95 | Latensi p95 | Mismatch | Insiden | Keputusan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | | | | |
```

Lampirkan per hari: `GET /metrics` snapshot, hasil rekonsiliasi, daftar event kill switch, screenshot MT5 posisi (bila ada).

## 7. Stop conditions (STOP segera, tidak menunggu review)

| # | Kondisi | Aksi |
| --- | --- | --- |
| S-1 | SEV-1: posisi tanpa SL, ledger mismatch, orphan baru, credential compromise | `GLOBAL_HALT` segera; `CHECKLIST_ROLLBACK_v2.2.md` |
| S-2 | Mismatch posisi broker vs DB tanpa penjelasan | Halt + rekonsiliasi; tidak resume sebelum cocok |
| S-3 | Slippage abnormal melebihi ambang kalibrasi atau spread p95 >= 0,50 USD berkelanjutan | `STOP_NEW_ORDERS`; review; owner putuskan lanjut/tidak |
| S-4 | DD harian >= 3% atau DD total >= 8% (angka final owner) | Auto-halt harus terpicu; verifikasi; owner keputusan |
| S-5 | Latensi p95 T0-T2 >= 300 ms lebih dari 30 menit, atau >= 3 order FAILED beruntun | `STOP_NEW_ORDERS`; investigasi; owner putuskan |
| S-6 | EA offline dengan posisi terbuka, atau >= 2x `auto:ea_offline` dalam 24 jam | Halt; stabilisasi MT5 dulu; owner putuskan |
| S-7 | Data quality: candle stale > 10 menit, data gap > 60 s, tick basi | Pause entry; perbaiki feed; verifikasi sebelum lanjut |
| S-8 | Alert tidak terkirim 30 menit saat ada kondisi SEV-1/SEV-2 | Anggap sistem tak terawasi: halt manual, perbaiki alert, owner keputusan |
| S-9 | Batas kerugian absolut D1 tersentuh | Stop canary permanen; rollback; postmortem |
| S-10 | Order di luar parameter canary (lot, strategi, simbol) | Halt; anggap guardrail gagal; audit penuh |

Aturan keputusan: siapa pun (owner, QA, DevOps) boleh mengaktifkan halt. Hanya owner yang melepas. Tidak ada "tunggu sampai besok" untuk S-1, S-2, S-8, S-9.

## 8. Kriteria keluar canary (DoD P10)

Canary dinyatakan lulus bila semua terpenuhi:

1. Durasi >= 10 hari kerja dan >= 30 trade.
2. Tidak ada critical incident (SEV-1) dan tidak ada S-9.
3. Reconciliation konsisten setiap hari (0 mismatch tanpa penjelasan).
4. Slippage dan latensi dalam ambang §5 tanpa pengecualian berulang.
5. Semua keputusan harian owner tercatat.
6. Pemahaman rollback dan flatten terverifikasi (drill atau insiden nyata yang ditangani benar).

Keputusan owner setelah DoD:

- **GO perluasan**: owner menyetujui kenaikan eksposur bertahap ke `GENERAL_RELEASE_PLAN_v2.2.md`; setiap kenaikan butuh approval eksplisit.
- **NO-GO**: kembali ke paper, catat alasan, perbaiki, ulangi canary dari hari 1 setelah owner setuju.
- **PERPANJANG**: durasi ditambah bila kriteria belum meyakinkan (mis. trade < 30 karena sinyal jarang).

## 9. Integrasi rollback

- Trigger dan langkah lengkap: `ROLLBACK_PLAN_v2.2.md`.
- Checklist cepat 1 halaman: `CHECKLIST_ROLLBACK_v2.2.md`.
- Target waktu: halt < 1 menit dari keputusan; snapshot sebelum aksi; flatten hanya owner (confirm + 2FA + TOTP).
- Setelah insiden: incident report sesuai `INCIDENT_PLAYBOOK_v2.2.md`, append `INSIDEN_LOG_v2.2.md`.

## 10. Hal yang tidak boleh dilakukan saat canary

- Menambah strategi atau simbol tanpa approval owner.
- Menaikkan lot atau exposure "sekalian uji".
- Melepas halt tanpa 7 butir checklist recovery dan 2FA owner.
- Mengubah parameter risiko lewat `psql` atau env tanpa audit UI.
- Menggunakan keuntungan canary sebagai bukti strategi (sampel terlalu kecil; PRD §0.2).

## 11. Sign-off rencana

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-devops | 25 Nov 2026 | Kartu t_128a9dee |
| Review QA | hf-qa | menunggu | Ambang §5 dan §7 |
| Review owner | owner | menunggu | D1, lot, durasi, batas kerugian |
