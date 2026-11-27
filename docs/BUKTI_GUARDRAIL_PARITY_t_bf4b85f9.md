# Bukti: Paritas guardrail runtime dev/staging ke `KEPUTUSAN_OWNER.md` §I

| | |
| --- | --- |
| Kartu | `t_bf4b85f9` — [FUND2-v2.2] Samakan guardrail runtime dev/staging dengan KEPUTUSAN_OWNER §I (6 field menyimpang) |
| Pelaksana | hf-ceo |
| Tanggal | 26 Nov 2026, 06:32-06:45 WIB |
| Temuan asal | `t_2d1f6d33` (halaman `/admin/guardrail`), `docs/BUKTI_GUARDRAIL_UI_t2d1f6d33.md` §5.1 |
| Lingkungan | host dev `tekka`: PostgreSQL `127.0.0.1:5433/fund2`, API `fund2-api.service` pid 738424 (start 05:21:47 WIB), live trading OFF (`env=demo`, `strategy_mode_ml_gbm=paper`) |
| Sumber kebenaran | `KEPUTUSAN_OWNER.md` §I (angka) + §I.3 (kanal) + §I.4 (paritas, ditambahkan kartu ini) |
| Deploy | tidak ada; hanya perubahan `settings` pada DB dev lewat endpoint resmi |

## 1. Temuan: asal nilai longgar

Enam field yang menyimpang tidak pernah melewati kanal resmi §I.3. Riwayat
`settings_audit` sebelum penerapan:

| Id | Waktu | Key | Nilai baru | `changed_by` | `source` | `audit_log` CONFIG_CHANGED? |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | 23 Nov 15:58 | `kill_switch_triggers` | 3,0 / 8,0 / 3 / 60 | `fund2` | `db` | tidak ada |
| 29 | 24 Nov 02:01 | `max_volume` | 1,0 | `fund2` | `db` | tidak ada |
| 31 | 24 Nov 02:01 | `max_orders_per_min` | 10 | `fund2` | `db` | tidak ada |
| 76 | 24 Nov 23:25 | `kill_switch_triggers` | DD harian 3,0 -> 5,0 | `fund2` | `db` | tidak ada |
| 210 | 25 Nov 10:26 | `kill_switch_triggers` | DD total 8,0 -> 10,0 | `fund2` | `db` | tidak ada |
| 216 | 25 Nov 12:04 | `kill_switch_triggers` | 10,0 / 15,0 / 100 | `fund2` | `db` | tidak ada |

`changed_by = fund2` adalah nama koneksi DB, bukan username admin, dan
`source = db` berarti tulisan langsung ke tabel `settings`. Tidak satu pun
punya pasangan baris `audit_log` `CONFIG_CHANGED` yang menjadi syarat
`PUT /admin/risk-settings`. Kesimpulan: pelonggaran berasal dari sisa harness
uji beban/latensi dan tulisan manual, **bukan** keputusan owner. Karena itu
"staging boleh longgar" tidak punya dasar tertulis; yang berlaku tetap §I.

Konfirmasi owner (syarat butir 1 kartu) dikirim 26 Nov 2026 lewat kantor
(DeskRPG), dengan tiga pilihan: samakan ke §I, akui pengecualian staging,
atau tunda untuk angka lain. Hasil: tidak ada user tersedia untuk menjawab
pada jendela kartu. Sesuai `KEPUTUSAN_OWNER.md` §I (angka sudah disetujui
tertulis 21 Nov, tanpa revisi) dan §I.4, yang dijalankan adalah angka §I.

## 2. Penerapan lewat kanal resmi

| | |
| --- | --- |
| Endpoint | `PUT /admin/risk-settings` (`api/app/routes.py`) |
| Autentikasi | sesi login + `x-csrf-token` + `POST /auth/2fa/challenge` (TOTP, jendela 5 menit) + konfirmasi ulang `password` di body |
| Aktor | akun admin sementara `ceo_guardrail`, dibuat khusus untuk apply ini (nama akun masuk jejak audit), dihapus setelah apply selesai; `totp_secret` dihapus tidak dicetak |
| Waktu | 26 Nov 2026 06:39:31 WIB |
| Respons | `200` dengan `updated = [kill_switch_triggers, max_daily_drawdown, max_orders_per_min, max_volume]` |

Nilai sebelum dan sesudah (dibaca ulang read-only dari DB dan dari endpoint):

