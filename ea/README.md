# LumineEA.mq5 — kontrak bridge (v5.10)

Ringkas: EA ini satu-satunya penulis data pasar dari MT5 ke API (`/bridge/*`).
Dokumen ini mencatat kontrak yang **dipakai EA sekarang**, khususnya tambahan
v5.10 (bar native per TF, status market eksplisit, kegagalan 10018).

## 1. Heartbeat — `POST /bridge/heartbeat`

Dikirim dari `OnTimer` setiap `InpHeartbeatSec` (default 2 dtk), **satu request
per slot simbol** (slot 0 = simbol chart, sisanya `g_seedSymbols`), bukan hanya
`_Symbol`. Tetap dikirim walau tidak ada tick: market tutup, akhir pekan, atau
feed macet.

```json
{
  "ts": 1795000000,
  "symbol": "XAUUSD",
  "bid": 3565.97, "ask": 3566.27, "spread": 0.30,
  "ea": "v5",
  "market_status": "OPEN",
  "market_close_reason": "",
  "trade_mode": "FULL",
  "trade_enabled": true,
  "symbol_time": 1794999998,
  "tick_age_s": 2
}
```

| Field | Nilai | Sumber |
| --- | --- | --- |
| `ts` | epoch detik UTC | `TimeGMT()` |
| `symbol` | nama kanonik (`XAUUSD`, `BTCUSD`) | `NormalizeSymbol` |
| `market_status` | `OPEN` \| `CLOSED` | `EvalMarketStatus()` |
| `market_close_reason` | `""` saat OPEN; `weekend` \| `session` \| `holiday` \| `broker` \| `no_data` saat CLOSED | idem |
| `trade_mode` | `FULL` \| `LONGONLY` \| `SHORTONLY` \| `CLOSEONLY` \| `DISABLED` | `SYMBOL_TRADE_MODE` |
| `trade_enabled` | bool, turunan `trade_mode` (FULL/LONGONLY/SHORTONLY) | idem |
| `symbol_time` | epoch detik **jam server** (0 = belum ada quote) | `SYMBOL_TIME` |
| `tick_age_s` | `TimeTradeServer() - symbol_time`, `-1` = tidak diketahui | dihitung EA |

Urutan keputusan status (berhenti di aturan pertama yang cocok):

1. `SYMBOL_TRADE_MODE == DISABLED` → `CLOSED` / `broker`
2. retcode 10018 dalam `InpClosedHoldSec` terakhir → `CLOSED` / `broker`
3. jadwal `SymbolInfoSessionTrade` menutup simbol → `CLOSED` / `weekend`
   (Sabtu-Minggu), `holiday` (hari kerja tanpa sesi), `session` (di luar jam sesi)
4. `tick_age_s > InpTickStaleSec` (default 300) atau belum ada tick →
   `CLOSED` / `no_data`
5. selain itu → `OPEN`

Kalau broker tidak menyediakan jadwal sesi (0 sesi sepekan), aturan 3 dilewati
dan status jatuh ke aturan 4 (heartbeat tetap mengalir).

Bid/ask diambil dari simbol **broker** (`g_slotBroker`), jadi simbol ber-prefix
(`#BTCUSD`) tidak lagi mengirim harga 0.

## 2. Candle bar native per TF — `POST /bridge/tick`

Bentuk body tidak berubah: `{symbol, ticks:[...], candles:[...]}`. Timeframe
kanonik: `M1`, `M5`, `M15`, `H1`, `H4`, `D1`; `ts` = waktu buka bar **UTC
eksplisit** (`YYYY-MM-DDThh:mm:ss+00:00`), sama seperti jalur seed.

Pemicu: `iTime(sym, tf, 0)` berubah (dicek `InpBarPollMs`, default 1 dtk, dari
`OnTick` **dan** `OnTimer`). Saat bar baru muncul EA mengirim **dua** candle:

* `shift=1` — bar yang baru tutup, OHLCV final;
* `shift=0` — bar berjalan (hanya bila `market_status == OPEN`).

Semua harga berasal dari `CopyRates` (Bid-based, jam server broker); tidak ada
pencampuran Ask/Last dan tidak ada sampling tick. Bar dengan `tick_volume == 0`
(tidak ada tick sama sekali, mis. akhir pekan atau bar kosong) **dilewati** —
EA tidak pernah mengarang bar `O=H=L=C`.

Kalau request gagal, bar tidak dimajukan dan dicoba ulang maksimal 1x per 5 dtk
(bukan loop ketat); log kegagalan dibatasi 1 baris per menit per simbol.

Seed historis (`InpSeedHistory`) tidak berubah: pagination `CopyRates` 6 TF,
nama TF lowercase (`1m`..`1d`) yang dinormalisasi API ke kanonik.

## 4. Polling command — kenapa TIDAK 100 ms lagi (v5.10)

Backend memaksa long-poll minimal 5 detik (`BRIDGE_POLL_MIN_S = 5.0` di
`api/app/bridge.py`; `timeout_s=0` tetap di-clamp ke 5.0). `WebRequest` MQL5
sinkron, jadi polling 100 ms **selalu** timeout sebelum server menjawab:

