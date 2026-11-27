# Rollback Plan — Fund2 v2.2

Kartu: t_f2v22a17 · Tanggal: 25 Nov 2026 · Referensi: PRD v2.2 §26, §16, §17
Dokumen pendukung: `DR_v2.2.md` (backup/restore), `INCIDENT_PLAYBOOK_v2.2.md` (pelaporan), `RELEASE_CHECKLIST_v2.2.md`

## 0. Prinsip

1. **Halt dulu, diagnosis kemudian.** Kerugian dibatasi sebelum akar masalah dicari.
2. **Tidak pernah auto-flatten (D6).** `STOP_AND_FLATTEN` hanya manual oleh owner dengan `confirm=true` + 2FA + TOTP; risiko slippage dijelaskan sebelum eksekusi.
3. **Hanya owner yang melepas halt (D11).** Pelepasan `GLOBAL_HALT` wajib checklist recovery + 2FA. Agent/tim tidak berhak.
4. **Jangan rollback schema secara destruktif.** Selalu forward-fix (`alembic upgrade head`); data append-only tidak diedit/dihapus.
5. **Selisih reconciliation ditangani dengan event kompensasi/adopsi**, bukan mengedit ledger (PRD §15.3, D5).
6. **Snapshot sebelum menyentuh apa pun.** Bukti (broker + DB) harus ada sebelum rollback dieksekusi.

## 1. Trigger rollback dan deteksi

| # | Trigger (PRD §26) | Sinyal deteksi | Severity | Mode default | Sumber |
| --- | --- | --- | --- | --- | --- |
| T1 | Order duplicate/unknown (orphan) | `order_events` reconciled_unexplained / ORPHAN_ADOPTED baru; order tidak dikenal di broker | SEV-1 | GLOBAL_HALT | auto + manual |
| T2 | Mismatch posisi | Reconciler: posisi broker vs DB beda tanpa deal penutup | SEV-1 | GLOBAL_HALT (`position_mismatch`) | auto + manual |
| T3 | SL tidak terpasang | Posisi terbuka tanpa SL broker-side (snapshot EA / cek terminal) | SEV-1 | GLOBAL_HALT | manual |
| T4 | Event ledger corrupt/unavailable | DB down; integritas ledger gagal (order tanpa event; append-only trigger nonaktif) | SEV-1/2 | GLOBAL_HALT | manual |
| T5 | Kill-switch gagal | Aktivasi tidak mengubah state; order tetap lolos saat halt | SEV-1 | (halt manual darurat) | manual |
| T6 | Credential compromise | Admin lockout, login asing, token bocor, perubahan settings tidak sah | SEV-1 | GLOBAL_HALT | manual |
| T7 | Drawdown threshold | DD harian ≥ **3%** equity (A6), DD total ≥ **8%** dari puncak equity (A7) | SEV-1 | GLOBAL_HALT (`daily_drawdown`/`total_drawdown`) | auto |
| T8 | Abnormal spread/slippage | Spread p95 ≥ ambang; slippage fill melawan posisi melebihi normal; rekap anomali harian | SEV-3 → eskalasi | STOP_NEW_ORDERS (manual) | watch + manual |
| T9 | API/EA instability | EA offline > **60 s** (GLOBAL_HALT, dengan posisi terbuka); EA offline > **6 s** = tanda offline + tolak order baru (A11/A12); **3** FAILED beruntun; latensi ≥ SLO; crash loop | SEV-1/2 | GLOBAL_HALT / STOP_NEW_ORDERS | auto + manual |

Ambang auto-trigger final (satu sumber kebenaran: `KEPUTUSAN_OWNER.md` §I, 26 Nov 2026): DD harian **3%**, DD total **8%**, order FAILED beruntun **3**, EA offline **6 s** untuk tanda offline/blokir entry dan **60 s** untuk `GLOBAL_HALT` (wajib ada posisi terbuka), position mismatch aktif, mode per trigger sesuai tabel. Nilai runtime diverifikasi ulang lewat `scripts/validate_release_packet.py` (gate `guardrails_sesuai_policy`); PASS terakhir 26 Nov 2026 06:39 WIB setelah runtime disamakan ke §I (`KEPUTUSAN_OWNER.md` §I.4, `docs/BUKTI_GUARDRAIL_PARITY_t_bf4b85f9.md`).

**Catatan operasional 25 Nov 2026:** trigger T9 (EA offline) terjadi 2x pagi ini (05:05 & 06:45 WIB, keduanya dengan posisi terbuka) — auto `GLOBAL_HALT` bekerja sesuai desain kedua kali; akar masalah koneksi terminal belum diketahui (`INSIDEN_LOG_v2.2.md` INS-20261125-03). Jalur T9 paling sering terpakai saat ini: prioritaskan drill T9 dan investigasi stabilisasi terminal sebelum canary.