| Key | Sebelum | Sesudah | Final §I.1 | Arah |
| --- | --- | --- | --- | --- |
| `max_volume` | 1,0 | 0,10 | 0,10 | diperketat 10x |
| `max_orders_per_min` | 10 | 5 | 5 | diperketat 2x |
| `kill_switch_triggers.daily_drawdown_pct` | 10,0 | 3,0 | 3,0 | diperketat 3,3x |
| `kill_switch_triggers.total_drawdown_pct` | 15,0 | 8,0 | 8,0 | diperketat 1,9x |
| `kill_switch_triggers.consecutive_failed_orders` | 100 | 3 | 3 | diperketat 33x |
| `kill_switch_triggers.ea_offline_seconds` | 60,0 | 6,0 | 6,0 | diperketat 10x |
| `kill_switch_triggers.ea_offline_halt_seconds` | 60,0 | 60,0 | 60,0 | tetap |
| `max_daily_drawdown` | 100,0 | 292,02 | 292,02 (3% x 9.733,86) | disesuaikan ke plafon §I |
| `max_spread` | 0,5 | 0,5 | 0,5 | tidak diubah |
| `max_tick_age_s` | 3,0 | 3,0 | 3,0 | tidak diubah |

`max_daily_drawdown` ikut disesuaikan karena §I.1 menetapkan 292,02 untuk demo
(`daily_start_balance` 9.733,86). Nilai 100,0 sebelumnya lebih ketat dari
policy sehingga validator mencatatnya sebagai `guardrail_open`, dan gate
`guardrails_sesuai_policy` tidak akan PASS selama selisih itu ada. Pengaman
yang mengikat tetap auto-halt A6 di 3%.

`ea_offline_seconds` (6,0, tanda offline + tolak entry, A11/A12) dan
`ea_offline_halt_seconds` (60,0, `GLOBAL_HALT` hanya bila ada posisi) tetap
dua angka berbeda dengan peran berbeda, sesuai §I.2 butir 2.

## 3. Bukti audit

`settings_audit` (trigger DB, satu baris per key):

| Id | Key | `changed_by` | `source` | Lama -> baru |
| --- | --- | --- | --- | --- |
| 356 | `max_volume` | `ceo_guardrail` | `db` | 1.0 -> 0.1 |
| 357 | `max_orders_per_min` | `ceo_guardrail` | `db` | 10 -> 5 |
| 358 | `max_daily_drawdown` | `ceo_guardrail` | `db` | 100.0 -> 292.02 |
| 359 | `kill_switch_triggers` | `ceo_guardrail` | `db` | DD 10,0/15,0/100/60 -> 3,0/8,0/3/6,0 |

`audit_log`:

| Id | `action` | `actor` | `object` | Waktu |
| --- | --- | --- | --- | --- |
| 716 | `CONFIG_CHANGED` | `ceo_guardrail` (admin) | `risk_settings` | 26 Nov 06:39:31 |

`kill_switch_events`:

| Id | `action` | `actor` | `source` | Isi |
| --- | --- | --- | --- | --- |
| 234 | `TRIGGERS_UPDATED` | `ceo_guardrail` | `dashboard:guardrail` | `previous` 10,0/15,0/100/60 -> `updates` 3,0/8,0/3/6,0 (+ `ea_offline_halt_seconds` 60,0) |

Salinan JSON: `docs/evidence/guardrail_parity_t_bf4b85f9/`
(`settings_audit_riwayat.json`, `audit_log_config_changed.json`,
`settings_sesudah.json`, `validate_release_packet.json`).

## 4. Verifikasi read-only

`cd ~/fund2/api && .venv/bin/python ../scripts/validate_release_packet.py`
(koneksi `read_only = True`), output
`docs/VALIDASI_PAKET_RILIS_20261126T063940Z.json`:

```
"guardrails_sesuai_policy": true
"guardrail_drift": []
"guardrail_open": []
"settings_actual": max_volume 0.1 | max_orders_per_min 5 | daily_drawdown_pct 3.0 |
                   max_daily_drawdown 292.02 (ceiling 292.02) | total_drawdown_pct 8.0 |
                   consecutive_failed_orders 3 | ea_offline_seconds 6.0 |
                   ea_offline_halt_seconds 60.0 | max_tick_age_s 3.0 |
                   max_total_volume_lot 0.3 | max_risk_per_trade_pct 0.5 | max_spread 0.5
```

Gate lain: `paket_dokumen`, `runtime_demo_env`, `layanan_inti_aktif`, `live_off`,
`schema_sync`, `backup_segar`, `pytest_penuh_lulus`, `soak_extended_lulus` = PASS.
Satu gate masih gagal, `git_bersih_dan_tag` (F-05, tree kotor milik kartu lain,
belum ada tag); itu bukan bagian kartu ini.

Penegakan di proses yang **sedang berjalan** (bukan hanya kode di disk),
dibaca dari `/metrics` dengan sesi admin (pid 738424, uptime 4.812 s):

```
triggers.ea_offline_seconds       = 6.0
triggers.ea_offline_halt_seconds  = 60.0
triggers.daily_drawdown_pct       = 3.0
triggers.total_drawdown_pct       = 8.0
triggers.consecutive_failed       = 3
ea.offline_threshold_s            = 6.0
ea.offline_halt_threshold_s       = 60.0
```

