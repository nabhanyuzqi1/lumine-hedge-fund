# QA P1b — UI 4 halaman, Ronde 2 (build baru pasca-fix)

Task: t_eb648747 · Tanggal: 2026-11-22 · QA: hf-qa
Gerbang Direktur: dijalankan SETELAH 4 kartu fix selesai + redeploy
(t_1ae5d258, t_2233e7b7, t_22f5d556, t_ef2f49c6 — semua done + verifikasi Direktur).

## Build yang dites (bukan build lama)

- Service live: uvicorn PID 1896128 start **04:08 WIB** > commit fix terakhir
  e792011 (03:25). Frontend dist build **04:16**, asset yang diserve API =
  `index-5c1vHCt-.js` (memuat KillSwitchCard, EaChip, checklist_ack, CSV,
  listener `/auth/me`).
- `GET /strategies` → **401 JSON** (endpoint ada, bukan SPA fallback HTML).
- Marker build baru terverifikasi di bundle yang diserve.

## Cakupan

| Platform | Cara |
| --- | --- |
| Desktop Chrome | browser nyata via CDP, 1440×900 |
| Desktop Firefox | Firefox 160.0 jendela nyata di display :0 (1280×768) |
| Mobile | emulasi perangkat Chrome (CDP) 390×844 + touch — setara Chrome DevTools |
| BrowserStack | **tidak dijalankan** — tidak ada kredensial akun di environment (deviasi dari body task, dicatat) |

## Hasil verifikasi fix ronde 1

| ID | Area | Hasil |
| --- | --- | --- |
| F1 | Login membuka aplikasi | **PASS** |
| F2 | Dashboard tidak white-screen saat ada posisi | **PASS** |
| F3 | Service live kode baru | **PASS** |
| F4 | Kill-switch + status EA di Dashboard | **PASS** |
| F5 | Riwayat: CSV + event log + label | **PASS** |
| F6 | Strategy Lab daftar strategi + mode | **PASS** |

Detail:

- **F1**: password salah → pesan "invalid credentials" tampil; login benar →
  Dashboard terbuka (checkAuth via `GET /auth/me`), tombol tidak stuck
  "Memeriksa…". Terverifikasi di Chrome dan Firefox.
- **F2**: posisi nyata di live DB (open_price 2000.0, profit 2.0, sl/tp null —
  bentuk persis pemicu crash ronde 1) render benar: **BELI 0.10 / 2000.00 /
  SL · / TP · / +$2.00**, tanpa white-screen. `normalizePosition` + guard null
  bekerja (Chrome + Firefox).
- **F4**: kartu "Kill-switch dan status EA" di Dashboard dengan hold-to-arm.
  Arm via UI (tahan 1.2 dtk) → "TERARM · order baru diblokir" + server
  `active=true, mode=STOP_NEW_ORDERS` + audit `kill_switch_events` id 46
  (ACTIVATE, source=dashboard, actor=qa_ui_r2). Saat armed, form order otomatis
  diganti notice halted (order tak bisa dikirim — perilaku benar). Release via
  UI → "AMAN · order diizinkan" + audit id 47 (RELEASE). Badge "EA · ONLINE"
  saat heartbeat fresh; saat heartbeat stale badge "EA · OFFLINE" + harga
  "·····" (fallback sesuai desain).
- **F5**: tombol CSV mengunduh `fund2-riwayat-20261122-0442.csv` (BOM ada,
  delimiter `;`, mengikuti filter aktif). Klik baris → event log lazy-load
  (RECEIVED → FAILED + alasan risk gate, timestamp, source). Side BUY/SELL →
  **BELI/JUAL benar** (ronde 1: selalu "JUAL"), entry dari `price_filled`
  (null → "·"), SL/TP null → "·".
- **F6**: daftar strategi tampil — London Breakout + Spread Filter (Track A),
  statistik jujur dari ledger paper (0 trades, balance 10000, winrate 0%).
  Toggle Paper → Live → Paper via UI benar (aria-pressed, refleks SSE).
  KillSwitchCard dipakai bersama Dashboard & Lab.

## Cek lain dari body task

- **Form order SL/TP wajib + arah + konfirmasi**: PASS. Kosong → "Stop loss
  wajib diisi" / "Take profit wajib diisi"; arah salah (BUY, SL di atas harga)
  → "SL harus di bawah harga sekarang" / "TP harus di atas harga sekarang";
  dialog konfirmasi menampilkan rekap (arah, volume, harga, SL, TP, risiko
  maksimum $50.05) + Batal / "Ya, kirim order". Order nyata sengaja tidak
  dikirim (pasar tutup Minggu; E2E order penuh sudah dibuktikan kartu
  t_ef2f49c6: RECEIVED→RISK_PASS→SENT→FAILED retcode 10018).
