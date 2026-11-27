# Bukti: Halaman admin Guardrail Risiko (kartu t_2d1f6d33)

| | |
| --- | --- |
| Kartu | `t_2d1f6d33` — [FUND2-v2.2] Halaman admin Guardrail Risiko (UI password + 2FA + audit) |
| Pelaksana | hf-frontend |
| Tanggal uji | 26 Nov 2026, 02.50–03.10 WIB |
| Lingkungan | host dev `tekka` (bukan produksi): PostgreSQL lokal `127.0.0.1:5433/fund2`, API `uvicorn app.main:app` port 8000, SPA = `frontend/dist` hasil `npm run build` |
| PRD | §14 (kanal perubahan guardrail), §18 (audit), `KEPUTUSAN_OWNER.md` §I |
| Deploy | **tidak ada** — hanya build + uji lokal |

## 1. Yang dibangun

Halaman `/admin/guardrail` (nav **Guardrail**, hanya role `admin`) di
`frontend/src/pages/AdminGuardrails.jsx` + `frontend/src/styles/guardrail.css`,
memakai dua endpoint baca baru dan dua endpoint tulis yang sudah ada:

| Kebutuhan | Endpoint | Sifat |
| --- | --- | --- |
| Nilai guardrail inti AKTIF + rentang + `defaults` | `GET /admin/risk-settings` | read-only (`require_admin`) |
| Riwayat perubahan | `GET /admin/settings-audit?limit=` | read-only, cap 200, whitelist key guardrail |
| Simpan guardrail inti | `PUT /admin/risk-settings` | `require_2fa` + `password` di body |
| Simpan auto-trigger | `PUT /kill-switch/triggers` | `require_2fa` + `password` di body (`password` opsional untuk kompatibilitas klien lama: tanpa password tetap 2FA-only seperti sebelumnya, jalur UI selalu mengirimnya) |

Isi halaman:

1. **Peringatan** nilai final ada di `KEPUTUSAN_OWNER.md` §I, plus penegasan
   `ea_offline_seconds` (6 s, tanda offline) ≠ `ea_offline_halt_seconds`
   (60 s, `GLOBAL_HALT`, hanya bila ada posisi).
2. **Kartu "Nilai aktif vs angka final §I"**: mendeteksi drift runtime vs §I
   dan menampilkannya sebagai tabel `Guardrail | Aktif | Final §I | Arah
   selisih` (mis. `lebih longgar (10,0×)`), plus chip `≠ §I` di tiap baris
   form yang menyimpang. Halaman tidak menyamakan angka sendiri.
3. **Guardrail inti**: `max_volume`, `max_orders_per_min`,
   `max_daily_drawdown`, `max_spread`, `max_tick_age_s`.
4. **Auto-trigger**: `daily_drawdown_pct`, `total_drawdown_pct`,
   `consecutive_failed_orders`, `ea_offline_seconds`,
   `ea_offline_halt_seconds`; aksi tiap trigger (GLOBAL_HALT /
   STOP_NEW_ORDERS) ditampilkan sebagai chip tetap, tidak bisa diubah di sini.
5. **Dialog konfirmasi**: tabel lama → baru + konsekuensi + checkbox
   pengakuan, lalu langkah 2FA (TOTP) + input **password akun** yang dikirim
   di body. Tag `≠ §I` per baris yang menyimpang.
6. **Hasil audit terakhir** + **Riwayat perubahan (`settings_audit`)**:
   Waktu · Key · Lama · Baru · Oleh · Sumber.
7. Mode `admin` bukan admin → kartu "Halaman ini hanya untuk admin" (tanpa
   form); mode DEMO → halaman menjelaskan bahwa perubahan hanya tersedia di
   mode real.

Tidak ada jalan pintas: password dan 2FA diverifikasi server pada setiap
simpan; nilai default (`db.DEFAULT_SETTINGS`) tidak diubah oleh endpoint baca
maupun oleh halaman ini.

## 2. Berkas yang berubah (kartu ini)

```
frontend/src/pages/AdminGuardrails.jsx   (baru)
frontend/src/styles/guardrail.css        (baru)
frontend/src/lib/api.js                  fetchGuardrailSettings, fetchSettingsAudit, updateRiskSettings
frontend/src/App.jsx                     route /admin/guardrail + nav "Guardrail"
frontend/src/components/ConfirmDialog.jsx  dukung requires2fa + password (kartu ini memakainya)
api/app/routes.py                        GET /admin/risk-settings, GET /admin/settings-audit, password pada PUT /kill-switch/triggers
api/tests/test_guardrail_admin_ui.py     (baru) 8 test endpoint baca + password trigger
api/tests/test_risk_settings_api.py      (baru) 7 test tulis guardrail
docs/RUNBOOK_v2.2.md §6.1                cara pakai + tabel kegagalan wajar
docs/BUKTI_GUARDRAIL_UI_t2d1f6d33.md      dokumen ini
docs/evidence/guardrail_ui_t2d1f6d33/     screenshot
```