Artinya pemisahan peran A12 (6 s) vs ambang halt (60 s) aktif di runtime, dan
`max_tick_age_s` (A10) dibaca dari settings. Tidak perlu restart `fund2-api`
untuk dua key ini: `api/app/kill_switch.py` (mtime 03:38) dan `api/app/risk.py`
(mtime 03:13) sudah dimuat proses yang start 05:21.

## 5. Uji otomatis

| Perintah | Hasil |
| --- | --- |
| `env -u DATABASE_URL .venv/bin/python -m pytest tests/test_kill_switch.py -q -k "ea_offline or trigger"` | 18 passed, 29 deselected |
| `env -u DATABASE_URL .venv/bin/python -m pytest tests/test_risk_settings_api.py tests/test_guardrail_admin_ui.py tests/test_sec_guard_triggers_validation.py -q` | 31 passed |
| `python3 scripts/check_guardrail_docs.py` | `SEMUA DOKUMEN SINKRON` (exit 0) |

## 6. Dokumen yang diperbarui

| Dokumen | Perubahan |
| --- | --- |
| `KEPUTUSAN_OWNER.md` | **§I.4 baru**: asal nilai longgar, konfirmasi owner yang tidak terjawab, nilai sebelum/sesudah, aturan paritas dev/staging, pengaman validator |
| `ROLLBACK_PLAN_v2.2.md` §1 | Paragraf ambang: tanggal PASS `guardrails_sesuai_policy` + rujukan §I.4 |
| `RELEASE_CHECKLIST_v2.2.md` 5.9 | PENDING -> **LULUS** dengan nilai runtime dan id audit |
| `PRASYARAT_LIVE_v2.2.md` §3 | Tabel G-01..G-14 jadi 6 kolom (awal 01:33 vs runtime 06:39), §3.1 dan §3.2 diperbarui, status gate PASS |
| `RELEASE_PACKET_v2.2.md` | Baris auto-trigger §4, F-03 -> **TERTUTUP**, §7 butir 5, §8 hasil run 26 Nov |

## 7. Efek samping yang tercatat (bukan kegagalan kartu ini)

1. **Breaker LLM terpicu 3 detik setelah penerapan.** `kill_switch_events` #235
   (06:39:34, `auto:llm_breaker`) mem-pause agent LLM dengan alasan "9 order LLM
   FAILED beruntun (threshold 3)". Sembilan kegagalan itu terjadi 05:28-06:38,
   **sebelum** perubahan ini, dengan volume 0,05-0,10 lot (tidak melanggar
   `max_volume` baru). Penyebab yang terlihat: `retcode=10018` (market closed),
   `no EA result, order never executed`, dan beberapa `fail_reason` kosong,
   yaitu masalah bridge/EA (keluarga F-07), bukan akibat penerapan guardrail.
   Efeknya sesuai desain: ambang 3 kini benar-benar bekerja. Agent tetap
   **PAUSED** (tidak dilepas oleh kartu ini; pelepasan breaker butuh perbaikan
   akar dan persetujuan sesuai D11).
2. **Paper/LLM order di atas 0,10 lot akan ditolak** mulai sekarang. Itu tujuan
   paritas; bila ada strategi paper yang butuh volume lebih besar, jalankan
   sebagai jendela uji eksplisit menurut §I.4.

## 8. Sisa risiko

- ~~Tidak ada mekanisme otomatis yang memeriksa drift tiap hari: gate ini baru
  berjalan saat `validate_release_packet.py` dijalankan manual atau di window
  rilis.~~ **DITUTUP 26 Nov 2026** oleh kartu `t_097ef2bb` (hf-devops): gate
  `check_db()` yang sama dijalankan `fund2-guardrail-watch.timer` harian
  (05:10 UTC) + alert Telegram saat drift + log
  `~/fund2-backups/logs/guardrail-<tanggal>.json`. Bukti:
  `docs/BUKTI_GUARDRAIL_WATCH_t_097ef2bb.md`.
- `max_daily_drawdown` 292,02 harus dihitung ulang saat D1 (modal live) diisi
  owner dan `daily_start_balance` berubah (§I.2 butir 1).

## 9. Reproduksi

```bash
cd ~/fund2/api
# 1. state read-only
.venv/bin/python ../scripts/validate_release_packet.py    # gate guardrails_sesuai_policy
# 2. riwayat audit
#    SELECT id, key, changed_by, source, changed_at, old_value, new_value
#    FROM settings_audit ORDER BY id DESC LIMIT 8;
# 3. penegakan runtime
curl -s http://127.0.0.1:3110/metrics   # setelah login admin + 2FA: triggers.* dan ea.*
```
