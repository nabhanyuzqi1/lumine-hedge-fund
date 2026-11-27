# PRD & Rencana Eksekusi — Lumine Fund v2 (Fund Core) rev 2.1

Tanggal: 2026-11-21 | Status: DRAFT untuk persetujuan owner | Menggantikan: PRD 2026-11-20 Pendahulu: lumine-hedge-fund (fund.lumine.biz.id) tetap jalan sampai v2 lolos QA (P5).

Angka bertanda **\[USULAN\]** adalah default awal yang wajib dikonfirmasi owner dan dikalibrasi dengan data HFM dari P0.

---

# BAGIAN A — PRD

> **AMANDEMEN OWNER 22 November 2026:** Owner memilih **Full LLM trading**
> (KEPUTUSAN_OWNER.md bagian G): LLM boleh mengambil keputusan order langsung
> MELALUI risk gate deterministik yang sama. Prinsip no.1 di bawah dan garis
> merah §5.9 diamandemen sesuai blok amandemen di PRD v2.2. Gerbang paper
> 20 hari/100 trade, kill-switch, dan approval live owner (D1) tetap.

## 1. Perubahan dari draf 2026-11-20

| # | Perubahan | Alasan |
| --- | --- | --- |
| 1 | Tambah **P0 Fondasi & Pengukuran** (2 hari) | Perekaman spread/slippage HFM harus mulai sebelum backtest dibangun |
| 2 | **P1 dipecah** jadi P1a (backend) dan P1b (UI + strategi) | 5-6 hari tidak cukup untuk API + state machine + bridge + 4 halaman UI |
| 3 | `liquidity_samples` masuk P1 (bukan P2) | Menghilangkan inkonsistensi: modul likuiditas wajib sejak P1 |
| 4 | Latensi didefinisikan dengan titik ukur T0..T4 | Target <300 ms sebelumnya ambigu |
| 5 | Risk gate punya angka default, kill-switch, dan perilaku saat disconnect | Sebelumnya hanya daftar nama |
| 6 | Auth endpoint lokal (HMAC + nonce) | `127.0.0.1:3110` tetap perlu autentikasi |
| 7 | Tick tidak ditulis mentah ke Postgres | Menjaga latensi saat volatilitas XAUUSD tinggi |
| 8 | Paper trading dimulai paralel setelah P1b, syarat min. 100 trade | Sampel kecil menghasilkan false positive |
| 9 | **P3 (ML/RL) opsional**, tidak menghambat cutover | Risiko molor dan overfitting |

## 2. Visi dan prinsip

Quant desk XAUUSD yang cepat, terlacak, dan bisa memperbaiki dirinya sendiri. Bukan chatbot yang main uang.

1. **LLM tidak pernah memegang tombol order** dan tidak mengubah parameter risiko.
2. **Satu `decide()`** dipakai backtest, paper, dan live. Hanya sumber data yang beda.
3. **Setiap order punya buku besar** (`order_events` append-only). Tidak ada order tanpa jejak.
4. **Biaya adalah kenyataan**: spread, slippage, jam likuid dihitung di setiap evaluasi.
5. **Gagal aman**: saat ragu (disconnect, data basi, anomali), sistem berhenti membuka posisi baru.

## 3. Kenyataan yang diakui

- HFT mikrodetik mustahil di MT5 retail. Latensi broker HFM 100-300 ms di luar kendali kita.
- RL untuk trading eksperimental dan rawan overfitting. Hanya jalur riset dengan gerbang ketat.
- Likuiditas menentukan profit lebih dari kecerdasan model.
- Data historis gratis (Dukascopy) tidak mencerminkan spread dan slippage HFM.

## 4. Scope dan non-goals

**In scope:** XAUUSD + BTCUSD (multipair, keputusan owner 2026-11-22 — lihat `KEPUTUSAN_OWNER.md` F1; BTCUSD membuat trading bisa 24/7, XAUUSD tetap instrumen live utama), 1 broker (HFM), 1 akun, 1-2 strategi rule-based live per simbol, UI 4 halaman, backtester, modul likuiditas, laporan otomatis.

**Non-goals v2:** multi-broker, multi-aset di luar XAUUSD+BTCUSD (keputusan F1), HFT mikrodetik / co-location, copy trading / marketplace strategi, live trading sebelum P5 lulus QA dan owner approve.

