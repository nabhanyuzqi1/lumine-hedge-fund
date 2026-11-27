# PRD — Lumine Fund v2 ("Fund Core")

Tanggal: 2026-11-20 | Status: DRAFT untuk eksekusi tim
Pendahulu: lumine-hedge-fund (fund.lumine.biz.id) — tetap jalan sampai v2 lolos QA

## 1. Visi

Platform trading XAUUSD yang **cepat, terlacak, dan bisa memperbaiki dirinya sendiri** —
dengan Hermes + skills sebagai lapisan riset, kode deterministik sebagai lapisan eksekusi.

Satu kalimat: *quant desk yang self-improving, bukan chatbot yang main uang.*

## 2. Kenyataan yang harus diakui (sebelum janji apa-apa)

- **HFT sejati (mikrodetik) mustahil di MT5 retail.** Latensi broker HFM ~100-300 ms,
  di luar kendali kita. Target realistis: **eksekusi <300 ms end-to-end** dari sinyal ke
  MT5, dan strategi per-tick (scalping) — itu kelas "high-frequency" yang bisa dicapai.
- **RL untuk trading itu eksperimental.** Overfitting adalah musuh utama. RL masuk jalur
  riset dengan gerbang ketat, bukan jalur live sejak hari pertama.
- **Likuiditas = biaya.** Spread, slippage, dan jam likuid (London/NY) menentukan
  profitabilitas lebih dari kecerdasan model. Modul likuiditas wajib ada sejak Phase 1.

## 3. Arsitektur

3 service saja: `fund2-api` (FastAPI + serve UI + SSE), Postgres 16 (db `fund2`),
MT5 + EA (endpoint baru). Caddy-edge tetap. Tanpa Redis, tanpa proxy, tanpa worker terpisah.

```
┌────────────────────────────────────────────────────────────┐
│ LAPISAN RISET (Hermes + skills, boleh LLM)                 │
│ trading-analysis skill · backtest · self-improvement loop  │
│ usulkan → validasi → LAPOR KE OWNER → approve             │
└─────────────────────┬──────────────────────────────────────┘
                      │ 1 pintu bergerbang (human approve)
┌─────────────────────▼──────────────────────────────────────┐
│ LAPISAN EKSEKUSI (deterministik, tanpa LLM)                │
│ sinyal → risk gate → state machine → MT5 → event log       │
│ reconciler · kill-switch · max-drawdown auto-halt          │
└────────────────────────────────────────────────────────────┘
```

### 3.1 Data layer
- **Feed langsung**: EA kirim tick (batch) + candle ke API via `http://127.0.0.1:3110` (jalur lokal, tanpa TLS/Caddy).
- **Crawler data historis**: unduh candle/tick XAUUSD (Dukascopy, MQL5, sumber gratis)
  → disimpan parquet + tabel `candles` (partitioned per bulan). Crawler = skill Hermes
  (`data-crawler`) yang bisa dijalankan manual/jadwal.
- **Likuiditas** (tabel `liquidity_ticks`): spread bid-ask real-time, profil jam
  (sesi Asia/London/NY), estimasi slippage per ukuran order. Strategi wajib baca ini
  sebelum mengeksekusi (filter: spread > X = jangan entry).

### 3.2 Strategy layer — format "skill"
Setiap strategi = satu skill Hermes: `SKILL.md` (logika, parameter, risk, hasil backtest)
+ kode Python murni `decide(context) -> OrderIntent | None`.
- **Track A (default)**: rule-based (MA crossover, RSI, breakout, mean reversion)
- **Track B (ML)**: model lightgbm/scikit, fitur dari candles + likuiditas, dilatih offline
- **Track C (RL, eksperimental)**: reinforcement learning (stable-baselines3), action =
  {buy, sell, hold, close}; reward = risk-adjusted PnL; WAJIB lolos gerbang walk-forward
  + paper trading 10 hari kerja sebelum diusulkan live

### 3.3 Backtesting engine (jantung riset)
- Event-driven, **kode yang sama dengan live** (satu `decide()`, beda data source)
- Biaya realistis: spread dari modul likuiditas + komisi + slippage model
- Walk-forward validation + metrik: winrate, profit factor, max drawdown, Sharpe
- Output: laporan yang bisa dibaca owner (bukan angka mentah)

### 3.4 Execution layer
- State machine: `RECEIVED → RISK_PASS → SENT → FILLED/FAILED/STUCK`
- Semua transisi tercatat di `order_events` (append-only) — buku besar
- Risk gate (pure function): SL wajib, max volume, max drawdown harian (auto-halt),
  max order/menit, spread filter
- Reconciler: order SENT >60s → cek MT5 → resolve/STUCK
- Target latency: **<300 ms** (EA jalur lokal + websocket push + worker 50 ms)

### 3.5 Hermes layer (riset + operasi, bukan eksekusi)
- Skills: `trading-analysis`, `data-crawler`, `backtest-runner`, `strategy-author`
- Self-improvement loop mingguan: analisa event log + hasil → usulkan perbaikan
  → backtest → laporan ke owner → approve → deploy
- Cron harian: rekap P&L, kesehatan bridge, deteksi anomali → Telegram
- Garis merah: LLM tidak pernah pegang tombol order, tidak mengubah risk parameter

### 3.6 UI (4 halaman, standar awwwards/impeccable, mode Operate)
1. **Login**
2. **Dashboard**: harga live (websocket), posisi, form order (SL/TP wajib + konfirmasi),
   spread & sesi likuiditas terlihat
3. **Riwayat** = buku besar event log, bisa dibuka per order
4. **Strategy Lab**: daftar strategi (skill), hasil backtest, mode paper/live, kill-switch

## 4. Database (7 tabel)

`users`, `sessions`, `orders`, `order_events`, `positions`, `candles`, `settings`
(+ `liquidity_ticks`, `signals` di Phase 2)

## 5. Rencana eksekusi (sprint)

| Fase | Isi | Durasi | Done criteria |
|---|---|---|---|
| **P1 Core** | API + auth + state machine + event log + bridge baru + UI 4 halaman + 1 strategi rule | 5-6 hari | 1 order E2E <300ms tercatat lengkap di event log |
| **P2 Data & Riset** | crawler + backtester + modul likuiditas + strategy skill format | 4-5 hari | 1 strategi lolos backtest 2 tahun data dengan biaya realistis |
| **P3 ML/RL** | feature store + training + walk-forward + paper trading | 2-3 minggu | 1 model ML/RL lolos walk-forward + paper 10 hari |
| **P4 LLM & Ops** | self-improvement loop + cron laporan + anomaly detection | 3-4 hari | 1 laporan mingguan otomatis + 1 usulan strategi ter-approve |
| **P5 Cutover** | QA paritas penuh → pindah domain → v1 diarsipkan | 2 hari | QA lulus semua, fund.lumine.biz.id menjalankan v2 |

Tim: hf-backend (P1), hf-devops (P2 data/crawler), hf-frontend (UI sejak P1),
hf-qa (tiap fase), hf-ceo (koordinasi).

## 6. Metrik sukses (30 hari pasca-live)

- Eksekusi order <300 ms (p95)
- 0 order hilang / nyangkut (event log lengkap 100%)
- Uptime bridge >99,5%
- ≥1 strategi profitabel setelah biaya di paper trading 20 hari
- 1 siklus self-improvement yang menghasilkan perbaikan ter-approve

## 7. Non-goals (v2)

- Multi-broker, multi-aset (fokus XAUUSD + 1 broker)
- HFT mikrodetik / co-location
- Live trading sebelum P5 lulus QA & owner approve
- Copy trading / marketplance strategi
