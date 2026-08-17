# Evaluasi Chart Library: FCS Chart vs lightweight-charts (Lumine)

> Status: **RANCANGAN** — keputusan + roadmap
> Studi: `fcsapi/chart-js` v4.0.4 (MIT) — kloning 18 Aug 2026
> Konteks: chart pasar di frontend Lumine sekarang memakai **lightweight-charts** (TradingView, open-source)
> Dokumen terkait: `docs/15-implementation/EA-V5-WEBSOCKET-UI-DESIGN.md` (plan utama), `docs/10-frontend/design-tokens.md`

---

## 1. Ringkasan Keputusan

**TIDAK mengganti lightweight-charts.** FCS Chart tidak lebih baik untuk kasus Lumine — ia terikat format API FCS, tidak punya test suite, dan keunggulannya (60+ indikator built-in) tidak relevan karena Lumine menghitung indikator di backend (TA-Lib). Namun **3 fitur FCS layak diadopsi sebagai roadmap**: chart replay, heikin-ashi/hollow via transform, dan price-line TP/SL — dua di antaranya sudah didukung lightweight-charts secara native/transform.

---

## 2. FCS Chart — Hasil Studi Source (bukan hanya README)

### 2.1 Profil

| Item | Fakta (dari source) |
|------|---------------------|
| Lisensi | MIT, gratis, self-hostable |
| Ukuran | `src/fcsapi-chart.js` = **731 KB minified**, +172 chunk indikator/pattern/drawing |
| Test suite | **TIDAK ADA** — `package.json` → `"test": "echo No tests specified && exit 0"` |
| Dependency | Zero (pure JS) |
| Data source | Terikat **FCS API** (`https://api-v4.fcsapi.com`) + WS (`wss://ws-v4.fcsapi.com/ws`) |
| Mode gratis | `accessKey = "free_chart"` (ditemukan via base64 decode) → **batas 300 candle**, branding "Powered by vunelix.com" |
| Override | `apiUrl` / `socketUrl` adalah config merge `{...default, ...user}` → **bisa diarahkan ke backend sendiri** |

### 2.2 Protokol yang diharapkan (wajib ditiru backend kalau mau self-host)

1. **History**: `GET {apiUrl}/forex/history?symbol=X&period=1H&length=600&accessKey=...`
   → `{success: true, response: [{t, o, h, l, c, v}, ...]}`
2. **Search**: `GET https://api-v4.fcsapi.com/forex/search` (untuk symbol picker)
3. **Realtime**: WS `join_symbol {type:"join_symbol", symbol, timeframe}`, `leave`, `remove_all`
   → push candle `{t, o, h, l, c, v}`

### 2.3 Fitur yang dimiliki FCS (relevan untuk Lumine)

- 8 chart types: candlestick, bars, line, area, **hollow, heikin-ashi**, high-low, volume candles
- 60+ indikator built-in (RSI, MACD, BB, Ichimoku, VWAP, Supertrend, dsb) + pattern recognition (doji, engulfing, harami…)
- Drawing tools: trendline, Fibonacci, XABCD, shapes, text, **undo/redo (Ctrl+Z/Y)**, keyboard shortcuts
- **Chart Replay mode** (replay historis untuk backtest visual)
- **Horizontal Line API**: `addHorizontalLine({price, color, label, style})` → TP/SL/entry lines
- Multi-chart layout, screenshot/export image, timezone, dark/light theme, mobile responsive

---

## 3. Perbandingan untuk Kasus Lumine

