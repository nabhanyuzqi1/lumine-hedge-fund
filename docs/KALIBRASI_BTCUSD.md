# Kalibrasi Data & Biaya BTCUSD (t_f2mp4)

Tanggal: 23 Nov 2026. Semua angka dari data live (bukan simulasi).

## 1. Recorder HFM: parquet per simbol

`data/hfm_recording/recorder.py` kini menulis **satu parquet per simbol**:

- `parquet/ticks_BTCUSD_YYYY-MM-DD.parquet`
- `parquet/ticks_XAUUSD_YYYY-MM-DD.parquet`
- `parquet/fills_YYYY-MM-DD.parquet` (tanpa simbol, tidak berubah)
- `log/ticks_YYYY-MM-DD.jsonl` (crash-safe, campur simbol, ada kolom `symbol` — layout lama, dipakai `paper/feed.py`)

Riwayat combined lama sudah di-split per simbol; original diarsipkan di
`parquet/legacy_combined/`. Verifikasi 23 Nov 10:07 WIB:

```
[flush] 651 ticks XAUUSD -> ticks_XAUUSD_2026-11-23.parquet (total 164460 rows)
[flush] 58 ticks BTCUSD  -> ticks_BTCUSD_2026-11-23.parquet (total 11048 rows)
```

## 2. Profil sesi/spread per jam (median + p95), diperbarui harian

Script: `scripts/spread_profile.py` (service `fund2-spread-profile.service`,
timer `fund2-spread-profile.timer` **harian 00:15 UTC**, Persistent=true).

Output per simbol: tabel per jam UTC (median, p95, n, sesi) dicetak ke
jurnal; JSON riwayat di `data/hfm_recording/spread_profile_<SYMBOL>.json`;
settings `spread_profile_<SYMBOL>`.

Hasil BTCUSD (window 21 Nov 21:53 - 23 Nov 03:07 UTC): spread stabil
39-40 USD sepanjang 24 jam, p95 40-42 USD. Jam 04-05 UTC kosong (EA offline
sementara di window tersebut). Detail per jam di settings
`spread_profile_BTCUSD`.

## 3. Ambang spread per simbol (PRD 5.2)

Formula PRD 5.2: `gate = max(2 x median 15 menit, ambang_absolut)`.

Metode kalibrasi BTCUSD dari data:
- `median_15m` = median dari median spread per bucket 15 menit = **39,00 USD** (93 bucket)
- `p95_15m` = p95 median bucket 15 menit = **40,00 USD**
- `ambang_absolut` = p95_15m dibulatkan ke atas ke kelipatan 5 = **40,00 USD**
- `gate` = max(2 x 39, 40) = **78,00 USD**

Disimpan di settings **`spread_calibration_BTCUSD`** (JSON lengkap: formula,
window, computed_at). Wiring ke risk gate per-simbol adalah scope t_f2mp1
(`spread_abs_max_usd` per simbol).

Catatan XAUUSD: kalibrasi ulang ambang baru jatuh tempo setelah 2 minggu
data HFM (baru ~2 hari), jadi nilai terkunci A9 = 0,50 USD tetap berlaku.
Profil XAUUSD disimpan informatif di `spread_profile_XAUUSD`; entri
kalibrasi XAU sengaja TIDAK dipasang agar tidak salah baca.

## 4. Candles BTCUSD M1+

Sudah mengalir live ke tabel `candles` (partisi bulanan, kolom `symbol`
terisi semua baris, diverifikasi 0 null). Kondisi 23 Nov 10:16 WIB:

| TF | Baris | Terakhir |
| --- | --- | --- |
| M1 | 7.029 | 23 Nov 10:16 WIB (live dari tick EA) |
| M5 | 5.305 | 23 Nov 10:15 WIB (rollup server-side) |
| M15 | 5.074 | 23 Nov 03:15 WIB |
| H1 | 5.002 | 22 Nov 10:00 WIB |
| H4 | 1.952 | 22 Nov 08:00 WIB |
| D1 | 326 | 22 Nov |

## 5. Faktor kalibrasi biaya backtest BTC (PRD 5.2)

Script: `scripts/calibrate_btc_cost.py` (idempoten, `--fetch` unduh candle
m1 Dukascopy BTCUSD; skala harga 1/10 USD diverifikasi terhadap HFM).

- Spread Dukascopy: 4.320 menit (20-22 Nov UTC), median **50,00 USD** per sesi
- Spread HFM (liquidity_samples, window overlap): median 39,20-40,00 USD
- Faktor koreksi per sesi = median HFM / median Dukascopy:
  - asia 0,800; london 0,784; london_newyork 0,784; newyork 0,784
- Biaya fill per sesi = Duka x faktor x (1 + haircut 20%):
  - asia **48,00 USD**; london/london_newyork/newyork **47,04 USD**
- Window overlap: 20 Nov 00:00 - 22 Nov 23:59 UTC; 13.542 sampel HFM 5-detik

Disimpan di settings **`backtest_cost_calibration_BTCUSD`** dan
`data/dukascopy/m1_btc/cost_calibration_BTCUSD.json`. Faktor di-cap 3,0
(paper.costs) - tidak aktif di sampel ini.

## Catatan & batasan

1. Komisi (7 USD/lot round-turn) dan slippage (0,10 USD/fill) pada cost
   model masih default [USULAN] XAUUSD; kontrak size BTCUSD (1 BTC/lot)
   belum diverifikasi ke contract spec HFM - konfirmasi sebelum dipakai
   keputusan backtest BTC (t_f2mp3).
2. Sampel HFM BTC baru ~26 jam; faktor wajib dikalibrasi ulang seiring data
   bertambah (otomatis oleh timer harian).
3. Candle m1 Dukascopy hari berjalan memang 404 (hanya hari penuh yang
   tersedia); kalibrasi memakai overlap hari penuh.
4. Entri settings lama `max_spread` (0,5 global) tidak diubah di kartu ini -
   per-simbolnya di t_f2mp1.

## File

- `data/hfm_recording/recorder.py` - recorder per simbol
- `scripts/spread_profile.py` - profil per jam + kalibrasi ambang
- `scripts/calibrate_btc_cost.py` - faktor biaya backtest
- `data/dukascopy/m1_btc/raw/*.bi5` - candle m1 Dukascopy BTCUSD
- Unit: `fund2-spread-profile.service` + `.timer` (harian 00:15 UTC)
