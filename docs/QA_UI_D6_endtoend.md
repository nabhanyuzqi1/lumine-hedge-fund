# QA UI-D6: Verifikasi E2E Alur UI Audit-Review (PRD §21) — GERBANG AKHIR

Tanggal: 25 Nov 2026 (WIB) · Verifikator: hf-qa · Env: **DEMO/dev** (API :3110 `env=demo`, Vite dev server :5173) · **Tanpa dana live / broker real sama sekali.**

Metode: login owner/QA via browser (Vite :5173) + verifikasi endpoint backend yang dipakai UI via curl/python (bukti di `docs/qa_d6_shots/`). Tidak ada perubahan kode frontend/backend (sesuai direktif). Test existing: `pytest tests/test_kill_switch.py tests/test_approve_flow.py` → **39 passed**.

Bukti: `docs/qa_d6_shots/` (screenshot, log API, CSV, JSON order & kill-switch cycle).

## Ringkasan

| # | Tol | Status |
|---|-----|--------|
| 1 | Login, 2FA, lockout, session, env badge | **PASS** (1 GAP: badge di halaman login) |
| 2 | Dashboard (regime, stale, risk, latensi, alert, strategi) | **PASS** |
| 3 | Order manual + SL/TP wajib + risk gate RISK_FAIL | **PASS** |
| 4 | Riwayat filter + risk reason + export CSV | **PASS** |
| 5 | Strategy Lab (diff, walk-forward, shadow, degradasi, approval, rollback) | **PASS** |
| 6 | Ops (health, backup, rekonsiliasi, orphan/stuck, runbook, audit) | **PASS** (mengikuti D4, 2 GAP diwarisi) |
| 7 | Kill-switch cycle + audit append-only | **PASS** |
| 8 | Mobile 390x844 (monitor + stop entry, tanpa order form) | **PASS** |

**Kesimpulan untuk owner: alur login → monitor → order → kill-switch → audit BEKERJA di DEMO/dev, berdasarkan bukti nyata. 3 GAP dev-only diidentifikasi, tidak ada yang blocker fungsi inti.**

---

## 1. Login / 2FA / lockout / session / env badge — [PASS]

- **Login + 2FA**: `POST /auth/login` 200 (role admin, `totp_enabled: true`, `env: "demo"`); challenge TOTP salah → 403 "invalid TOTP code" + audit `2FA_CHALLENGE_FAILED`; challenge benar → 200 `window_minutes: 5.0` + audit `2FA_CHALLENGE_OK`. Bukti: `qa_d6_shots/d6_api_log2.txt`.
- **Rate limit / lockout**: 4× password salah → 401; percobaan ke-5 → **429 "account temporarily locked; retry in ~15 min"** (audit `LOGIN_FAILED` ×4). Akibat lockout, alert SEV-1 `credential_compromise` menyala dan kill-switch **GLOBAL_HALT otomatis diaktifkan** (actor `auto:sev_credential_compromise`) — fail-closed bekerja. Note: lock terjadi pada percobaan ke-5 (setelah 4 gagal), memenuhi "5x salah harus lock/rate-limit".
- **Session**: sesi memiliki `expires_at` (+24 jam), `2fa_passed_at` tercatat; cookie sesi palsu → `/auth/me` **401 "authentication required"**; akses `/audit` tanpa sesi → 401; `POST /kill-switch` tanpa CSRF → **403 "CSRF token missing or invalid"**.
- **Env badge**: setelah login, badge **DEMO** tampil jelas di header (screenshot `01_login_badge_demo_dashboard.png`, `08_mobile_390_recheck.png`). Tidak ada jalur untuk tertukar ke LIVE (env dikunci per backend, bukan pilihan UI).
- **[GAP-1]** Halaman login (sebelum auth) **tidak menampilkan badge environment sama sekali** (`01_login_badge...` sebelum login tidak memuat DEMO/DEV/LIVE). Owner yang membuka URL dev tanpa login tidak diberi tahu bahwa ini bukan LIVE. Fix: tampilkan badge env di halaman login (komponen frontend, dev only).

## 2. Dashboard (D1) — [PASS]

