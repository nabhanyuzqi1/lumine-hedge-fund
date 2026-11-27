# Runbook Operasional v2.2 — Alert Kritis & Respon Insiden

Task **t_f2v22b2** (PRD v2.2 §20.2 alert severity, §23.9 P8 "Runbook" +
"Runbook diuji oleh orang selain pembuatnya" + "Alert kritis sampai ke owner").

File ini **terpisah** dari INCIDENT_PLAYBOOK (task t_f2v22a17). Pembatasan
Direktur 22 Nov 2026: jalur kirim Telegram adalah milik t_f2p1b3 /
t_f2v22a10 — runbook ini hanya **memakai** jalur tersebut, tidak
mengimplementasikan ulang.

- Modul terkait: `api/app/metrics.py` (kolektor + evaluator SEV),
  `api/app/alerts.py` (daemon watcher), `api/app/telegram_bot.py` (sender
  `notify_owner`), `api/app/kill_switch.py` (mode + checklist recovery).
- Daftar berjalan: `docs/OBSERVABILITY_v2.2.md`, `docs/DR_v2.2.md`.

## 1. Prinsip respon

1. **SEV-1/SEV-2 = safety first.** Baca alert penuh (Apa / Dampak / Waktu /
   Otomatis / Manual), baru bertindak. Jangan tebak.
2. **Kill-switch tidak pernah auto-flatten (D6).** Auto-trigger hanya
   `STOP_NEW_ORDERS` / `GLOBAL_HALT`. Keputusan menutup posisi selalu owner
   (`/stopflatten confirm`, risiko slippage).
3. **Pelepasan GLOBAL_HALT hanya owner** lewat `/resume ACK` setelah 7 butir
   checklist recovery (`kill_switch.RECOVERY_CHECKLIST`) terpenuhi.
4. Semua perintah kontrol dikirim dari Telegram **owner** (chat
   `TELEGRAM_OWNER_ID`); perintah pengirim lain diabaikan.
5. Drill/simulasi SELALU memakai jalur `[TEST]` (§6). Jangan pernah memicu
   alert palsu non-`[TEST]` ke Telegram produksi.
6. Setelah insiden: catat timeline + update runbook bila langkah ternyata
   salah/kurang. Runbook yang tidak pernah direvisi = tidak pernah diuji.

## 2. Peta alarm (siapa mengirim apa)

Semua alert masuk ke satu pipeline: daemon `fund2-alerts` (systemd user) →
`telegram_bot.notify_owner` → Telegram owner. Dashboard membaca strip
`GET /alerts/active` (read-only, dihitung ulang dari kolektor yang sama
dengan `/metrics`).

| Watcher (interval) | Pemicu | SEV | Aksi otomatis |
| --- | --- | --- | --- |
| sev-watch (30 s) | posisi tanpa SL broker-side | 1 | `GLOBAL_HALT` (`auto:sev_*`) |
| sev-watch | ledger mismatch / orphan baru / admin lockout | 1 | `GLOBAL_HALT` |
| sev-watch | EA offline + posisi terbuka (> 60 s) | 2 | `GLOBAL_HALT` (`auto:ea_offline`) |
| sev-watch | DB unavailable | 2 | alert via Telegram langsung (tanpa DB) |
| sev-watch | ≥ 3 order FAILED beruntun | 2 | `STOP_NEW_ORDERS` |
| sev-watch | latensi/spread/feed/gap/disk/backup/DD/stuck/failure-rate/paper-stale | 3 | watch (tanpa halt) |
| ks-watch (5 s) | event `kill_switch_events`: ACTIVATE / ESCALATE / RELEASE / FLATTEN_REQUEST | ikut mode | — |
| ea-watch (10 s) | transisi heartbeat EA (`ea_last_seen_at`, threshold `ea_offline_seconds` = 60) | ikut kondisi | — |
| paper-watch (60 s) | service `fund2-paper-runner` mati, atau market buka tapi `paper_state` > 15 menit | 2-ish | — |
| candle-watch (60 s) | candle XAUUSD M5 > 10 menit di balik waktu live | 3 | — |
| rekap 07:00 + anomali 07:05 WIB | laporan harian | 4 | — |
| guardrail-watch (harian 05:10 UTC) | runtime `settings` menyimpang dari `KEPUTUSAN_OWNER.md` §I (`guardrail_drift`) atau setting hilang/lebih ketat (`guardrail_open`) | 3 | — (read-only, tanpa auto-fix; log `~/fund2-backups/logs/guardrail-<tanggal>.json`) |

