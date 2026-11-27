# Bukti Uji Runbook v2.2

Penguji   : hf-qa (bukan pembuat runbook; pembuat = hf-devops per t_f2v22b2)
Tanggal   : 25 Nov 2026, 07:15–07:35 WIB
Runbook   : ~/fund2/docs/RUNBOOK_v2.2.md (commit b0dd93e; terverifikasi identik dengan HEAD a9a8c83 — file tidak berubah sebelum drill)

| # | Langkah | Hasil (OK/GAGAL) | Bukti (output/link) |
| 1 | precondition fund2-alerts active | OK (systemd) / **GAGAL (fungsi)** — unit `active (running)` sejak 06:44:40 WIB, tetapi daemon beku: CPU tidak bertambah (2411 tick → 2411 tick selama 60s), log terakhir 06:45:20 WIB, nol pengiriman Telegram dari daemon sejak itu | `systemctl --user is-active fund2-alerts` → `active`; `/proc/1294/stat` utime+stime flat 60s; `journalctl --user -u fund2-alerts --since 06:44` berhenti di 06:45:20 |
| 2 | --send-test: 4x sent=True | OK | `cd ~/fund2/api && set -a; source .env; source .env.alerts; set +a; .venv/bin/python -m app.metrics --send-test` (07:20:26 WIB) → 4 baris `[test] SEV-1 posisi_tanpa_sl: sent=True`, `[test] SEV-1 ledger_mismatch: sent=True`, `[test] SEV-2 ea_offline: sent=True`, `[test] SEV-2 repeated_execution_failures: sent=True`; 4x `POST .../sendMessage "HTTP/1.1 200 OK"`; diulang 07:33 WIB → kembali 4x sent=True |
| 3 | 4 pesan [TEST] diterima owner Telegram | OK (kirim API 200 OK x4) | Bukti tingkat penguji: HTTP 200 dari `api.telegram.org/bot…/sendMessage` per pesan (response ok=True berarti diterima Telegram untuk dikirim ke chat owner). Konfirmasi visual di aplikasi Telegram owner tidak bisa dilakukan dari server — mohon owner mengonfirmasi 8 pesan `[TEST]` (2 ronde) masuk. Pengiriman lewat jalur resmi `notify_owner` (milik t_f2p1b3/t_f2v22a10), bukan reimplementasi. |
| 4 | tabletop insiden nyata per runbook | OK untuk RB-05 terhadap insiden 05:05 WIB; **GAGAL untuk insiden 06:45 WIB** (alert SEV-2 + release tidak pernah terkirim — daemon beku, lihat Temuan F1) | Tabel timeline & verifikasi langkah di bawah |

## Tabletop RB-05 — SEV-2 `EA_OFFLINE` (insiden 25 Nov 2026)

Dua insiden `auto:ea_offline` hari ini (kill_switch_events id 98 dan 138):

### Insiden A — 05:05 WIB (id 98; yang dirujuk kartu drill)

| Waktu (WIB) | Peristiwa | Sumber |
| --- | --- | --- |
| 05:04:43 | `fund2-alerts` restart (fungsi systemd user) | journalctl |
| 05:05:16 | `ACTIVATE GLOBAL_HALT` `auto:ea_offline`: "EA offline 63s (threshold 60.0s), 2 posisi terbuka" | kill_switch_events id 98 |
| 05:05:24 | `ea_watch error: couldn't get a connection after 30.00 sec` — pool DB gagal (Postgres belum siap) | journalctl fund2-alerts |
| 05:18:44 | `fund2-alerts` restart lagi | journalctl |
| 05:19:14 | ks-watch baseline event id 98; pool connect gagal "database system is starting up" | journalctl fund2-alerts |
| 05:19:35 | **Alert SEV-2 `ea_offline` terkirim ke owner (sendMessage 200 OK)**: "EA offline 77s (threshold 60s) saat 2 posisi terbuka." | journalctl fund2-alerts |
| 05:21:17 | Pesan pemulihan paper runner **GAGAL 400** (markdown rusak, lihat Temuan F2) | journalctl fund2-alerts |
| 05:21:47 | Alert `✅ EA ONLINE kembali \| Bridge pulih.` → **200 OK** (05:21:48) | journalctl fund2-alerts |
| 06:38:01 | `RELEASE GLOBAL_HALT` oleh admin (dashboard), `checklist_ack: true` | kill_switch_events id 102 |

Verifikasi langkah RB-05 terhadap state live (semua read-only):

1. **Cek host** — OK: proses MT5 hidup (`terminal64.exe` PID 2717, wineserver aktif), `DISPLAY :99` merespons (`xdpyinfo` OK), koneksi broker OK (tick XAUUSD/BTCUSD mengalir; recorder flush tiap menit; `fund2-hfm-recorder` reconnect sukses 06:45:05 setelah reboot). `journalctl --user -u fund2-hfm-recorder` menunjukkan restart 06:44:40 + reconnect 06:45:05.
2. **Restart MT5 bila perlu** — N/A: EA online kembali sendiri (heartbeat segar, `ea.last_seen_age_s` 0–8s saat drill).
3. **Posisi & SL broker-side tetap aktif** — OK: `GET /positions` 3 posisi OPEN semuanya punya SL & TP broker-side; `GET /metrics` → `risk.unprotected_positions: []`; sel offline SL/TP tidak terpengaruh (tidak ada bukti posisi tanpa SL selama insiden).
4. **EA online + rekonsiliasi cocok → /resume ACK** — OK: `reconciliation.new` = `{mismatch_new: 0, orphan_new: 0}` saat drill; RELEASE 06:38 dengan `checklist_ack: true` (7 butir checklist recovery §3 cocok dengan `RECOVERY_CHECKLIST` di kode). Pelepasan hanya oleh owner/admin — sesuai prinsip §1.3; drill TIDAK menyentuh kill-switch.
- **Verifikasi pemulihan** — OK: alert `✅ EA ONLINE kembali` terkirim 05:21:48; heartbeat segar (`/status` ≡ `GET /kill-switch` + `/metrics`: `ea_last_seen_age_s` 0.1–8s).

