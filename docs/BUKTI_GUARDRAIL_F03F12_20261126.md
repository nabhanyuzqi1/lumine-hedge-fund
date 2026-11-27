# Bukti Penutupan F-03 / F-12: Angka Guardrail Final

Kartu: **t_d3ab9839** · Tanggal: 26 Nov 2026 (WIB) · Penyusun: hf-ceo
Dokumen induk: `KEPUTUSAN_OWNER.md` §I · Temuan asal: `RELEASE_PACKET_v2.2.md` F-03, F-12

> Live trading tetap **OFF** (`env=demo`, `strategy_mode_ml_gbm=paper`). Kartu ini tidak mengaktifkan order nyata, tidak melepas halt, dan tidak mengubah kredensial.

## 1. Keputusan angka

Angka final ditetapkan di `KEPUTUSAN_OWNER.md` §I. Dasarnya keputusan **tertulis** owner 21 Nov 2026 (bagian E: **SETUJU SEMUA** A1-A12). Kartu ini **tidak** menetapkan angka baru: ia mengikat runtime, dokumen, dan kode ke angka yang sudah disetujui.

Pertanyaan konfirmasi akhir dikirim ke owner lewat kantor (DeskRPG) 26 Nov 2026; owner tidak menjawab dalam jendela kerja kartu, sehingga yang berlaku adalah angka yang sudah tertulis. Bila owner memberi revisi, §I direvisi dan dokumen turunan disinkronkan ulang.

| Item | Final | Key runtime |
| --- | --- | --- |
| Volume maks/order (A3) | 0,10 lot | `max_volume` = 0.10 |
| Order/menit (A8) | 5 | `max_orders_per_min` = 5 |
| DD harian (A6) | 3% | `kill_switch_triggers.daily_drawdown_pct` = 3.0 |
| DD harian absolut (A6) | 292,02 USD (3% × 9.733,86) | `max_daily_drawdown` = 292.02 |
| DD total (A7) | 8% | `kill_switch_triggers.total_drawdown_pct` = 8.0 |
| FAILED beruntun | 3 | `kill_switch_triggers.consecutive_failed_orders` = 3 |
| EA offline: tanda offline + blokir entry (A11/A12) | 6 s | `kill_switch_triggers.ea_offline_seconds` = 6.0 |
| EA offline: `GLOBAL_HALT` (v2.1 §5.7) | 60 s | `kill_switch_triggers.ea_offline_halt_seconds` = 60.0 |
| Tick basi (A10) | 3 s | `max_tick_age_s` = 3.0 |
| SL distance (A2) | XAUUSD 0,50-15,00; BTCUSD 10,00-1.000,00 | `symbol_specs[*].sl_min_usd/sl_max_usd` |

## 2. Sinkronisasi dokumen

| Dokumen | Bagian | Perubahan |
| --- | --- | --- |
| `KEPUTUSAN_OWNER.md` | §I (baru) | Tabel angka final + key runtime, penjelasan tiga angka ambigu, kanal perubahan wajib |
| `ROLLBACK_PLAN_v2.2.md` | §1 (T7, T9, paragraf ambang) | "live: 5%" dihapus → DD harian 3%; EA offline 6 s (tanda) vs 60 s (halt); rujukan §I |
| `RELEASE_CHECKLIST_v2.2.md` | 5.9 (baru), §6 butir 6, ringkasan | Butir gate guardrail + syarat GO baru |
| `PRASYARAT_LIVE_v2.2.md` | §3 (tabel + 3.1 + 3.2) | Kolom "Final (§I)" + runtime read-only 26 Nov; G-06b, G-11, G-12, G-14 diperjelas |
| `RELEASE_PACKET_v2.2.md` | F-03, F-12 | F-12 TERTUTUP; F-03 = angka final tetap, penerapan DB terbuka |

Bukti otomatis: `scripts/check_guardrail_docs.py` → `SEMUA DOKUMEN SINKRON` (exit 0). Output JSON: `docs/VERIFIKASI_GUARDRAIL_DOKUMEN_20261126.json`.

```
$ python3 scripts/check_guardrail_docs.py
LULUS  KEPUTUSAN_OWNER.md
LULUS  ROLLBACK_PLAN_v2.2.md
LULUS  RELEASE_CHECKLIST_v2.2.md
LULUS  PRASYARAT_LIVE_v2.2.md
LULUS  RELEASE_PACKET_v2.2.md

hasil: SEMUA DOKUMEN SINKRON
```

