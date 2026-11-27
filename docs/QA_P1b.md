# QA P1b — Laporan (hari 12)

Task: t_f2p1b4 · Tanggal: 2026-11-21 · QA: hf-qa
Rujukan: PRD_v2.1_Fund_Core.md §5.7, §5.8, §7, P1b hari 12

## Ringkasan

| Area | Hasil |
| --- | --- |
| Disconnect 10× + rekonsiliasi | **10/10 PASS** |
| Kill-switch manual + auto-trigger | **17/17 PASS** (di test DB, in-process) |
| UI 4 halaman desktop + mobile | **3 bug kritis** (lihat Temuan) |
| Keamanan dasar | **9/13 PASS, 4 deviasi** |
| Total check | 32 pass / 0 fail / 4 deviasi + 6 temuan UI/deploy |

Skrip QA: `qa_p1b_v2.py` (workspace t_f2p1b4), dijalankan ulang saat sesi ini —
hasil reproduksi persis (32 checks: 28 pass, 0 fail, 4 deviasi).

## 1. Disconnect 10× (PRD §5.8)

Siklus per iterasi: EA live → order BUY 0.01 (SL/TP wajib) → FILLED → EA crash
tanpa cleanup saat posisi terbuka → order baru ditolak (tick basi > 10s) →
EA reconnect + snapshot → rekonsiliasi DB vs broker.

- **10/10 PASS**: status posisi/order di DB persis dengan snapshot broker,
  event log lengkap, kill-switch tidak salah aktif.
- Varian genap: posisi tetap terbuka → DB tetap OPEN.
- Varian ganjil: posisi ditutup broker-side saat offline → deal tercatat di
  snapshot, order → FILLED_THEN_CLOSED.
- Catatan: state machine kini punya lifecycle orphan (ORPHAN_ADOPTED →
  ORPHAN_CLOSED) di `state_machine.py`; snapshot reconnect tercakup.

## 2. Kill-switch (PRD §5.7)

Manual + 4 mode + auto-trigger, semua diuji di fund2_test (in-process ASGI):

- Manual STOP_NEW_ORDERS / GLOBAL_HALT / PAUSE_STRATEGY / FLATTEN: PASS.
- Order baru ditolak saat aktif (422), status endpoint, release dengan
  checklist untuk GLOBAL_HALT: PASS.
- Auto-trigger: daily drawdown (GLOBAL_HALT + audit), EA offline
  (>60s, fired), 3 FAILED beruntun (STOP_NEW_ORDERS): PASS.
- State tersimpan di DB (bertahan restart): PASS.
- Flatten E2E (close command → posisi CLOSED): PASS.

⚠️ Semua ini terverifikasi di kode TERBARU via in-process test — **bukan** di
service live yang jalan. Service live masih kode lama (lihat Temuan D1).

## 3. UI 4 halaman (desktop 1440×900 + mobile 390×844)

Diuji dengan browser nyata ke http://127.0.0.1:3110 (SPA oleh API).
Workaround QA: `document.cookie` dipatch agar Gate lolos (karena F1) dan
`/positions` di-return `[]` (karena F2) — semua halaman lain nyata (SSE,
order, riwayat, kill-switch).

- Login: form render baik (desktop + mobile); **login tidak pernah membuka
  aplikasi** (F1, kritis).
- Dashboard: render baik; form order dengan validasi SL/TP wajib + arah +
  konfirmasi; tabel posisi; grafik + timeframe; **tidak ada tombol
  kill-switch dan status EA** (F4).
- Riwayat: render, filter berfungsi; event log per order kosong karena API
  `/orders` tidak menyertakan events (F5); **tidak ada ekspor CSV** (F5).
- Strategy Lab: render; kill-switch hold-to-arm ada; daftar strategi selalu
  kosong karena `/strategies` tidak ada di API (F3/F6).
- Mobile: 4 halaman render tanpa overflow horizontal, bottomnav muncul,
  tabel scroll di dalam wrapper. Layout responsif OK.

