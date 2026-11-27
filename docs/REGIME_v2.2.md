# Market Regime Detection v1.0.0 (PRD v2.2 §6, t_f2v22a2)

Classifier deterministic berversi untuk filter kelayakan strategi. Modul
murni: `api/app/regime.py` (tanpa I/O, jam, RNG). Dipakai SAMA oleh paper
runner (live/paper) dan backtest (PRD §6.5), jadi label pada dataset yang
 sama selalu identik.

## Status

| Butir | Status |
| --- | --- |
| Versi classifier | `REGIME_VERSION = "1.0.0"` (di `app/regime.py`) |
| Parameter | `RegimeParams` frozen dataclass; semua ambang **[USULAN], BELUM DIKALIBRASI** (PRD §6.4) |
| Label dikeluarkan | `TREND_UP, TREND_DOWN, RANGE, HIGH_VOLATILITY, LOW_LIQUIDITY, UNKNOWN` |
| `NEWS_OR_EVENT_RISK` | **RESERVED - tidak pernah dikeluarkan** v1: belum ada kalender/sumber event tervalidasi (PRD §6.2 mensyaratkan sumber tervalidasi). Konstanta `NEWS_SOURCE_VALIDATED = False`. |
| Regime vs risk limit | Regime TIDAK mengubah risk limit (PRD §6.4). Modul regime tidak menyentuh `app.risk`; gate hanya filter entry. |
| Dampak regime filter vs baseline out-of-sample | Belum dievaluasi (butuh strategi yang mendeklarasikan ALLOWED_REGIMES + run OOS) - kartu evaluasi terpisah. |

## Pohon keputusan (prioritas tetap)

1. **Data quality gagal** → `UNKNOWN` (kondisi aman): bar `< min_bars`,
   bar belum closed, bar stale (> 2.5×tf + 60s), timestamp tidak naik
   ketat, harga non-finite/≤ 0, OHLC rusak, gap jam pasar > 15 menit atau
   > 5% menit pasar hilang, spread hilang/negatif, likuiditas tidak fresh
   atau stale > 120s. Gap akhir pekan/break harian XAUUSD **bukan** gap
   (mirror `app.data_quality`, dijaga sinkron oleh test).
2. **`LOW_LIQUIDITY`**: spread > max(2 × median15, absolut per simbol)
   ATAU tick rate < 5/menit (fitur live; absen = tidak memicu).
3. **`HIGH_VOLATILITY`**: vol percentile ≥ 0.90 ATAU ATR/median-TR ≥ 1.5
   (range expansion). Prioritas di atas trend: transisi flat→trend adalah
   ekspansi volatilitas.
4. **`TREND_UP` / `TREND_DOWN`**: ADX ≥ 25 DAN |slope MA50| ≥ 0.04 ATR/bar
   DAN close di sisi yang benar dari MA50.
5. **`RANGE`**: default bila data OK dan tidak ada rule lain terpicu.

## Fitur (semua dari bar CLOSED - tanpa look-ahead)

| Fitur | Rumus | Window |
| --- | --- | --- |
| Realized vol | std log-return close (sample) | 60 bar |
| Vol percentile | peringkat vol saat ini di series rolling vol | 150 titik × 60 bar |
| ATR | Wilder RMA dari true range | 150 bar |
| Range expansion | ATR / median TR window | 150 bar |
| ADX | Wilder standar (DX series → RMA) | 100 bar |
| MA slope | (MA50 kini − MA50 20 bar lalu) / (20 × ATR), ATR/bar | 50+20 bar |
| Spread | spread terkini, median 15m, p95 (opsional) | — |
| Tick rate | tick/menit dari feed (opsional, live-only) | 15 menit |
| Sesi | asia 21-07, london 07-12, london_ny 12-16, ny 16-21 UTC (mirror `app.ingest.session_of`, dijaga sync test) | — |

Volume candle TIDAK dipakai (runner mengisi volume=0; tidak tersedia
konsisten di backtest). `spread_p95` dan `tick_rate` = fitur pelengkap:
dilaporkan di `features`, memicu LOW_LIQUIDITY hanya tick rate, dan
ketidakhadirannya menurunkan confidence (×0.95; median15 hilang ×0.9)
TANPA mengubah label - inilah yang membuat definisi label backtest dan
live identik.

## Confidence

