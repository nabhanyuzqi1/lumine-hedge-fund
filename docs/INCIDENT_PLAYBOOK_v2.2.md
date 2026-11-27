# Incident Playbook — Fund2 v2.2

Kartu: t_f2v22a17 · Tanggal: 25 Nov 2026 · Referensi: PRD v2.2 §27, §20.2, §16
Dokumen pendukung: `ROLLBACK_PLAN_v2.2.md` (runbook halt/rollback), `OBSERVABILITY_v2.2.md` (metrik & severity alert), `DR_v2.2.md` (backup/restore)

## 1. Definisi severity insiden

Sama dengan severity alert (PRD §20.2, `OBSERVABILITY_v2.2.md`):

| Severity | Kriteria contoh | Respon |
| --- | --- | --- |
| **SEV-1** | Posisi terbuka tanpa SL broker-side; ledger mismatch/orphan baru; order tak diketahui; admin lockout/kompromi kredensial; kill-switch gagal | Global halt + owner alert segera; rollback plan bila perlu; incident report wajib |
| **SEV-2** | EA offline dengan posisi terbuka; DB unavailable; ≥ 3 FAILED beruntun | Halt entry + investigasi; incident report wajib |
| **SEV-3** | Latensi ≥ SLO; spread p95 ≥ ambang; candle/tick stale; data gap; disk penuh; backup > 26 jam; DD ≥ watch; order stuck; EA offline tanpa posisi | Watch/pause; catat di log; incident report ringkas |
| **SEV-4** | Rekap harian / anomali / backup sukses | Laporan harian, bukan insiden |

Auto-action dari metrics daemon: SEV-1 → `GLOBAL_HALT` (source `auto:sev_*`), SEV-2 → `GLOBAL_HALT`/`STOP_NEW_ORDERS`. **Tidak pernah auto-flatten (D6).**

## 2. Siklus penanganan insiden

1. **Deteksi** (alert Telegram / dashboard / manual) → catat waktu mulai.
2. **Containment**: aktifkan halt sesuai trigger (lihat `ROLLBACK_PLAN_v2.2.md` langkah 1-2).
3. **Snapshot bukti**: broker + DB + audit events (sebelum menyentuh state).
4. **Resolusi**: rollback/forward-fix/reconcile sesuai runbook.
5. **Resume**: owner menyetujui dengan checklist recovery (D11).
6. **Pelaporan**: incident report + append ke log insiden.
7. **Tindak lanjut**: corrective/preventive action dengan pemilik + tenggat; verifikasi penutupan.

## 3. Template incident report (wajib, PRD §27)

Setiap insiden mencatat **semua** field berikut (jangan dihapus, isi `N/A` bila memang tidak ada):

```markdown
## INS-<YYYYMMDD>-<nn> — <judul singkat>

| Field | Isi |
| --- | --- |
| Severity | SEV-1..SEV-4 (+ alasan) |
| Waktu mulai / selesai | <ISO 8601 dengan zona> / <ISO 8601> |
| Terdeteksi oleh | alert auto / manual (siapa) |
| Dampak posisi & order | jumlah posisi/order terdampak, nilai exposure, P&L terdampak (bila diketahui) |
| Timeline | daftar kronologis (waktu UTC/WIB + kejadian) |
| Penyebab langsung | what broke |
| Akar masalah | why (5-whys / fakta) |
| Tindakan otomatis | auto-halt, auto-reconcile, alert (dengan source + waktu) |
| Tindakan manual | langkah yang dijalankan siapa, kapan |
| Keputusan owner | keep/flatten/resume/rollback — waktu + penegas |
| Bukti ledger | order_id/chain, order_events, kill_switch_events, reconciliation_runs (path/screenshot) |
| Bukti broker | snapshot posisi/balance/equity (screenshot/catatan MT5) |
| Corrective action | memperbaiki akar masalah — pemilik + tenggat |
| Preventive action | mencegah terulang — pemilik + tenggat |
| Status | OPEN / MITIGATED / CLOSED (penutup oleh owner) |
```

## 4. Aturan log insiden (garis merah)

1. **Tidak boleh menghapus log insiden untuk mempercantik metrik** (PRD §27). Log bersifat append-only: koreksi dilakukan dengan entri baru yang merujuk entri lama, bukan mengedit/menghapus.
2. Register resmi: `docs/INSIDEN_LOG_v2.2.md`. Bukti teknis (JSON/log/screenshot) disimpan di `docs/bukti/` atau path yang direferensikan.
3. Insiden yang berhubungan dengan uang/live wajib SEV-1/2 + laporan owner di Telegram kanal primer (D12).
4. Incident report dibuat **setelah** containment, sebelum close; akar masalah boleh menyusul (status `MITIGATED`) tapi corrective action tidak boleh kosong saat `CLOSED`.

## 5. Peran

| Peran | Tanggung jawab |
| --- | --- |
| OPS (backend/DevOps on-call) | Deteksi, containment, snapshot, rollback, draft incident report |
| OWNER | Keputusan flatten/keep/resume, penutupan insiden, approval corrective action (D11) |
| QA | Verifikasi bukti, re-test corrective action |
| Semua | Melapor segera; tidak menghapus/mengedit log |

## 6. Jalur pelaporan owner (D12)

- Kanal primer: Telegram (`fund2-alerts` → `notify_owner`), dengan struktur Apa / Dampak / Waktu / Otomatis / Manual.
- Pesan Telegram: escape nilai dinamis (insiden 23 Nov: underscore → 400 diam-diam); `send_message` wajib raise saat `ok=false`.
- Kanal kedua (email): menyusul sesuai D12; sementara catat di log insiden bila Telegram down.

## 7. Indeks dokumen terkait

- Trigger & runbook rollback: `ROLLBACK_PLAN_v2.2.md`
- Backup/restore: `DR_v2.2.md`
- Metrik, ambang, severity alert: `OBSERVABILITY_v2.2.md`
- Register insiden (append-only): `INSIDEN_LOG_v2.2.md`
- Simulasi uji playbook: `SIMULASI_INSIDEN_<tanggal>.md` (terbaru di docs/)