```
res=1003  err=5203 (ERR_WEBREQUEST_REQUEST_FAILED)  bodyLen=0   3001 ms
```

Gejalanya di lapangan: command tidak pernah diterima, dan log EA berosilasi
`bridge UNREACHABLE at PollCommands-http code=1003` + `bridge RECOVERED` tiap
~3 detik (15.014 baris/hari pada build lama). Lebih berbahaya: server sudah
menandai command `DELIVERED` saat menyerahkannya ke socket yang sudah ditutup
EA, sehingga command itu **hilang** tanpa jejak.

Perbaikan: interval polling dan timeout HTTP diselaraskan dengan floor server.

| Input | Default | Arti |
| --- | --- | --- |
| `InpPollSec` | `5` | interval antar-poll (server butuh >= 5 dtk) |
| `InpPollHttpMs` | `6500` | timeout HTTP poll (dipaksa minimal 5500 ms) |

Konsekuensi yang disengaja: tiap siklus poll memblokir thread EA ~5 dtk, jadi
heartbeat saat pasar tutup berjarak ~2,7 dtk (diukur), bukan 2,0 dtk persis.
Heartbeat tetap mengalir; yang dikorbankan adalah ketepatan interval.

Jendela 4014 saat start: ±2 menit pertama setelah MT5 dibuka, semua WebRequest
ditolak (`err=4014`) sampai terminal menerapkan whitelist dari `lumine-login.ini`.
EA hanya mencoba ulang (tidak ada retry buta), jadi tidak perlu intervensi.

## 5. Order gagal karena market tutup (retcode 10018)

`HandleOrderFail()` dipakai semua jalur order (OPEN/CLOSE/MODIFY). Untuk
`TRADE_RETCODE_MARKET_CLOSED` **tidak ada retry**: satu result terstruktur per
command, dan slot ditandai `CLOSED`/`broker` di heartbeat selama
`InpClosedHoldSec`.

```json
{
  "command_id": "…", "status": "FAILED", "ticket": 0,
  "price": 0.0, "profit": 0.0,
  "reason": "market closed", "retcode": 10018,
  "error": "market_closed", "action": "OPEN", "volume": 0.06
}
```

Field tambahan (`retcode`, `error`, `action`, `volume`) diabaikan backend lama
(`ResultBody` pydantic tanpa `extra="forbid"`), jadi kompatibel. Untuk retcode
lain, `reason` tetap format lama (`OrderSend failed retcode=NNNNN`) supaya
konsumen yang mem-parse string tidak berubah perilaku. Log: satu baris saat
10018 pertama, lalu dedup 60 dtk per simbol agar command yang dikirim ulang
backend tidak membanjiri journal.

## 6. Input baru v5.10 (default aman)

| Input | Default | Arti |
| --- | --- | --- |
| `InpLiveBars` | `true` | kirim bar native per TF saat bar baru |
| `InpBarPollMs` | `1000` | interval cek bar baru (min 200 ms) |
| `InpTickStaleSec` | `300` | umur tick yang dianggap `CLOSED`/`no_data` |
| `InpClosedHoldSec` | `300` | lama status `CLOSED`/`broker` setelah 10018 |
| `InpHeartbeatLogSec` | `60` | interval log ringkas heartbeat (0 = hanya saat berubah) |

Input lama tidak diubah nama, tipe, maupun default.

## 7. Build & deploy

```bash
# kompilasi headless (log ditulis ke path /log, bukan ke LumineEA.log)
cd "/home/tekka/wine-mt5/drive_c/Program Files/MetaTrader 5"
DISPLAY=:99 WINEPREFIX=/home/tekka/wine-mt5 \
  /home/tekka/fund2/runtime/wine-10.20/opt/wine-devel/bin/wine MetaEditor64.exe \
  /compile:"MQL5\Experts\LumineEA.mq5" /log:"MQL5\Experts\lumineea_compile.log"
iconv -f UTF-16LE -t UTF-8 MQL5/Experts/lumineea_compile.log | grep Result
```

Pitfalls:

* Pakai **path relatif** dari folder MT5. Path absolut `C:\Program Files\...`
  membuat MetaEditor keluar tanpa mengompilasi (tanpa error, exit 0).
* `MQL5/Experts/LumineEA.log` adalah sisa kompilasi lama; log yang benar adalah
  file yang disebut di `/log:`.
* Unit `lumine-hedge-fund-mt5` menyalin `~/lumine-hedge-fund/scripts/deploy/mt5/LumineEA.mq5`
  ke prefix saat start. Sinkronkan file itu setiap kali `ea/LumineEA.mq5`
  berubah, kalau tidak EA di MT5 kembali ke versi lama pada restart unit.

## 8. Verifikasi cepat

* Log EA (`MQL5/logs/YYYYMMDD.log`): baris
  `selfcheck status XAUUSD Sabtu 12:00 -> CLOSED/weekend` (fungsi status yang
  sama, waktu diinjeksi) dan
  `heartbeat XAUUSD status=OPEN reason=- mode=FULL sym_time=… tick_age=2s (ok=2/2)`.
* DB (`candles`): bar `M15`/`H1`/`H4`/`D1` bertambah di batas bar dengan
  `volume > 0` (jalur live, bukan seed).
