# Rancangan: LumineEA v5 — WebSocket Transport + UI Chart "Lumine" + Multi-EA

> Status: **RANCANGAN** (belum implementasi)
> Referensi: `docs/08-trading/mt5-integration.md` (Redis bridge v1), `docs/09-api/sse-api.md` + `backend/src/lumine/api/routers/ws.py` (WS transport backend), `docs/10-frontend/design-tokens.md` (warna/UI), skill `lumine` (21 pitfalls EA), `docs/15-implementation/CHART-LIBRARY-EVALUATION.md` (chart frontend: FCS vs lightweight-charts)
> Studi source: mobjoy0/mt5-bridge, niiisho/TradingView-MT5-Bridge, akivajp/mt5-bridge (fork niiisho), api2trade quickstart, ding9736/MT5BridgeAPI, fcsapi/chart-js

---

## 1. Tujuan & Lingkup

1. **Transport utama EA → backend menjadi WebSocket** (bukan polling HTTP 1 detik), dengan fallback otomatis ke HTTP polling yang sudah terbukti jalan.
2. **EA mendapat visual "Lumine banget"**: theme chart custom (background, warna candle bull/bear), panel UI institusional sesuai design tokens Lumine, warna status semantik.
3. **Menjawab skenario multi-EA / multi-MT5** streaming simbol sama (XAUUSD): dedup, leader election, dan konflik data — dirancang dari awal, bukan ditambal.
4. Mengadopsi bagian yang **terbukti berguna** dari 5 repo bridge; menolak yang tidak cocok dengan arsitektur Lumine (jelaskan alasannya).

Prinsip desain (dari CLAUDE.md): EA = *data feed + eksekusi + visual tipis*; backend = komputasi & AI. EA **tidak** menghitung indikator berat — cukup render hasil keputusan backend (warna candle, level, signal).

---

## 2. Adopsi dari 5 Repo Bridge — Matriks Keputusan

| # | Repo | Yang BERGUNA & diadopsi | Yang TIDAK diadopsi + alasan |
|---|------|------------------------|------------------------------|
| 1 | **mobjoy0/mt5-bridge** | (a) WebSocket handshake + text-frame encoding di MQL5 (`WebSocketLib.mqh`) — basis untuk WS client di EA. (b) Arsitektur REST + WS paralel pada port beda — model channel separation. (c) Tracking toggle (`track/prices`, `track/ohlc`) → pola subscribe dinamis. (d) Docker MT5 + VNC — sudah dimiliki Lumine (`lumine-mt5`). | EA sebagai **WS server** (listen port 8890) — salah arah untuk Lumine: EA di balik Caddy/NAT, backend harus connect keluar. Desain kita: EA = WS **client** ke backend. |
| 2 | **niiisho/TradingView-MT5-Bridge** | (a) Pola **ack/processed** (`signal` → `processed`) — idempotensi command, mencegah eksekusi ganda. (b) `WebRequest` polling JSON sebagai fallback transport — sudah dipakai Lumine. (c) "Signal Rejection" (tolak refresh/false signal) → dedup berbasis ID. | Chrome extension scraping TradingView DOM — bukan jalur institusional, rapuh terhadap update TradingView. Tidak relevan untuk feed harga; hanya untuk manual signal. |
| 3 | **akivajp/mt5-bridge** | Fork identik niiisho — **tidak ada nilai tambah**. | — |
| 4 | **api2trade quickstart** | (a) Envelope REST konsisten + kode operasi 0–5 (Buy/Sell/Limit/Stop). (b) Contoh WebSocket quote streaming (`wss://.../stream?api_key=&id=`) — pola auth via query param pada WS. (c) JSON payload minimal (symbol, operation, volume, SL/TP). | Hosted third-party SaaS (kredensial broker dikirim ke cloud mereka) — melanggar prinsip keamanan Lumine (credentials stay on machine). |
| 5 | **ding9736/MT5BridgeAPI** | (a) **Pub/Sub topic** (`TICK.<symbol>`) + subscribe/unsubscribe dinamis — pola stream terbaik untuk multi-simbol. (b) **ZeroMQ ZAP + Curve25519** — inspirasi: koneksi EA harus terautentikasi (HMAC token), bukan open socket. (c) Config JSON eksternal + hot-reload — pola konfigurasi port/key. (d) Heartbeat keep-alive + connection status monitoring. (e) Client Python reference + test suite. | ZeroMQ itu sendiri: dependency DLL (`libzmq.dll`, `libsodium.dll`) di Wine container = kompleksitas ekstra tanpa keuntungan vs WebSocket native. EA source hanya `.ex5` (tidak terbuka) — kita tulis sendiri. |