## 5. Arsitektur

Tiga service: `fund2-api` (FastAPI + serve UI + SSE/WebSocket), Postgres 16 (db `fund2`), MT5 + EA. Caddy-edge tetap. Tanpa Redis, tanpa proxy, tanpa worker terpisah (worker = task asyncio di dalam `fund2-api`).

```
LAPISAN RISET (Hermes + skills, boleh LLM)
  trading-analysis · data-crawler · backtest-runner · strategy-author
  usulkan → backtest → laporan ke owner → APPROVE
                    | 1 pintu bergerbang (human approve)
LAPISAN EKSEKUSI (deterministik, tanpa LLM)
  sinyal → risk gate → state machine → EA/MT5 → event log
  reconciler · kill-switch · auto-halt drawdown
```

### 5.1 Alur data

- **Feed live:** EA kirim tick (batch tiap 250 ms) + candle ke `http://127.0.0.1:3110`.
- **Tick:** ditahan di ring buffer memori, di-flush tiap 60 detik ke file parquet. **Tidak** ditulis mentah ke Postgres.
- **Postgres hanya menyimpan:** candle M1 dan di atasnya (partisi bulanan), agregat spread per 5 detik (`liquidity_samples`), dan data transaksi.
- **Backpressure:** jika antrean tulis > 5 detik, buang sampel likuiditas (bukan event order). Order path tidak pernah menunggu tulis tick.
- **Crawler historis:** skill `data-crawler` (Dukascopy, MQL5, sumber gratis) → parquet + tabel `candles`. Manual atau terjadwal.

### 5.2 Modul likuiditas (wajib sejak P1)

- **Spread:** dicatat real-time dari EA, diagregat min/avg/max per 5 detik.
- **Profil sesi:** Asia / London / NY, median dan p95 spread per jam, diperbarui harian.
- **Slippage:** dihitung dari tiap fill: `fill_price − requested_price` (dalam points), disimpan di `orders` dan `order_events`. Model slippage per ukuran order dibangun dari data ini.
- **Filter entry:** strategi tidak boleh entry bila spread > `max(2 × median 15 menit, ambang_absolut)`. Ambang absolut **\[USULAN\]** 0,50 USD, dikalibrasi ulang setelah 2 minggu data HFM.
- **Kalibrasi biaya backtest:** karena data HFM awalnya pendek, biaya backtest = spread Dukascopy × faktor koreksi (rasio median HFM/Dukascopy per sesi) + haircut keamanan 20%. Faktor diperbarui setiap data HFM bertambah.

### 5.3 Strategy layer (format skill)

Setiap strategi = satu skill Hermes: `SKILL.md` (logika, parameter, risk, hasil backtest) + kode Python murni `decide(context) -> OrderIntent | None`.

- **Track A (default):** rule-based (MA crossover, RSI, breakout, mean reversion).
- **Track B (ML, opsional):** lightgbm/scikit, fitur dari candle + likuiditas, dilatih offline.
- **Track C (RL, eksperimental, opsional):** stable-baselines3; action = {buy, sell, hold, close}; reward = PnL disesuaikan risiko. Wajib lolos walk-forward + paper trading sebelum diusulkan live.

`context` berisi: candle, snapshot likuiditas, posisi terbuka, parameter risiko (read-only). `OrderIntent` wajib memuat SL; tanpa SL ditolak di risk gate.

### 5.4 Backtest engine

- Event-driven, kode `decide()` identik dengan live.
- Biaya: spread terkalibrasi + komisi + model slippage.
- Walk-forward (window latih 6 bulan / uji 1 bulan, geser 1 bulan) **\[USULAN\]**.
- Metrik: winrate, profit factor, max drawdown, Sharpe, jumlah trade, expectancy per trade, distribusi per sesi.
- Output: laporan yang dibaca owner (ringkasan + grafik equity + catatan kapan strategi gagal), bukan angka mentah.
- Anti-overfitting: parameter dipilih di window latih, dilaporkan hanya di window uji; semua percobaan parameter dicatat (`backtest_runs`) agar jumlah percobaan terlihat.

### 5.5 Execution layer

State machine:

`RECEIVED → RISK_PASS → SENT → FILLED | FAILED | STUCK` (+ `RECONCILED` / `ORPHAN_ADOPTED` / `ORPHAN_CLOSED` dari reconciler).

