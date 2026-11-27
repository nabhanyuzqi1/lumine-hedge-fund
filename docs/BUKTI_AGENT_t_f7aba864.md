# BUKTI FUND2-LLM-F1 (t_f7aba864): halaman /agent + /settings

Tanggal uji: 26 Nov 2026, 06.10-06.40 WIB. Lingkungan: `~/fund2/frontend` build produksi
dilayani API di `http://127.0.0.1:3110` (DB `fund2`, data audit nyata).

## 1. Hasil build dan lint

| Perintah | Hasil |
| --- | --- |
| `npm run build` | lolos: `dist/assets/index-B6FAvHaj.js` 526.40 kB, css 122.20 kB |
| `npx oxlint src/pages/Agent.jsx src/lib/api.js` | 0 error; warning `react-hooks/set-state-in-effect` (pola sama dengan halaman existing: set state di dalam efek fetch) |

Console browser: `window.__errs` kosong di /agent dan /settings untuk semua sesi uji
(QA, admin+2FA, demo): tidak ada error maupun unhandled rejection.

## 2. /agent: feed live SSE `agent_cycle`

Uji dengan event nyata ke broadcaster lewat endpoint yang sudah ada
(`POST /llm-agent/cycle`, body `{"cycle_id":"f1a7b0c84d2e6319","phase":"started"}`,
sesi QA + header `x-csrf-token`):

- sebelum trigger: 50 baris transcript (backfill `GET /llm-agent/decisions?limit=50`);
- sesudah trigger (<1 dtk): 51 baris; baris terakhir `06.18.40 CYCLE · siklus dimulai`
  dengan `cycle f1a7b0c84d2e6319`, `fase started`, tanpa reload halaman;
- strip identitas: `SIKLUS TERAKHIR` berubah dari `belum ada` menjadi `06.18.40`;
  `Stream SSE` tetap `LIVE` dengan umur event yang dihitung ulang tiap detik.

Status stream jujur: `LIVE` saat `onopen`, `PUTUS` + tombol "Sambung ulang" bila
`EventSource` gagal (401 membuat EventSource CLOSED permanen, reconnect manual wajib),
`SUNYI <umur>` bila live tapi tidak ada event lebih dari 6 menit.

## 3. Dua cacat yang ditemukan saat verifikasi, dan perbaikannya

### 3.1 Balapan CSRF saat reload penuh

`csrfToken` di `api.js` hanya diisi `checkAuth()`/`login()`. Pada reload penuh halaman
mount sebelum `checkAuth()` selesai, sehingga `GET /llm-agent/config` dan
`GET /llm-agent/decisions` (keduanya `require_csrf`) menjawab 403. Transcript jadi kosong
dan halaman menulis "Menunggu event agent pertama" padahal fetch-nya gagal: melanggar
aturan jujur "jangan pura-pura live".

Perbaikan:
- `f1Get` (blok F1 di `api.js`): bila balasan 403, segarkan token via `real.checkAuth()`
  lalu ulangi SEKALI (403 karena role tetap 403 dan tampil sebagai FORBIDDEN, bukan loop).
- `Agent.jsx`: kegagalan backfill disimpan di `backfillErr` dan dirender sebagai
  "Backfill keputusan gagal: <sebab>" + tombol "Coba lagi", bukan empty state palsu.

Bukti: 390 px, reload penuh dengan cache dimatikan, sesi QA: 50 baris / 33 entri `INVALID`
tampil; jalur yang sama sebelum perbaikan menghasilkan 0 baris.

### 3.2 Payload order mentah menenggelamkan reasoning

34 dari 50 keputusan terakhir ber-`kind=invalid`: backend menulis
`risk gate/API rejected: {payload order JSON} | <prosa analisa>`, dan reasoning dipotong
backend sekitar 508 karakter sehingga JSON-nya berakhir di tengah string (`"created`).
Sebelum perbaikan tiap baris menampilkan ~500 karakter JSON lebih dulu, prosanya di
belakangnya.

Perbaikan (tampilan saja, tidak satu karakter pun dibuang):
- prefiks `risk gate/API rejected:` menjadi baris bendera amber;
- fakta order dibaca per field (regex, tetap benar walau JSON terpotong) dan tampil sebagai
  chip: SIDE, VOL, STATUS, SL, TP, MINTA, ISI, TICKET, GAGAL
  (`ISI`/`TICKET` = "tidak ada", `GAGAL` = "tidak dicatat");
- prosa reasoning dinaikkan ke atas payload;
- payload mentah tetap utuh di `<details>` berlabel
  "Payload order mentah (audit) · terpotong di audit".

Baris non-`invalid` (order/hold/cut/sl/be/tp/layer) tetap satu paragraf prosa apa adanya.

## 4. /agent: riwayat keputusan

- `GET /llm-agent/decisions?limit=100` merender 100 baris (dari 114 baris audit).
- Kolom: waktu, simbol, kind, confidence, token prompt/completion, latency, siklus, reasoning.
- Filter simbol berfungsi: pilih `BTCUSD` menjadi 1 baris, semuanya BTCUSD.
- Expand per baris (`aria-expanded`, bukan `tr onClick`) agar navigasi keyboard tetap benar.
- 390 px: tabel menjadi blok berlabel (`::before` = "Waktu", "Simbol", ...), `thead`
  disembunyikan, tanpa overflow horizontal.

## 5. /agent: tab introspeksi

- Scope `Per trade`: 31 baris nyata dari `llm_introspections`, narasi + evidence ringkas
  (symbol, side, outcome, profit, entry/close, sl, tp, mfe, mae, holding, order_status).
