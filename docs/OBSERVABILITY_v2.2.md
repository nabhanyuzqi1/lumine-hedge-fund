# Observability & Alerting SEV-1..SEV-4 (PRD v2.2 §20)

Task t_f2v22a10. Modul: `api/app/metrics.py` (collector + evaluator +
`GET /metrics`), watcher berjalan di daemon `fund2-alerts` (pembatasan
Direktur: infra pengirim Telegram milik t_f2p1b3 — SATU pipeline, sender
`telegram_bot.notify_owner`).

## Metrics (PRD §20.1) dan sumbernya

| Metric | Sumber | Ambang / catatan |
| --- | --- | --- |
| API availability/latency | `/health`, service status, DB roundtrip | DB query > 1 s = degradasi (dashboard) |
| T0→T2 / T2→T3 / T0→T4 p50/p95/p99 | `order_events.payload.latency` (harness QA); fallback kolom orders (T0=created, T1=delivered, T4=resolved) | SLO p95 < 300 ms, p99 < 500 ms (v2.1 §6) |
| EA heartbeat age | `settings.ea_last_seen_at` | offline > 60 s |
| Tick age & data gaps | `candles` max(ts), `liquidity_samples` (gap > 60 s) | candle stale > 10 menit |
| Spread median/p95 | `liquidity_samples` per simbol, 1 jam & 24 jam | XAUUSD p95 ≥ 0.50 [USULAN] |
| Slippage distribution | `orders` price_filled vs price_requested (OPEN, 24 jam) | per simbol |
| Order state counts | `orders.status` | stuck: SENT > 60 s |
| Rejection/failure rate | FAILED vs terminal 24 jam; payload risk=rejected | ≥ 20% watch [USULAN]; 3 beruntun = SEV-2 |
| Reconciliation mismatch count | `order_events` reconciled_unexplained / ORPHAN_ADOPTED | event baru = SEV-1 |
| Strategy runtime/error/timeout | `paper_state` age, mode, FAILED per strategi, `llm_agent_pause` | state stale > 15 menit (market buka) |
| DB connections/disk/backup age | pg_stat_activity, pg_database_size, statvfs, JSON backup `~/fund2-backups/logs/` | koneksi ≥ 80%, disk ≥ 80%, backup > 26 jam |
| CPU/RAM/swap/disk I/O | /proc (tanpa dependensi baru) | watch di dashboard |
| Drawdown/exposure/margin/kill-switch | kill_switch.compute_metrics + notional posisi | DD watch 1.5%, auto-halt 3%/8% |

Margin broker-side tidak tersimpan di DB (EA snapshot positions/deals saja);
metrik margin diekspos sebagai exposure + equity (lihat `margin_note`).
Forwarding accountInfo margin butuh perubahan kontrak EA (kartu terpisah).

## Severity (PRD §20.2)

- **SEV-1** (global halt + owner alert): posisi terbuka tanpa SL broker-side;
  ledger mismatch (posisi hilang tanpa deal penutup); order tak diketahui
  (orphan baru); admin lockout (indikasi credential compromise). Auto-action:
  `kill_switch.activate(GLOBAL_HALT, source="auto:sev_*")` — tidak pernah
  auto-flatten (D6).
- **SEV-2** (halt entry + investigasi): EA offline dengan posisi terbuka; DB
  unavailable; ≥ 3 FAILED beruntun. Auto-action: GLOBAL_HALT / STOP_NEW_ORDERS
  (idempotent; auto-trigger kill_switch yang sama tetap sumber utama).
- **SEV-3** (watch/pause): latensi ≥ SLO; spread p95 ≥ ambang; candle/tick
  stale; data gap; koneksi DB tinggi; disk penuh; backup > 26 jam; DD ≥ 1.5%;
  order stuck; failure rate ≥ 20%; paper runner stale; EA offline tanpa
  posisi. Tanpa auto-halt.
- **SEV-4** (laporan harian): rekap 07:00 WIB (`app.alerts.build_recap`) +
  anomali 07:05 WIB (`app.anomaly`) + backup sukses — milik kartu sebelumnya,
  tidak diimplementasi ulang.

Alert actionable (PRD §20): setiap alert memuat Apa / Dampak / Waktu /
Otomatis / Manual (langkah bernomor).

## Operasional

- Dashboard: panel "System metrics" (poll `/metrics` 30 s, auth session).
- Uji tanpa kirim: `cd api && .venv/bin/python -m app.metrics`
- Uji kirim [TEST] SEV-1+SEV-2 ke owner:
  `.venv/bin/python -m app.metrics --send-test`
- Anti-spam: SEV-1/2 alert saat deteksi (termasuk kondisi yang sudah ada saat
  daemon start), kirim ulang tiap 30 menit bila persisten; SEV-3 baseline
  pertama diam; pesan pulih sekali per insiden; dedup 300 s di notify_owner.
- Semua nilai dinamis di-escape Markdown Telegram (insiden 23 Nov 2026:
  underscore → 400 diam-diam).
- Test: `pytest tests/test_metrics.py` (24 test).