- Semua transisi masuk `order_events` (append-only, tanpa UPDATE/DELETE; dijaga permission DB).
- Idempotensi: tiap order punya `client_order_id`; request duplikat dikembalikan hasil sebelumnya.
- **EA heartbeat** tiap 2 detik. 3 heartbeat terlewat (6 detik) = EA dianggap OFFLINE.

### 5.6 Risk gate (fungsi murni, tanpa efek samping)

| Aturan | Default **\[USULAN\]** | Aksi bila dilanggar |
| --- | --- | --- |
| SL wajib, dipasang di sisi broker | Ya | Tolak |
| Jarak SL minimum / maksimum | 0,50 / 15,00 USD dari harga | Tolak |
| Volume maks per order | 0,10 lot | Tolak |
| Eksposur total terbuka maks | 0,30 lot | Tolak |
| Risiko per trade maks | 0,5% equity | Tolak |
| Drawdown harian maks | 3% equity | **Auto-halt** sampai reset manual owner |
| Drawdown total dari puncak equity | 8% | Auto-halt + notifikasi Telegram |
| Order per menit maks | 5 | Tolak |
| Spread filter | lihat 5.2 | Tolak |
| Data basi (tick > 3 detik) | Ya | Tolak |
| EA OFFLINE | Ya | Tolak order baru |

Parameter risiko disimpan di `settings`, hanya bisa diubah owner lewat UI dengan konfirmasi ulang password. LLM/Hermes read-only.

### 5.7 Kill-switch

- Tombol di Dashboard dan perintah Telegram (owner saja).
- Efek: tolak semua order baru → opsional tutup semua posisi (pilihan eksplisit: "stop saja" vs "stop + flatten").
- Auto-trigger: drawdown limit, EA offline > 60 detik dengan posisi terbuka, 3 order FAILED beruntun, reconciler menemukan selisih posisi yang tidak bisa dijelaskan.
- Status kill-switch tersimpan di DB, bertahan saat restart.

### 5.8 Skenario disconnect dan rekonsiliasi

1. EA OFFLINE terdeteksi → risk gate tolak order baru. Posisi terbuka tetap dilindungi SL di sisi broker.
2. Order `SENT` > 60 detik tanpa konfirmasi → status `STUCK`, reconciler dijadwalkan.
3. Saat EA kembali: EA kirim **snapshot** (posisi terbuka + deal 24 jam terakhir).
4. Reconciler membandingkan snapshot dengan `positions` / `orders`:
   - posisi ada di broker, tidak ada di DB → `ORPHAN_ADOPTED` (dicatat, diberi SL darurat bila belum ada, notifikasi);
   - ada di DB, tidak ada di broker → tandai `FILLED_THEN_CLOSED` bila ada deal penutup, selain itu `FAILED`;
   - tidak bisa dijelaskan → kill-switch + alert.
5. Semua langkah tercatat di `order_events`.

### 5.9 Hermes layer (riset dan operasi)

- Skills: `trading-analysis`, `data-crawler`, `backtest-runner`, `strategy-author`.
- **Self-improvement loop mingguan:** analisa event log + hasil → usulan perbaikan → backtest → laporan owner → approve → deploy.
- **Cron harian:** rekap P&L, kesehatan bridge, deteksi anomali → Telegram.
- **Garis merah:** LLM tidak punya kredensial endpoint order, tidak mengubah parameter risiko, tidak deploy tanpa approve owner. Deploy strategi = commit ke repo + flag `enabled` yang hanya bisa diubah owner.

### 5.10 UI (4 halaman, mode Operate)

1. **Login** (rate limit, sesi dengan expiry).
2. **Dashboard:** harga live, posisi, form order (SL/TP wajib + konfirmasi), spread + sesi likuiditas, status EA (online/offline + latensi terakhir), tombol kill-switch.
3. **Riwayat:** buku besar event log, buka per order, filter status/tanggal, ekspor CSV.
4. **Strategy Lab:** daftar strategi, hasil backtest, mode paper/live, toggle enable, kill-switch.

Standar visual: awwwards/impeccable, responsif (mobile dipakai untuk memantau).

## 6. SLO dan definisi latensi

Titik ukur (timestamp monotonic, dicatat di `order_events`):