## 2. Langkah rollback (runbook global)

Jalankan berurutan. Role: **OPS** (backend/DevOps on-call), **OWNER** (keputusan bisnis + risk), **QA** (verifikasi).

### Langkah 1 — Aktifkan global halt (OPS, < 1 menit)

```bash
# login + CSRF (ganti kredensial sesuai kebijakan; JANGAN menyimpan password di shell history)
curl -s -c /tmp/f2cookie -X POST http://127.0.0.1:3110/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<admin>","password":"<password>"}'
CSRF=$(grep _csrf /tmp/f2cookie | awk '{print $7}')

# halt darurat: sengaja TANPA 2FA agar cepat (PRD §18)
curl -s -b /tmp/f2cookie -X POST http://127.0.0.1:3110/kill-switch \
  -H "Content-Type: application/json" -H "x-csrf-token: $CSRF" \
  -d '{"mode":"GLOBAL_HALT","reason":"rollback: <trigger>"}'
```

Jika API mati (T4/T9): halt tidak bisa via API → **cabut koneksi EA** (disable auto-trading di MT5 / blok network bridge) agar tidak ada order baru, lalu pulihkan API dulu.

Verifikasi: `curl -s -b /tmp/f2cookie http://127.0.0.1:3110/kill-switch` → `active: true, mode: GLOBAL_HALT`.

### Langkah 2 — Hentikan order baru & proses penulis (OPS)

GLOBAL_HALT sudah menolak semua entry di risk gate. Tambahan:

```bash
systemctl --user stop fund2-llm-agent fund2-paper-runner   # cegah noise/push tambahan
systemctl --user status fund2-api fund2-postgres           # catat state
```

### Langkah 3 — Putuskan posisi: dikelola atau flatten (OWNER)

- Default (D4): posisi **tetap terbuka**, dilindungi SL broker-side, tidak auto-close.
- Jika posisi tidak lagi aman (SL lepas T3, ledger corrupt T4, kompromi T6): owner memutuskan flatten manual:

```bash
# STOP_AND_FLATTEN: manual saja, confirm=true + 2FA + TOTP (D6)
curl -s -b /tmp/f2cookie -X POST http://127.0.0.1:3110/kill-switch/flatten \
  -H "Content-Type: application/json" -H "x-csrf-token: $CSRF" \
  -d '{"confirm": true, "code": "<totp>"}'
```

Risiko slippage: eksekusi tutup tidak dijamin pada harga yang diminta (pesan `SLIPPAGE_WARNING` di API).

### Langkah 4 — Snapshot broker dan database (OPS)

1. **Broker** (dari MT5 terminal): screenshot + catat posisi (ticket, symbol, volume, open price, SL/TP, profit), pending order, balance, equity, margin, server time.
2. **DB penuh** (terenkripsi, offsite):
   ```bash
   ~/fund2/scripts/fund2_backup.sh pre-deploy
   ```
3. **Bukti cepat** (JSON, sebelum rollback menyentuh state):
   ```bash
   PGPASSWORD=<pw> pg_dump -h 127.0.0.1 -p 5433 -U <user> -Fc fund2 -f /tmp/fund2-pre-rollback.dump
   # ekspor audit: kill_switch_events, order_events, orders, positions terbaru → JSON di docs/bukti/
   ```

### Langkah 5 — Rollback aplikasi ke artifact sebelumnya (OPS)

Pilih strategi sesuai sumber masalah:

| Masalah | Aksi rollback |
| --- | --- |
| Bug kode API/bridge | `git -C ~/fund2 checkout <tag/commit-rilis-terakhir>` → `systemctl --user restart fund2-api` → cek `/health` |
| Versi strategi buruk | `POST /strategies/{id}/rollback` (owner: 2FA + `owner_username`) → kembali ke versi terakhir APPROVED |
| Caddy/edge | `~/fund2/scripts/rollback_caddy_fund.sh v1` (snapshot Caddyfile v1 tersedia) |
| DB corrupt (T4) | Jangan patch di tempat: restore ke instance baru dari arsip terverifikasi (DR §5 langkah 3-4), validate sha256, lalu alihkan |
| Kredensial kompromi (T6) | Rotasi `bridge_token` + password admin + secret terkait; paksa logout semua sesi; blok IP penyerang di Caddy |