### Insiden B — 06:45 WIB (id 138; setelah reboot host 06:44)

| Waktu (WIB) | Peristiwa | Sumber |
| --- | --- | --- |
| 06:44:40 | Reboot host selesai; `fund2-alerts` start; Postgres start 06:44:55 | journalctl |
| 06:45:20 | `ea_watch error` + `paper_watch error` (pool) — **log terakhir daemon** | journalctl fund2-alerts |
| 06:45:23 | `ACTIVATE GLOBAL_HALT` `auto:ea_offline`: "EA offline 63s, 1 posisi terbuka" | kill_switch_events id 138 |
| 06:45:20–sekarang | Daemon beku total: TIDAK ada alert SEV-2, TIDAK ada alert kill-switch, TIDAK ada `✅ EA ONLINE`, TIDAK ada rekap 07:00, TIDAK ada alert FLATTEN (07:02–07:19) | journalctl (kosong setelah 06:45:20) |
| 06:56:20 | `RELEASE GLOBAL_HALT` oleh admin (dashboard), `checklist_ack: true` — tanpa alert apa pun ke owner | kill_switch_events id 139 |

Alert `[TEST]` 07:20/07:33 terkirim karena `--send-test` memanggil `notify_owner` in-process, **bukan** lewat daemon — jalur kirimnya sehat, pengantarnya (daemon) yang mati.

## Temuan / langkah yang membingungkan

- **F1 — KRITIS (pipeline alert mati diam-diam):** `fund2-alerts` (PID 1294) beku sejak 06:45:20 WIB setelah reboot 06:44: systemd `active` tapi semua watcher mati (CPU flat, log kosong, nol sendMessage). Akibatnya alert kritis SEV-2 insiden 06:45, alert RELEASE 06:56, rekap harian 07:00, dan alert FLATTEN 07:02–07:19 **tidak pernah sampai ke owner**. DoD "alert kritis terkirim ke owner" untuk insiden nyata saat ini TIDAK terpenuhi. Indikasi awal: watcher yang start sebelum Postgres siap menggantung selamanya di `db.pool().connection()` (ks-watch bahkan tidak pernah mencetak baseline log "ks-watch aktif" setelah restart 06:44:40; berbeda dengan restart 05:18 yang baseline-nya muncul). Perlu investigasi pemilik t_f2p1b3/t_f2v22a10 + restart service oleh DevOps (di luar kewenangan drill read-only ini).
- **F2 — 400 `can't parse entities` terulang saat insiden nyata:** 05:21:17 pesan `✅ PAPER RUNNER pulih: service active, paper_state terupdate.` gagal terkirim (byte offset 45 = underscore pada `paper_state` tidak di-escape, parse_mode Markdown). Persis pola pelajaran 23 Nov 2026 di §5.2 runbook. File: `api/app/alerts.py:272` (teks tidak lewat `_md_escape`). Dilaporkan ke pemilik t_f2p1b3/t_f2v22a10, tidak dipatch drill ini (jalur kirim bukan milik kartu ini).
- **F3 — Alert SEV-2 tertunda 14 menit pada insiden A:** halt 05:05:16, alert SEV-2 baru terkirim 05:19:35 karena `fund2-alerts` + Postgres ikut restart dan pool gagal saat DB "starting up". Runbook belum menjelaskan skenario "daemon/DB ikut mati saat insiden" (langkah RB-05 §1 fokus ke MT5/EA, tidak ke kesehatan daemon alertnya sendiri).
- **F4 — State kartu drill sudah basi saat drill:** kartu menyebut GLOBAL_HALT masih aktif sejak 05:05 dan 0 posisi; kenyataan live saat drill (07:15–07:35 WIB): halt sudah dilepas 06:38, terjadi halt kedua 06:45–06:56, dan ada 3 posisi terbuka. Tidak masalah untuk drill (tabletop memakai insiden terakhir per §6.4), tapi info state di kartu tidak boleh dipakai sebagai dasar keputusan tanpa cek live.
- **F5 — Minor, langkah jelas:** §6 bisa diikuti tanpa bertanya ke pembuat. `/status` di Telegram dipetakan ke `GET /kill-switch` + `GET /metrics` + `GET /positions` (setara read-only, auth session admin sementara QA yang sudah dihapus setelah drill). Tidak ada langkah yang salah.

## Tindak lanjut

- **F1 (prioritas):** kartu ke hf-devops/pemilik t_f2p1b3/t_f2v22a10 — selidiki + perbaiki penggantung pool saat Postgres belum siap (tambah timeout/retry yang benar atau urutan start), lalu restart `fund2-alerts`. Sebelum beres, alert kritis produksi TIDAK sampai ke owner.
- **F2:** komentar di kartu induk t_f2v22b2 + laporkan ke pemilik t_f2p1b3/t_f2v22a10 (escape `_md_escape` untuk teks `paper_state`).
- **F3:** usulan revisi runbook (pemilik runbook hf-devops): tambah langkah cek `systemctl --user is-active fund2-alerts` + log terakhir daemon di awal RB-05 / §3.
- Konfirmasi visual owner untuk 8 pesan `[TEST]` (ronde 07:20 dan 07:33 WIB) di Telegram.