**Keputusan arsitektur transport:** WebSocket (RFC 6455) — karena (1) backend `ws.py` sudah ada, (2) browser/frontend native support, (3) tanpa dependency DLL eksternal, (4) Caddy reverse-proxy sudah menangani upgrade WS (terbukti di route `/novnc/websockify`).

---

## 3. Kendala Teknis MQL5 yang Menentukan Desain

> ⚠️ Fakta dari kode EA existing (header `LumineEA.mq5`):
> `// Transport: HTTP polling (bypass demo account socket block)`

1. **`WebRequest()` = HTTP/HTTPS saja** — tidak bisa WebSocket, tidak bisa custom headers untuk WS upgrade, butuh whitelist URL di Tools → Options (di Wine container di-set via config).
2. **`SocketCreate()`/`SocketConnect()`** — satu-satunya jalan WebSocket di MQL5 (manual handshake + frame). **Pada akun demo beberapa broker/metaquotes, koneksi socket keluar diblokir** (inilah kenapa LumineEA v1–v4 memakai HTTP polling).
3. Konsekuensi desain: **dual-transport** — EA coba WebSocket dulu; jika socket block / gagal handshake → **fallback otomatis ke HTTP polling** yang sudah jalan. Tidak ada single point of failure.
4. **Tidak ada Strategy Tester untuk socket** — semua pengujian WS di demo/real account, bukan di tester.
5. MQL5 tidak punya API pewarnaan **per-candle** — hanya global `CHART_COLOR_CANDLE_BULL/BEAR`. Warna candle "custom" = tema global + highlight objek untuk bar signal (detail §5).

---

## 4. Arsitektur WebSocket — EA ⇄ Backend

### 4.1 Topologi

```
┌─────────────┐   wss://lumine.biz.id/ws/ea?token=...   ┌─────────────┐
│  MT5 (Wine) │ ──────────────────────────────────────▶ │   Caddy     │
│  LumineEA   │ ◀────────────────────────────────────── │ (reverse    │
│  v5 (WS     │   frame JSON: command/ack/result/status │  proxy, WS  │
│  client +   │                                         │  upgrade)   │
│  HTTP fallback)                                       └──────┬──────┘
└─────────────┘                                                │ :8000
                               ┌────────────────────────────────┘
                               ▼
                     ┌──────────────────┐   Redis pub/sub   ┌──────────────┐
                     │  FastAPI /ws/ea  │ ─────────────────▶ │ SSEPublisher │
                     │  /ws/market (lama)                   │ (market)     │
                     └──────────────────┘                   └──────┬───────┘
                                                                   ▼
                                                       Frontend useMarketWS
                                                       (sudah jalan, 17 Aug)
```

**Alasan EA = WS client (bukan server):**
- EA di dalam Wine container di VPS, di belakang Caddy — membuat EA listen port = perlu expose port + NAT + firewall; rapuh.
- Backend sudah punya endpoint WS + auth (HMAC/session). EA connect keluar seperti HTTP polling sekarang, hanya beda protokol.
- Satu arah koneksi keluar = satu aturan firewall.

### 4.2 Endpoint & Auth

| Item | Nilai |
|------|-------|
| URL | `wss://lumine.biz.id/ws/ea` (Caddy `handle /ws/ea/*` → `reverse_proxy api:8000`) |
| Auth | Query param `?token=` — HMAC-signed, expiry 60s, dari REST `/api/v1/ws-token` (pola yang sama dengan `/ws/market`; EA minta token via `WebRequest` HTTP dulu, lalu connect WS) |
| Instance ID | `?instance_id=ea-<hostname>-<account>` — unik per EA, dipakai untuk dedup & leader election (§6) |
| Header EA | `ea_build`, `ea_version` (sudah ada di status push) |

### 4.3 Protokol Frame (JSON, text frame UTF-8)