Anti-spam yang perlu diketahui saat membaca log:

- dedup `notify_owner`: baris pertama identik dalam 300 s dikirim sekali;
- SEV-1/2 persisten dikirim ulang tiap 30 menit; pesan pulih sekali per
  insiden; observasi pertama watcher = baseline (tanpa alert) supaya restart
  daemon tidak mengspam;
- event kill-switch dengan `source` berawalan `kanban:` (hasil uji worker)
  **tidak** dikirim ke owner — anti-spam insiden 23 Nov 2026;
- env `TELEGRAM_ALERTS_OFF=1` membuat `notify_owner` no-op (guard test/worker,
  jangan pernah aktif di produksi).

## 3. Alur umum SEV-1 / SEV-2

1. **Ack + catat waktu** mulai insiden (journal `fund2-alerts` = sumber waktu
   deteksi).
2. **`/status`** di Telegram owner: mode kill-switch aktif, posisi terbuka,
   metrik risiko. Cocokkan dengan isi alert.
3. **Amankan posisi** (bila ada): verifikasi SL/TP broker-side di MT5. Ingat:
   tidak ada auto-flatten; flatten hanya atas keputusan owner.
4. **Investigasi** per runbook spesifik (§4).
5. **Pulihkan**: penuhi checklist recovery, owner `/resume ACK`.
6. **Post-insiden**: timeline + penyebab + koreksi, simpan di
   `docs/` (insiden besar masuk INCIDENT_PLAYBOOK a17 bila relevan).

Checklist recovery `GLOBAL_HALT` (wajib sebelum `/resume ACK`):

1. Sumber masalah sudah ditemukan dan host aman
2. Trading halt masih aktif (kill-switch tidak dilepas sebelum verifikasi)
3. MT5/EA sudah hidup kembali tanpa mengirim order baru
4. Snapshot posisi broker sudah diambil
5. Rekonsiliasi: posisi & pending orders cocok antara broker dan DB
6. Heartbeat dan command channel sudah diuji di demo/staging
7. Owner menyetujui resume trading

## 4. Runbook per alert

### RB-01 — SEV-1 `POSISI_TANPA_SL` 🚨

- **Pemicu:** posisi terbuka tanpa SL broker-side (hasil snapshot/reconciler).
- **Otomatis:** `GLOBAL_HALT` (`auto:sev_posisi_tanpa_sl`), alert owner.
- **Langkah:**
  1. Buka MT5 → posisi terbuka → cek kolom S/L per ticket yang disebut alert.
  2. Bila SL memang kosong: pasang SL manual di MT5 (level sesuai risk policy
     per trade).
  3. Bila posisi harus ditutup: owner kirim `/stopflatten confirm`
     (slippage mungkin terjadi).
  4. Cari penyebab SL hilang: order manual di MT5? EA gagal memasang? LLM
     order tanpa SL lolos gate? (harusnya tidak mungkin — investigasi).
  5. Setelah semua posisi terlindungi: `/resume ACK`.
- **Verifikasi pemulihan:** `/status` → 0 posisi unprotected; `GET /metrics`
  → `risk.unprotected_positions` kosong; alert pulih.
- **Eskalasi:** owner (satu-satunya yang bisa resume).

### RB-02 — SEV-1 `LEDGER_MISMATCH` 🚨

- **Pemicu:** posisi hilang dari snapshot broker TANPA deal penutup yang bisa
  dijelaskan (reconciler `reconciled_unexplained`).