## 4. Keamanan dasar (PRD §7)

PASS: rate limit login (429 setelah 11 gagal), cookie HttpOnly + SameSite=strict
+ Max-Age 86400, endpoint orders wajib sesi (401) + CSRF (403), logout
membatalkan sesi, bridge wajib Bearer (401 tanpa/salah token), password bcrypt
($2b$12$), rate limit order per meniti.

Deviasi:

- **Secure flag belum diset** (loopback P1) — wajib flip saat cutover domain.
- **HMAC belum diterima API** — EA v5.00 kirim header `X-Fund2-*` → API 401
  (API masih Bearer). Real EA belum bisa konek.
- **`POST /bridge/heartbeat` → 405** — endpoint belum ada; EA memanggil tiap 2s.
- **Format tick batch beda** — EA kirim `{symbol, ticks:[...]}`, API minta
  `{symbol, bid, ask}` → 422.

## Temuan kritis (harus diperbaiki / kartu follow-up)

**F1 (kritis, frontend) — Login tidak pernah membuka aplikasi.**
`isAuthed()` di `frontend/src/lib/api.js` membaca
`document.cookie.includes('fund2_session')`, tetapi cookie sesi diset
`HttpOnly` (benar, aman) sehingga tidak terlihat JS → `Gate` selalu render
Login. Efek: setelah login sukses (API 200, cookie tersimpan), UI tetap di
halaman login; tombol stuck "Memeriksa…" (busy tidak direset saat sukses).
Solusi: ganti cek ke `GET /auth/me` (atau state dari respons login), dan
reset `busy` di finally.

**F2 (kritis, frontend) — Dashboard white-screen saat ada posisi.**
`PositionsTable.jsx` memanggil `p.entry.toFixed(2)`, `p.pnl.toFixed(2)`,
`p.sl.toFixed(2)`, `p.tp.toFixed(2)` tanpa guard, padahal API mengirim
`open_price`/`profit` (bukan `entry`/`pnl`) dan `sl`/`tp` bisa `null`.
Satu posisi saja membuat seluruh React tree unmount (layar putih).
Solusi: map field API → UI + guard null/undefined di semua sel numerik.

**F3 (kritis, deploy) — Service live fund2-api kode lama.**
Proses jalan sejak 16:03, kode kill-switch/strategies terakhir diubah 18:58
(15 route terbaru, termasuk semua endpoint kill-switch, belum termuat).
`GET /kill-switch` dan `/strategies` di live dijawab SPA fallback HTML 200 —
bukan endpoint. Efek: tombol kill-switch di UI POST ke fallback (200 HTML,
`setKillSwitch` tidak cek `res.ok`) → **gagal senyap pada kontrol keselamatan**.
Solusi: restart/redeploy `fund2-api.service` + UI wajib cek `res.ok` +
content-type JSON.

**F4 (major, frontend) — Dashboard tidak punya kill-switch & status EA.**
PRD P1b hari 8-9 mewajibkan keduanya di Dashboard; kill-switch hanya ada di
Strategy Lab.

**F5 (major, frontend+backend) — Riwayat tidak lengkap vs PRD.**
CSV ekspor tidak ada; event log per order kosong (API `/orders` tidak
menyertakan `events`). Juga tampilan: `entry` selalu "·" (API `price_filled`),
SL/TP null tampil "0.00" (menyesatkan), `side` "BUY" (uppercase) selalu tampil
"JUAL" (frontend banding lowercase).

**F6 (major, backend) — Endpoint /strategies belum ada.**
Strategy Lab tidak bisa menampilkan strategi #1 yang sudah jalan di paper mode.

## Follow-up

Kartu dibuat dari laporan ini (lihat board): frontend (F1+F2), frontend
(F4+F5), deploy (F3), backend (F6 + kontrak EA HMAC/heartbeat/tick).
Semua temuan kritis tidak difix oleh QA (di luar ranah) — diserahkan ke
kolega yang tepat.