Semua pesan = satu envelope konsisten (adopsi dari api2trade + ding9736 + skema Redis existing):

```json
{
  "v": 1,
  "type": "tick | command | result | status | seed | ack | error | heartbeat",
  "id": "<uuid>",
  "ts": 1755400000,
  "instance_id": "ea-1",
  "data": { "...": "schema per type" }
}
```

| type | Arah | Data | Catatan |
|------|------|------|---------|
| `tick` | EA → BE | `{symbol, bid, ask, timestamp, equity, balance, margin}` | Sama dengan payload HTTP `/ticks` sekarang — **backend tidak perlu adaptor** |
| `command` | BE → EA | `{command_id, action, symbol, volume, sl, tp, idempotency_key}` | Schema identik skema Redis `mt5:commands` |
| `ack` | EA → BE | `{command_id, status: "received"}` | Idempotensi: EA ACK sebelum eksekusi (adopsi niiisho `processed`) |
| `result` | EA → BE | `{id, order_id, status, ticket, fill_price, error_code}` | Identik `BuildResultJson` existing |
| `status` | EA → BE | status/equity/positions snapshot (interval 5s) | Menggantikan push status HTTP |
| `seed` | EA ↔ BE | `{symbol, timeframe, from, to, bars:[...]}` | Chunk seed via WS (1 chunk/OnTimer, tetap non-blocking) |
| `heartbeat` | EA ↔ BE | `{ts}` | Ping/pong 5s (adopsi ding9736) |
| `error` | dua arah | `{code, message}` | |

### 4.4 Implementasi MQL5 (yang harus ditulis)

1. `ws_client.mqh` — handshake client (kirim `GET /ws/ea?token=...` + `Sec-WebSocket-Key` random base64, parse `101 Switching Protocols`), SHA1+base64 accept key (pola `WebSocketLib.mqh` mobjoy0 dibalik arahnya), encode/decode frame (masking client→server wajib).
2. `SocketCreate`/`SocketConnect`/`SocketSend`/`SocketReceive` non-blocking di `OnTimer` (pola sama dengan polling sekarang — OnTimer 1s, bukan OnTick, karena feed pause).
3. Reconnect: backoff eksponensial (reuse `g_backoff` existing), max 60s.
4. **Fallback**: jika `SocketConnect` gagal dengan error socket-block (`error 5270`/`-1` pattern yang sudah terdeteksi) atau WS handshake gagal 3× berturut → `g_transport = HTTP` → semua payload via `WebRequest` seperti sekarang. Coba balik ke WS tiap 5 menit (probe ringan).

### 4.5 Perubahan Backend

| File | Perubahan |
|------|-----------|
| `backend/src/lumine/api/routers/ws.py` | Tambah endpoint `/ws/ea` (auth token HMAC + instance_id), loop `receive` command → publish ke EA, `send` tick/result dari subscriber Redis |
| `backend/src/lumine/api/routers/ws_token.py` (baru) | REST `/api/v1/ws-token` — HMAC token 60s untuk EA & frontend (frontend sudah punya, refactor jadi shared) |
| `backend/src/lumine/trading/market_service.py` | Tambah `ea_registry`: map `instance_id → (symbol, last_seen, is_leader)` — basis leader election (§6) |
| `backend/src/lumine/api/sse/publisher.py` | Publisher EA-channel → frontend channel (`tick_update` tetap format lama → **frontend tidak berubah**) |
| Caddy `Caddyfile.prod` | Route `handle /ws/ea/* { reverse_proxy api:8000 }` (WS upgrade otomatis) |

**Kontrak ke frontend TIDAK berubah** — frontend tetap pakai `/ws/market` dengan envelope `{event: tick_update, data: {tick}}` (lihat `_serialize_event`). EA transport internal boleh berubah kapan saja tanpa sentuh frontend.

---

## 5. UI Chart & Panel EA — "Lumine Banget"

### 5.1 Design Tokens (salin dari `frontend/src/index.css` — dark mode)

