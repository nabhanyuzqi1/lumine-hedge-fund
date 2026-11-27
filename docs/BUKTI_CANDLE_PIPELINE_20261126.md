# BUKTI: candle pipeline, /market/status, gate 409 (26 Nov 2026)

Kartu: "Backend candle pipeline: bar native MT5, kolom source + cutover,
hentikan bar datar, GET /market/status, blokir order saat tutup".
Repo: `/home/tekka/fund2` (branch `master`, worktree kotor oleh kartu lain:
tidak ada commit, tidak ada revert).

## 1. Yang berubah (file)

| File | Isi perubahan |
| --- | --- |
| `api/app/market_status.py` (baru) | Resolver status pasar berlapis: laporan EA -> `market_sessions` -> bukti feed. `decide()` murni, `resolve()`, `closed_flag()`, `enforceable()`, `record_report()`, `persist_throttled()`, SSE `type='market'` saat status berubah. |
| `api/alembic/versions/p016_candle_source.py` (baru) | `candles.source TEXT NOT NULL DEFAULT 'legacy'` + index `idx_candles_source_ts (symbol, timeframe, source, ts)`. Additive, tanpa backfill tebakan. |
| `api/app/ingest.py` | Rantai rollup `M1->M5->M15/H1->H4->D1`; filter `volume > 0`; tulis `source='rollup'`; upsert tidak menimpa `source='ea'`; bar tick `source='ea'`; `feed_age_s()`; `_suppress_new_bar()` + `bars_suppressed_closed`. |
| `api/app/bridge.py` | `HeartbeatBody` menerima `market_status`, `market_close_reason`, `trade_mode`, `symbol_time`, `tick_age_s` (opsional). Heartbeat menyimpan status + SSE + persist throttled (best-effort). |
| `api/app/routes.py` | `GET /market/status`; cutover `GET /candles` (+`include_legacy=1`); gate `POST /orders` -> 409 `market_closed`. |
| `api/app/preflight.py` | Cek sesi memakai status yang sama; laporan EA CLOSED menggagalkan cek sesi (libur bursa/maintenance broker tidak ada di tabel jadwal). |
| `api/app/candle_rollup.py` | Docstring + log menyebut rantai penuh (bukan hanya M1->M5). |
| `api/tests/test_candle_source_cutover.py` (baru, 10 test) | Migrasi, cutover, include_legacy, cutover per (symbol,tf), rollup tidak menimpa EA, rollup abaikan volume 0, H4/D1, bar tick `source='ea'`. |
| `api/tests/test_candle_flat_bars.py` (baru, 6 test) | Tidak ada bar datar baru saat tick berhenti / pasar CLOSED; bar terakhir utuh; tick pertama sesi baru membuka bar; tidak ada bar hantu di DB. |
| `api/tests/test_market_status.py` (baru, 21 test) | `decide()` OPEN/CLOSED/UNKNOWN, weekend vs session, BTC 24/7, laporan EA menang, laporan basi diabaikan, shape kontrak, heartbeat opsional/legacy/nilai asing, SSE on-change, persist throttled, `enforceable()`. |
| `api/tests/test_market_gate_orders.py` (baru, 6 test) | 409 saat CLOSED (tanpa baris order), 201 saat OPEN, order agent/LLM juga 409, tanpa EA tidak memblokir, CLOSE/flatten tidak diblokir, pipeline tick tidak terganggu. |
| `api/tests/test_ingest.py` | 2 assertion hitungan rollup diperbarui (8 -> 10, 3 -> 5) karena rantai kini sampai H4/D1. Tidak ada kasus yang dihapus. |

## 2. Migrasi

```
$ cd api && .venv/bin/alembic current
p016 (head)
$ .venv/bin/alembic upgrade head     # idempotent, kolom + index sudah ada
```

Bukti skema + sebaran sumber (DB live `fund2`):

```
col: ('source', 'text', 'NO', "'legacy'::text")
idx: ['candles_pkey', 'idx_candles_source_ts']
ver: [('p016',)]
by source: [('legacy', 2344554), ('ea', 43986), ('rollup', 10)]
```