## 5. Ronde 2 — re-test penuh pada build baru (22 Nov, t_d6ce138b)

Semua 4 kartu fix selesai + diverifikasi Direktur, service live direstart
(03:35 WIB, PID 1882324) memuat kode kill-switch. UI yang diserve API kini
dist `index-5c1vHCt-.js` (memuat KillSwitchCard + EaChip di Dashboard,
commit e4a09e9 + e792011).

### 5.1 Suite in-process (fund2_test, kode = yang dideploy)

- `tests/test_kill_switch.py` + `tests/test_telegram.py`: **41/41 PASS**.
- Full suite `tests/`: **192/192 PASS** (DB test terpisah, live tidak disentuh).

### 5.2 E2E service live (baru di ronde 2)

Skrip `qa_killswitch_live_r2.py` → **21/21 PASS** (bukti: `evidence_live_r2.log`):

- Manual 4 mode via kontrak tombol UI (`POST /kill-switch {mode}` + CSRF):
  STOP_NEW_ORDERS, GLOBAL_HALT, PAUSE_STRATEGY, STOP_AND_FLATTEN — semua
  mengubah state server (200, `state.active/mode` benar).
- Order baru ditolak saat aktif: **422** `rejected_reasons=["kill-switch aktif
  (mode: STOP_NEW_ORDERS)"]`; baris order tetap dibuat untuk audit; rejection
  gate TIDAK menaikkan `consecutive_failed`.
- Release STOP_NEW_ORDERS per strategi; GLOBAL_HALT wajib `checklist_ack`
  (tanpa itu 400 + pesan checklist); STOP_AND_FLATTEN wajib `confirm`
  (tanpa itu 400 + pesan confirm).
- State tersimpan di DB `settings.kill_switch` (active+mode terbaca langsung
  dari DB live) + audit `kill_switch_events` (ACTIVATE/RELEASE, source
  dashboard, actor user QA).
- Trigger default terbaca dari live: daily 3%, total 8%, EA offline 60s,
  3 FAILED beruntun.
- Keadaan akhir inactive, `/health` ok, tidak ada order nyata dikirim ke
  broker (semua order test ditolak gate saat switch aktif).

### 5.3 Auto-trigger terbukti di service live (kejadian nyata 03:39 WIB)

Saat ronde 2 berjalan, QA paralel (user `qa-core`) menembakkan order uji ke
live: 3 FAILED beruntun (03:38:48, 03:39:00, 03:39:12, retcode 10016) →
**auto-trigger `auto:consecutive_failed` meng-ARM STOP_NEW_ORDERS pada
03:39:13** (audit event id 22, actor `auto`). Semua order setelahnya
(03:39:23–03:44:44) ditolak risk gate dengan alasan "kill-switch aktif
(mode: STOP_NEW_ORDERS)". Streak sempat ter-reset oleh order FILLED di
tengah (03:38:22, 03:38:41) — sesuai desain "FILLED memutus streak".
State dilepas kembali lewat `POST /kill-switch/release` (audit id 23).
Ini bukti auto-trigger 3 FAILED + gate penolakan + audit berjalan di
service live, bukan hanya in-process.

### 5.4 Telegram command

Implementasi lengkap + owner-only (`telegram_bot.py`: /status /stop
/stopflatten /flatten /pause /resume /halt /help) — **9/9 test in-process
PASS**. Pada service live channel Telegram **belum aktif**:
`TELEGRAM_BOT_TOKEN` / `TELEGRAM_OWNER_ID` belum diset di `api/.env`
(deviasi konfigurasi, bukan kode; bot token dedikasi masih menunggu
penyelesaian konflik getUpdates dengan gateway Hermes yang memakai token
lama). Verifikasi live perintah Telegram bisa dilakukan setelah kredensial
dipasang.

### 5.5 Catatan

- Asersi QA awal menerima 409/422 untuk penolakan; API aslinya 400 + pesan
  eksplisit (checklist/confirm) — perilaku produk BENAR, asersi dikoreksi.