- Scope `Harian`: kosong dengan pesan jujur bahwa engine belum menulis rekap harian.
- Tombol "Minta introspeksi" HANYA untuk `role=admin` + `totp_enabled` + `2fa_valid`:
  - sesi QA (`role=qa`): tombol TIDAK ADA di DOM (dicek lewat `querySelectorAll('button')`),
    yang tampil hanya catatan bahwa aksi ini milik admin + 2FA;
  - sesi admin setelah `POST /auth/2fa/challenge` (200): tombol tampil.
- Jalur gagal diuji nyata: `POST /llm-agent/introspect` menjawab 503 karena proses API tidak
  memuat kredensial LLM. UI memetakannya menjadi kalimat jujur, bukan error telanjang, dan
  tombol kembali aktif.

### Temuan (bukan regresi frontend)

`api/.env` tidak memuat `LLM_BASE_URL`/`LLM_API_KEY`; kredensial LLM ada di `api/.env.llm`
yang hanya dimuat `fund2-llm-agent.service`. Akibatnya `POST /llm-agent/introspect` selalu
503 pada proses API dan tombol on-demand belum bisa sukses di host ini. Perbaikan = menambah
`EnvironmentFile=/home/tekka/fund2/api/.env.llm` pada `fund2-api.service` (keputusan
kredensial, perlu persetujuan owner).

## 6. /settings (READ-only)

- 4 kartu: Identitas & status, Batas llm_risk efektif, Calendar blackout, System prompt.
- `document.querySelectorAll('.settings-page input, textarea, select, form').length === 0`
  di 1280 dan 390: tidak ada satu pun kontrol tulis.
- Kill-switch hanya status; catatan kaki menyebut kontrol ada di `/ops` (tidak diduplikasi).
- Kunci agent v2 (`block_new_order_with_position`, `max_layers`, `layer_volume_ratio_max`,
  `modify_sl_only_tighten`) ditampilkan "tidak dilaporkan API", bukan angka karangan,
  karena `get_llm_agent_config` tidak mengirimkannya.
- System prompt: 4.671 karakter, `<pre>` mono `white-space: pre-wrap`, `overflow-y: auto`,
  `max-height: 380px`, `scrollHeight 1423 > clientHeight 380` (scroll sendiri, bukan halaman).
- Pemeriksaan kebocoran: teks halaman tidak memuat `LLM_API_KEY`, `Bearer`, `password`,
  `secret`; satu-satunya kecocokan pola `sk-` adalah kata "risk-sentiment" di system prompt,
  bukan kredensial.

## 7. Tata letak, kontras, dan mode demo

Diukur di browser (viewport CSS 1280x900 dan 390x844, `deviceScaleFactor=1`):

| Ukuran | /agent | /settings |
| --- | --- | --- |
| `scrollWidth > innerWidth` | tidak (390/390, 1274/1280) | tidak |
| baris melebar keluar panel | 0 dari 50 | n/a |
| strip identitas | 6 sel tanpa teks terpotong | n/a |
| grid kartu | n/a | 2 kolom (1280), 1 kolom (390) |
| bottomnav | 7 label; terlebar "Guardrail" 46 px di kolom 56 px, tidak terpotong | idem |

Kontras terhadap panel: body 17.57:1, muted 6.00:1, faint 5.53:1, tag down 5.09:1,
tag hold 6.00:1 (semua >= 4.5:1). Palet hanya token monochrome glass (`--line`, `--text`,
`--text-muted`, `--up`, `--down`, `--warn`); tidak ada `#d9a648` / `#11100e` / `--gold`
di berkas F1.

Mode demo `?demo=1` (login simulator, lalu `/agent`): 3 baris contoh semuanya bertanda
`[DEMO]`, `PROMPT VERSION DEMO-0.0.1`, `MODEL demo-model`, `Stream SSE DEMO`, chip `DEMO`
di header. `/settings?demo=1` tetap READ-only. Tidak ada data live yang dikarang.

## 8. Berkas yang berubah

| Berkas | Sifat |
| --- | --- |
| `frontend/src/pages/Agent.jsx` | BARU, 1.036 baris |
| `frontend/src/pages/Settings.jsx` | BARU, 329 baris |
| `frontend/src/App.jsx` | import + 2 entri NAV + 2 route + ikon nav (`short:'Lab'` untuk bottomnav 390 px) |
| `frontend/src/lib/api.js` | APPEND blok helper F1 (tidak ada fungsi lama diubah) |
| `frontend/src/styles/pages.css` | APPEND blok F1 |

Commit `53649b9` ("label strip Stream SSE + penutup F1", menyebut t_2a751a6c/F1). Badan F1
(Agent.jsx, Settings.jsx, App.jsx, api.js, pages.css) sudah masuk HEAD lewat `2dedf64`,
commit milik kartu lain yang menyapu index saat kartu ini berjalan; tidak ada perubahan F1
lain yang tertinggal di worktree. `git add` per berkas, tidak pernah `git add -A`.

## 9. Screenshot (`docs/evidence/agent_t_f7aba864/`)

- `agent-1280.png` transcript live + strip identitas (1280x900)
- `agent-390.png` transcript 390x844, entri INVALID dengan chip + prosa
- `agent-riwayat-1280.png`, `agent-riwayat-390.png` tabel riwayat keputusan
- `agent-introspeksi-1280.png` tab introspeksi sesi QA (tombol tersembunyi)
- `agent-introspeksi-admin-1280.png` sesi admin + 2FA (tombol tampil)
- `agent-demo-1280.png` mode demo (baris berlabel DEMO)
- `settings-1280.png`, `settings-1280-full.png` (seluruh tinggi halaman), `settings-1280-prompt.png`
- `settings-390.png`, `settings-demo-1280.png`
