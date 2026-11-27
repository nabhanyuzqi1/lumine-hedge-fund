# BUKTI — AgentModelPicker: model PER PERAN (t_0ff73490)

Kartu: `[FUND2-LLM-UI4] AgentModelPicker: pilih model PER PERAN (roles), bukan cuma 3 global`
Assignee: hf-frontend · 26 Nov 2026

## Ringkasan

Backend sudah punya override model per peran (`settings.llm_models.roles` →
`llm_models.resolve()` → `run_specialists(role_models=...)`), tetapi
`PUT /llm-agent/models` **membuang** field `roles` (payload dibangun ulang dari
`resolve()` yang hanya memuat specialist/synth/fallback), dan komponen
`AgentModelPicker` tidak menyebut `roles` sama sekali. Jadi sebelumnya owner
tidak bisa menyimpan maupun melihat model per specialist.

Yang dikerjakan:

1. **Backend** `api/app/llm_agent.py`: `PUT /llm-agent/models` menerima dan
   menyimpan `roles` (dict peran → model), string kosong = hapus override.
   Peran di luar `ROLE_KEYS` dan nama model tidak valid ditolak **422**.
   `GET /llm-agent/models` kini mengembalikan `roles_saved`, `role_keys`,
   `role_defaults`, dan `last_cycle` (evidence `AGENT_EVIDENCE`).
2. **Backend** `api/app/llm_models.py`: `ROLE_KEYS` + `is_valid_name()` publik.
3. **Frontend** `AgentModelPicker.jsx`: blok "Model global" (3 select + paralel)
   dan tabel "Model per specialist" 4 baris (technical, macro, sentiment,
   portfolio) dengan select katalog; opsi kosong = ikut global/bawaan sistem.
   Kolom ketiga "Efektif siklus terakhir" membaca `last_cycle` dari server
   (model + latensi yang benar-benar dipakai), bukan pilihan tersimpan.
   Nama di luar katalog ditolak di klien sebelum PUT.
4. CSS `pages.css`: tabel peran (grid 3 kolom; 1 kolom di ≤720 px).
5. Test baru `api/tests/test_llm_models_roles.py` (8 test).

## Berkas berubah

| Berkas | Perubahan |
| --- | --- |
| `api/app/llm_agent.py` | PUT menyimpan `roles`; GET + `roles_saved`/`role_defaults`/`role_keys`/`last_cycle`; validasi 422 |
| `api/app/llm_models.py` | `ROLE_KEYS`, `is_valid_name()` |
| `api/tests/test_llm_models_roles.py` | 8 test (simpan, baca ulang, hapus override, 422, evidence) |
| `frontend/src/components/AgentModelPicker.jsx` | tabel 4 peran + kolom efektif siklus terakhir + validasi katalog |
| `frontend/src/lib/api.js` | dokumentasi kontrak GET/PUT `/llm-agent/models` |
| `frontend/src/styles/pages.css` | layout `.ag-models-*` / `.ag-role-*` (desktop + mobile) |
| `docs/evidence/llm_ui4_t_0ff73490/` | 3 screenshot + respons API |

## Bukti kriteria selesai

### 1. `npm run build` sukses

```
$ cd ~/fund2/frontend && npm run build
dist/assets/index-Rv4IfO5_.css    124.49 kB │ gzip: 26.43 kB
dist/assets/index-C_j9_MBy.js   1,050.80 kB │ gzip: 284.43 kB
✓ built in 1.51s
```

`npx oxlint src/components/AgentModelPicker.jsx src/lib/api.js` → tanpa temuan.

### 2. Simpan `roles {technical: lucif-claude}` lalu GET mengembalikan roles yang sama

Live API `127.0.0.1:3110`, user admin uji ber-2FA (dibuat + dihapus dalam sesi ini):

```
PUT /llm-agent/models {"roles":{"technical":"lucif-claude"}} -> 200
  {"ok":true,"roles_saved":{"technical":"lucif-claude"},"effective":{"roles":{"technical":"lucif-claude"},...}}

GET /llm-agent/models -> 200
  roles_saved  {"technical": "lucif-claude"}      # sama
  effective.roles {"technical": "lucif-claude"}
```

Bukti tambahan jalur UI (bukan hanya API): tombol **Simpan pilihan** di
`/agent` → 403 `Perlu 2FA aktif` → kode TOTP → note
`Tersimpan. Model peran dipakai pada siklus berikutnya…`, dan
`GET /llm-agent/models` sesudahnya: `roles_saved {"technical": "lucif-claude"}`.

### 3. Evidence siklus nyata: technical = lucif-claude, peran lain = model global

Dari `GET /llm-agent/models` → `last_cycle` (order_events `AGENT_EVIDENCE`,
`decision->>'role'` + `decision->>'model'`):

