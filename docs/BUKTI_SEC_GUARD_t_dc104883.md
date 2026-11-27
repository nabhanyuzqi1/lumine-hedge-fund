# BUKTI kartu t_dc104883 — SEC-GUARD `PUT /kill-switch/triggers`

Tanggal: 26 Nov 2026. Pelaksana: hf-backend. Commit: **`0a14f7a`**
(`fix(guardrail): satu validator + password wajib + deprecated jalur Ops
trigger`). Scope: **validasi + audit saja**, perilaku risk gate tidak diubah.

## Perubahan inti kartu

| File | Perubahan |
| --- | --- |
| `api/app/guardrail_ranges.py` | `TRIGGER_RANGES` diselaraskan ke rentang kartu (anti-salah-ketik, bukan policy): daily 0.1..50, total 0.1..80, failed 1..1000, ea_offline 1..3600, halt 1..86400, check_interval 5..3600. `validate_trigger_updates` kini memvalidasi `modes` (param `allowed_modes`) dan melaporkan SEMUA field yang salah sekaligus (pesan per field). |
| `api/app/routes.py` | `PUT /kill-switch/triggers`: `deprecated=True` di OpenAPI, `logger.warning` tiap pemakaian, `password` WAJIB (422 bila kosong, 403 bila salah + audit `RISK_SETTINGS_REJECTED`), event `TRIGGERS_UPDATED` lewat helper `_record_triggers_updated`. `PUT /admin/risk-settings`: memakai validator + event helper yang sama. |
| `api/tests/test_sec_guard_triggers_validation.py` | 16 test baru (unit + API) untuk DoD a–e. |
| `api/tests/test_kill_switch.py`, `api/tests/test_llm_risk.py` | Pemanggil `PUT /kill-switch/triggers` kini mengirim `password` (kontrak baru). |
| `api/tests/test_guardrail_admin_ui.py` | `test_triggers_without_password_still_supported` → `test_triggers_without_password_rejected` (422). |

## Keputusan yang diambil

1. **Rentang = rentang kartu.** Ini penjaga salah ketik; nilai policy final
   KEPUTUSAN_OWNER §I (3 / 8 / 3 / 6 / 60) tetap di dalam rentang dan tidak
   diubah. Penggantian nilai policy tetap butuh keputusan owner.
2. **`password` wajib untuk SEMUA pemanggil endpoint deprecated ini.** Kartu
   mengizinkan pengecualian pemanggil *service token*; tidak ada EA/CLI di
   repo ini yang memanggil endpoint (`grep` seluruh `ea/`, `recorder/`,
   `scripts/`: hanya frontend legacy + docs), dan endpoint ini hanya menerima
   sesi user. Membuka jalur Bearer bridge token justru memberi token EA
   wewenang tulis guardrail = memperluas serangan, jadi tidak dibuka.
   Implikasi: klien sesi lama yang dulu 2FA-only kini wajib kirim password.
3. **`modes` ikut validator bersama** supaya kedua endpoint benar-benar
   memakai satu set aturan, bukan dua salinan.
4. **Commit membawa dependensi paralel.** Tree bersama berisi pekerjaan
   IA-MERGE (t_f412fd48) yang belum di-commit dan menjadi dependensi langsung
   (routes.py memakai `db.set_setting(actor)`; test memakai default trigger
   A12/halt; GET /llm-agent/config interval efektif). Commit `0a14f7a`
   menyertakan file backend stabil tersebut agar checkout bersih hijau;
   frontend IA-MERGE TIDAK disentuh (masih di-stage pemilik kartu).

## Bukti test

```
tests/test_sec_guard_triggers_validation.py   16 passed
  (a) out-of-range via /kill-switch/triggers -> 422 + settings tidak berubah
  (b) patch valid via kedua endpoint -> TRIGGERS_UPDATED berbentuk identik
      (details {updates, previous}, mode/strategy NULL, previous per-key)
  (c) password salah jalur Ops -> 403 + audit RISK_SETTINGS_REJECTED
  (d) tanpa password -> 422, settings tidak berubah
  (e) OpenAPI deprecated=True + log warning pemakaian

Full suite (tree bersama, 26 Nov ~05:45):  1480 passed
Full suite (checkout bersih dari commit):  1458 passed  (selisih = file test
                                              untracked milik kartu lain)
```

## Verifikasi live DB (read-only)

Dibaca dari db `fund2` (port 5433) SETELAH semua run test: nilai
`kill_switch_triggers` live masih `daily_drawdown_pct=10.0`,
`total_drawdown_pct=15.0`, `consecutive_failed_orders=100`,
`ea_offline_seconds=60.0`, `updated_at=26 Nov 02:59` — sebelum run test
saya (05:39–06:30), jadi run test tidak menyentuh live DB.

Catatan: nilai live masih di luar policy §I (3 / 8 / 3 / 6). Penyetelan
runtime adalah langkah deploy/owner (kartu t_728f89e4), bukan kartu ini;
setelah commit ini aktif, penulisan di luar rentang dari jalur mana pun
ditolak 422.

## Catatan lanjutan

- `docs/KEPUTUSAN_OWNER.md` §I.3 masih menulis `PUT /kill-switch/triggers`
  sebagai kanal resmi auto-trigger. Sinkronisasi dokumen turunan ada di scope
  IA-MERGE (t_f412fd48): kanal resmi UI = `PUT /admin/risk-settings`;
  endpoint ini deprecated + tetap tervalidasi untuk klien lama.
- `frontend/src/lib/api.js` masih menyimpan helper `setTriggers` (deprecated,
  tidak dipanggil UI). Penghapusan helper + verifikasi bundle ada di scope
  IA-MERGE.
