# Verifikasi t_f2mp1 — Risk gate & settings multipair (per-simbol)

Tanggal: 23 Nov 2026, ~10:39–10:45 WIB. Implementasi: commit `644c7a9`.

## 1. Unit test

`api/.venv/bin/python -m pytest tests/` → **318 passed** (test_risk 42 + test_orders_api
termasuk 6 test integrasi multipair baru; seluruh suite lama tetap hijau).

## 2. Deploy

- `systemctl --user restart fund2-api fund2-candle-rollup fund2-alerts` — semua `active`,
  ingest auto-heal M1→M5 jalan (6 bar saat startup).
- Settings live ter-seed otomatis saat startup: `symbol_specs` (XAUUSD + BTCUSD),
  `exposure_max_usd` 107370, `risk_per_trade_pct` 0.5.
- Sebelum demo, kill-switch GLOBAL_HALT stale (auto-trigger `ea_offline` 22 Nov 08:13;
  kondisinya sudah lewat: EA online kembali — `ea_last_seen_at` update terus, posisi nol)
  dilepas via `kill_switch.release(checklist_ack=True, source='kanban:t_f2mp1',
  actor='hf-backend')`. Trigger auto tetap ter-armed bila kondisi berbahaya terulang.

## 3. Demo E2E di sistem live (akun demo)

| # | Order | Hasil |
|---|-------|-------|
| 1 | BTCUSD BUY 0.01, SL ask−5 (3.80 < sl_min 10) | **FAILED 422** — `SL distance 3.80 below min 10.0 for BTCUSD` (tolakan per-simbol) |
| 2 | BTCUSD BUY 0.01, SL 50/TP 100 | **RISK_PASS** → SENT → FAILED di broker `retcode=10016` (invalid stops: SL 50 di bawah stops level broker BTCUSD; semua order BTC yang pernah fill sebelumnya tanpa SL) |
| 2b | BTCUSD BUY 0.01, SL 200/TP 400 | **RISK_PASS** → SENT → **FILLED** ticket 504548243 @61319.55 → CLOSE → FILLED_THEN_CLOSED (profit −0.57) |
| 3 | XAUUSD BUY 0.01, SL 3.0/TP 6.0 | **RISK_PASS** → SENT → **FILLED** ticket 504546241 @3606.47 → CLOSE → FILLED_THEN_CLOSED (profit +0.18) — XAUUSD tidak berubah perilaku |

Order ID: sc1 `881decfa`, sc2 `37a33d44`, sc2b `49b8b62f`, sc3 `e1f41c97`,
close `9b515f10` (XAU), `539c87ff` (BTC). Semua rantai event lengkap di `order_events`.

Temuan follow-up (bukan regresi t_f2mp1): stops level broker BTCUSD > 50 USD — order
BTC dengan SL 10–50 USD lolos risk gate tapi ditolak broker. Perlu kalibrasi
`sl_min_usd` BTCUSD atau SL darurat di atas stops level broker (kartu terpisah).

## 4. Cleanup

- Kedua posisi demo ditutup; `positions` tanpa baris OPEN.
- Password user demo `demo_mp1` dirotasi (random), session demo dihapus.