```bash
# contoh rollback aplikasi
git -C ~/fund2 log --oneline -5                 # identifikasi commit rilis terakhir yang sehat
git -C ~/fund2 checkout <commit-atau-tag>
systemctl --user restart fund2-api
sleep 3 && curl -s http://127.0.0.1:3110/health # wajib {"ok":true,...}
```

### Langkah 6 — Schema: forward-fix, bukan downgrade (OPS)

```bash
cd ~/fund2/api && .venv/bin/python -m alembic upgrade head   # selalu maju
```

Jangan pernah `alembic downgrade` atau DROP/ALTER destruktif di produksi. Skema baru harus backward-compatible dengan kode lama selama window rollback (migration compatibility).

### Langkah 7 — Reconcile broker state (OPS + QA)

1. Bandingkan snapshot broker (langkah 4.1) vs DB (`positions`, `orders`, `order_events`).
2. Selisih dicatat sebagai **event kompensasi / adopsi orphan** (D5) — tidak mengedit/hapus baris ledger.
3. Jalankan query integritas drill (DR §3 tahap 7): 0 order tanpa event, trigger append-only `order_events` aktif, konsistensi candle.
4. Hasil reconciliation dicatat di `reconciliation_runs` + lampirkan ke incident report.

### Langkah 8 — Uji read-only dan bridge demo (OPS)

1. API read-only sehat: `/health`, `/auth/me`, `/positions`, `/metrics`.
2. Bridge demo: EA demo menerima command via `/bridge/poll`, `POST /bridge/result` idempotent, heartbeat masuk, latensi T0→T2 < 300 ms.
3. Jangan aktifkan auto-trading sebelum langkah 9.

### Langkah 9 — Owner menyetujui resume (OWNER)

Checklist recovery wajib (`RECOVERY_CHECKLIST`, 7 butir):

1. Sumber masalah sudah ditemukan dan host aman
2. Trading halt masih aktif (kill-switch tidak dilepas sebelum verifikasi)
3. MT5/EA sudah hidup kembali tanpa mengirim order baru
4. Snapshot posisi broker sudah diambil
5. Rekonsiliasi: posisi & pending orders cocok antara broker dan DB
6. Heartbeat dan command channel sudah diuji di demo/staging
7. Owner menyetujui resume trading

```bash
# release GLOBAL_HALT: 2FA + checklist_ack=true (D11)
curl -s -b /tmp/f2cookie -X POST http://127.0.0.1:3110/kill-switch/release \
  -H "Content-Type: application/json" -H "x-csrf-token: $CSRF" \
  -d '{"checklist_ack": true}'
```

Setelah release: start ulang runner (`fund2-llm-agent`, `fund2-paper-runner`) dan pantau 30 menit pertama.

### Langkah 10 — Incident report dan corrective action (OPS → OWNER)

Buat incident report sesuai `INCIDENT_PLAYBOOK_v2.2.md` (template §3) dan **append** ke `docs/INSIDEN_LOG_v2.2.md`. Log insiden tidak pernah dihapus (PRD §27). Corrective action punya pemilik + tenggat.

## 3. RTO / RPO

| Komponen | Target | Terukur |
| --- | --- | --- |
| Halt manual via API | < 1 menit | aktivasi kill-switch instan (DB settings + SSE) |
| Restore DB (RTO komponen) | 4 jam (D7 usulan) | ~21 s (restore 9 s + start API 12 s), DB 64 MB |
| RPO | maks 24 jam (backup harian 04:30 UTC); pre-deploy backup mempersempit | cek `manifest.tsv` / `logs/backup-*.json` |
| Rollback edge ke v1 | < 5 menit (D13) | `rollback_caddy_fund.sh v1` (validate + graceful reload) |

## 4. Drill wajib sebelum canary (menutup deviasi RELEASE_CHECKLIST 3.6)

1. Di staging: deploy commit rilis kandidat → inject scenario (order orphan) → jalankan langkah 1-10 penuh kecuali flatten nyata.
2. Ukur total durasi halt → resume-ready; catat di `docs/DR_v2.2.md` atau laporan drill.
3. Ulangi setiap sebelum rilis mayor.

## 5. Role & keputusan

| Keputusan | Pihak | Dasar |
| --- | --- | --- |
| Aktivasi halt darurat | OPS/admin (tanpa 2FA demi kecepatan) | PRD §18 |
| Flatten posisi | OWNER manual (confirm + 2FA + TOTP) | D6 |
| Rollback aplikasi/versi strategi | OPS eksekusi; owner setuju bila dampak bisnis | PRD §26 |
| Melepas halt / resume | OWNER (2FA + checklist recovery) | D11 |
| Menandai insiden selesai | OWNER setelah baca incident report | PRD §27 |