- **Otomatis:** `GLOBAL_HALT` (`auto:position_mismatch` / `auto:sev_ledger_mismatch`).
- **Langkah:**
  1. Bandingkan posisi MT5 (History + Trade) vs DB (`/positions`, dashboard
     Operations).
  2. Telusuri deal MT5 untuk ticket yang hilang (manual close? stop out
     broker?).
  3. Catat temuan di `order_events` (append-only) — jangan menghapus/mengubah
     baris ledger.
  4. Setelah cocok: `/resume ACK`.
- **Verifikasi:** rekonsiliasi berikutnya 0 mismatch; `reconciliation.new`
  kosong di `/metrics`.
- **Preseden:** 25 Nov 2026 — EA flatten CLOSE tertinggal STUCK padahal posisi
  broker sudah tertutup; gate menolak semua order, breaker menghentikan LLM
  paper trading; penyelesaian: rekonsiliasi manual + settle order.

### RB-03 — SEV-1 `ORDER_TAK_DIKETAHUI` (orphan) 🚨

- **Pemicu:** posisi di broker TANPA order di DB (manual di MT5, atau command
  gagal sebelum tercatat).
- **Otomatis:** `GLOBAL_HALT`; reconciler memasang SL darurat pada orphan.
- **Langkah:**
  1. Identifikasi asal orphan (logfile command bridge, MT5 manual?).
  2. Adopsi manual ke DB (prosedur rekonsiliasi) ATAU tutup posisi
     (`/flatten confirm` / manual MT5 dengan catatan).
  3. Setelah ledger cocok: `/resume ACK`.
- **Verifikasi:** `orphan_new` = 0; eksposur riil = eksposur tercatat.

### RB-04 — SEV-1 `CREDENTIAL_COMPROMISE` 🚨

- **Pemicu:** penguncian akun admin setelah login gagal beruntun.
- **Otomatis:** `GLOBAL_HALT` (`auto:sev_credential_compromise`).
- **Langkah:**
  1. Pastikan percobaan login bukan milik Anda (cek `audit_log`, IP).
  2. Bila bukan: ganti password admin, cabut semua sesi
     (`/auth/sessions/revoke-all`), tinjau audit_log, anggap host tidak aman
     sampai terbukti sebaliknya.
  3. Bila milik Anda sendiri (lupa password): `/resume ACK` setelah verifikasi.
- **Verifikasi:** 0 lockout baru; login admin normal kembali.

### RB-05 — SEV-2 `EA_OFFLINE` (dengan posisi terbuka) 🔥

- **Pemicu:** `settings.ea_last_seen_at` > 60 s (`ea_offline_seconds`) saat
  ada posisi terbuka. Tanpa posisi turun jadi SEV-3 (RB-09).
- **Otomatis:** `GLOBAL_HALT` via `auto:ea_offline` (kill-switch); alert
  `🚨 EA OFFLINE` dari ea-watch + SEV-2 dari sev-watch.
- **Langkah:**
  1. Cek host: proses wine/MT5 hidup? `DISPLAY :99`? koneksi broker?
     (`journalctl --user -u fund2-hfm-recorder -n 50`, log EA).
  2. Restart MT5 bila perlu — EA reconnect otomatis setelah login broker
     (diamati 80–141 s pada migrasi native).
  3. Verifikasi posisi & SL broker-side tetap aktif sel offline (SL/TP
     broker-side tidak terpengaruh).
  4. Setelah EA online + rekonsiliasi cocok: `/resume ACK` (checklist §3).
- **Verifikasi pemulihan:** alert `✅ EA ONLINE kembali` dari ea-watch;
  `/status` heartbeat segar.
- **Contoh penerapan (insiden nyata 25 Nov 2026):** 05:05 WIB EA offline 63 s
  saat 2 posisi terbuka → `GLOBAL_HALT` otomatis (`auto:ea_offline`); 05:21
  EA online kembali; kill-switch TIDAK melepas diri sendiri — statusnya tetap
  GLOBAL_HALT sampai owner `/resume ACK` setelah checklist. 0 posisi terbuka
  saat dokumen ini dibuat.

