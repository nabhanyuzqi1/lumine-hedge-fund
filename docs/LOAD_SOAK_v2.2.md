# Load & Soak Test v2.2: Bukti dan Batas

Kartu: **t_128a9dee** (paket kesiapan operasional) · Tanggal: 25 Nov 2026 (WIB) · Pemilik: hf-devops
Referensi: PRD v2.2 §22.1.8 (load & soak), §23.12 (P11), SLO v2.1 §6 (T0-T2 p95 < 300 ms, p99 < 500 ms)

> Semua angka di bawah dihasilkan dari eksekusi nyata (bukan estimasi). Dua dari tiga eksekusi berjalan in-process terhadap DB sekali buangan; itu **bukan angka produksi**. Batasnya dijelaskan §4.

## 1. Ringkasan eksekusi

| # | Eksekusi | Tanggal | Skala | Hasil inti | Verdict |
| --- | --- | --- | --- | --- | --- |
| L1 | Load 2.000 request + soak 30 s (`scripts/load_soak_check.py`) | 23 Nov 2026 17:34 WIB | 175 rps puncak, 20 konkuren | 0 error 5xx; load p95 303,8 ms; soak p95 12,8 ms; drift 1,05 | LULUS (isolated) |
| L2 | **Extended soak 360 s** (`scripts/soak_extended.py`, baru) | 25 Nov 2026 21:52-21:57 WIB | 32.848 request, 91,2 rps rata-rata, 20 konkuren | 0 error 5xx; p95 220,8 ms; RSS +5,9%; p95 per menit stabil | **LULUS** (isolated) |
| L3 | Latensi jalur order P5 rerun v11 (`QA_P5_cutover.md` §2) | 25 Nov 2026 18:05-19:39 WIB | 207 order demo lengkap T0-T4 | p95 T0-T2 182,8 ms; p99 215,5 ms; 0 ditolak risk gate | LULUS (API + EA demo nyata) |

## 2. Detail L1: load & soak dasar (23 Nov)

Sumber: `docs/QA_v22_load_soak.json`, driver `scripts/load_soak_check.py`.

| Fase | Metric | Nilai |
| --- | --- | --- |
| Load (2.000 req, 20 konkuren) | rps | 175,4 |
| | p50 / p95 / p99 / max | 97,7 / 303,8 / 353,1 / 573,8 ms |
| | status | 1.389 `200`, 419 `401`, 192 `422` |
| | error 5xx/exception | 0 |
| Soak (30 s) | request | 5.463 (182,1 rps) |
| | p50 / p95 / p99 | 3,5 / 12,8 / 17,3 ms |
| | error 5xx | 0 |
| | drift latensi (paruh 2 / paruh 1) | 1,05 |

Catatan: status `401`/`422` pada fase load berasal dari traffic campuran (permintaan tanpa sesi/CSRF dan order dengan payload validasi), bukan kegagalan server. Tidak ada `500`. p95 campuran 303,8 ms 1,3 ms di atas SLO 300 ms, tetapi SLO didefinisikan untuk jalur order T0-T2 (L3: 182,8 ms), bukan campuran auth/validasi; tetap dicatat sebagai pemantauan, bukan kegagalan.

## 3. Detail L2: extended soak 6 menit (25 Nov)

Sumber: `docs/QA_v22_soak_extended_20261125T215716Z.json`, driver `scripts/soak_extended.py` (warmup 30 s, terpisah).

| Metric | Nilai |
| --- | --- |
| Durasi terukur | 360 s (plus warmup 30 s) |
| Request | 32.848 (91,2 rps) |
| p50 / p95 / p99 / max | 30,8 / 220,8 / 370,5 / 789,9 ms |
| Status | 19.744 `200`, 8.080 `401`, 5.024 `422` |
| Error 5xx/exception | **0** |
| p95 per menit (1-6) | 219,7 / 196,5 / 229,1 / 201,4 / 230,6 / 237,7 ms |
| RSS proses | 105.276 KB awal, 111.536 KB akhir, puncak 111.536 KB (**+5,9%**) |
| Kriteria | zero_5xx, rss_growth <= 20%, p95 drift <= 1,5x, no_error_burst: **semua lulus** |

