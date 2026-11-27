# TAHAP 0 — Probe kapabilitas partial close EA (RISK-C, t_00db2872)

Tanggal probe: 26 Nov 2026 (WIB). Lingkup: EA `LumineEA.mq5` v5.03 yang berjalan
di MT5 (Wine) pada host ini + jalur bridge/result di API.

## Keputusan

**Partial close (TP1/TP2/TP3) DIDESCOPE.** EA yang berjalan tidak bisa menutup
sebagian volume, dan menambahkannya bukan sekadar mengubah satu baris MQL5:
hasil CLOSE parsial akan membuat DB menandai posisi `CLOSED` sementara broker
masih memegang sisa volume, sehingga trailing RISK-B berhenti mengawal posisi
nyata. Karena kartu ini secara eksplisit mengizinkan descope bila partial close
tidak aman, lingkup yang dikerjakan adalah **tool Fibonacci** (level benar
secara matematika + konteks opsional LLM), tanpa jalur partial close backend.

Rencana partial close yang benar (butuh approval owner + rebuild EA) dicatat di
bagian "Prasyarat bila nanti dilanjutkan" dan dilaporkan ke Director.

## Bukti 1 — EA menutup SELURUH volume, field `volume` diabaikan

`ea/LumineEA.mq5` (sama persis dengan source EA yang ter-deploy, lihat bukti 4):

| Lokasi | Fakta |
| --- | --- |
| `ProcessCommand()` baris 1495 | `double lots = ExtractJsonDouble(json, "volume");` — nilai volume payload DIBACA |
| `ProcessCommand()` baris 1528-1532 | cabang `CLOSE` hanya memanggil `ExecuteClose(id, ticket);` — `lots` tidak diteruskan |
| `ExecuteClose()` baris 1631-1683 | `double volume = PositionGetDouble(POSITION_VOLUME);` (1640) lalu `req.volume = volume;` (1648) — selalu volume penuh |
| `ExecuteClose()` | tidak memanggil `NormalizeVolume()`; tidak ada parameter volume parsial, tidak ada validasi sisa volume |

Konsekuensi: command CLOSE dengan `volume: 0.01` pada posisi 0.02 lot tetap
menutup 0.02 lot. Tidak ada cara memaksa partial close dari sisi backend tanpa
memodifikasi EA.

## Bukti 2 — Backend memperlakukan setiap CLOSE sebagai penutupan penuh

| Lokasi | Fakta |
| --- | --- |
| `api/app/bridge.py` 353-357 | payload CLOSE hanya `{action, ticket}`; tidak ada field volume |
| `api/app/bridge.py` 385 | command queue `bridge_commands` dikirim dengan `volume: 0` |
| `api/app/schema.sql` 87-88 | `bridge_commands.action` hanya `'MODIFY_SL' | 'CLOSE'`, payload `{ticket, sl, tp, reason}` |
| `api/app/bridge.py` 443-521 | result CLOSE `FILLED` langsung `UPDATE positions SET status = 'CLOSED'` (baris 521) + menutup order OPEN induk |
| `api/app/bridge.py` 767-809 | reconciler: bukti "deal penutup" → posisi `FILLED_THEN_CLOSED` / `ORPHAN_CLOSED` |
| `api/app/schema.sql` 59-78 | tabel `positions`: satu kolom `volume`, status `OPEN|CLOSED`, **tanpa ledger volume sisa** |

Skenario bahaya yang terbukti dari kode: bila EA (versi baru) mengirim CLOSE
parsial 50%, bridge menandai posisi `CLOSED` di DB. RISK-B (`app/auto_sl.py`,
BE + trailing) berhenti karena posisi sudah dianggap tutup, padahal broker masih
memegang 50% volume tanpa SL terkelola. Posisi itu jadi telanjang sampai
ditutup manual.

## Bukti 3 — Batasan volume broker memperkecil ruang partial close

Dari `settings.symbol_specs` (`api/app/db.py` 82-110): `vol_min_lot = 0.01`,
`vol_step_lot = 0.01`, `vol_max_lot = 0.10` untuk XAUUSD dan BTCUSD.

- Posisi 0.01 lot: TP1 50% = 0.005 lot < minimum → mustahil; tidak ada partial close.
- Ladder 50/30/20 pada 0.02 lot: 0.01 / 0.006 / 0.004 → tranche 2 dan 3 di bawah minimum, harus dibulatkan ulang (0.01 / 0.01), bukan 50/30/20 lagi.
- Ladder 3 tranche yang benar-benar feasible butuh posisi ≥ 0.05 lot (mis. 0.03 / 0.01 / 0.01), dan default `llm_auto_lot` ada di 0.01-0.10.

Artinya partial close TP1/TP2/TP3 hanya masuk akal untuk sebagian posisi, bukan
semua: aturan pembulatan deterministik harus jadi bagian desain, bukan detail.

## Bukti 4 — Yang diuji adalah EA yang benar-benar berjalan

```
$ md5sum ea/LumineEA.mq5 "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MQL5/Experts/LumineEA.mq5"
78f7e6c9c1fb6f5e23d03ccdb5221475  ea/LumineEA.mq5
78f7e6c9c1fb6f5e23d03ccdb5221475  .../MQL5/Experts/LumineEA.mq5
```

- `#property version "5.03"` (baris 44), `.ex5` dikompilasi 24 Nov 16:57 setelah
  source 24 Nov 15:37.
- Proses MT5 hidup (`terminal64.exe /config:C:\lumine-login.ini`), heartbeat EA
  terakhir tercatat di `settings.ea_last_seen_at` = 2026-11-25T23:44:59Z.
- `ea/ea_simulator.py` tidak mengimplementasikan CLOSE sama sekali (hanya OPEN +
  seed candle), jadi tidak ada jalur simulasi yang bisa dipakai untuk menguji
  partial close tanpa EA asli.

## Bukti 5 — Tripwire otomatis

`api/tests/test_ea_partial_close_capability.py` (3 test, hijau) mengunci ketiga
asumsi di atas: EA memakai `POSITION_VOLUME`, `ProcessCommand` tidak meneruskan
`volume`, dan bridge menutup posisi penuh tanpa ledger `remaining_volume`.
Begitu EA benar-benar mendukung partial close, test itu gagal dan memaksa
probe ini dibuka ulang sebelum fitur diaktifkan.

## Prasyarat bila nanti dilanjutkan (belum dikerjakan)

1. EA: `ExecuteClose(id, ticket, volume)` dengan `NormalizeVolume()`; tolak bila
   `volume >= sisa` atau `< vol_min_lot`; laporkan `volume_executed` di result.
2. Skema: ledger volume sisa posisi (mis. `positions.remaining_volume` +
   `partial_closes` append-only) dan status parsial eksplisit.
3. Bridge/reconciler: result CLOSE dengan volume < sisa → update ledger, JANGAN
   `status='CLOSED'`; hanya tranche terakhir yang menutup posisi + profit akumulatif.
4. RISK-B: trailing tetap dihitung terhadap volume sisa; slot exposure portofolio
   disesuaikan (risiko yang sudah direalisasi vs terbuka).
5. Feature flag OFF default + audit + approval owner (kartu RISK-C original) dan
   deploy EA baru butuh persetujuan owner (rebuild .ex5 + restart terminal MT5).