| Token | Hex | Penggunaan di EA |
|-------|-----|------------------|
| abyss | `#070b12` | Background chart utama |
| bg | `#0b0f17` | Background panel |
| raised | `#0f1522` | Header panel / section |
| overlay | `#131b2b` | Card dalam panel |
| line | `#1c2534` | Border panel |
| ink | `#e8eef7` | Teks utama |
| ink-dim | `#a7b3c5` | Teks sekunder |
| ink-faint | `#6d7c92` | Label/unit |
| accent | `#4d8dff` | Aksen (judul, tombol aktif) |
| up | `#34d399` | Candle bullish, profit, ONLINE |
| down | `#f0555b` | Candle bearish, loss, OFFLINE |
| warn | `#ffb020` | Seed aktif, warning |
| cyan | `#22d3ee` | Info, WS connected |

### 5.2 Theme Chart (di `OnInit` + toggle)

```mql5
ChartSetInteger(0, CHART_COLOR_BACKGROUND, 0x0B0707);   // #070b12
ChartSetInteger(0, CHART_COLOR_FOREGROUND, 0xF7EEEF);  // #e8eef7 (axes/labels)
ChartSetInteger(0, CHART_COLOR_GRID,       0x222115);  // #1c2534
ChartSetInteger(0, CHART_COLOR_CHART_UP,    0x99D334); // #34d399
ChartSetInteger(0, CHART_COLOR_CHART_DOWN,  0x5B55F0); // #f0555b
ChartSetInteger(0, CHART_COLOR_CANDLE_BULL, 0x99D334); // up
ChartSetInteger(0, CHART_COLOR_CANDLE_BEAR, 0x5B55F0); // down
ChartSetInteger(0, CHART_COLOR_CANDLE_BULL_BODY, 0x99D334);
ChartSetInteger(0, CHART_COLOR_CANDLE_BEAR_BODY, 0x5B55F0);
ChartSetInteger(0, CHART_COLOR_VOLUME, 0x22D3EE);      // cyan volume
ChartSetInteger(0, CHART_SHOW_GRID, false);
ChartSetInteger(0, CHART_SHOW_PERIOD_SEP, false);
```

> Catatan BGR: MT5 pakai format `0xBBGGRR` (bukan RGB). Contoh: `#34d399` → RGB(0x34,0xd3,0x99) → BGR `0x99D334`. **Pitfall umum** — harus pakai konversi BGR, kalau tidak warna kebalik.

### 5.3 Warna Candle "Custom" (jawaban: apa yang mungkin di MT5)

MT5 **tidak punya API per-candle coloring** — `CHART_COLOR_CANDLE_BULL/BEAR` berlaku global untuk semua candle. Strategi yang feasible:

1. **Tema global** (§5.2) — semua candle bull/bear pakai warna Lumine. Ini yang "custom" secara visual.
2. **Highlight bar signal** (dari backend/AI): gambar objek per bar penting, bukan mewarnai ulang semua candle:
   - `OBJ_RECTANGLE` tipis (semi-transparent `clrNONE` fill + border accent) di area bar → menandai bar signal BUY/SELL.
   - `OBJ_ARROW` (236 ▲ / 234 ▼) + label `OBJ_TEXT` di atas/bawah bar → signal entry.
   - `OBJ_TREND` putus-putus → level SL/TP aktif.
3. **Batas realistis**: jangan gambar ulang ribuan candle via objek (bobot OnTimer). Maksimal 10–20 objek highlight + level. Chart tetap candle native dengan tema.

> **Keputusan desain**: indikator teknikal (EMA/RSI/ATR dsb) **TIDAK dihitung di EA**. Perhitungan tetap di backend (`FeatureProvider` TA-Lib), EA hanya menggambar hasil (level, signal, warna) yang dikirim backend via `command`/`status`. Ini menghindari divergensi EA vs backend (satu source of truth) dan menjaga EA tipis.

### 5.4 Panel UI v5 (upgrade dari panel v4)

Layout (260px → **340px** lebar, kiri-atas, `CORNER_LEFT_UPPER`):