## 3. Uji otomatis

| Perintah | Hasil |
| --- | --- |
| `api/.venv/bin/python -m pytest tests/test_guardrail_admin_ui.py tests/test_risk_settings_api.py -q` | **15 passed**, 1 warning (DeprecationWarning alembic), 24,96 s |
| `api/.venv/bin/python -m pytest tests/test_kill_switch.py -q` | **47 passed**, 38,79 s (endpoint trigger tetap utuh setelah penambahan `password`) |
| `cd frontend && npm run build` | ✓ built, `dist/assets/index-d45H-qOr.js` 453,62 kB (gzip 132,26 kB) |
| `cd frontend && npx oxlint src` | 0 error; `AdminGuardrails.jsx` tanpa warning (warning yang tampil berasal dari komponen lain yang sudah ada) |

Cakupan test yang relevan dengan klaim keamanan halaman ini:

- `GET /admin/risk-settings` mengembalikan nilai AKTIF dari tabel `settings`
  (bukan default kode) + rentang validasi; tanpa sesi 401, role `user` 403.
- `GET /admin/settings-audit` membaca baris `settings_audit` dengan
  `changed_by` = username admin (bukan role koneksi DB), limit dibatasi.
- `PUT /admin/risk-settings` tanpa `password` → 422; password salah → 403 dan
  tidak ada nilai yang berubah; sukses → `settings_audit` mencatat lama → baru.
- `PUT /kill-switch/triggers` dengan password salah → 403
  (`detail: "password salah"`), nilai tidak berubah, penolakan tercatat di
  `audit_log` sebagai `RISK_SETTINGS_REJECTED`; dengan password benar →
  tersimpan + `settings_audit` mencatat `kill_switch_triggers`; `A12`
  (`ea_offline_seconds` = 6) tidak ikut berubah.
- `password` benar tanpa step-up 2FA tetap ditolak 401/403.

## 4. Uji manual di browser (nyata, bukan simulasi)

Sesi: akun admin QA `qa_guardrail` (role admin, TOTP terdaftar) dibuat lewat
API resmi `/auth/2fa/setup` + `/auth/2fa/enable` khusus untuk uji ini, lalu
dihapus setelah uji. Semua nilai yang diubah adalah **nilai uji** dan sudah
dikembalikan ke nilai semula; jejaknya tetap ada di `settings_audit`.

| # | Langkah | Hasil | Bukti |
| --- | --- | --- | --- |
| 1 | Login admin, buka `/admin/guardrail` | Halaman memuat 10 baris guardrail, 25 baris riwayat audit, badge `2FA terdaftar · perlu step-up` | `shot_01_guardrail_desktop_full.png` |
| 2 | Isi `max_tick_age_s` = 3,5 → tombol berubah "Simpan 1 perubahan" → klik | Dialog "Simpan guardrail inti" menampilkan `Usia tick maksimum 3,0 detik → 3,5 detik` + 3 konsekuensi | `shot_02_dialog_konfirmasi.png` |
| 3 | Langkah 2FA: kode TOTP + password **salah** | Ditolak: pesan `password salah` di dialog, dialog tetap terbuka, nilai aktif tetap **3,0 detik** | `shot_03_tolak_password_salah.png` |
| 4 | Jendela TOTP berikutnya + password benar → "Simpan & audit" | Toast "Guardrail inti tersimpan"; kartu "Hasil audit terakhir": `3,0 detik → 3,5 detik`, oleh `qa_guardrail`; badge 2FA jadi `2FA AKTIF` | `shot_04_simpan_sukses.png` |
| 5 | Kembalikan lewat UI: `max_tick_age_s` 3,5 → 3,0 | Tersimpan, riwayat audit bertambah baris `3,5 → 3,0` oleh `qa_guardrail` | `shot_01` (kolom riwayat) |
| 6 | Auto-trigger: `ea_offline_halt_seconds` 60 → 45 | Tersimpan; audit `Auto-trigger kill-switch: EA offline: belum di-set (bawaan kode) → EA offline: 45,0 detik` | `shot_06_trigger_tersimpan.png` |
| 7 | Kembalikan: 45 → 60 | Tersimpan; audit `EA offline: 45,0 detik → EA offline: 60,0 detik`; `ea_offline_seconds` (A12) tetap 60,0 | `shot_06_trigger_tersimpan.png` |
| 8 | Nilai DB setelah uji | `max_tick_age_s` = 3,0 dan `ea_offline_halt_seconds` = 60,0 → **kembali ke nilai awal**, tidak ada default yang berubah | query `settings` (lihat §6): `max_tick_age_s 3.0`, `ea_offline_halt_seconds 60.0` |
| 9 | Layout desktop 1440×900 & mobile 390×844 | Tidak ada overflow horizontal (`scrollWidth` = lebar viewport), tidak ada elemen bertumpuk; kartu terakhir berhenti 20 px di atas nav bawah (`main` punya `padding-bottom: 76px`). Tabel drift di mobile menggeser horizontal di dalam `.table-wrap` (324 px tampak, 771 px isi), pola yang sama dengan tabel lain | `shot_01`, `shot_05_mobile_full.png` |

