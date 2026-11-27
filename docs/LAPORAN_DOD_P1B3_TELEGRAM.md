# LAPORAN DoD — [FUND2-P1b] Telegram alert: kill-switch, EA offline, rekap harian

Task: t_f2p1b3 · Tanggal: 22 Nov 2026 · Commit: 5f3f6e7 (kode), commit ini (laporan)
PRD: v2.1 §5.9 (cron harian), §5.8 (notifikasi), KEPUTUSAN_OWNER D11/D12, sprint P1b hari 11.

## Arsitektur

Daemon **terpisah** `fund2-alerts` (systemd user service) — BUKAN bagian dari fund2-api:

- Alert tetap hidup tanpa me-restart fund2-api (guardrail Direktur 22 Nov: backend
  t_ef2f49c6 sedang edit repo yang sama). Selama tugas ini fund2-api TIDAK pernah
  saya restart.
- Nol edit ke modul API existing (file baru saja) — anti-clobber.
- Sumber data dibaca dari Postgres yang sama: `kill_switch_events`,
  `settings.ea_last_seen_at`, `positions`, `orders`, `candles`.
- Kirim pesan via `telegram_bot.notify_owner` (owner-only channel; token + chat id
  owner dari env; tanpa token daemon no-op).

File baru:

| File | Isi |
| --- | --- |
| `api/app/alerts.py` | Daemon: poller event kill-switch, watcher EA offline, scheduler rekap 07:00 WIB, CLI `--rekap-now` |
| `api/tests/test_alerts.py` | 16 test tanpa jaringan (format, escaping, poll, transisi EA, rekap, scheduler) |
| `deploy/fund2-alerts.service` | Unit systemd (tanpa secret) |
| `api/.env.alerts.example` | Contoh env (token + owner id + jam rekap) |
| `api/.env.alerts` | Secret live (gitignored, mode 600) |

## Cakupan alert (semua teruji live, Telegram jawab 200 OK)

| Kasus | Pemicu | Bukti live (journal fund2-alerts) |
| --- | --- | --- |
| Kill-switch AKTIF | event `ACTIVATE` (dashboard/API/Telegram/auto — semua lewat `kill_switch.activate`) | 03:05:47 🛑 → HTTP 200 |
| Kill-switch NONAKTIF | event `RELEASE` | 03:05:57 ✅ → HTTP 200 |
| ESKALASI mode | event `ESCALATE` (termasuk mode sebelumnya) | unit test |
| Flatten | event `FLATTEN_REQUEST` | unit test |
| EA OFFLINE | transisi online→offline (threshold `kill_switch_triggers.ea_offline_seconds`, default 60s) | 03:07:53 🚨 → HTTP 200 |
| EA ONLINE kembali | transisi offline→online | 03:07:32 & 03:08:03 ✅ → HTTP 200 |
| Rekap harian | scheduler 07:00 WIB (`TELEGRAM_RECAP_HOUR_WIB`) + CLI `--rekap-now` | 03:05:4x, tanpa "sendMessage failed" |

Anti-spam: observasi pertama hanya baseline (restart service tidak mengspam);
tiap transisi di-alert sekali; event lama tidak di-replay (baseline MAX(id));
`TRIGGERS_UPDATED`/`AUTO_TRIGGER` tidak di-alert (auto-trigger sudah menulis
ACTIVATE/ESCALATE sendiri).

## Isi rekap harian (PRD 5.9: P&L, posisi, kesehatan bridge)

```
📊 REKAP HARIAN fund2 — 22 Nov 2026 (window 24 jam)
P&L 24 jam: +2.00 USD (1 ditutup: 1 win / 0 loss)
Balance: 10002.00 | Equity: 10002.00 (floating +0.00)
DD harian: 0.00% | DD total: 0.00% (puncak 10002.00)
Posisi terbuka: 0
Bridge:
• EA: ONLINE (5s lalu)
• Order SENT/STUCK: 0 | FAILED 24 jam: 6
• Kill-switch: AMAN
• Candle terakhir: 1 menit lalu
• Recorder: active
```

## Pengujian

- Unit: `pytest tests/test_alerts.py` → **16/16 lulus**; suite penuh → **192/192
  lulus** (fund2_test, tanpa jaringan).
- E2E live (driver `e2e_alerts.py` + journal): keenam kasus di tabel terkirim
  nyata ke chat owner (Telegram API jawab **200 OK**, nol kegagalan di window
  final). Simulasi EA offline = geser `settings.ea_last_seen_at` -120s; real EA
  memulihkan timestamp (≤15s, persist throttle) → alert recovery menyala sendiri.
- State akhir live aman: kill-switch inactive, `paused_strategies` [],
  ea_last_seen 8s (online), fund2-api / fund2-recorder / fund2-alerts semua active.

### Bug yang ditemukan & diperbaiki saat E2E

Run pertama: 4 alert kill-switch **gagal 400** "can't parse entities" — underscore
pada teks dinamis (reason memuat id task `t_f2p1b3`) dianggap italic Markdown yang
tidak tertutup. Fix: `_md_escape()` meng-escape `_ * ` [` pada semua nilai dinamis
(reason, strategi, sumber, aktor, simbol, mode) — test baru `test_fmt_escapes_
markdown_specials` menjaganya. Run final: semua 200 OK. (Catatan: jawaban
perintah `telegram_bot.py` punya penyakit yang sama untuk input owner yang
mengandung `_` — masuk daftar perbaikan kanal perintah di bawah.)

Catatan race: satu run driver gagal di kasus EA karena fund2-api di-restart
worker lain (deploy 64b230a) di tengah tes — proses baru langsung persist
`ea_last_seen_at` sehingga simulasi offline tertimpa. Bukan bug daemon; run
ulang membuktikan transisi berjalan.

## Keputusan yang masih dibutuhkan owner: kanal perintah (poller)

"Owner saja yang bisa memberi perintah" sudah diimplementasi + teruji di
`telegram_bot.py` (P1a): `handle_command` memverifikasi `sender_id ==
TELEGRAM_OWNER_ID`, selain owner diabaikan (test `test_non_owner_ignored`,
`test_no_owner_config_ignored`). Perintah tersedia: /status /stop /stopflatten
/flatten /pause /resume /halt /help.

Namun **poller perintah di fund2-api masih OFF** karena satu-satu token bot di
host ini dipakai Hermes gateway (getUpdates bersamaan = 409 conflict). Agar
owner bisa memberi perintah lewat Telegram, perlu **bot khusus fund2** (2 menit
via @BotFather) yang tokennya diisi ke `api/.env` — tanpa itu alert tetap jalan
(send-only) tetapi perintah balasan tidak dilayani. Sekalian saat itu: escape
Markdown pada balasan perintah (bug yang sama seperti di atas).

Catatan: selama E2E owner menerima beberapa pesan berulang (driver dijalankan
beberapa kali sampai semua assert lulus + simulasi manual).
