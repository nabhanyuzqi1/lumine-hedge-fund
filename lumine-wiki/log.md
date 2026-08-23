---
title: "Ingest Log"
type: moc
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#log", "#meta"]
---

# Vault Ingest Log

Log of all INGEST operations and major vault changes.

## 2026-08-23

- [2026-08-23] **Vault initialized** — Created directory structure and SCHEMA.md
- [2026-08-23] **Index created** — MoC with navigation links to core concepts

## 2026-08-23 — Fix MT5 crypto instance (BTCUSD)
**Status: MAJOR FIX — crypto seed + status live**

### Masalah
1. EA crypto menimpa `mt5:status` HFM (pakai URL HFM `/mt5-proxy`)
2. `mt5crypto:*` keys kosong — EA tidak kirim ke namespace crypto
3. Chart XAUUSD di terminal rusak (data BTCUSD ketabrak)
4. Commands campur (mt5:commands shared HFM + crypto)

### Root Cause (berlapis)
1. Container crypto mount `/opt/lumine-ea` SAMA dengan HFM → EA identik
2. Caddy 2.11.4 TIDAK menambahkan header X-Instance/query ke upstream (header_up/rewrite diabaikan)
3. Whitelist WebRequest: WebRequestUrl hash hilang → 4014 semua request
4. chart01.chr (MQL5/Profiles) parameter input override default source → proxy URL lama
5. Entrypoint compile tanpa `|| true` → crash-loop (set -euo pipefail)

### Solusi
1. EA crypto terpisah: `/opt/lumine-ea-crypto/LumineEA.mq5` (InpProxyURL lumine.biz.id + `?instance=crypto` di HttpPostJson)
2. Proxy `_ns()`: detect dari query param `instance` > header X-Instance > default mt5:
3. Proxy `/commands`: BRPOP per-instance (`mt5crypto:commands`)
4. Backend `POST /admin/ea-command`: accept `instance: crypto` → mt5crypto:commands
5. Restore WebRequestUrl hash di common.ini
6. Update chart01.chr di MQL5/Profiles + backup (parameter input override)
7. Entrypoint: copy EA ke Common + Install folder, `|| true` di compile, copy ex5 ke install

### Hasil
- ✅ `mt5crypto:status` LIVE: seed_done=1, bid/ask BTCUSD realtime
- ✅ Seed semua timeframe: 1m 100k, 5m 67k, 15m 22k, 1h 5.6k, 4h 1.4k, 1d 235
- ✅ `mt5:status` HFM tidak tertimpa
- ⚠️ Ticks belum masuk mt5:ticks (ticks_sent=0) — NEXT TASK

## 2026-08-23 (part 2) — Bar builder live + CI hijau + frontend filter
**Status: BTCUSD chart realtime — bar 1m update live**

### Fix
1. **Backend: silent exception logging** — `except Exception: pass` di tick_worker & bar_flush_worker menjadi `print(error)` — debugging diam-diam mati
2. **EA v4.22**: `g_ticksSent++` di SendTick (counter tidak pernah di-increment — bug)
3. **Caddyfile.prod**: route `/mt5-proxy-crypto/*` di-commit ke repo (sebelumnya hanya di VPS)
4. **Frontend**: semua panel terminal filter by selectedSymbol (OrdersTable, ActivityLog, RiskGauges exposure, CommitteeFeed)
5. **CI**: F821/F841/SIM108/C901/PLR0915/RUF003 — semua lint errors fixed, CI hijau

### Bar builder live
- Seed worker: consume mt5:seed_bars → insert bars_1m
- Tick worker: consume mt5:ticks → _update_bar_builder + MarketService + SSE
- Bar flush worker: tiap 60s flush bar ts < current_minute → bars_1m + agregasi 5m/15m/1h/4h
- Bar terakhir BTCUSD: 18:48 (update live)
- EA crypto intermittent 521 (Cloudflare origin) — masih perlu investigasi

### Masih Open
- EA crypto intermittent 521 (Cloudflare → origin kadang down)
- ActivityLog tidak punya field symbol (filter by message/stream — tidak sempurna)
- CommitteeFeed tidak punya field symbol (filter by decision/agent text — tidak sempurna)