Bar lama tidak diubah (semua tetap `legacy`), penulis baru mengisi sendiri.

## 3. Bukti runtime (setelah `systemctl --user restart fund2-api`)

Restart: `Thu 2026-11-26 16:21:20 WIB`, `is-active` = `active`,
`GET /health` -> `{"ok":true,"subscribers":3,"env":"demo"}`.

```
GET /market/status?symbol=XAUUSD -> 200
{
  "symbol": "XAUUSD",
  "market_status": "OPEN",
  "market_close_reason": null,
  "trade_mode": "FULL",
  "last_tick_ts": "2026-11-26T09:21:26.680571+00:00",
  "last_tick_age_s": 7.4,
  "next_open_ts": null,
  "ea_seen_s": 1.7,
  "source": "ea"
}

GET /market/status?symbol=BTCUSD -> 200
{ "symbol": "BTCUSD", "market_status": "OPEN", "market_close_reason": null,
  "trade_mode": "FULL", "last_tick_age_s": 7.4, "next_open_ts": null,
  "ea_seen_s": 1.7, "source": "ea" }
```

EA sudah mengirim field baru, jadi `source='ea'` (lapisan terkuat).

```
GET /candles?symbol=XAUUSD&tf=M5&limit=5 -> 200
keys: ['candles', 'count', 'symbol', 'tf'] count: 5
  {'ts': '2026-11-26T09:00:00+00:00', 'open': 3570.54, 'high': 3572.28, 'low': 3569.89, 'close': 3572.01, 'volume': 259.0}
  {'ts': '2026-11-26T09:05:00+00:00', 'open': 3574.28, 'high': 3574.79, 'low': 3571.72, 'close': 3571.73, 'volume': 830.0}
  {'ts': '2026-11-26T09:10:00+00:00', 'open': 3571.8,  'high': 3573.63, 'low': 3570.52, 'close': 3571.89, 'volume': 1428.0}
  {'ts': '2026-11-26T09:15:00+00:00', 'open': 3571.99, 'high': 3573.46, 'low': 3569.28, 'close': 3572.83, 'volume': 587.0}
  {'ts': '2026-11-26T09:20:00+00:00', 'open': 3572.85, 'high': 3574.47, 'low': 3572.4,  'close': 3574.44, 'volume': 341.0}
ts naik: True | unik: True
keys bar: ['close', 'high', 'low', 'open', 'ts', 'volume']   # shape tidak berubah
```

Volume 259-1428 (kelas data baru). Seri legacy (volume 2-5) tidak ikut tercampur.
`include_legacy=1` -> 200 (param riset, shape sama).

```
POST /orders (status OPEN) -> 422
{"status":"FAILED", ..., "fail_reason":"rejected: kill-switch aktif ..."}
```

Order sampai ke lapisan risk (bukan 409): gate pasar tidak aktif saat OPEN.
Kill-switch aktif adalah kondisi lain di luar kartu ini.
Jalur 409 dibuktikan oleh `tests/test_market_gate_orders.py` (pesan + kode persis).

## 4. Efek data: bar datar

Sebelum: XAUUSD M1 1.086.148 bar, 353.500 (32%) flat O=H=L=C dengan volume 0;
M5 68.387/215.138 flat; hari 11-22 420/420 bar flat, 11-15 1440/1440.

Setelah restart (bar XAUUSD tersimpan sejak 24 jam terakhir, per sumber):

```
('M1',  'ea',     2303 bar, flat 0,   avg volume 467.9)
('M5',  'ea',      461 bar, flat 0,   avg volume 2337.9)
('M15', 'ea',      154 bar, flat 0,   avg volume 6999.4)
('H1',  'ea',       39 bar, flat 0,   avg volume 27641.9)
('D1',  'ea',        2 bar, flat 0,   avg volume 480693.0)
('H4',  'rollup',    4 bar, flat 0,   avg volume 1337.0)
('D1',  'rollup',    1 bar, flat 0,   avg volume 1094.0)
('M1',  'legacy',   31 bar, flat 26)   # sisa penulis lama, semua > 6 jam lalu
```