- **Live price + spread**: PASS. XAUUSD 3537.68 (mid), ask 3537.90,
  spread 0.43 = ask−bid (konsisten; header = mid, bukan bid). SSE tick
  mengalir saat EA aktif (7 event/6 dtk). Chart menggambar ≤2 dtk setelah
  login dan stabil 30 dtk (paintedPx ~110k).
- **Auth HMAC**: PASS. Bridge unauth → 401, signature HMAC salah → 401.
  Kontrak HMAC/heartbeat/tick batch diverifikasi penuh di kartu t_ef2f49c6 +
  verifikasi Direktur; dari sisi UI: badge EA · ONLINE saat heartbeat fresh.
- **Mobile 4 halaman**: PASS. Tanpa overflow horizontal (scrollWidth =
  clientWidth = 390 di semua halaman), bottomnav muncul dengan 3 link, tabel
  Riwayat scroll di dalam wrapper (scrollW 569 > clientW 360, halaman tetap
  390). Login mobile render baik.
- **Console errors**: 0 di semua halaman & interaksi (hook `__qa_errors`).

## Temuan baru (ronde 2)

- **F7 (minor, frontend+API)** — "Posisi terbuka" menampilkan posisi
  berstatus CLOSED: `GET /positions` mengembalikan semua status, UI tidak
  memfilter; chip "1 aktif" menghitung posisi closed; tombol "Tutup" tampil
  untuk posisi closed; kolom ORDER kosong (`order_id` null, `ticket` 601
  tidak dipakai). Saran: filter `status=OPEN` di UI (atau query param), dan
  tampilkan ticket bila order_id null.
- **F8 (minor, UX)** — chart tanpa empty-state: di luar jam pasar (tick
  berhenti) canvas kosong tanpa pesan. Data chart murni ring buffer SSE
  (maks 320 tick), tidak ada sumber histori candle ke UI.
- **F9 (minor, UX mobile)** — Riwayat mobile: tabel scroll horizontal dalam
  wrapper tapi tanpa hint visual (UUID terpotong tanpa ellipsis); konten
  scroll di belakang bottomnav tanpa padding-bottom; margin kontainer tabel
  asimetris (kiri ±15px, kanan 0).
- **F10 (minor, kosmetik)** — Strategy Lab: label nilai "10000" (nilai awal &
  akhir curve) di canvas EquityCurve tampak "melayang" saat kurva
  flat/single-point.
- **OBS-1 (environment, bukan regresi UI)** — EA bridge berhenti heartbeat
  ±04:50 WIB (ea_last_seen_age_s 429 dtk @ 04:57; proses MT5 hidup, CPU ~50%).
  UI menampilkan fallback "EA · OFFLINE" + harga "·····" dengan benar —
  justru memverifikasi jalur offline badge. MT5 dilindungi, QA tidak
  me-restart. Follow-up: cek kesehatan EA/bridge (backend/devops).

## Deviasi

- BrowserStack free tier tidak dijalankan (tidak ada kredensial akun di
  environment ini); mobile memakai emulasi Chrome DevTools (CDP).

## Bukti

- Screenshot (21): `shots/` dalam arsip `qa_ui_r2_evidence.zip` — login,
  validasi form (kosong/arah), konfirmasi order, kill-switch arm/release,
  dashboard (termasuk fallback EA OFFLINE), riwayat + event log, lab,
  mobile 4 halaman, Firefox 7 tahap.
- Video pendek: `login.mp4` (10 dtk), `dashboard.mp4` (9 dtk),
  `riwayat.mp4` (10 dtk), `lab.mp4` (4 dtk), `mobile_dashboard.mp4` (6 dtk),
  `firefox_flow.mp4` (120 dtk, Firefox nyata: login → dashboard → riwayat →
  lab, di-crop ke jendela Firefox).
- CSV: `fund2-riwayat-20261122-0442.csv`.
- Audit: `kill_switch_events` id 46/47 (ACTIVATE/RELEASE, dashboard, qa_ui_r2).
- Hasil mesin: `~/fund2/docs/qa_p1b_ui_r2.json`.

## Cleanup / guardrail

- User QA temp `qa_ui_r2` dihapus (baris audit order dipertahankan).
- Kill-switch diakhiri **inactive**; strategy mode diakhiri **paper**.
- Tidak ada order live baru; recorder tidak disentuh; `/health` ok.