## 3. Penegakan di kode (yang sebelumnya tidak mungkin dipatuhi)

| Temuan | Akar masalah | Perbaikan |
| --- | --- | --- |
| A10 (tick 3 s) tidak bisa ditegakkan | `risk.py` hardcoded `tick_age_s > 10` | Ambang dibaca dari `settings.max_tick_age_s` (default 3,0) |
| A12 (6 s) vs halt 60 s bertabrakan di satu key | `kill_switch.py` memakai `ea_offline_seconds` untuk menandai offline **dan** memicu `GLOBAL_HALT` | Dipisah: `ea_offline_seconds` = 6 s (tanda offline, alert, blokir entry LLM) dan `ea_offline_halt_seconds` = 60 s (halt, hanya bila ada posisi) |
| A2 belum terpetakan jelas | Tidak ada key tunggal | Sudah benar per simbol: `symbol_specs[SYMBOL].sl_min_usd/sl_max_usd` (XAUUSD 0,50/15,00, `spec_verified=true`) |
| Tidak ada kanal UI ter-audit untuk guardrail inti | Hanya CLI `set-setting` / `psql` | Endpoint baru `PUT /admin/risk-settings`: sesi 2FA + konfirmasi ulang password + `audit_log` (`CONFIG_CHANGED`, termasuk nilai lama → baru) + trigger `settings_audit` |
| Default aplikasi lebih longgar dari policy | `db.DEFAULT_SETTINGS` | `max_volume` 0.10, `max_orders_per_min` 5, `max_tick_age_s` 3.0 |
| Ambang halt tidak terlihat di monitoring | `metrics.py` | `ea.offline_halt_threshold_s` dan `triggers.ea_offline_halt_seconds` ditambahkan |

File: `api/app/risk.py`, `api/app/kill_switch.py`, `api/app/db.py`, `api/app/routes.py`, `api/app/metrics.py`, `api/tests/test_risk_settings_api.py`, `api/tests/test_risk.py`, `api/tests/test_kill_switch.py`, `scripts/validate_release_packet.py`, `scripts/check_guardrail_docs.py`.

PENTING: perubahan ini **belum di-commit** karena working tree `~/fund2` sedang berisi pekerjaan belum-commit dari kartu lain (RISK-D `t_a172bb7b`, perbaikan pool timeout `t_f837fe2c`, frontend). Commit bersih + tag adalah lingkup F-05.

## 4. Uji

| Perintah | Hasil |
| --- | --- |
| `pytest tests/test_risk.py tests/test_kill_switch.py -q` | 92 lulus |
| `pytest tests/test_risk_settings_api.py -q` | 6 lulus |
| `pytest tests/test_risk_settings_api.py tests/test_portfolio_risk.py tests/test_risk.py -q` | 101 lulus |
| `pytest -q` (penuh, 26 Nov 02:0x WIB) | 1389 lulus, 7 gagal: 6 gagal milik kartu RISK-D yang sedang in-flight (`tests/test_risk_config.py` ×5, `test_l012_downgrade_upgrade` ×1 karena migrasi m013 belum diterapkan) + 1 gagal milik kartu ini (`test_update_portfolio_risk_merges`, ketergantungan baris `portfolio_risk` parsial sisa test lain) yang sudah diperbaiki dan lulus |
| `pytest -q --ignore=tests/test_risk_config.py --deselect ...test_l012_downgrade_upgrade` (ulang setelah perbaikan) | **1357 lulus, 0 gagal**, 16 mnt 36 s (`/tmp/pytest_t_d3ab9839_run2.log`) |

Tes baru yang menutup policy:

1. `test_tick_age_3s_boundary`: usia tick tepat 3,0 s lulus, 3,01 s ditolak.
2. `test_tick_age_setting_overrides_default`: ambang dibaca dari settings, bukan hardcode.
3. `test_trigger_ea_offline_uses_halt_threshold`: offline 10 s **tidak** memicu `GLOBAL_HALT`; 61 s memicu.
4. `test_triggers_update_ea_offline_split`: `PUT /kill-switch/triggers` menerima dua ambang dan tercatat di `settings_audit`.
5. `test_update_guardrails_*`: password salah ditolak + ter-audit, tanpa 2FA ditolak, rentang kewajaran ditegakkan, audit memuat nilai lama → baru, merge `portfolio_risk` tidak menghilangkan default.

