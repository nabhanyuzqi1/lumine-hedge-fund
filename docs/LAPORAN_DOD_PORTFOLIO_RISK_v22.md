# Laporan DoD: Portfolio Risk Manager (PRD v2.2 §7)

Task: t_f2v22a3 · Tanggal: 23 Nov 2026 · Worker: hf-backend

## Deliverable

- `api/app/portfolio_risk.py` — Portfolio Risk Manager: perhitungan
  worst-case loss per posisi/order sampai SL termasuk biaya (komisi
  round-turn) + buffer (spread + slippage), agregat open risk, stress
  scenario, dan gerbang keputusan order baru. Murni fungsi keputusan
  (tanpa DB/IO di path evaluasi); collector DB tersedia untuk fund2.
- Wiring `POST /orders` (`api/app/routes.py`): lapisan portofolio
  dievaluasi di dalam transaksi order setelah `pg_advisory_xact_lock`
  (race dua sinyal simultan tidak bisa oversubscribe), hasil keputusan +
  snapshot portofolio ter-audit di `order_events.payload`.
- `GET /risk/portfolio` — snapshot agregat + daftar breach untuk UI/
  monitoring (read-only; tidak pernah menutup posisi, PRD §7.3).
- Migration `g007_portfolio_risk`: seed settings `portfolio_risk` +
  backfill `tick_value`/`tick_size`/`spec_verified` untuk symbol_specs
  XAUUSD/BTCUSD yang sudah ada di DB (idempotent, override owner tidak
  ditimpa).
- Test: `api/tests/test_portfolio_risk.py` (43 test) + penyesuaian 2 test
  exposure di `test_orders_api.py` (posisi fixture kini diberi SL).

## Aturan yang diimplementasikan (PRD §7.3)

| Aturan | Implementasi |
| --- | --- |
| Worst-case loss per posisi sampai SL + biaya + buffer | `leg_worst_case_loss`: (dist SL + spread + slippage) × tick_value/tick_size × lot + komisi; pending/SENT pakai fill terburuk (slippage melawan posisi) |
| Aggregate open risk | `portfolio_snapshot`: Σ semua leg hidup (OPEN + RECEIVED/RISK_PASS/SENT/STUCK) + kandidat, post-trade |
| Pending & SENT dihitung | `collect_legs` memuat kedua status + RECEIVED/RISK_PASS/STUCK |
| Limit per trade / total risk / gross exposure / volume / margin / konsentrasi | `max_risk_per_trade_pct` 0.5%, `max_open_risk_pct` 2%, `exposure_max_usd`, `max_total_volume_lot` 0.30, `max_margin_utilization_pct` 20%, `max_symbol_risk_pct` 1% equity |
| Tolak bila contract spec/tick value tak terverifikasi | `portfolio_spec` fail-closed: butuh `tick_value`, `tick_size`, `contract_size` valid + `spec_verified=true` |
| Tanpa kredit hedging/korelasi | BUY+SELL simbol sama tetap dihitung keduanya (gross, tanpa netting); semua SL diasumsikan kena bersamaan |
| Stress scenario | gap 0.5% harga + spread 3× + slippage; cap `stress_max_risk_pct` 3% (= halt harian A6) |
| Equity/margin stale → tidak buka posisi baru | feed hilang / umur > `max_feed_age_s` (60s) → blokir order baru |
| Posisi terbuka tidak auto-close | modul hanya memutuskan order baru; penutupan tetap policy owner (kill-switch/flatten) |

Semua nilai default adalah [USULAN] PRD §7.4; owner dapat mengubah via
settings `portfolio_risk` (merge parsial, ter-audit `settings_audit`).

## DoD → Bukti

| DoD kartu | Test |
| --- | --- |
| Fixture contract spec benar | `test_verified_spec_accepted`, `test_candidate_with_verified_spec_passes`, 9 varian spec tak terverifikasi ditolak (`test_unverifiable_spec_rejected_fail_closed`) |
| Beberapa posisi + pending bersamaan | `test_aggregate_counts_positions_pending_sent` (2 OPEN + PENDING + SENT + kandidat, angka eksak), `test_open_risk_over_limit_rejected` |
| Race 2 sinyal simultan | `test_race_two_simultaneous_signals` (API, advisory lock: cap 0.35%, tepat 1 lolos, 1 FAILED "total open risk") |
| Equity/margin hilang | `test_equity_missing_blocks_new_orders`, `test_equity_age_unknown_blocks_new_orders`, `test_margin_feed_stale_blocks_new_orders`, `test_equity_stale_blocks_new_orders` |
| SL ditolak broker | `test_open_position_without_sl_blocks_new_orders`, `test_pending_without_sl_blocks_new_orders`, endpoint `test_risk_portfolio_endpoint_flags_unbounded_sl` |
| Tidak ada order lolos saat total risk lewat limit | `test_open_risk_over_limit_rejected`, `test_order_rejected_when_portfolio_risk_over_limit` (jalur API + snapshot audit di order_events) |

## Hasil test

```
tests/test_portfolio_risk.py            43 passed
tests/test_orders_api.py                16 passed (2 fixture diberi SL)
full suite (831 passed, 5 skipped)      0 failed  (441s)
```

Live DB terverifikasi tidak tersentuh (snapshot users/orders/order_events/
positions/settings/sessions/bridge_commands identik sebelum-sesudah).

## Catatan

- Migration g007 berlaku saat service berikutnya restart (jalur deploy
  DevOps); sampai itu, DB live belum punya settings `portfolio_risk` —
  `portfolio_config` fallback ke default modul yang sama.
- Feed margin broker belum ada di EA snapshot; margin dihitung dari
  notional/leverage (selalu segar). Ketika EA mengirim account margin,
  isi `PortfolioFeed.margin_used/margin_age_s` — gerbang stale sudah siap.
- Paper runner (simulator satu posisi) belum memakai lapisan ini; gate
  lama tetap berlaku di paper.