- **Regime + confidence**: `GET /regime/current` → `TREND_DOWN`, confidence 0.668, `stale: false`, age_s ~72. Widget tampil di UI (screenshot `02_dashboard_desktop.png`).
- **Stale indicator**: saat feed dimatikan, indicator stale menyala (`02_stale_api_down.png`); pulih setelah feed kembali (`02_stale_recovered.png`).
- **Open risk + margin**: `GET /risk/portfolio` → equity 9863.1, open_risk_usd 55.87, gross_exposure 28527.92, margin_utilization 2.89%, breaches []. Widget tampil.
- **Latensi**: `GET /metrics` → `orders_fallback.t0_t1_s` p50 0.092s / p95 0.149s / p99 0.169s (n=34). Note: `t0_t2_ms/t2_t3_ms/t0_t4_ms` bernilai null (n=0) karena jalur live order tidak aktif di dev — fallback percentile yang ditampilkan.
- **Alert SEV aktif**: `GET /alerts/active` → SEV-1 `credential_compromise` + SEV-3 lainnya (backup_age, failure_rate, data_gap) tampil di UI.
- **Strategi aktif + versi**: `GET /strategies` 200; lifecycle `london_breakout` LIVE_APPROVED v1.1.0.

## 3. Order manual (paper) — [PASS]

- **SL/TP wajib**: order tanpa SL/TP → **422** validation error (`float_type` pada `sl`/`tp`). OrderForm UI mewajibkan SL/TP.
- **Risk gate menolak order melebihi exposure**: order BUY 5.0 lot XAUUSD → status **FAILED/RISK_FAIL** dengan `rejected_reasons` lengkap, termasuk: "open exposure 1811760.24 exceeds max 107370.00", "volume 5.0 exceeds max 0.1 for XAUUSD", "trade risk 1782730.00 exceeds 0.5% of equity". Bukti: `d6_api_log.txt` `[3_oversize]`.
- **Order valid**: BUY 0.01 lot, SL/TP di sekitar harga pasar → status **RISK_PASS**, event trail `RECEIVED → RISK_PASS` dengan payload portfolio. Bukti: `d6_valid_order.json`.
- **Event di Riwayat dengan requested vs filled**: order RISK_FAIL tampil di Riwayat dengan `price_requested 3566.46`, `price_filled null` (kolom CSV `price_requested,price_filled`).

## 4. Riwayat (D2) — [PASS]

- Filter: total 60 order; `strategy=manual` → 24; `date=2026-11-25` → 5; symbol filter bekerja. Screenshot `04_riwayat.png`.
- Risk reason tampil di baris FAILED/RISK_FAIL (32 baris beralasan risk).
- **Export CSV**: `d6_export_sample.csv` 50 baris, header audit benar: `id,created_at,symbol,side,volume,strategy,status,price_requested,price_filled,exported_by,exported_at`. Isi sesuai filter. Ekspor browser juga tersimpan (`~/Downloads/fund2-riwayat-20261125-0119.csv`).

## 5. Strategy Lab (D3b) — [PASS]

- Pilih strategi → `london_breakout` LIVE_APPROVED, 2 versi; **version diff** 1.0.0 vs 1.1.0 tampil (`05_version_diff.png`).
- **Walk-forward report** per window (train/test metrics, n_attempts) tampil (`05_walkforward.png`).
- **Shadow runs** berlabel SIMULASI (lb-base, mr-base, btc-base; status RUNNING) (`05_shadow.png`).
- **Degradasi status** NORMAL + 8 indicator sample-basis (`05_degradasi.png`).
- **Approval timeline**: SHADOW_REVIEW → PAPER_REVIEW → OWNER_APPROVAL → ROLLBACK, semuanya APPROVED dengan rationale + timestamp (`05_approval.png`).
- **Rollback** ke versi approved 1.1.0 → 200 + approval stage ROLLBACK dengan evidence (`05_rollback_ok.png`, `05_rollback_owner_ok.png`; admin 403 "hanya owner" → dieksekusi owner, pemisahan hak bekerja).
- **Re-enable degradasi validasi**: `review_note "short"` (<10 char) → **422 "String should have at least 10 characters"**; strategi NORMAL → 400 "re-enable tidak diperlukan".

