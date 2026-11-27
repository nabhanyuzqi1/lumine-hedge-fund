# Bukti AUDIT-F2: kill-switch anti-flapping & release owner-only

Kartu: `t_7c070c31` · Assignee: hf-backend · Tanggal: 26 Nov 2026 (WIB)
Commit: `5c70a07`

## Keputusan owner yang dieksekusi

25 Nov 2026: **driver QA TIDAK BOLEH me-release kill switch. RELEASE hanya oleh
owner via dashboard + 2FA.** Aktivasi tetap tanpa 2FA (emergency stop).

## Akar masalah (data live `kill_switch_events`)

- Siklus 25 Nov 18:07-18:21 WIB: **7 ACTIVATE + 7 RELEASE** bergantian tiap
  ~60-70 detik (total hari itu 34 ACTIVATE / 33 RELEASE).
- ACTIVATE: `source=auto:daily_drawdown_risk_gate`, mode **GLOBAL_HALT**
  (hardcode di `routes.py`), padahal evaluator kill-switch memakai
  `kill_switch_triggers.modes.daily_drawdown` -> satu kondisi, dua mode.
- RELEASE: `source=kanban:t_baeb3ce4`, `actor=svc-qa-driver` (driver QA
  latensi). Role `qa` + 2FA diizinkan release sejak t_4651d431, sehingga driver
  me-release halt tiap jeda burst, lalu order berikutnya mengaktifkan halt lagi.
- Setiap siklus menulis event baru -> alerts watcher mengirim alert Telegram
  (ACTIVATE bukan sumber `kanban:`, jadi tidak pernah dilewati filter anti-spam
  yang sudah ada) -> spam owner.

## Perbaikan (commit `5c70a07`)

1. `kill_switch.release()`: `ReleaseForbidden` (subclass `PermissionError`)
   bila `source` berawalan `kanban:`/`auto:`/`svc`/`agent` atau `actor`
   berawalan `svc-`/`svc_`/`agent`/`auto`/`system`/`bot`. State tidak berubah,
   tidak ada event RELEASE.
2. Route `POST /kill-switch/release`: dependency `require_2fa`
   (admin + TOTP window, bukan lagi `require_2fa_control` yang menerima role
   `qa`); `source` dari body dipaksa `dashboard` (nilai lain -> 403).
   `ReleaseForbidden` -> HTTP 403; checklist GLOBAL_HALT tetap 400.
3. Idempotensi aktivasi: `activate()` hanya menulis event pada transisi nyata
   (ACTIVATE sekali, ESCALATE hanya saat mode lebih berat). Mode+reason sama
   = no-op, tidak ada event baru -> tidak ada alert ulang.
4. Flapping guard alert: `alerts.ks_poll_once()` mendedupe ACTION
   `ACTIVATE`/`RELEASE` per `(action, mode, source)` dalam jendela
   `ALERTS_KS_DEDUPE_S` (default 300 s). Alert pertama tetap terkirim;
   `ESCALATE` dan `FLATTEN_REQUEST` selalu dikirim.
5. Satu mode untuk daily drawdown: `kill_switch.trigger_mode(trigger)` membaca
   `kill_switch_triggers.modes.*`; risk gate di `routes.py` memakai
   `trigger_mode("daily_drawdown")`, sama dengan `run_trigger_checks()`.

## Bukti test (pytest, `TELEGRAM_ALERTS_OFF=1`, DB test terisolasi)

Baru: `api/tests/test_kill_switch_audit_f2.py` (15 test) + update
`test_agent_role.py` (role qa -> 403).

```
tests/test_kill_switch_audit_f2.py + tests/test_agent_role.py   32 passed
tests/test_kill_switch.py test_alerts.py test_alerts_resilience.py
  test_daily_drawdown_source.py test_telegram.py               117 passed
tests/test_bridge.py test_risk.py test_metrics.py test_auto_sl.py 150 passed
Pristine worktree pada commit 5c70a07 (tanpa perubahan uncommitted kolega):
  test_kill_switch_audit_f2.py test_agent_role.py test_kill_switch.py 71 passed
```

## Bukti live setelah deploy (`systemctl --user restart fund2-api fund2-alerts`, 26 Nov 03:47:55)

- `fund2-api` active, `[ingest] auto-heal M1->M5: 14 bar ditulis`;
  `fund2-alerts` active, `alerts ks-watch aktif (baseline event id 232)`.
  Tidak ada error/traceback di journal setelah restart.
- Login live sebagai `svc-qa-driver` (role `qa`, 2FA aktif), lalu
  `POST /kill-switch/release` (`checklist_ack=true`, `source=kanban:t_baeb3ce4`):

  ```
  login: 200 role=qa
  release as qa: 403 {"detail":"admin role required (agent credentials are read-only for controls)"}
  state setelah: active=true mode=GLOBAL_HALT (tidak berubah)
  ```

## Jumlah event sebelum/sesudah (SQL `kill_switch_events`)

| Waktu | ACTIVATE | RELEASE | total event |
| --- | --- | --- | --- |
| Sebelum perbaikan (s.d. 25 Nov 21:21 WIB) | 38 | 36 | 200 |
| Setelah deploy, observasi 1 jam (26 Nov 03:47:55-04:48:18) | 38 | 37 | 201 |

Satu-satunya event baru dalam jendela 1 jam itu: RELEASE id 233 pukul 04:43:30
`source=dashboard actor=owner` (owner me-release manual lewat dashboard, lolos
jalur baru) dan **tidak ada ACTIVATE maupun RELEASE berulang** sesudahnya.
Alert RELEASE itu tetap terkirim (`settings.alerts_last_ks_event_id` = 233),
jadi dedupe tidak menelan alert pertama yang sah.

Snapshot tabel lain sebelum -> sesudah restart (read-only count): orders
1931->1931, order_events 9182->9183 (1 event order dari aktivitas lain),
positions 251->251, settings 40->40; candles bertambah normal (ingest).
`users`/`sessions` sedikit berubah karena aktivitas worker kartu lain
(login/cleanup), bukan oleh deploy ini; tabel transaksi tidak drift.

## Catatan operasional

- Driver QA (`scripts/_p5_latency_driver_v11.py`) masih mencoba
  `POST /kill-switch/release` di pre-flight; sekarang dijawab 403 sehingga
  driver berhenti dengan pesan jelas. Release untuk driver harus dilakukan
  owner lewat dashboard (2FA) sebelum driver dijalankan.
- Kanal owner Telegram (`source=telegram`, actor `tg:<id>`) tetap boleh
  release karena sudah digerbangi `TELEGRAM_OWNER_ID`.
