# P4: Alur Approve Laporan → Deploy Flag `enabled`

Kartu: t_f2p4a3 · PRD v2.1 §5.9 & P4 ("Alur approve: laporan → owner approve
via UI/Telegram → deploy (flag `enabled`)") · 2026-11-23

## Alur end-to-end

1. **Laporan**: siklus mingguan `self_improve.run_cycle()` menganalisa event
   log + hasil, menjalankan backtest otomatis (tercatat di `backtest_runs`),
   menulis `improvement_proposals` (status `PROPOSED`), lalu mengirim laporan
   ke owner via Telegram (`notify_owner`). Sudah jalan sejak W48
   (kartu t_f2p4a1, commit 6eed55e).
2. **Owner approve**, dua kanal yang setara:
   - **UI/HTTP**: `GET /improve/proposals` (sesi login) →
     `POST /improve/proposals/{id}/decision` dengan
     `{"decision": "APPROVED"|"REJECTED", "rationale": ...}`.
     Gerbang: **admin + CSRF + 2FA step-up + username ==
     `settings.owner_username`** (default `admin`).
   - **Telegram**: `/proposals`, `/approve <id> [alasan]`,
     `/reject <id> [alasan]`. Gerbang: hanya pengirim dengan ID ==
     `TELEGRAM_OWNER_ID` yang dilayani; pengirim lain diabaikan (tanpa balasan).
3. **Deploy**: `self_improve.decide()` mencatat keputusan lalu (bila APPROVED)
   `deploy()`: `strategies.enabled = true` (status `PAPER`,
   `current_version` naik), settings `strategy_params_<id>` +
   `strategy_mode_<id>` (ter-audit otomatis oleh trigger `settings_audit`),
   `strategy_versions` status `APPROVED`, `strategy_approvals` append-only
   (`OWNER_APPROVE` → `DEPLOY`), dan `deployment_records`.

## Garis merah: non-owner tidak bisa mengubah flag

Tulis `strategies.enabled` hanya ada di `self_improve.deploy()`, yang hanya
dapat dicapai lewat keputusan owner terverifikasi. Matriks penolakan
(di-test di `tests/test_approve_flow.py`, DB test terisolasi conftest):

| Percobaan non-owner | Hasil |
| --- | --- |
| Anonim tanpa sesi (HTTP) | 401 |
| Role `user` + sesi + CSRF + 2FA sah | 403 |
| Role `agent` (kredensial LLM) + 2FA sah | 403 |
| Admin lain (username ≠ `owner_username`) + 2FA sah | 403 |
| Owner sendiri tanpa step-up 2FA | 403 |
| Pengirim Telegram bukan `TELEGRAM_OWNER_ID` | diabaikan (None, tanpa balasan) |
| Keputusan kedua pada usulan yang sama | 409 (append-only) |

Setelah seluruh penolakan: `improvement_proposals.status` tetap `PROPOSED`,
`strategies.enabled` tetap tidak pernah di-set, `strategy_approvals` dan
`deployment_records` tetap kosong. Catatan desain: endpoint mode strategi
(`POST /strategies/{id}/mode`) memang terbuka untuk role admin (PRD v2.2
§18), tapi itu flag mode (`strategy_mode_<id>`), bukan flag deploy
`enabled`.

## Bukti test

`tests/test_approve_flow.py` (7 test, semua lulus):

- `test_http_e2e_owner_approve_lalu_deploy_flag_enabled` — approve via HTTP
  (kanal UI) → 200 `DEPLOYED`, flag enabled=true, stages
  `[OWNER_APPROVE, DEPLOY]`, `deployment_records.deployed_by` = owner,
  settings params tercatat, keputusan kedua 409.
- `test_telegram_e2e_owner_approve_lalu_deploy_flag_enabled` — approve via
  Telegram owner → `DEPLOYED`, reviewer `tg:<owner_id>` tercatat append-only.
- `test_telegram_non_owner_diabaikan_flag_tetap`,
  `test_telegram_reject_tidak_mengubah_flag_enabled`,
  `test_telegram_approve_tidak_dikenal_dan_sudah_diputuskan`,
  `test_telegram_tanpa_argumen_dan_owner_belum_diset`.
- `test_http_non_owner_dan_tanpa_2fa_ditolak_flag_tetap` — matriks 401/403
  di atas, flag tidak berubah.

Regresi: full suite pytest lulus (lihat komentar kartu untuk angka pasti).

## Cara pakai (owner)

- Telegram: kirim `/proposals` ke bot, lalu `/approve w47-p3-mlgbm-paper
  <alasan>` (atau `/reject ...`). Balasan bot menyatakan hasil deploy.
- UI: login → buka halaman dengan daftar usulan (endpoint
  `/improve/proposals`); approvia butuh 2FA aktif (step-up).

## Status live saat laporan dibuat

- Deploy: commit `22ead98`, service `fund2-api` + `fund2-candle-rollup` +
  `fund2-alerts` di-restart 23 Nov 20:35 WIB, semua `active`. Snapshot DB
  live sebelum/sesudah deploy identik (users 4, orders 21, order_events 102,
  positions 0, settings 22, sessions 10, candles 228691) - deploy tidak
  mengubah state; hanya audit_log +2 (LOGIN_SUCCESS/LOGOUT admin untuk
  verifikasi read-only).
- Kanal UI/HTTP live terverifikasi: login admin → `GET /improve/proposals`
  mengembalikan 3 usulan W48 → logout (semua 200).
- 3 usulan W48 masih `PROPOSED` menunggu keputusan owner
  (`w47-p3-mlgbm-paper` LULUS semua kriteria; P1/P2 GAGAL).
- `strategies` kosong, `strategy_approvals`/`deployment_records` 0 — flag
  `enabled` belum pernah di-set; tidak ada deploy tanpa owner.

## Ketergantungan kanal Telegram live (butuh keputusan owner)

Perintah `/approve` via Telegram sudah teruji, tapi **poller perintah
fund2-api sengaja OFF** (`TELEGRAM_POLLER_OFF=1` di `api/.env`): satu-satu
token bot di host ini dipakai Hermes gateway, getUpdates bersamaan = 409
conflict (sudah dicatat di LAPORAN_DOD_P1B3_TELEGRAM.md; berlaku juga untuk
perintah kill-switch yang ada sejak P1a). Agar jalur Telegram hidup, perlu
bot Telegram khusus fund2 via @BotFather, tokennya diisi ke `api/.env`
lalu restart `fund2-api` (tanpa mengubah `TELEGRAM_ALERTS_OFF`). Sampai itu,
approve lewat UI/HTTP adalah kanal live; kode Telegram siap dan aktif
otomatis begitu token dedicated dipasang.