### RB-06 — SEV-2 `DB_UNAVAILABLE` 🔥

- **Pemicu:** kolektor tidak bisa menghubungi Postgres (:5433).
- **Otomatis:** alert dikirim langsung via Telegram (tidak lewat DB); halt
  entry TIDAK bisa ditulis ke DB selama DB down — anggap sistem unprotected.
- **Langkah:**
  1. `systemctl --user status fund2-postgres` +
     `journalctl --user -u fund2-postgres -n 50`.
  2. Cek disk penuh (`df -h`) — Postgres bisa berhenti karena disk.
  3. Restart Postgres bila aman; fund2-api/fund2-alerts reconnect sendiri
     (pool psycopg).
  4. Selama DB down: jangan ada ekspektasi risk gate aktif; pertimbangkan
     hentikan runner manual bila market buka.
- **Verifikasi:** `/health` API OK; `/metrics` `db.available: true`.

### RB-07 — SEV-2 `REPEATED_EXECUTION_FAILURES` 🔥

- **Pemicu:** ≥ 3 order FAILED beruntun (threshold `consecutive_failed_orders`).
- **Otomatis:** `STOP_NEW_ORDERS` via `auto:consecutive_failed`.
- **Langkah:**
  1. Cek `fail_reason` order terakhir di `/orders` (reject broker? simbol
     tidak aktif? spread filter?).
  2. Verifikasi koneksi broker & sesi MT5.
  3. Reset streak: `/resume` (marker `trigger_ack`) setelah penyebab hilang.
- **Verifikasi:** order baru sukses; streak 0 di `/metrics`.

### RB-08 — Alert watcher lain

| Alert | Arti | Langkah pertama |
| --- | --- | --- |
| `🛑 KILL-SWITCH AKTIF` / `⚠️ ESKALASI` | kill-switch berpindah mode (aktor: owner/auto/dashboard) | `/status`, lalu runbook SESUAI penyebab (lihat `reason` + `sumber`) |
| `✅ KILL-SWITCH NONAKTIF` | mode dilepas | pastikan yang melepas memang berhak (owner) |
| `🟠 FLATTEN: N posisi dikirim` | perintah flatten berjalan | pantau order → CLOSED; rekonsiliasi menyusul |
| `🚨 EA OFFLINE` / `✅ EA ONLINE` | transisi heartbeat EA | RB-05 (dengan posisi) / pantau pemulihan |
| `🚨 PAPER RUNNER TIDAK SEHAT` | service mati atau `paper_state` basi > 15 m saat market buka | `systemctl --user status fund2-paper-runner`; cek feed candle; restart bila perlu |
| `⚠️ candle XAUUSD M5 stale` | feed candle > 10 menit | cek EA/tick pipeline + `fund2-candle-rollup`; lihat skill fund2-ops (TS_FUTURE skew, offset broker) |

### RB-09 — SEV-3 (watch, tanpa auto-halt) ⚠️

| Alert key | Ambang | Tindakan |
| --- | --- | --- |
| `latensi_t02` | p95 T0→T2 ≥ 300 ms | cek beban API/DB; `scripts/latency_harness.py`; pause strategi bila berlanjut |
| `spread_tinggi` | XAUUSD p95 1 jam ≥ 0.50 USD | tunda entry; cek sesi/berita |
| `feed_stale` | candle > 10 menit | cek EA + rollup |
| `data_gap` | gap likuiditas > 60 s | cek koneksi EA / log ingest tick |
| `db_connections` | ≥ 80% max_connections | buruan koneksi bocor (`pg_stat_activity`) |
| `disk_penuh` | ≥ 80% | bersihkan log/parquet/backup kadaluarsa |
| `backup_age` | > 26 jam | `journalctl --user -u fund2-backup`; `~/fund2/scripts/fund2_backup.sh` |
| `drawdown_watch` | DD harian ≥ 1.5% (auto-halt 3%) | review posisi & sinyal |
| `order_stuck` | SENT > 60 s | cek `/orders`; reconciler menyusul |
| `failure_rate` | FAILED ≥ 20% (≥ 5 terminal) | cek `fail_reason`; waspadai 3 beruntun |
| `paper_runner_stale` | `paper_state` > 15 menit | sama dgn RB-08 paper runner |
| `ea_offline_tanpa_posisi` | EA offline, 0 posisi | cek MT5/koneksi sebelum entry baru |