| Kriteria | lightweight-charts (sekarang) | FCS Chart | Pemenang |
|----------|-------------------------------|-----------|----------|
| **Kualitas & maturity** | TradingView, dipakai jutaan situs, update rutin | Project kecil, minified, **tanpa test** | ✅ LWC |
| **Bundle size** | ~45 KB gzip | 731 KB + 172 chunk (harus tree-shake manual) | ✅ LWC |
| **Integrasi design tokens** | Sudah: `chart-theme.ts`, `chart-transform.ts` | Perlu adaptasi; default theme FCS | ✅ LWC |
| **Indikator** | Tidak built-in (dihitung backend TA-Lib) | 60+ built-in (tapi backend sudah hitung!) | ⚖️ LWC (indikator dari backend = single source of truth, konsisten dgn EA plan) |
| **Data source** | Murni client-side, data apa pun | Terikat format FCS API → **harus bangun adapter backend** | ✅ LWC |
| **Realtime** | `useMarketWS` → `/ws/market` sudah jalan | WS `join_symbol` format FCS → adapter lagi | ✅ LWC |
| **Drawing tools** | v5 primitives plugin (manual) | Built-in lengkap + undo/redo | ✅ FCS |
| **Chart replay** | Tidak ada built-in | Built-in | ✅ FCS |
| **Heikin-Ashi / hollow** | Tidak built-in, tapi = transform OHLC (mudah) | Built-in | ⚖️ FCS (murah ditiru) |
| **TP/SL price lines** | `createPriceLine` native | `addHorizontalLine` API | ⚖️ Setara |
| **Performa 60 FPS** | Dikenal sangat ringan | 731 KB engine, belum teruji | ✅ LWC |
| **Test & CI (filosofi Lumine)** | Dipakai di test suite existing | `"No tests specified"` — melanggar standar `docs/13-testing` | ✅ LWC |

**Verdict: lightweight-charts menang 8–0–3.** Keunggulan FCS (drawing tools, replay, heikin-ashi) tidak sebanding dengan biaya adopsi (adapter API FCS, bundle 731 KB, tanpa test, risiko maintenance project kecil).

---

## 4. Yang DIADOPSI ke Roadmap (ide fitur FCS, dikerjakan dengan LWC)

| Fitur | Cara (di lightweight-charts) | Prioritas | Masuk tahap |
|-------|------------------------------|-----------|-------------|
| **Heikin-Ashi / hollow candles** | Transform OHLC di `chart-transform.ts` (hitung HA: `close=(o+h+l+c)/4` dst) — murni fungsi, murah, testable | P2 | Frontend sprint berikutnya |
| **Chart Replay mode** (backtest visual) | Data bars sudah di backend (`get_bars`/seed) → scrub timeline + replay; LWC `setData` per step | P3 | Roadmap backtest visual |
| **TP/SL/Entry price lines** | `series.createPriceLine()` native (sudah didukung) — tinggal wire ke data posisi | **P1 (sudah ada rencana)** | Tahap T5 EA plan (level dari backend) |
| **Keyboard shortcuts chart** | Event listener container (←/→ scrub, +/- zoom) | P3 | Nice-to-have |
| **Export chart image** | LWC punya `chart.takeScreenshot()` | P2 | Mudah, berguna utk laporan |

**Tidak diadopsi:** 60+ indikator built-in (backend sudah punya TA-Lib — menambah indikator client = duplikasi & divergensi), symbol search FCS (Lumine punya katalog sendiri), pattern recognition (SMC/analyst AI di backend, bukan client-side JS).

---

## 5. Integrasi dengan Plan EA-V5 (referensi silang)

- **TP/SL/Entry lines** (P1) → sumber data level dari backend via `command`/`status` (lihat `EA-V5-WEBSOCKET-UI-DESIGN.md` §5.3 — highlight signal & level).
- **Heikin-Ashi** (P2) → konsisten dengan prinsip "EA tipis, backend hitung": transform dilakukan client-side murni visual, tidak memengaruhi data mentah.
- **Chart Replay** (P3) → memanfaatkan data historis yang sudah ada (`bars_1m` dll, lihat `docs/05-data/`), tidak butuh provider baru.

---

## 6. Kesimpulan

1. **Tetap lightweight-charts** — lebih ringan, matang, sudah terintegrasi design tokens & test suite Lumine, dan data pipeline sudah nyambung (`/ws/market` + backend TA-Lib).
2. **Jangan adopsi FCS Chart** — biaya adapter API + bundle besar + tanpa test, untuk fitur yang mayoritas bisa ditiru murah di LWC.
3. **Adopsi idenya, bukan library-nya**: heikin-ashi, replay mode, price lines, screenshot — masuk roadmap frontend di atas.
4. FCS Chart tetap layak dipantau sebagai referensi UX drawing tools/replay — bukan sebagai dependency.