Tidak ada bar `legacy` baru dalam 6 jam terakhir: setiap penulis yang jalan
sekarang mengisi `source`, dan bar volume 0 tidak lagi naik ke TF tinggi.

Rantai rollup terbukti menulis H4/D1 (sebelumnya hanya dari seed EA):

```
H4 terakhir: 2026-11-26 15:00 rollup vol 4308 | 13:00 ea | 11:00 rollup | 09:00 ea | 07:00 rollup
D1 terakhir: 2026-11-26 07:00 rollup vol 1094 | 05:00 ea | 25 Nov 05:00 ea
```

## 5. Test

```
$ cd api && .venv/bin/python -m pytest -q
1676 passed, 5 warnings in 1051.92s (0:17:31)
EXIT=0
```

Run ini diulang setelah commit `a9abad2` (worker lain: isolasi registry
`market_status` lewat fixture autouse di `tests/conftest.py` + normalisasi
`report()`) supaya angka di atas mencerminkan tree terbaru.

Baseline sebelum kartu ini: `4 failed, 1614 passed` (3x `test_anomaly.py`,
1x `test_metrics.py`). Keempat kegagalan itu hilang di run akhir (bukan dari
perubahan kartu ini: `app/anomaly.py`/`app/metrics.py` tidak disentuh).

Subset baru + yang terkait (dijalankan terpisah, hijau):
`tests/test_candle_source_cutover.py test_candle_flat_bars.py test_market_status.py
test_market_gate_orders.py` -> 43 passed;
`test_ingest.py test_candles_api.py test_candles_timeframes.py test_orders_api.py
test_preflight_gate.py test_bridge.py test_migrations.py test_kill_switch.py` -> 176 passed.

## 6. Restart & service

```
systemctl --user restart fund2-api          -> active (16:21:20 WIB)
systemctl --user restart fund2-candle-rollup -> active (16:26:29 WIB)
journal: candle-rollup daemon aktif (siklus 60s)
```

Pre-restart import check (skill fund2-deploy):
`TELEGRAM_ALERTS_OFF=1 .venv/bin/python -c "import app.main, app.alerts, app.metrics, app.llm_agent_loop"` -> OK.

Catatan: `fund2-api` sudah pernah di-restart jam 15:18 WIB oleh proses lain
sebelum suite hijau, jadi kode kartu ini (saat masih setengah jadi) sempat
live lebih dulu. Restart resmi + verifikasi di atas dilakukan setelah
`pytest` hijau.

### File uncommitted milik worker lain yang ikut aktif setelah restart

`api/app/db.py`, `api/app/guardrail_ranges.py`, `api/app/llm_agent.py`,
`api/app/llm_risk.py`, `api/tests/test_*.py` (4 file), `deploy/fund2-alerts.service`,
`deploy/fund2-candle-rollup.service`, `ea/LumineEA.mq5`, `frontend/**`, `docs/**`.
Tidak ada yang di-revert atau di-commit.

## 7. Catatan / batasan

- Volume bar native EA (`CopyRates`, tick volume broker: H1 ~27rb, D1 ~480rb)
  beda skala dengan volume rollup (jumlah tick M1: H1 ~1,3rb). Ini konsekuensi
  "native menang": bar native adalah ground truth broker, rollup hanya pengisi
  gap. Histogram akan menunjukkan level berbeda pada bar native vs gap rollup.
- Cutover per (symbol, timeframe) memakai `min(ts)` bar non-legacy. Nilai live
  saat ini: XAUUSD M5 = 2026-11-02 12:40, M1 = 2026-11-20 23:57, H4 = 2026-01-01 17:00
  (WIB). Seri tanpa bar baru tetap menyajikan legacy (chart tidak kosong).
- `scripts/backfill_*.py` dan `api/paper/dukascopy.py` masih menulis dengan
  default `legacy` (di luar scope kartu ini): hasilnya benar (bukan data baru
  pipeline) tapi tidak akan tampil di chart default.
- Gate 409 hanya aktif bila `market_status.enforceable()` (EA terhubung segar).
  Tanpa EA tidak ada yang bisa mengeksekusi order, jadi penolakan berbasis jam
  dinding saja akan mengunci order sah (mis. suite test di jendela tutup).