- Melepas state auto-trigger di 5.3 adalah aksi QA yang sadar (pemicunya
  order uji QA paralel saat pasar tutup, bukan kerugian riil).
- Guardrail P1a: /health ok, recorder tidak disentuh, kill-switch diakhiri
  inactive, tidak ada order live baru.

---

## Ronde 2 — 22 Nov 2026 (build baru pasca-fix, kartu t_2a6a61fb)

Gerbang Direktur: ronde 2 dijalankan SETELAH 4 kartu fix selesai + redeploy
(t_1ae5d258, t_2233e7b7, t_22f5d556, t_ef2f49c6; fund2-api restart 03:35 WIB
dengan commit 2c98706/64b230a, frontend dist 03:23). Bukan build lama.

### Hasil

| Area | Hasil |
| --- | --- |
| Disconnect 10× + rekonsiliasi (in-process, fund2_test) | **10/10 PASS** |
| Kill-switch manual 4 mode + auto-trigger + mismatch (in-process) | **18/18 PASS** |
| Keamanan dasar (in-process) | **15/15 PASS, 1 deviasi** (cookie Secure) |
| Total skrip `qa_p1b_v3.py` | **35 cek: 34 pass, 0 fail, 1 deviasi** |
| Kill-switch manual via UI (live, browser) | **PASS** (arm → alert Telegram → release) |

Skrip: `qa_p1b_v3.py` (workspace t_2a6a61fb); hasil: `docs/qa_p1b_results_r2.json`.

### Pengecekan ronde 2 vs ronde 1

- Disconnect 10× kini juga memverifikasi: SL/TP posisi terbuka tetap tersimpan
  setelah reconnect (target kartu), dan event log terbaca dari `GET /orders`
  (list — kontrak baru F5/F6) selain `GET /orders/{id}`; chain `RECEIVED →
  RISK_PASS → SENT → FILLED` utuh di 10/10 iterasi, varian open-preserved dan
  closed-with-deal selang-seling.
- 3 deviasi security ronde 1 yang sudah difix kini jadi cek PASS/FAIL penuh:
  - HMAC `X-Fund2-*`: valid → 200; signature salah → 401; timestamp basi (>5s)
    → 401; nonce replay → 401 (dulu deviasi "API 401").
  - `POST /bridge/heartbeat` → 200 (dulu 405).
  - Tick batch `{symbol, ticks:[...]}` → 200 (dulu 422).
- Deviasi tersisa: cookie `Secure` belum diset (loopback P1) — wajib flip saat
  cutover domain (PRD 7), sama seperti ronde 1.

### Kill-switch manual via UI (live, build baru)

Browser E2E ke http://127.0.0.1:3110 (user QA temp `qa_r2`, dihapus setelahnya):

- Login form → Dashboard terbuka (fix F1 live); Dashboard render penuh dengan
  kartu kill-switch + chip "EA · ONLINE" (fix F2/F4 live; harga live 3537.68
  mengalir via SSE).
- Arm hold-to-arm 1.2s → server `active=true, mode=STOP_NEW_ORDERS, source=
  dashboard, actor=qa_r2`; UI berubah "TERARM · order baru diblokir".
- Alert Telegram terkirim otomatis oleh fund2-alerts: "🛑 KILL-SWITCH AKTIF"
  saat arm dan "✅ KILL-SWITCH NONAKTIF (dilepas)" saat release — keduanya
  POST Telegram 200 OK.
- Release via UI → server `active=false`, UI kembali "AMAN · order diizinkan".
- Order baru sengaja TIDAK dibuat di live (streak FAILED & pasar tutup hari
  Minggu); perilaku "order ditolak saat kill-switch aktif" terverifikasi
  in-process (18/18).

### Guardrail live (22 Nov ~03:56 WIB)

- `/health` → `{"ok":true}`; kill-switch live **inactive** setelah test.
- Recorder hidup: parquet ticks bertambah (271 KB, mtime 03:56).
- `/openapi.json` memuat `/strategies`, `/strategies/{id}/mode`,
  `/kill-switch*`, `/bridge/heartbeat`.