Baris `settings_audit` yang dihasilkan (append-only, terverifikasi lewat
query DB dan lewat halaman):

```
341  kill_switch_triggers  qa_guardrail  ea_offline_halt_seconds: (belum di-set) -> 45.0
342  kill_switch_triggers  qa_guardrail  ea_offline_halt_seconds: 45.0 -> 60.0
339  max_tick_age_s        qa_guardrail  3.0 -> 3.5
340  max_tick_age_s        qa_guardrail  3.5 -> 3.0
```

## 5. Temuan selama uji

1. **Drift runtime vs §I pada DB dev (bukan bug halaman).** Nilai aktif di DB
   dev berbeda dari `KEPUTUSAN_OWNER.md` §I pada 6 field: `max_volume` 1,00 vs
   0,10; `max_orders_per_min` 10 vs 5; `daily_drawdown_pct` 10,0 vs 3,0;
   `total_drawdown_pct` 15,0 vs 8,0; `consecutive_failed_orders` 100 vs 3;
   `ea_offline_seconds` 60,0 vs 6,0. Sesuai batasan kartu, nilai **tidak**
   diubah; sebagai gantinya halaman menandainya (kartu "Nilai aktif vs angka
   final §I" + chip `≠ §I` per baris) supaya selisih ini tidak lolos ke live
   tanpa keputusan owner. Perlu kartu lanjutan untuk menyamakan staging/demo
   ke §I lewat UI ini (bukan bagian kartu ini).
2. **Label audit untuk key yang belum pernah ada di `settings`.** Simpan
   pertama `ea_offline_halt_seconds` membuat `old_value` tanpa key tersebut
   (nilai efektif sebelumnya berasal dari bawaan kode), sehingga sisi "Lama"
   terbaca "tanpa perubahan angka guardrail". Diperbaiki: kini tampil
   `belum di-set (bawaan kode)`.
3. **Sesi uji.** Cookie sesi bersifat session-cookie; setiap kali browser uji
   di-restart, halaman mengembalikan ke login. Tidak ada masalah di aplikasi
   (perilaku normal), hanya dicatat agar penguji berikutnya tidak bingung.
4. **Cascade chip (temuan lintas komponen, tidak diubah global).**
   `pages.css` memuat aturan `.chip` SETELAH `global.css`, sehingga varian
   `.chip-gold` / `.chip-up` kalah cascade di bundle dan tampil netral di
   seluruh aplikasi. Untuk kartu ini warna peringatan diatur ulang secara
   lokal di `guardrail.css` (`.gr-drift-card .card-head .chip`); komponen
   lain sengaja tidak disentuh. Perbaikan menyeluruh perlu kartu terpisah
   (pindahkan varian chip ke satu berkas setelah `pages.css`).

## 6. Reproduksi

```bash
# API + SPA (dist) di host dev
cd ~/fund2/api && set -a && . ./.env && set +a && TELEGRAM_ALERTS_OFF=1 \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd ~/fund2/frontend && npm run build     # SPA disajikan API di /admin/guardrail
cd ~/fund2/api && .venv/bin/python -m pytest tests/test_guardrail_admin_ui.py \
  tests/test_risk_settings_api.py tests/test_kill_switch.py -q

# verifikasi nilai kembali ke semula
cd ~/fund2/api && .venv/bin/python -c "
import psycopg,pathlib
env=dict(l.split('=',1) for l in pathlib.Path('.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
c=psycopg.connect(env['DATABASE_URL']);cur=c.cursor()
cur.execute(\"select key,value from settings where key in ('max_tick_age_s','kill_switch_triggers')\")
print(cur.fetchall())"
```

## 7. Sisa pekerjaan (di luar kartu ini)

- Menyamakan nilai guardrail staging/demo ke §I (temuan §5.1) lewat halaman
  ini atau endpoint resmi, lalu memperbarui dokumen turunan §I.3.