## 5. Verifikasi runtime read-only (26 Nov 2026)

`cd ~/fund2/api && .venv/bin/python ../scripts/validate_release_packet.py` → hasil terbaru: `docs/VALIDASI_PAKET_RILIS_20261126T021524Z.json` (sebelumnya `...T013353Z`). Validator **tidak** menulis DB (koneksi `read_only = True`).

| Gate | Status 01:33 | Status 02:15 | Catatan |
| --- | --- | --- | --- |
| `guardrails_sesuai_policy` | FAIL | **FAIL (sesuai harapan)** | Nilai DB belum diterapkan lewat kanal audit. Drift: `max_volume` 1.0 (final 0,10), `max_orders_per_min` 10 (5), `daily_drawdown_pct` 10.0 (3), `total_drawdown_pct` 15.0 (8), `consecutive_failed_orders` 100 (3), `ea_offline_seconds` 60.0 (6). `max_tick_age_s` **sudah** 3.0 (ter-seed saat layanan restart). `ea_offline_halt_seconds` belum ada (efektif 60 s dari default kode). `max_daily_drawdown` 100.0 vs plafon §I 292,02 → lebih ketat, dicatat |
| `live_off` | FAIL | **PASS** | Halt sempat aktif dua kali (`auto:sev_db_unavailable`: event 224 01:22, dilepas owner 01:37 (225), aktif lagi 01:44 (226), dilepas owner 02:05 (227)). Live trading sendiri tidak pernah menyala (`env=demo`, `strategy_mode_ml_gbm=paper`) |
| `schema_sync` | FAIL | **PASS** | `alembic_version` DB sekarang `m013` = head (migrasi diterapkan pemilik kartu RISK-D) |
| `layanan_inti_aktif` | FAIL | **FAIL** | `fund2-candle-rollup` inactive (unit `Type=simple` + `Restart=always`, jadi ini kegagalan, bukan unit oneshot) |
| `git_bersih_dan_tag` | FAIL | **FAIL** | Working tree berisi pekerjaan beberapa kartu; belum ada tag (F-05) |
| `paket_dokumen`, `runtime_demo_env`, `backup_segar`, `pytest_penuh_lulus`, `soak_extended_lulus` | PASS | PASS | |

Validator versi baru menambah uji **plafon A6 absolut**: `max_daily_drawdown` tidak boleh melebihi 3% × `daily_start_balance` (292,02). Sebelumnya key ini tidak diuji sama sekali, sehingga bisa dilonggarkan tanpa terdeteksi. Hasil nyata sekarang: `ceiling 292.02`, `actual 100.0` → tercatat sebagai "lebih ketat dari §I" (bukan pelanggaran, tapi gate order berhenti di ~1% sehingga perilaku berbeda dari policy; penerapan 292,02 diserahkan ke kartu DevOps).

Simulasi gate dengan nilai final: `{"drift": [], "open_items": [], "guardrails_pass": true}` — gate akan PASS segera setelah nilai diterapkan, tanpa ubah kode lagi.

Penerapan nilai DB dan penutupan F-03 dikerjakan di kartu anak **t_728f89e4** (hf-devops): restart layanan (wajib, kode baru), `PUT /admin/risk-settings` + `PUT /kill-switch/triggers` (password + 2FA + audit), verifikasi read-only, lalu gate harus PASS.

## 6. Sisa pekerjaan (bukan lingkup dokumen ini)

| Kartu | Pemilik | Isi |
| --- | --- | --- |
| `t_728f89e4` | hf-devops | Terapkan angka §I lewat UI admin, restart, verifikasi, gate `guardrails_sesuai_policy` PASS, bukti F-03 |
| `t_2d1f6d33` | hf-frontend | Halaman UI admin "Guardrail Risiko" (PRD §14 mensyaratkan UI; saat ini kanal ter-audit tersedia sebagai API) |
| `t_925637a0` | hf-devops | Investigasi halt `auto:sev_db_unavailable` (event 224), `fund2-candle-rollup` mati, status migrasi m013 |

## 7. Reproduksi

```bash
cd ~/fund2
python3 scripts/check_guardrail_docs.py          # sinkronisasi dokumen
cd api && .venv/bin/python ../scripts/validate_release_packet.py   # state runtime + gate
TELEGRAM_ALERTS_OFF=1 .venv/bin/python -m pytest tests/test_risk.py tests/test_kill_switch.py \
    tests/test_risk_settings_api.py -q           # uji policy
```
