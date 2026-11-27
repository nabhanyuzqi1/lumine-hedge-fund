# QA UI-D4: Verifikasi E2E Operations & Recovery vs PRD §21.5

Tanggal: 25 Nov 2026 (WIB) · Verifikator: hf-qa · Env: DEMO (FUND2_ENV=demo), dev server Vite :5173 + API :3110
Metode: login owner (session cookie) → halaman /ops di browser → tiap section dicocokkan dengan respons API nyata (curl) + siklus kill-switch dijalankan dari UI.

## Hasil per section

### 1. Health status — [PASS]
- Halaman: "API+DB OK", DB ok · 23ms, API uptime 3 menit, EA ONLINE · terlihat 4 detik lalu, Kill-switch AMAN.
- 8 layanan systemd tampil semua `active`: fund2-api, fund2-postgres, fund2-alerts, fund2-paper-runner, fund2-hfm-recorder, fund2-llm-agent, fund2-candle-rollup, fund2-edge-proxy.
- Bukti: identik dengan `GET /metrics` → `api.services` (8/8 active). Screenshot: ops_page.png.

### 2. Backup & restore drill — [PASS] (akurat menampilkan ketiadaan)
- Halaman: "BELUM ADA BACKUP", "BELUM ADA DRILL", age_s kosong.
- Fakta: `~/fund2-backups/db/` kosong (belum pernah backup), `~/fund2-backups/drill/` tidak ada; `GET /metrics` → `backup: {age_s: null, last: null}`, `drill: {status: null, ts: null, age_s: null}`. Tampilan konsisten dengan kondisi nyata.

### 3. Rekonsiliasi — [PASS]
- Halaman: selisih tak terjelaskan 24j = 0, orphan diadopsi 24j = 0, tertutup via recon 24j = 0, total selisih = 0, total orphan = 0.
- Bukti: identik dengan `GET /metrics` → `reconciliation` (mismatch_24h/orphan_24h/reconciled_closed_24h/mismatch_all/orphan_all semuanya 0).

### 4. Order pending / stuck / orphan — [PASS]
- Halaman: "TIDAK ADA YANG BERMASALAH"; breakdown FILLED_THEN_CLOSED: 15, FAILED: 27, FILLED: 9, FAILED 24j: 11, REJECT 24j: 11.
- Bukti: `GET /orders?limit=100` → 52 order (28 FAILED, 15 FILLED_THEN_CLOSED, 9 FILLED), 0 PENDING/SENT (stuck), 0 orphan. Breakdown cocok dengan `metrics.orders.state_counts` (28 vs 27 = 1 FAILED baru antara dua poll, timing normal).

### 5. Kill-switch control — [PASS] (siklus penuh diuji dari UI, env DEMO)
- stop_entry: klik "Hentikan entry baru (STOP_NEW_ORDERS)" → badge langsung "AKTIF · STOP_NEW_ORDERS" (pelindung, sengaja tanpa dialog).
- flatten: dialog 2 langkah → teks konsekuensi (market order, slippage, tidak bisa dibatalkan) → checkbox ack → langkah 2FA → eksekusi (0 posisi terbuka → requested: 0).
- release: dialog 2 langkah + 2FA → badge kembali "AMAN · ORDER DIIZINKAN". Kode 2FA salah ditolak inline ("invalid TOTP code") tanpa menutup dialog.
- Event log kill-switch (append-only): ACTIVATE 23:56:54 → RELEASE 00:01:14 (actor admin, source dashboard).
- API-level cycle (curl) juga lolos: activate → flatten {confirm:true} → release {checklist_ack:true} dengan 2FA challenge; state akhir bersih.

### 6. Runbook recovery — [PASS]
- Checklist 7 item resume tampil; DR DOC `~/fund2/docs/DR_v2.2.md`, BACKUP SCRIPT `~/fund2/scripts/fund2_backup.sh`, RESTORE DRILL `~/fund2/scripts/fund2_restore_drill.sh --latest` — ketiga file ada di disk, tombol Salin tersedia.

### 7. Audit history — [PASS] (dengan GAP, lihat bawah)
- 50 baris terakhir tampil append-only (waktu, aktor, aksi, objek, IP); baris teratas cocok dengan `GET /audit?limit=50` (LOGIN_SUCCESS / 2FA_CHALLENGE_OK / 2FA_CHALLENGE_FAILED tercatat).

### 8. Approval self-improve — [GAP] (sudah dilaporkan sebelumnya)
- [GAP] Ops/Approval self-improve - daftar usulan gagal dimuat di dev server: GET /improve/proposals dijawab index.html (SPA fallback), bukan JSON, karena vite.config.js tidak mem-proxy path /improve ke API. Harusnya: tambah '/improve': API di frontend/vite.config.js. Bukti: halaman menampilkan "Gagal memuat usulan: Unexpected token '<'" sedangkan curl langsung ke 127.0.0.1:3110/improve/proposals mengembalikan JSON 3 proposal.
- Backend approve/reject + 2FA + append-only + 409 sudah diverifikasi run sebelumnya (LOLOS di level API).

## Kepatuhan UX §21.6 — [PASS]
- Konfirmasi dua langkah untuk flatten/release/triggers; teks konsekuensi eksplisit; fokus awal dialog pada "Batal"; stop_entry sengaja instan (aksi pelindung, tidak destruktif); error 2FA inline; destroy action (flatten) butuh ack + 2FA.

## GAP yang dilaporkan
1. [GAP] Ops/Approval self-improve - /improve tidak di-proxy vite dev server (lihat §8). Fix: tambah '/improve' ke proxy di frontend/vite.config.js (dev only; prod build served oleh API).
2. [GAP] Ops/Audit history - event kill-switch (ACTIVATE/RELEASE/FLATTEN) tidak masuk audit_log yang ditampilkan section "Audit history" (hanya event auth: LOGIN, 2FA), dan tidak dirender di UI mana pun. Dialog release mengklaim "Pelepasan tercatat di audit log" padahal yang dimaksud event store kill-switch (GET /kill-switch events, append-only) yang tidak terlihat owner di UI. Harusnya: tampilkan kill-switch events di halaman Ops (atau tulis ke audit_log) agar klaim dialog benar.

## Test otomatis
- `pytest tests/test_kill_switch.py tests/test_approve_flow.py` → 39 passed.

## Kesimpulan
7/8 section §21.5 berfungsi live dan menampilkan data nyata yang cocok dengan API. 2 GAP dilaporkan untuk kartu follow-up (proxy /improve, visibilitas event kill-switch di audit UI).