| Peran | Model efektif (siklus `3327e61421a14d1f`) | Latensi |
| --- | --- | --- |
| technical | `lucif-claude` | 2.713 s |
| macro | `lucif-flash` | 2.881 s |
| sentiment | `lucif-flash` | 2.724 s |
| portfolio | `lucif-flash` | 2.575 s |

Model global `specialist = lucif-flash` → tiga peran tanpa override benar-benar
memakai model global. Siklus berjalan live selama pengujian (cycle id berubah
beberapa kali: `5f093d00…`, `8848824e…`, `3327e614…`).

Respons lengkap: `docs/evidence/llm_ui4_t_0ff73490/model_api_after_save.json`.

### 4. Peran tanpa override menampilkan "ikut global" dan tetap jalan

UI (desktop) membaca:

| Peran | Model dipilih | Efektif siklus terakhir |
| --- | --- | --- |
| Technical | `lucif-claude` | `lucif-claude 3.0 s` |
| Macro | `Ikut global: lucif-flash` | `lucif-flash 2.8 s` |
| Sentiment | `Ikut global: lucif-flash` | `lucif-flash 3.1 s` |
| Portfolio | `Ikut global: lucif-flash` | `lucif-flash 2.3 s` |

Peran yang kosong tetap jalan: evidence siklus membuktikan macro/sentiment/
portfolio dieksekusi dengan `lucif-flash` (model specialist global).

Catatan jujur: `technical` punya **bawaan sistem** `lucif-claude`
(`DEFAULT_ROLE_MODELS`, hasil benchmark 26 Nov). Karena itu label kosongnya
`Bawaan sistem: lucif-claude`, bukan "ikut global", supaya UI tidak berbohong;
mengosongkan override technical mengembalikan ke bawaan sistem, bukan ke
`lucif-flash`.

## Validasi negatif (ditolak, bukan diabaikan)

| Uji | Hasil |
| --- | --- |
| `PUT {"roles":{"technikal":"lucif-claude"}}` | 422 `peran tidak dikenal: technikal` |
| `PUT {"roles":{"macro":"nama model aneh!"}}` | 422 `model untuk peran macro tidak valid` |
| Klien: opsi model di luar katalog dipilih lalu Simpan | pesan `Model "model-palsu" untuk peran Macro tidak ada di katalog…`, tidak ada request PUT (state server tidak berubah) |
| `PUT {"roles":{"technical":""}}` | override terhapus, `roles_saved {}`, `effective.roles.technical` kembali ke bawaan sistem |

## Hasil test

```
$ cd ~/fund2/api
$ .venv/bin/python -m pytest tests/test_llm_models_roles.py \
    tests/test_llm_parallel_pipeline.py tests/test_llm_parallel_budget.py \
    tests/test_agent_role.py tests/test_guardrail_admin_ui.py -q
48 passed, 2 warnings in 32.33s
```

## Uji UI (browser, live)

| Viewport | Hasil |
| --- | --- |
| 1440x900 | 4 baris peran + kolom efektif tampil utuh, `scrollWidth == clientWidth` (tanpa overflow), `window.__errs` kosong |
| 390x844 | baris peran jadi 1 kolom; seluruh isi kartu terjangkau scroll (tombol simpan `bottom 442 px`, bottom nav mulai `788 px`), tanpa overflow horizontal |

Screenshot:

- `agent_model_picker_desktop.png`
- `agent_model_picker_mobile.png`
- `agent_model_picker_mobile_bottom.png`

## Temuan / catatan

1. **Bug kontrak backend (diperbaiki di kartu ini).** `PUT /llm-agent/models`
   sebelumnya membangun payload dari `resolve()[:, specialist/synth/fallback]`
   sehingga `roles` dari klien hilang tanpa error. Test baru
   `test_put_roles_persisted_and_read_back` mengunci perilaku ini.
2. **Isolasi test settings.** Tabel `settings` tidak ikut TRUNCATE conftest
   (`test_llm_models.roles` bocor antar test). File test baru mereset key
   `llm_models` lewat fixture autouse.
3. **Label select terpotong** (`Ikut model specialist g…`) pada percobaan
   pertama; diperbaiki dengan label ringkas `Ikut global: <model>` +
   `title` berisi kalimat penuh, kolom select dilebarkan, font select 12,5 px.
4. Kartu setinggi ±585 px di desktop; di 390x844 perlu scroll (bukan bug,
   diverifikasi seluruh kontrol terjangkau di atas bottom nav).
5. Pengujian memakai admin sementara `llm4_admin` (2FA TOTP) yang **sudah
   dihapus** beserta sesinya; `settings_audit` menyimpan jejak perubahan
   (append-only, memang bukti permanen). State akhir
   `llm_models.roles = {"technical":"lucif-claude"}` (sama dengan perilaku
   efektif sebelum perubahan, karena itu bawaan sistem).