| Titik | Kejadian |
| --- | --- |
| T0 | API menerima sinyal/order (request masuk) |
| T1 | EA menerima command (push) |
| T2 | EA memanggil `OrderSend` |
| T3 | `OrderSend` return (retcode dari server broker) |
| T4 | Fill terkonfirmasi di DB |

- **SLO internal (mengikat):** T0→T2 **p95 < 300 ms**, p99 < 500 ms, diukur ≥ 200 order paper/demo.
- **Dilaporkan terpisah (tanpa SLO keras sampai ada data P0-P1):** T2→T3 (latensi broker), T0→T4 total.
- Harness latensi otomatis berjalan di QA tiap fase; hasil masuk laporan.
- Metrik lain: uptime bridge ≥ 99,5% (jam pasar), 0 order hilang/nyangkut.

## 7. Keamanan

- Endpoint EA hanya bind `127.0.0.1`; firewall menutup port 3110 dari luar.
- Setiap request EA ↔ API ditandatangani **HMAC-SHA256** (shared secret di env, bukan di repo) + timestamp + nonce; toleransi jam 5 detik, nonce dipakai sekali.
- Password owner di-hash (argon2); sesi httpOnly + secure; rate limit login; 2FA Telegram untuk aksi sensitif (ubah risk parameter, flatten semua).
- Kredensial broker tidak pernah masuk ke layer riset.
- Backup Postgres harian (`pg_dump`) + uji restore sekali per fase; retensi 30 hari.
- Audit: perubahan `settings` tercatat (siapa, kapan, nilai lama/baru).

## 8. Database

| Tabel | Fase | Catatan |
| --- | --- | --- |
| `users`, `sessions` | P1a | auth |
| `orders` | P1a | termasuk `client_order_id`, `requested_price`, `fill_price`, `slippage_points` |
| `order_events` | P1a | append-only, T0..T4, payload JSONB |
| `positions` | P1a | snapshot posisi |
| `candles` | P1a | partisi bulanan, M1+ |
| `settings` | P1a | risk parameter + audit |
| `liquidity_samples` | **P1a** | agregat spread per 5 detik + sesi |
| `signals` | P2 | keluaran `decide()` |
| `strategies`, `backtest_runs` | P2 | versi, parameter, hasil, jumlah percobaan |

## 9. Metrik sukses dan gerbang go-live

**Gerbang go-live (semua wajib, sebelum live uang nyata):**

1. QA paritas penuh v1 vs v2 lulus.
2. Latensi T0→T2 p95 < 300 ms pada ≥ 200 order demo.
3. Uji disconnect (EA dimatikan saat posisi terbuka) → rekonsiliasi benar 10/10.
4. Uji kill-switch dan auto-halt drawdown berfungsi.
5. Paper trading ≥ 20 hari kerja, **≥ 100 trade**, profit factor ≥ 1,3 setelah biaya, max drawdown ≤ 5% **\[USULAN\]**.
6. Restore backup teruji.
7. Owner approve tertulis.

**Metrik 30 hari pasca-live:** p95 latensi tetap < 300 ms; 0 order hilang; uptime bridge ≥ 99,5%; ≥ 1 strategi profit setelah biaya; 1 siklus self-improvement ter-approve.

---

# BAGIAN B — RENCANA EKSEKUSI

## 10. Ringkasan jadwal

Total jalur kritis ±25 hari kerja (±5 minggu). P3 berjalan paralel/ditunda dan **tidak** ada di jalur kritis.

| Fase | Durasi | Hari kerja kumulatif |
| --- | --- | --- |
| P0 Fondasi & Pengukuran | 2 hari | 1-2 |
| P1a Core Backend | 5 hari | 3-7 |
| P1b UI + Strategi + Reconciler | 5 hari | 8-12 |
| P2 Data & Riset | 6 hari | 13-18 |
| P4 LLM & Ops | 4 hari | 19-22 |
| P5 Cutover | 3 hari | 23-25 |
| P3 ML/RL (opsional) | 2-3 minggu, paralel | setelah P2 |
| Paper trading 20 hari kerja | paralel | mulai akhir P1b, selesai ±hari 32 |

Catatan: paper trading dimulai setelah P1b dengan strategi rule-based pertama, jadi tidak memperpanjang jalur kritis. Jika paper belum mencapai 20 hari saat P5 siap, cutover menunggu gerbang 5 (bukan dipaksa).