```
┌────────────────────────────────┐
│ ● LUMINE  EA v5    build 20260818 │ ← header: bg raised, aksen accent, dot status
│ ws: CONNECTED · http: fallback   │ ← cyan (ws) / warn (http) / down (offline)
├────────────────────────────────┤
│ XAUUSD         bid 3350.42      │ ← ink, tabular
│                ask 3350.58      │
│ spread: 1.6   tick: 12,483      │
│ session H: 3351.20 L: 3348.10   │ ← up/down colored
├────────────────────────────────┤
│ EQUITY  12,450.10               │ ← ink-bold
│ BALANCE 12,000.00  margin 450   │
│ NET P&L +450.10  [+3.90%]       │ ← up/down colored
├────────────────────────────────┤
│ seed M1: 87% ████████░░ 1234/1420│ ← progress warn
│ leader: ✓ this instance         │ ← cyan/ink (multi-EA, §6)
│ cmd queue: 3 · last cmd: ack ✓  │
├────────────────────────────────┤
│ [SEED]  [STATUS]  [WS]  [HIDE]  │ ← buttons: accent bg / raised bg
└────────────────────────────────┘
```

Komponen: `OBJ_RECTANGLE_LABEL` (panel bg + section separators), `OBJ_LABEL` (teks), `OBJ_BUTTON` (4 tombol), `OBJ_EDIT` (read-only, untuk teks dengan font mono). Font: `Consolas`/`Courier New` untuk angka (tabular), ukuran 9–10.

Perubahan kode: `CreatePanel()` v5 + `UpdatePanel()` (update warna status dot: up=ws ok, warn=http fallback, down=offline). Tombol baru `WS` (toggle paksa transport / reconnect manual).

---

## 6. Skenario Multi-EA / Multi-MT5 Streaming Simbol Sama (XAUUSD)

### 6.1 Masalah yang Muncul

| Masalah | Contoh |
|---------|--------|
| **Duplikasi tick** | 2 EA kirim tick XAUUSD → bar builder backend meng-aggregate 2× (bar M1 ganda, volume 2×) |
| **Konflik data** | Broker A bid 3350.42 vs broker B 3350.47 → harga melompat-lompat tergantung EA mana yang keburu |
| **Eksekusi ganda** | 1 command dikirim ke 2 EA → 2 order terbuka (duplikat posisi!) |
| **Status ambigu** | equity/positions snapshot dari 2 akun berbeda tercampur di dashboard |

### 6.2 Desain: Source Registry + Leader Election (di backend)

```
ea_registry (Redis, TTL 15s, renew tiap 5s):
  key:   ea:instance:<instance_id>
  value: {symbols:["XAUUSD"], account, broker, is_leader: bool, last_seen, ws: connected}
  key:   ea:leader:<symbol>   → instance_id  (dipakai hanya 1 EA per simbol)
```

1. **Setiap EA register** dengan `instance_id` unik (input `InpInstanceID`, default `ea-<AccountInfoInteger(ACCOUNT_LOGIN)>`).
2. **Leader election per simbol** (Redis `SETNX` + TTL lease, pola yang sudah ada di Redis roles):
   - EA pertama yang register untuk XAUUSD → leader, `is_leader=true`, streaming tick **aktif**.
   - EA kedua+ → standby: tick tetap dikirim (untuk health check), tapi ditandai `standby:true`; backend **mengabaikan** tick standby untuk bar builder.
   - Lease TTL 15s diperpanjang tiap 5s (heartbeat). Leader mati → TTL expire → EA standby otomatis promote (failover < 15s).
3. **Command routing**: command queue tetap `mt5:commands` (BRPOP) — tapi hanya **leader** yang boleh eksekusi order. Standby menerima command tapi balas `error code=NOT_LEADER`, command di-requeue. Idempotency key (`command_id`) menjamin tidak ada eksekusi ganda bahkan saat failover (adopsi niiisho ack/processed + skema Redis existing).
4. **Bar builder backend**: hanya consume tick dengan `leader:true`. Jika 2 broker beda harga → gunakan harga leader; standby hanya cadangan.

### 6.3 Konfigurasi (input EA baru)

```mql5
input string InpInstanceID    = "";     // kosong → auto ea-<login>
input bool   InpForceLeader   = false;  // paksa leader (VPS utama); false = election normal
input bool   InpEnableWS      = true;   // WS transport; false = HTTP polling saja
input int    InpLeaderTTL     = 15;     // detik lease kepemimpinan
```

### 6.4 Matriks Perilaku

| Situasi | Perilaku |
|---------|----------|
| 1 EA (VPS utama) | Auto jadi leader, `InpForceLeader=true` opsional |
| 2 EA, leader hidup | Standby stream tick (health), backend pakai tick leader |
| Leader mati | TTL 15s → standby promote → tick bar builder lanjut tanpa putus |
| Leader & standby beda broker | Harga pakai leader; perbedaan spread tercatat di `ea_registry` untuk TCA/audit |
| 2 EA eksekusi command sama | Idempotency key `command_id` → order kedua ditolak backend |