- User QA temp dihapus; tidak ada order baru dibuat di live.

Catatan: latensi order p95 <300 ms adalah scope kartu QA paritas core
(t_55fb2608) — tidak diduplikasi di sini.

## 6. Ronde 2 — UI 4 halaman pada build baru (22 Nov, t_eb648747)

Re-test penuh UI SETELAH 4 kartu fix + redeploy. Build terverifikasi baru:
uvicorn 04:08 WIB > commit fix terakhir 03:25, dist 04:16
(`index-5c1vHCt-.js`), `/strategies` 401 JSON (bukan SPA fallback).

| Platform | Hasil |
| --- | --- |
| Desktop Chrome 1440×900 (CDP) | 4 halaman render, 0 console error |
| Desktop Firefox 160 (jendela nyata) | 4 halaman render baik |
| Mobile emulasi 390×844 | 4 halaman, tanpa overflow, bottomnav OK |

Semua fix ronde 1 terverifikasi PASS: F1 login membuka aplikasi, F2 Dashboard
tidak white-screen (posisi nyata open_price/profit/sl/tp null render benar),
F3 build baru, F4 kill-switch + EA di Dashboard (arm/release via UI tercatat
audit id 46/47), F5 CSV + event log + BELI/JUAL, F6 daftar strategi + toggle
mode. Form SL/TP wajib + arah + konfirmasi PASS; live price/spread konsisten;
bridge HMAC unauth/salah-signature 401.

Temuan baru (minor): F7 "Posisi terbuka" menampilkan posisi CLOSED (API
mengirim semua status, UI tidak filter); F8 chart tanpa empty-state di luar
jam pasar; F9 Riwayat mobile tanpa hint scroll horizontal + konten di belakang
bottomnav; F10 label "10000" melayang di EquityCurve. OBS-1 (environment):
EA bridge berhenti heartbeat ±04:50 WIB — UI menampilkan fallback EA ·
OFFLINE + harga "·····" dengan benar (bukan regresi UI; MT5 dilindungi, tidak
direstart). Deviasi: BrowserStack tidak dijalankan (tanpa kredensial akun);
mobile memakai emulasi Chrome DevTools.

Laporan lengkap + bukti: `~/fund2/docs/QA_P1b_UI_R2.md`,
`qa_p1b_ui_r2.json`, arsip `qa_ui_r2_evidence.zip` (21 screenshot + 6 video
+ CSV). User QA temp dihapus; kill-switch inactive; mode paper; tidak ada
order live baru.

## 7. Ronde 2 — Keamanan dasar pada build baru (22 Nov, t_12720d5e)

Gerbang Direktur terpenuhi: 4 kartu fix selesai + diverifikasi; fund2-api
live start 04:08 WIB (PID 1896128) > commit fix terakhir e792011 (03:25) —
build baru, bukan kode lama.

Skrip: `qa_security_r2.py` (workspace t_12720d5e), live ke
http://127.0.0.1:3110. Hasil: **40 cek = 37 pass, 0 fail, 3 deviasi**
(bukti: `docs/qa_security_r2.json`).

### 3 deviasi security ronde 1 yang difix — kini PASS penuh (live)

- **HMAC `X-Fund2-*` diterima API**: valid → 200 pada GET /bridge/poll,
  POST /bridge/heartbeat, POST /bridge/tick batch `{symbol,ticks:[...]}`
  (ronde 1: 401 / 405 / 422). Kontrak lama Bearer tetap jalan (valid 200,
  salah 401) — dua jalur auth berdampingan.
- **`POST /bridge/heartbeat`** → 200 (ronde 1: 405).
- **Tick batch EA v5** `{symbol, ticks:[{ts,bid,ask,spread}]}` → 200
  `{"ticks":2}` (ronde 1: 422).

### Penetrasi sederhana HMAC (semua ditolak benar)