## 11. Detail fase

### P0 — Fondasi & Pengukuran (2 hari)

| Tugas | Owner | Keluaran |
| --- | --- | --- |
| Repo `fund2`, struktur folder, CI (lint + test), env template | hf-backend | repo berjalan |
| Postgres `fund2` + migrasi awal (Alembic) + permission append-only `order_events` | hf-backend | skema v0 |
| EA v0: heartbeat, kirim tick batch + spread ke endpoint dummy, HMAC | hf-backend | EA terhubung |
| **Perekaman spread/slippage HFM dimulai** (parquet + log), jalan terus sampai P5 | hf-devops | data HFM harian |
| Harness latensi T0..T4 (skeleton) | hf-qa | skrip ukur |
| Keputusan owner atas semua angka \[USULAN\] | owner | dokumen keputusan |

**DoD:** EA mengirim heartbeat + tick ke API dummy dengan HMAC valid; data spread HFM tersimpan; angka risk default disetujui.

### P1a — Core Backend (5 hari)

| Hari | Tugas | Owner |
| --- | --- | --- |
| 3 | Auth (login, sesi, rate limit), model `users/sessions/settings` | hf-backend |
| 3-4 | State machine order + `order_events` + idempotensi `client_order_id` | hf-backend |
| 4 | Risk gate (fungsi murni) + unit test tiap aturan (target cakupan 100% cabang) | hf-backend |
| 5 | Bridge: push command ke EA (WebSocket), EA `OrderSend`, retcode → event | hf-backend |
| 5-6 | Ingest tick: ring buffer, flush parquet, candle M1, `liquidity_samples` | hf-devops |
| 6 | Kill-switch (manual + auto-trigger), halt tersimpan di DB | hf-backend |
| 7 | Uji E2E di akun demo + ukur latensi (≥ 50 order) | hf-qa |

**DoD:** 1 order demo E2E tercatat lengkap T0..T4 di event log; risk gate menolak semua kasus uji; T0→T2 p95 < 300 ms pada ≥ 50 order; auto-halt drawdown teruji dengan simulasi.

### P1b — UI, Strategi, Reconciler (5 hari)

| Hari | Tugas | Owner |
| --- | --- | --- |
| 8-9 | Login + Dashboard (harga live, posisi, form order SL/TP wajib, status EA, kill-switch) | hf-frontend |
| 9-10 | Riwayat (event log per order, filter, CSV) + Strategy Lab (shell: daftar, toggle, mode) | hf-frontend |
| 8-10 | Reconciler: STUCK > 60 detik, snapshot saat EA reconnect, orphan adopt/close | hf-backend |
| 10-11 | Strategi rule #1 (mis. breakout sesi London dengan filter spread) sebagai skill + `decide()` | hf-backend |
| 11 | Telegram: alert kill-switch, EA offline, rekap harian | hf-devops |
| 12 | QA: uji disconnect 10×, kill-switch, UI mobile, keamanan dasar | hf-qa |

**DoD:** uji disconnect 10/10 rekonsiliasi benar; UI 4 halaman fungsional di desktop + mobile; strategi #1 jalan di **paper mode**; paper trading dimulai (hari ke-0 dari 20).

### P2 — Data & Riset (6 hari)

| Tugas | Owner |
| --- | --- |
| Skill `data-crawler` (Dukascopy + sumber lain) → parquet + `candles`, validasi gap/duplikat | hf-devops |
| Backtest engine event-driven (satu `decide()`), model biaya terkalibrasi (5.2) | hf-backend |
| Walk-forward runner + `backtest_runs` (catat jumlah percobaan) | hf-backend |
| Format skill strategi final (`SKILL.md` + `decide()`), template `strategy-author` | hf-backend |
| Laporan backtest yang bisa dibaca owner (ringkasan + equity + kapan gagal) | hf-frontend / hf-backend |
| Strategi #2 (mean reversion) untuk perbandingan | hf-backend |
| QA: verifikasi paritas backtest vs paper (sinyal identik pada periode yang sama) | hf-qa |

**DoD:** 1 strategi lolos backtest 2 tahun data dengan biaya realistis dan walk-forward; paritas sinyal backtest vs paper ≥ 99%; laporan terbaca owner.

### P3 — ML/RL (opsional, 2-3 minggu, paralel)

