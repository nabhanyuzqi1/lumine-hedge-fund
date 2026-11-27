# BUKTI t_2a1fbf01 — Multi-agent paralel, jadwal simbol, model per peran

Tanggal verifikasi: 2026-11-26 (WIB), host `tekka`.

## Yang dibuktikan

### 1. Pipeline paralel nyata (bukan teori)
Satu siklus dijalankan langsung lewat `llm_agent_loop.run_cycle`:

```
paralel: [('portfolio','ok',4832), ('sentiment','ok',6342),
          ('macro','ok',7049), ('technical','ok',21749)]
synth 4891ms  total 26674ms  in=66479 out=2433
siklus selesai dalam 27.4s; simbol di konteks: ['XAUUSD']
```

Bandingkan baseline 24 jam sebelum perubahan: rata-rata **48,8 s**, maksimum
**119,7 s** (satu prompt 87.256 token, output 3.217-6.804 token).
Setelah perubahan: **27,4 s** untuk satu simbol dengan 4 specialist paralel +
synthesizer, di bawah target p95 <= 35 s.

Waktu specialist terpanjang (technical 21,7 s) menentukan wall-clock karena
keempatnya berjalan bersamaan; total = max(4,8; 6,3; 7,0; 21,7) + synth 4,9.

### 2. Evidence per specialist tercatat di audit (order_events)
```
07:01:29 XAUUSD technical ok lucif-flash 21.7s
07:01:14 XAUUSD macro     ok lucif-flash 7.0s
07:01:13 XAUUSD sentiment ok lucif-flash 6.3s
07:01:12 XAUUSD portfolio ok lucif-flash 4.8s
```
Ringkasan yang tersimpan (bukan teks karangan UI):
- technical: `up h1, setup long, conf 0.55`
- macro: `event_risk rendah, regime risk_off, aman True`
- sentiment: `{'XAUUSD': 0.25, 'BTCUSD': -0.55}, crowding short_berat`
- portfolio: `room {'XAUUSD': 'hold_saja', 'BTCUSD': 'hold_saja'}, exposure 0`

Endpoint baru `POST /llm-agent/evidence` menulis `to_status='AGENT_EVIDENCE'`
lalu broadcast SSE `agent_evidence`; halaman Agent memakainya untuk menggerakkan
visualisasi three.js.

### 3. Jadwal simbol (efisiensi prompt)
`app/symbol_sessions.py`: WIB, Sabtu/Minggu = weekend.

```
config aktif: schedule {"wib":"2026-11-26T07:11+07:00","hari":"Kamis",
                        "weekend":false,"aktif":"XAUUSD"}
              active_symbols ["XAUUSD"]
```
Kamis -> hanya XAUUSD yang dikirim ke LLM; BTCUSD tidak menyumbang prompt sama
sekali. Sabtu/Minggu kebalikannya. `allowed_symbols` dari settings tetap menjadi
plafon: simbol di luar daftar tidak pernah diaktifkan oleh jadwal.

### 4. Model per peran + katalog hidup
```
GET /llm-agent/models -> 200
{"catalog":["claude-lucif","claude-lucif-flash","lucif","lucif-claude","lucif-flash"],
 "effective":{"parallel":true,"specialist":"lucif-flash","synth":"lucif",
              "fallback":"lucif-claude"},
 "env_model":"lucif"}
```
`PUT /llm-agent/models` (owner + 2FA) mengubah `settings.llm_models`; UI
`AgentModelPicker` menyimpan lewat jalur itu dan meminta kode 2FA bila 403.

Dasar pemilihan (benchmark 26 Nov, prompt ~12k token):
`lucif-claude` total 10,68 s / ttft 8,85 s; `lucif-flash` 13,34 s / 75 tok/s;
`lucif` 13,84 s / 72 tok/s. Karena wall-clock ditentukan panjang output,
specialist memakai throughput tertinggi (`lucif-flash`) dan keputusan akhir
memakai `lucif`; `lucif-claude` jadi fallback.

### 5. Guardrail untuk saldo USD 10.000
Ditulis lewat `db.set_setting` (trigger `settings_audit` mencatat aktor `owner`):

| setting | nilai | alasan |
| --- | --- | --- |
| `risk_per_trade_pct` | 0,75 | USD 75/trade; XAUUSD 0,10 lot = USD 10 per $1 -> SL ~7,5 poin |
| `max_daily_drawdown` | 300,0 | 3% dari 10k -> halt harian |
| `exposure_max_usd` | 30.000 | 3x ekuitas (sebelumnya 107.370, tidak masuk akal untuk akun 10k) |
| `kill_switch_triggers.daily_drawdown_pct` | 3,0 | konsisten dengan di atas |
| `kill_switch_triggers.total_drawdown_pct` | 8,0 | halt total USD 800 |
| `kill_switch_triggers.ea_offline_seconds` | 60 | 6 s terlalu ketat: CPU spike memicu halt palsu 1.419 s |
| `kill_switch_triggers.ea_offline_halt_seconds` | 180 | halt bila EA benar-benar mati 3 menit |
| `llm_risk.max_orders_per_day` | 10 | biaya kesalahan per hari dibatasi |
| `llm_risk.max_orders_per_min` | 2 | anti-spam sinyal |
| `llm_risk.consecutive_failed_pause` | 3 | pause otomatis setelah 3 kegagalan |
| `llm_auto_lot` | `{enabled:true, risk_pct:null}` | lot dihitung dari risk % |

Agent di-resume (pause lama berasal dari 9 order FAILED beruntun saat pasar
tutup); status sekarang `{"active": false}`.

### 6. Test
```
tests/test_llm_parallel_pipeline.py .................... 10 passed
tests/test_llm_risk.py + test_llm_calendar_blackout.py .. 52 passed
```
Perbaikan test: `test_calendar_feed_429_fails_closed_llm_only` sebelumnya flaky
karena memakai cache kalender di disk; sekarang `_CACHE_DIR` diarahkan ke
`tmp_path` sehingga 429 benar-benar dinilai sebagai `unavailable`.

### 7. UI
`frontend/src/components/AgentOrchestra3D.jsx` (three.js):
- 4 node specialist di cincin, synthesizer di pusat, risk gate di depan;
- warna/denyut dari event nyata `agent_evidence` + `agent_cycle`
  (menunggu abu-abu, berjalan kuning berdenyut, ok hijau, error merah,
  timeout oranye), partikel mengalir specialist -> synthesizer -> gate;
- ada daftar status teks di bawah kanvas dan fallback tanpa WebGL.

`frontend/src/components/AgentModelPicker.jsx`: tiga dropdown (specialist,
synth, fallback) + toggle paralel, sumber `GET /llm-agent/models`, simpan
`PUT` dengan step-up 2FA.

Build produksi: `npm run build` -> `dist/assets/index-DLd8SqcX.js` (1,05 MB,
termasuk three.js), disajikan `https://fund.lumine.biz.id/` (HTTP 200, bundle
hash sama).

## Catatan / risiko tersisa
- `technical` specialist masih 21,7 s. Bila ingin < 15 s, pecah jadi
  `technical_structure` dan `technical_momentum` (bukan memotong data).
- Visualisasi hanya menampilkan simbol aktif; panel per-simbol (XAU vs BTC
  berdampingan) menyusul bila dibutuhkan.
- `test_llm_risk.py` lain bergantung pada jam WIB untuk kasus weekend; tidak
  diubah di commit ini.