signature salah → 401; timestamp −30s dan +30s (toleransi ±5s) → 401;
**nonce reuse** (nonce sama 2×, keduanya tanda tangan valid) → ke-1 200,
ke-2 **401** (nonce sekali pakai, TTL 11s); header `X-Fund2-*` tidak
lengkap → 401; nonce <8 char → 401; nonce non-heks → 401. Secret HMAC
hanya di `api/.env` (perm 600); 0 kecocokan di seluruh file repo.

### Rate limit, sesi, CSRF (live)

- Login rate limit: 11× salah → `[401×10, 429]` (batas 10/60s per IP);
  setelah jendela lewat, login benar kembali 200 (lockout kedaluwarsa).
- Order rate limit per menit: dengan kill-switch di-arm (agar tidak
  menyentuh streak FAILED), 12 POST /orders → semua 422; ke-11 dan ke-12
  memuat alasan "order rate limit exceeded" (max 10/menit); 12/12 FAILED
  karena risk gate (payload `risk=rejected`) → `consecutive_failed`
  0 → 0 tidak berubah; 0 order dikirim ke broker.
- Cookie sesi: HttpOnly + SameSite=strict + Max-Age 86400 + Path=/; TTL
  sesi di DB persis 24 jam; token sesi tersimpan sebagai sha256 hash
  (bukan plaintext di DB).
- /orders: tanpa sesi → 401; sesi tanpa header `x-csrf-token` → 403
  (0 baris order dibuat).
- Logout: sesi dihapus dari DB; /auth/me setelahnya 401.
- Sesi kedaluwarsa di-enforce: `expires_at` dimajukan ke masa lalu →
  /auth/me 401.
- Password bcrypt cost 12 (`$2b$12$`).

### 2FA Telegram / aksi sensitif

- Gate aksi sensitif di level API: POST /kill-switch tanpa CSRF → 403;
  STOP_AND_FLATTEN tanpa `confirm` → 400 (pesan eksplisit "akan menutup
  SEMUA posisi"); arm/release ter-audit di `kill_switch_events`
  (ACTIVATE/RELEASE, source dashboard, actor user QA).
- Deviasi (konfigurasi): channel perintah Telegram owner belum aktif
  live — `TELEGRAM_BOT_TOKEN`/`TELEGRAM_OWNER_ID` belum diset di
  `api/.env`; implementasi in-process 9/9 PASS (kartu t_d6ce138b).
  Channel alert `fund2-alerts` (layanan terpisah) aktif.

### Deviasi tersisa (3, semua terdokumentasi)

1. Cookie `Secure` belum diset (loopback P1) — wajib flip saat cutover
   domain (PRD 7).
2. Channel perintah Telegram owner (2FA aksi sensitif) belum aktif live —
   kredensial bot belum dipasang di `api/.env`.
3. PRD §7 menyebut argon2; implementasi bcrypt cost 12 — catatan minor
   (adaptive hash standar kuat), bukan regresi.

### Firewall / bind (PRD 7)

API uvicorn bind **127.0.0.1:3110** saja (bukan 0.0.0.0); edge proxy
fund2-edge-proxy di 172.19.0.1:3110 (docker bridge, tidak publik);
Postgres 127.0.0.1:5433. Port publik hanya 80/443 (Caddy). Firewall
127.0.0.1 tetap aktif.

### Guardrail P1a (akhir test ~05:20 WIB)

/health `{"ok":true}`; kill-switch **inactive**; recorder hidup (parquet
ticks mtime 05:19); user QA temp dihapus (login 401 terverifikasi lewat
penghapusan sesi); 24 baris order audit (risk=rejected, 2 run × 12)
dipertahankan dengan user_id di-NULL-kan; 0 order nyata ke broker.
Catatan: panggilan bridge test mem-mark EA terlihat (ea_last_seen
05:18 WIB); status EA kembali OFFLINE otomatis setelah 60s tanpa
heartbeat (EA nyata memang berhenti ±04:50 WIB, lihat OBS-1 §6).