- Feature store (candle + likuiditas), pipeline training offline, walk-forward ketat.
- **Tidak** boleh menahan P4/P5. Mulai hanya jika P2 selesai dan owner menyetujui.
- Gerbang masuk ke live: walk-forward lolos + paper ≥ 20 hari kerja + ≥ 100 trade + mengalahkan baseline rule-based pada metrik yang sama setelah biaya.
- Jika tidak lolos: arsipkan, laporkan apa yang dipelajari. Itu hasil sah.

### P4 — LLM & Ops (4 hari)

| Tugas | Owner |
| --- | --- |
| Self-improvement loop mingguan: analisa event log + hasil → usulan → backtest otomatis → laporan | hf-backend / Hermes |
| Cron harian: rekap P&L, kesehatan bridge, anomali (latensi naik, spread abnormal, rasio FAILED) | hf-devops |
| Alur approve: laporan → owner approve via UI/Telegram → deploy (flag `enabled`) | hf-backend |
| Verifikasi garis merah: LLM tidak punya akses endpoint order / settings (uji penetrasi sederhana) | hf-qa |

**DoD:** 1 laporan mingguan otomatis terkirim; 1 usulan strategi ter-approve melewati seluruh alur; uji garis merah lulus.

### P5 — Cutover (3 hari)

| Hari | Tugas |
| --- | --- |
| 1 | QA paritas penuh v1 vs v2, ulangi harness latensi, uji restore backup, cek 7 gerbang go-live |
| 2 | Pindah domain `fund.lumine.biz.id` ke v2 pada jam pasar sepi; v1 tetap hidup di subdomain cadangan |
| 3 | Pantau intensif; rollback plan siap (arahkan Caddy kembali ke v1 < 5 menit) |

**DoD:** semua gerbang go-live terpenuhi dan owner approve; v1 diarsipkan hanya setelah 7 hari v2 stabil.

## 12. Tim dan koordinasi

- **hf-backend:** API, state machine, risk gate, bridge, backtester, reconciler.
- **hf-devops:** perekaman data HFM, ingest tick, crawler, Telegram, backup, cutover.
- **hf-frontend:** UI 4 halaman sejak P1b, laporan backtest.
- **hf-qa:** harness latensi, uji disconnect, paritas, keamanan, gerbang tiap fase.
- **hf-ceo:** koordinasi, review tiap DoD, eskalasi keputusan ke owner.
- Ritme: standup singkat harian; demo di akhir tiap fase; fase tidak lanjut sebelum DoD lulus (dinilai hf-qa).

## 13. Risiko dan mitigasi

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Backtest terlalu optimis (data Dukascopy ≠ HFM) | Strategi gagal di live | Kalibrasi biaya dengan data HFM + haircut 20%, paper wajib, laporkan jumlah percobaan |
| Latensi broker memburuk | SLO T2→T3 tidak terjaga | Dilaporkan terpisah, alert bila p95 naik 2×, filter volatilitas ekstrem |
| Beban tulis tick saat volatilitas tinggi | Latensi order naik | Ring buffer + parquet, Postgres hanya agregat, backpressure buang sampel |
| EA/MT5 putus saat posisi terbuka | Posisi yatim | SL di broker, heartbeat, snapshot + reconciler, kill-switch otomatis |
| Overfitting ML/RL | Kerugian live | P3 opsional, walk-forward + paper + baseline |
| Estimasi jadwal meleset | Cutover molor | P0 + pecah P1, paper paralel, P3 dikeluarkan dari jalur kritis |
| Kebocoran secret / endpoint lokal | Order tidak sah | HMAC + nonce, firewall, secret di env, 2FA aksi sensitif |
| Kegagalan `pg_dump` / disk penuh | Kehilangan buku besar | Backup harian + uji restore tiap fase + alert disk |

## 14. Keputusan terbuka untuk owner

1. Setujui / ubah semua angka risk gate bertanda \[USULAN\] (lot, drawdown, SL min/maks, ambang spread).
2. Modal dan lot awal untuk live (menentukan batas lot sebenarnya).
3. Tetap strategi pertama breakout London, atau pilih lain?
4. Apakah P3 (ML/RL) dikerjakan setelah P2 atau ditunda sampai v2 live stabil?
5. Kanal alert: Telegram saja, atau tambah email?
6. Jam cutover yang diizinkan (jam pasar sepi).