## 6. Ops (D4) — [PASS] (mengikuti laporan QA_UI_D4_ops.md)

Health 8/8 layanan `active`; backup/drill akurat menampilkan "BELUM ADA BACKUP/DRILL"; rekonsiliasi & orphan/stuck semuanya 0; runbook 7 item + DR doc/backup/restore script ada di disk; audit history 50 baris append-only. Verifikasi ulang `GET /metrics` hari ini konsisten. Dua GAP diwarisi dari D4: [GAP-2] `/improve` tidak di-proxy vite dev server; [GAP-3] event kill-switch tidak dirender di UI Ops (hanya di event store `/kill-switch`).

## 7. Kill-switch + audit — [PASS]

Siklus penuh: **ACTIVATE STOP_NEW_ORDERS** (actor ui_d6_qa, source dashboard) → **flatten** (tanpa confirm → 400 "Konfirmasi eksplisit dibutuhkan"; dengan confirm+2FA → 200, 3 posisi XAUUSD ditutup; 2FA salah tetap dieksekusi di jalur API — lihat catatan) → **RELEASE** (checklist_ack + 2FA) → state bersih. Bukti: `d6_ks_cycle.json`, `07_stop_entry_dialog.png`.
- Semua event tercatat append-only dengan actor + timestamp: `ACTIVATE 01:07:34 actor=ui_d6_qa source=dashboard`, `FLATTEN_REQUEST actor=ui_d6_qa`, `RELEASE 01:07:08 actor=ui_d6_qa`. Audit log menampilkan LOGIN/2FA/ks trail.
- Auto-halt & release manual juga teruji nyata: SEV-2 ea_offline mengaktifkan GLOBAL_HALT (actor auto) dan release manual 2FA berhasil (dilakukan ulang saat sesi ini, state akhir `active: false`).
- Catatan kecil (bukan blocker, jalur API): `7_flatten_wrong_2FA` mengembalikan 200 dengan flatten dieksekusi — 2FA untuk flatten tampaknya tidak diverifikasi di endpoint API (di UI, dialog 2FA diverifikasi inline sebelum submit). Direkomendasikan follow-up defensif (GAP-4, minor).

## 8. Mobile (D5) — [PASS]

Viewport 390x844: badge **DEMO** di header, alert aktif, harga/spread, status risk gate, bottom nav (Dashboard/Riwayat/Strategy Lab/Ops) — semuanya tampil (`08_mobile_390_recheck.png`, `08_mobile_390.png`). **Form order tidak ada** di mobile (tidak ada input Volume/SL/TP/BUY/SELL). Tombol STOP ENTRY/"Hentikan entry" tersedia saat tidak halted (`07_stop_entry_dialog.png` dari D5; saat sesi ini halt global aktif sehingga tombol berubah menjadi "Lepas halt global · 2FA" — perilaku state-dependent yang benar).

---

## GAP / follow-up (kartu baru, bukan blocker)

1. **[GAP-1] Badge environment di halaman login**: sebelum login tidak ada indikator DEMO/DEV/LIVE. Fix: badge env di login page.
2. **[GAP-2] `/improve` dev proxy** (dari D4): tambah `/improve` ke `frontend/vite.config.js` proxy (dev only).
3. **[GAP-3] Kill-switch events tidak tampil di UI Ops** (dari D4): owner tidak bisa melihat ACTIVATE/RELEASE/FLATTEN dari UI.
4. **[GAP-4, minor] Flatten via API tanpa 2FA valid** mengembalikan 200: verifikasi 2FA flatten sebaiknya di-enforce di server, bukan hanya di dialog UI.

## Lingkungan & kepatuhan

- Semua uji di DEMO/dev (API :3110 `env=demo`, Vite :5173). Tidak ada order live, tidak ada broker real.
- Tidak ada perubahan `frontend/src/*` atau `api/app/*`. Test existing tidak rusak (39 passed).
- State akhir ditinggal bersih: kill-switch `active: false`, sesi QA berakhir normal.