## 5. Kesehatan pipeline alert (cek berkala)

1. `systemctl --user is-active fund2-alerts` → `active`.
2. `journalctl --user -u fund2-alerts --since "-1 hours"` → cari
   `sendMessage ... 200 OK`. **400 Bad Request: can't parse entities** =
   teks Markdown rusak (underscore/dynamic text tidak di-escape) — alert
   GAGAL terkirim; pelajaran 23 Nov 2026: semua nilai dinamis wajib
   `_md_escape`. Laporkan ke pemilik t_f2p1b3/a10, jangan patch sendiri.
3. `notify_owner gagal` di log = kirim gagal (rate limit / parse) — cek
   deskripsi error di baris `telegram sendMessage failed`.
4. Uji kirim tanpa menyentuh kill-switch:
   `cd ~/fund2/api && .venv/bin/python -m app.metrics --send-test`
   → 4 baris `[test] ... sent=True` dan 4 pesan `[TEST]` muncul di Telegram
   owner (SEV-1 x2, SEV-2 x2, sampel sintetis — tidak ada auto-action).
5. Uji evaluasi tanpa kirim: `.venv/bin/python -m app.metrics`.

## 6. Prosedur simulasi (drill DoD §23.9)

Tujuan: membuktikan **alert kritis sampai ke owner** dan **runbook bisa
diikuti orang selain pembuatnya**.

1. **Precondition:** `fund2-alerts` active; `TELEGRAM_BOT_TOKEN` +
   `TELEGRAM_OWNER_ID` terkonfigurasi di `api/.env.alerts` (cek keberadaan
   file, JANGAN print isinya).
2. **Kirim alert [TEST]** (jalur resmi, tanpa auto-action):
   `cd ~/fund2/api && set -a; source .env; source .env.alerts; set +a;
   .venv/bin/python -m app.metrics --send-test`
   Hasil yang diharapkan: `sent=True` untuk SEV-1 `posisi_tanpa_sl`,
   SEV-1 `ledger_mismatch`, SEV-2 `ea_offline`,
   SEV-2 `repeated_execution_failures`.
3. **Bukti sampai:** 4 pesan `[TEST]` terlihat di Telegram owner.
4. **Tabletop satu insiden nyata:** ambil insiden terakhir (lihat
   `kill_switch_events` terbaru), telusuri runbook-nya langkah demi langkah
   terhadap state live — semua langkah verifikasi bersifat read-only
   (`/status`, `GET /metrics`, journalctl). Jangan mengubah kill-switch saat
   drill.
5. **Isi formulir bukti** (§7) ke `docs/RUNBOOK_v2.2_UJI.md`.

Kriteria lulus: seluruh langkah bisa diikuti TANPA bertanya ke pembuat
runbook; alert `[TEST]` diterima owner; temuan/selisih dicatat sebagai
tindak lanjut.

## 6.1 Mengubah guardrail risiko dari UI admin

Satu-satunya kanal resmi perubahan guardrail inti dan auto-trigger (PRD v2.2
§14/§18). Jangan memakai psql/CLI/file kode. Halaman: `/admin/guardrail`
(nav **Guardrail**, hanya role `admin`).

1. Pastikan akun Anda admin dan 2FA (TOTP) sudah terdaftar. Badge di kartu
   "Status 2FA sesi" menunjukkan `2FA AKTIF` / `perlu step-up`.