Skor komponen [0.5..1.0] saat rule terpicu (jarak terhadap ambang), lalu
dikali faktor ketersediaan fitur opsional, dibatasi [0,1], dibulatkan 4
desimal. `UNKNOWN` = confidence 0.0. Nilai ambang confidence untuk
keputusan **[USULAN]** - belum dikalibrasi (PRD §6.4); kalibrasi lewat
confusion matrix menyusul.

## Hysteresis / cooldown (anti flip-flop)

- Keputusan **dibekukan per bar**: memanggil ulang pada bar closed yang
  sama mengembalikan keputusan yang sama (idempoten; loop runner 15s
  tidak menghasilkan flip dalam bar).
- Ganti label butuh **2 bar konfirmasi** berturut-turut (`confirm_bars`)
  ATAU confidence ≥ label berjalan + 0.15 (`confidence_margin`) untuk
  ganti segera.
- Setelah pergantian, **3 bar cooldown** (`cooldown_bars`): hanya ganti
  lewat margin confidence.
- `UNKNOWN` dari data quality **selalu** lolos hysteresis (safety).
- State disimpan pemanggil (runner: in-memory per `SYMBOL:TF`, aman di-
  restart; backtest: variabel lokal). State JSON-serializable.

## Gate entry (PRD §6.2/§6.5)

`regime.permits_entry(label, allowed_regimes)`:

- `allowed_regimes` kosong → strategi tidak mensyaratkan regime → entry
  tidak diblokir regime (baseline tidak berubah).
- Non-kosong → label HARUS di dalam allowed DAN bukan `UNKNOWN`.
  `UNKNOWN` **selalu** memblokir (kondisi aman), bahkan bila seseorang
  mendaftarkan UNKNOWN di allowed.

Strategi mendeklarasikan lewat `ALLOWED_REGIMES = [...]` di modulnya, atau
`StrategySpec(allowed_regimes=[...])` di runner. Backtest memakai
`run_backtest(..., regime_filter=True, allowed_regimes=...)` dengan
classifier yang sama. Trade backtest membawa `regime` + `regime_confidence`
(RANGE saat `REGIME_OFF`); summary punya blok `regime` (labels_seen,
blocked_entries, breakdown per label).

## Recording (PRD §6.4)

Runner menulis `regime_observations` (kill-switch settings
`regime_detection_enabled = "off"`):

| context | Kapan | ref |
| --- | --- | --- |
| `PERIODIC` | sekali per bar closed baru per simbol | — |
| `SIGNAL` | strategi firing intent (termasuk saat diblokir gate) | strategy id |
| `ORDER` | order paper tercatat | paper_order id |
| `POSITION` | posisi terbuka, per bar closed | paper_order id |

## Integrasi

| Titik | File |
| --- | --- |
| Classifier murni | `api/app/regime.py` |
| Backtest gate + breakdown | `api/paper/backtest.py` (`regime_filter=True`) |
| Runner gate + recording | `api/paper/runner.py` (`tick_once`, `run_iteration`) |
| Test (53) | `api/tests/test_regime.py` |
| Stub strategi test | `api/tests/sbx_strategies/regime_stub*.py` |

Sync helper dengan modul live dijaga test: `_session_of` ↔
`app.ingest.session_of`, `_market_closed_minutes` ↔
`app.data_quality.market_closed_minutes`, `SPREAD_ABS_MAX` ↔
`app.data_quality.SPREAD_ABS_MAX`.

## Keterbatasan v1 (jujur)

- Ambang **belum dikalibrasi** (PRD §6.4) - nilai default [USULAN].
- ADX window 100 bar memakai RMA atas DX series; nilai bisa beda dengan
  platform charting yang memakai window penuh - tidak masalah untuk
  konsistensi backtest/live karena keduanya memakai modul ini.
- `tick_rate` hanya tersedia live (feed HFM); backtest memakai None
  (confidence ×0.95, label tidak berubah).
- Belum ada strategi yang mendeklarasikan ALLOWED_REGIMES - gate aktif
  tapi no-op sampai strategi regime-aware dibuat DAN dampaknya dilaporkan
  out-of-sample (PRD §6.5).
- Performa: ~5-10ms per klasifikasi (300 bar). Backtest regime_filter
  menambah biaya itu per bar - opsional, default mati.