---

## 7. Roadmap Implementasi (Urutan)

| Tahap | Isi | Kriteria selesai |
|-------|-----|------------------|
| **T1** | `ws_client.mqh` (handshake + frame) + endpoint `/ws/ea` backend + Caddy route | EA connect WS, heartbeat bolak-balik, reconnect + backoff |
| **T2** | Migrasi `tick`/`status`/`result` ke WS; HTTP fallback otomatis | No tick loss saat WS mati (bandingkan counter tick HTTP vs WS) |
| **T3** | `command` via WS (BE→EA) + `ack` idempotensi | Satu command → satu eksekusi, ack tercatat |
| **T4** | Theme chart Lumine + panel v5 | Screenshot chart: bg abyss, candle up/down, panel per §5.4 |
| **T5** | Highlight signal/level dari backend (OBJ_RECTANGLE/ARROW/TREND) | Signal bar tampil di chart saat backend kirim status |
| **T5b** | Frontend: TP/SL/Entry price lines via `createPriceLine` (level dari backend) + Heikin-Ashi transform (lihat `CHART-LIBRARY-EVALUATION.md` §4) | Price lines tampil di chart frontend; toggle HA/hollow |
| **T5c** | Frontend: chart replay mode (scrub historis dari `bars_*`) + export image | Replay jalan untuk backtest visual |
| **T6** | Multi-EA: registry + leader election + dedup bar builder | Uji 2 EA (lokal + VPS) stream XAUUSD → bar M1 tidak ganda, failover < 15s |
| **T7** | Test suite: contract test WS (backend), smoke di demo account | CI hijau + `vps_smoke.py` extended |

**Pitfall yang wajib dijaga (dari skill lumine):**
- `OnTimer` 1s untuk semua I/O (jangan OnTick — feed pause = EA mati).
- BGR vs RGB pada warna (`0xBBGGRR`).
- Whitelist URL `WebRequest` tetap dibutuhkan untuk fallback + minta ws-token.
- Result queue existing JANGAN dihapus saat migrasi — WS result gagal → fallback queue (uang tidak boleh hilang).
- `ea_build __DATE__` → tetap string-safe (pitfall integer) — tambahkan juga `ea_build_ws` untuk build WS layer.
- Demo account socket block: uji WS di demo dulu; jika block → fitur jalan di mode HTTP fallback (fitur tidak hilang, hanya transport).

---

## 8. Pertanyaan "Apakah Perlu Indikator Teknikal di EA?" — Jawaban Desain

**Tidak dihitung di EA, ya digambar di EA** (prinsip single source of truth):

| Layer | Hitung | Gambar |
|-------|--------|--------|
| Backend (TA-Lib) | EMA, RSI, ATR, VWAP, dsb | — |
| EA | spread, session H/L, tick count (lokal saja) | Hasil backend: level SL/TP, zona signal, warna tema |
| Frontend (lightweight-charts) | — | Indikator penuh + chart interaktif |

Alasan:
- **Divergensi**: kalau EA hitung EMA sendiri, bisa beda dengan backend (bar close vs tick) → keputusan AI vs visual EA tidak konsisten.
- **EA tipis**: EA di Wine + socket/HTTP, bukan tempat komputasi; jaga determinisme & auditability (evidence capital).
- **Panel EA cukup menampilkan** angka penting (equity, spread, session H/L) — sudah ada di v4, di-upgrade styling-nya saja.

---

## 9. Ringkasan Adopsi (checklist final)

- [x] WebSocket EA→backend (mobjoy0 frame lib + api2trade auth pattern + ding9736 heartbeat) dengan fallback HTTP
- [x] Ack/idempotensi command (niiisho)
- [x] Pub/Sub + subscribe dinamis (ding9736) — via Redis publisher existing, frontend tak berubah
- [x] Theme chart Lumine + panel v5 (design tokens frontend)
- [x] Multi-EA leader election + dedup (registry Redis)
- [ ] Implementasi T1–T7 (belum dikerjakan — menunggu approval rancangan)