Interpretasi: tidak ada indikasi kebocoran memori atau degradasi latensi pada 6 menit beban campuran ~90 rps. `401`/`422` tetap berasal dari campuran request uji (sesi/CSRF dan validasi payload), bukan error server; jumlahnya proporsional dengan rasio traffic yang sengaja dicampur.

## 4. Detail L3: jalur order end-to-end (25 Nov)

Sumber: `docs/QA_P5_cutover.md` §2, `scripts/p5_latency_v11.log`, label `p5-latency-gate-v11-b*`.

| Metric | Nilai |
| --- | --- |
| Sampel valid T0-T4 | 207 |
| p95 / p99 T0-T2 | **182,8 ms / 215,5 ms** |
| Order ditolak risk gate | 0 |
| Riwayat | run v10 gagal (p95 311,6 ms), akar: pickup `/bridge/poll` 0,25 s; fix ke 0,05 s (commit `40f9f09`) |

Ini satu-satunya bukti yang melibatkan EA MT5 nyata (akun demo) dan jalur order penuh, sehingga paling dekat dengan kondisi canary.

## 5. Verdict dan batas

**Verdict: LULUS untuk baseline kapasitas API; BELUM memadai sebagai jaminan produksi.**

Batas yang harus ditutup sebelum canary:

1. L1 dan L2 in-process (`ASGITransport`): tanpa jaringan, TLS, uvicorn worker ganda, dan konkurensi bridge/EA nyata. Angka hanya membuktikan logika aplikasi dan akses DB.
2. Durasi soak terpanjang 6 menit; kebocoran memori dan degradasi harian butuh >= 2 jam.
3. Tidak ada beban paralel dari EA nyata (heartbeat, poll, snapshot posisi) selama soak.
4. Tidak ada uji recovery di tengah beban (restart API, restart Postgres, EA offline).
5. Volume DB yang dihasilkan uji jauh di bawah volume produksi; perlu uji pertumbuhan tabel `candles`/`liquidity_samples`/`order_events`.

### 5.1 Uji wajib sebelum canary (ditambahkan ke window rilis)

| # | Uji | Kriteria lulus |
| --- | --- | --- |
| S-1 | Soak >= 2 jam melalui uvicorn nyata (bukan in-process), DB produksi-like | 0 error 5xx; RSS naik <= 20%; p95 akhir <= 1,5x p95 awal |
| S-2 | Soak dengan EA demo aktif (heartbeat + poll + snapshot) dan 1 runner | 0 order hilang; latensi T0-T2 p95 < 300 ms |
| S-3 | Restart API saat beban: order in-flight tidak hilang, state machine konsisten | 0 order STUCK permanen; reconcile bersih |
| S-4 | Uji pertumbuhan data: 1 hari candle + tick setara produksi | p95 query dashboard tetap < 1 s; disk tumbuh sesuai proyeksi |
| S-5 | Recovery DB: restart Postgres saat beban | API reconnect otomatis; alert `DB_UNAVAILABLE` terkirim; 0 korup |

Hasil S-1..S-5 wajib dilampirkan ke kartu rilis sebelum `RELEASE_CHECKLIST` 3.x dinyatakan penuh.

## 6. Referensi eksekusi

```bash
# L1 (lama, 23 Nov)
cd ~/fund2/api && TELEGRAM_ALERTS_OFF=1 .venv/bin/python ../scripts/load_soak_check.py

# L2 (baru, 25 Nov)
cd ~/fund2/api && .venv/bin/python ../scripts/soak_extended.py \
  --duration 360 --warmup 30 --concurrency 20

# L3 (jalur order, P5)
# driver: scripts/_p5_latency_driver_v11.py, log: scripts/p5_latency_v11.log
```

## 7. Sign-off

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Eksekusi | hf-devops | 25 Nov 2026 | L2 dijalankan ulang hari ini |
| Review | hf-qa | menunggu | Kriteria S-1..S-5 |