2. Buka **Guardrail**. Kartu "Guardrail inti" menampilkan nilai AKTIF dari
   tabel `settings`; "Auto-trigger" dari `GET /kill-switch` (`triggers`).
   Bandingkan dengan nilai final di `docs/KEPUTUSAN_OWNER.md` §I. Kartu
   **"Nilai aktif vs angka final §I"** melakukan pembandingan ini otomatis:
   badge `N selisih` + daftar `aktif X · final §I Y`, dan tiap baris yang
   menyimpang diberi chip `≠ §I`. Halaman **tidak** menyamakan angka sendiri —
   selisih harus diputuskan owner, lalu disamakan lewat langkah 3–5 di bawah.
3. Isi hanya field yang ingin diubah (kosong = tidak berubah). Angka memakai
   koma desimal (contoh `0,10`). Tombol berubah menjadi "Simpan N perubahan".
4. Klik simpan -> dialog menampilkan tabel **lama -> baru** dan daftar
   konsekuensi. Centang pengakuan, klik **Lanjut verifikasi 2FA**, masukkan
   kode TOTP 6 digit dan **password akun**, lalu **Simpan & audit**.
5. Verifikasi hasil: toast "Guardrail inti tersimpan" / "Auto-trigger
   tersimpan", kartu "Hasil audit terakhir", dan baris baru di "Riwayat
   perubahan (settings_audit)" dengan kolom Lama -> Baru dan nama operator.
   Bila trigger belum pernah diubah dari UI, sisi Lama berbunyi
   `belum di-set (bawaan kode)` — artinya nilai sebelumnya berasal dari
   bawaan kode, bukan dari tabel `settings`.

Kegagalan yang wajar:

| Gejala | Arti | Tindakan |
| --- | --- | --- |
| `password salah` (403) | Password ulang tidak cocok | Tidak ada nilai yang berubah; ulangi dengan password benar |
| `invalid TOTP code` | Kode kedaluwarsa / sudah dipakai (anti-replay) | Tunggu jendela 30 detik berikutnya, ulangi |
| `Harus 0,01–100` di baris input | Di luar rentang kewajaran server | Perbaiki angka; rentang bukan policy |
| 403 FORBIDDEN saat buka halaman | Akun bukan admin | Minta akses ke owner |

Catatan: `ea_offline_seconds` (6 s) hanya menandai EA offline (alert + tolak
order baru), sedangkan `ea_offline_halt_seconds` (60 s) memicu `GLOBAL_HALT`
dan hanya berlaku bila ada posisi terbuka. Jangan disamakan.

## 7. Formulir bukti uji (diisi penguji)

```
# Bukti Uji Runbook v2.2
Penguji   : <nama/profile, BUKAN pembuat runbook>
Tanggal   : <tanggal jam WIB>
Runbook   : ~/fund2/docs/RUNBOOK_v2.2.md (commit <sha>)

| # | Langkah | Hasil (OK/GAGAL) | Bukti (output/link) |
| 1 | precondition fund2-alerts active | | |
| 2 | --send-test: 4x sent=True | | |
| 3 | 4 pesan [TEST] diterima owner Telegram | | |
| 4 | tabletop insiden nyata per runbook | | |

Temuan / langkah yang membingungkan:
<daftar, atau "tidak ada">

Tindak lanjut:
<kartu/komentar, atau "tidak ada">
```

## 8. Referensi

- PRD v2.2 §20.2 (severity), §23.9 (P8 DoD), §17.5 (recovery sequence).
- `docs/OBSERVABILITY_v2.2.md` — metrics, ambang, anti-spam.
- `docs/DR_v2.2.md` — backup/restore, RTO/RPO, recovery sequence.
- INCIDENT_PLAYBOOK — task t_f2v22a17 (playbook insiden rilis).
- Kode: `api/app/metrics.py`, `api/app/alerts.py`, `api/app/telegram_bot.py`,
  `api/app/kill_switch.py`.
