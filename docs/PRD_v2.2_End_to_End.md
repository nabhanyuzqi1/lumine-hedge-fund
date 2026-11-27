# Lumine Fund v2.2 --- PRD, Technical Specification & End-to-End Delivery Plan

## Fund Core \| Dari fondasi sampai rilis produksi

**Tanggal:** 21 November 2026\
**Status:** Draft untuk persetujuan owner dan baseline eksekusi\
**Basis:** PRD Lumine Fund v2.1 (21 November 2026)\
**Produk:** Sistem riset, validasi, paper trading, dan eksekusi XAUUSD
melalui MT5/HFM\
**Prinsip utama:** Hermes meneliti dan mengusulkan; kode deterministik
mengendalikan risiko dan mengeksekusi; owner memegang keputusan live.

> **AMANDEMEN OWNER 22 November 2026 (KEPUTUSAN_OWNER.md bagian G):**
> Owner memilih **Full LLM trading** — LLM (Hermes agent) boleh mengambil
> keputusan order langsung. Prinsip "LLM tidak pernah memegang tombol order"
> (v2.1 §2.1) dan garis merah §5.9 / §12 diamandemen dengan syarat tetap:
> (1) setiap order LLM wajib melewati risk gate deterministik yang sama
> (SL wajib, lot maks, eksposur, drawdown auto-halt, spread filter),
> (2) kill-switch tetap menghentikan segalanya, (3) setiap keputusan LLM
> tercatat beserta reasoning di order_events, (4) gerbang paper trading
> 20 hari/100 trade dan approval live owner (D1) TIDAK berubah,
> (5) data tak tepercaya ke LLM wajib lolos guard injection (§12.4).

> Dokumen ini adalah spesifikasi dan rencana kerja, bukan bukti bahwa
> sistem telah dibangun atau lulus pengujian. "Siap rilis 100%"
> diartikan sebagai seluruh gerbang penerimaan, keamanan, pemulihan,
> operasional, dan persetujuan owner dalam dokumen ini telah lulus.
> Tidak ada sistem trading yang dapat dijamin bebas risiko atau selalu
> profit.

------------------------------------------------------------------------

# 0. Ringkasan keputusan

Lumine Fund v2.2 melanjutkan arsitektur v2.1 dengan menambahkan lapisan
keselamatan dan kualitas strategi: Strategy Isolation, Portfolio Risk
Manager, Market Regime Detection, Shadow Strategy, Strategy Degradation
Detection, Strategy Versioning/Rollback, Disaster Recovery, serta AI
Research Intelligence.

## 0.1 Tujuan produk

Membangun quant desk XAUUSD yang dapat:

1.  Menerima data pasar dan data eksekusi dari EA MT5.
2.  Menjalankan strategi dengan kontrak input/output yang konsisten pada
    backtest, paper, dan live.
3.  Mengendalikan risiko sebelum setiap order.
4.  Mencatat seluruh keputusan dan perubahan sebagai jejak audit.
5.  Mengukur kualitas eksekusi, spread, slippage, latency, dan kesehatan
    sistem.
6.  Menjalankan beberapa strategi secara terisolasi.
7.  Menguji strategi baru secara shadow/paper sebelum live.
8.  Mendeteksi perubahan rezim pasar dan penurunan performa strategi.
9.  Menggunakan Hermes untuk analisis, eksperimen, dan rekomendasi yang
    harus disetujui owner.
10. Pulih secara terkendali setelah restart, disconnect, crash, atau
    kegagalan infrastruktur.

## 0.2 Prinsip non-negotiable

-   LLM/Hermes tidak memiliki kredensial, endpoint, atau jalur langsung
    untuk mengirim order.
-   LLM tidak dapat mengubah risk limit, kill-switch, akun broker, atau
    status strategi live.
-   Tidak ada strategi live tanpa persetujuan owner yang tercatat.
-   Tidak ada order tanpa SL yang valid di sisi broker, kecuali order
    ditolak sebelum dikirim.
-   Saat data basi, EA offline, state tidak konsisten, atau risiko tidak
    dapat dihitung, sistem menolak order baru.
-   Posisi terbuka tetap dikelola dengan perlindungan broker-side;
    disconnect tidak boleh diasumsikan otomatis menutup posisi.
-   Backtest tidak boleh dipromosikan sebagai bukti profitabilitas live.
-   Semua angka bertanda **\[USULAN\]** harus dikonfirmasi owner setelah
    pengukuran P0.
-   Tidak boleh ada cutover atau live hanya karena jadwal telah habis;
    seluruh gerbang harus lulus.

## 0.3 Definisi "rilis selesai"

Rilis hanya boleh dinyatakan selesai jika: - semua requirement MUST
mempunyai bukti uji; - seluruh critical/high severity defect ditutup
atau memiliki keputusan tertulis yang dapat diterima; - rekonsiliasi
broker dan database lulus skenario normal maupun fault injection; -
backup berhasil dipulihkan dalam lingkungan terpisah; - paper trading
memenuhi durasi dan jumlah trade minimum; - strategi lolos evaluasi
out-of-sample dan biaya realistis; - security review dan akses kontrol
lulus; - monitoring, alert, runbook, rollback, dan owner approval
tersedia; - tidak ada penggunaan uang nyata sebelum gerbang live
disetujui.

------------------------------------------------------------------------

# BAGIAN A --- PRODUCT REQUIREMENTS

# 1. Ruang lingkup

## 1.1 In scope

-   Instrumen: XAUUSD.
-   Broker: HFM.
-   Akun: satu akun awal; environment demo dan live dipisahkan secara
    eksplisit.
-   Platform eksekusi: MetaTrader 5 + Expert Advisor (EA).
-   Backend: FastAPI.
-   Database: PostgreSQL 16.
-   Penyimpanan data historis/tick: Parquet.
-   UI: Login, Dashboard, Riwayat, Strategy Lab, ditambah halaman
    operasional/administrasi yang diperlukan.
-   Strategi awal: rule-based.
-   Riset: backtest, walk-forward, paper trading, shadow, analisis
    hasil.
-   Operasional: alert Telegram, backup, restore, monitoring, audit.
-   Hermes: riset, analisis, pembuatan proposal, dan laporan; bukan
    eksekutor order.

## 1.2 Out of scope v2.2

-   Multi-broker dan multi-aset.
-   High-frequency trading mikrodetik/co-location.
-   Copy trading, marketplace strategi, dan social trading.
-   Pengelolaan dana pihak ketiga.
-   Deposit/withdrawal pelanggan.
-   Model yang mengubah risk limit sendiri.
-   Eksekusi order oleh LLM/agent.
-   Klaim profit, return, atau tingkat akurasi yang dijamin.
-   Auto-deploy strategi live tanpa persetujuan owner.

## 1.3 Lingkungan

  -------------------------------------------------------------------------
  Environment      Tujuan                      Uang nyata Akun/credential
  ---------------- ---------------- --------------------- -----------------
  Local/dev        Pengembangan dan                 Tidak Dummy
                   unit test                              

  Staging          Integrasi, QA,                   Tidak Demo/test
                   simulasi fault                         

  Demo/paper       Pengamatan                       Tidak Akun demo
                   strategi dan                           terpisah
                   eksekusi demo                          

  Live             Produksi                            Ya Credential live,
                   terbatas                               akses paling
                                                          ketat
  -------------------------------------------------------------------------

Tidak boleh ada credential live di laptop developer, log, prompt Hermes,
file repository, atau environment demo.

# 2. Aktor dan kewenangan

  ----------------------------------------------------------------------------
  Aktor                   Hak                          Larangan
  ----------------------- ---------------------------- -----------------------
  Owner                   Approve strategi, mengubah   Tidak boleh melewati
                          risk setting,                pencatatan audit
                          mengaktifkan/menonaktifkan   
                          live, kill-switch, flatten   

  CEO agent               Merangkum status, membagi    Tidak mengirim order
                          tugas, meminta review        atau mengubah risiko

  Backend agent           Mengembangkan API, state     Tidak menyetujui live
                          machine, risk engine         

  DevOps agent            Infrastruktur, backup,       Tidak
                          deployment                   membaca/mengekspor
                                                       credential broker tanpa
                                                       kebutuhan

  QA agent                Menjalankan test dan         Tidak mengubah hasil
                          menyatakan hasil QA          test atau meluluskan
                                                       defect kritis

  Frontend agent          UI dan dashboard             Tidak mengakses secret
                                                       backend

  Hermes/research agent   Analisis, backtest, proposal Tidak punya akses
                          strategi                     order, broker
                                                       credential, atau risk
                                                       write

  EA/MT5                  Mengirim data, menerima      Tidak menentukan risk
                          command yang telah           policy
                          diotorisasi, melaporkan fill 
  ----------------------------------------------------------------------------

Semua agent bekerja dengan least privilege. Persetujuan akhir tetap
manusia.

# 3. Arsitektur target

## 3.1 Komponen logis

1.  **Market Data Adapter:** menerima tick, candle, spread, timestamp
    broker, dan status koneksi dari EA.
2.  **Data Normalizer:** memvalidasi simbol, digit, timezone, urutan
    timestamp, gap, duplikasi, dan kualitas data.
3.  **Strategy Runtime:** menjalankan `decide(context)` dalam batas
    waktu dan resource.
4.  **Strategy Isolation Supervisor:** mengawasi proses strategi,
    timeout, crash, konsumsi resource, dan circuit breaker.
5.  **Market Regime Service:** memberi label kondisi pasar beserta
    confidence dan status data.
6.  **Portfolio Risk Manager:** menghitung risiko gabungan posisi dan
    order yang sedang menunggu.
7.  **Risk Gate:** keputusan akhir allow/reject/reduce; tidak dapat
    dioverride Hermes.
8.  **Execution Orchestrator:** state machine order, idempotensi,
    dispatch ke EA, retry yang aman, dan rekonsiliasi.
9.  **MT5 EA Bridge:** heartbeat, command acknowledgement, order send,
    fill report, snapshot.
10. **Event Ledger:** event append-only untuk order, posisi, keputusan
    risiko, dan perubahan konfigurasi.
11. **Research Platform:** backtest, walk-forward, experiment registry,
    shadow, paper, dan laporan.
12. **Hermes Research Layer:** membaca data yang diizinkan dan membuat
    proposal.
13. **Control Plane/UI:** owner approval, risk configuration,
    kill-switch, status, audit, dan release controls.
14. **Observability & Recovery:** metrics, logs, traces, backup,
    restore, alert, runbook.

## 3.2 Batas service

Untuk fase awal, implementasi boleh tetap menggunakan tiga service
deployment seperti v2.1: - `fund2-api` (FastAPI, UI, WebSocket/SSE, task
supervisor) - PostgreSQL 16 - MT5 + EA

Komponen logis tidak harus menjadi microservice terpisah. Pisahkan modul
Python dan boundary antarmodul terlebih dahulu. Jangan menambah Redis,
message broker, atau worker terpisah sebelum metrik membuktikan
kebutuhan. Namun, proses strategi yang tidak dipercaya/berisiko tidak
boleh dijalankan di thread request API; gunakan subprocess/container
terbatas atau worker terisolasi sesuai kemampuan VPS.

## 3.3 Alur order

1.  Strategy menghasilkan `OrderIntent`.
2.  Schema dan freshness validation.
3.  Strategy supervisor memeriksa status strategi.
4.  Regime gate memeriksa apakah strategi boleh aktif pada regime
    tersebut.
5.  Portfolio Risk Manager menghitung risiko gabungan.
6.  Risk Gate memvalidasi SL, volume, exposure, drawdown, spread, data
    age, kill-switch, dan status EA.
7.  Execution Orchestrator membuat order intent yang idempotent.
8.  EA menerima command, memvalidasi signature/nonce/expiry, lalu
    memberi acknowledgement.
9.  EA mengirim order ke MT5.
10. EA mengirim retcode dan fill/deal.
11. Backend memperbarui projection posisi dan menambahkan event ledger.
12. Reconciler membandingkan kondisi backend dengan snapshot broker.
13. UI dan monitoring menampilkan status aktual.

**Kegagalan pada langkah mana pun harus menghasilkan status eksplisit,
bukan asumsi sukses.**

# 4. Kontrak data dan interface

## 4.1 `OrderIntent`

Wajib memiliki: - `strategy_id` - `strategy_version` - `signal_id` -
`client_order_id` unik - `symbol` - `side` (BUY/SELL) - `order_type` -
`volume` - `requested_price` bila relevan - `stop_loss` - `take_profit`
opsional sesuai policy - `created_at` - `expires_at` - `reason_code` -
`context_hash`

Order tanpa SL, volume valid, identitas strategi, atau expiry ditolak.

## 4.2 Market context

Minimal: - candle dan timestamp; - bid, ask, spread; - tick timestamp
dan age; - sesi pasar; - posisi dan pending order; - regime label dan
confidence; - status feed dan EA; - parameter risiko read-only; - versi
data/schema.

Context harus immutable untuk satu pemanggilan `decide()`, agar hasil
dapat direproduksi.

## 4.3 Timestamp

-   Simpan timestamp internal dalam UTC.
-   Simpan timestamp broker asli dan timezone/offset sumber.
-   Gunakan monotonic clock untuk pengukuran durasi di satu proses.
-   Jangan menghitung latency dengan mengurangkan jam dari host berbeda
    tanpa sinkronisasi.
-   Catat status NTP/clock drift.

## 4.4 Validasi data

Tolak atau tandai data bila: - timestamp mundur atau terlalu jauh di
masa depan; - bid/ask nol, negatif, atau tidak masuk akal; - ask \<
bid; - tick melewati freshness threshold; - simbol/contract
specification berubah; - gap data melebihi batas; - duplicate
tick/candle tidak dapat diidentifikasi; - EA mengirim versi schema yang
tidak didukung.

------------------------------------------------------------------------

# BAGIAN B --- STRATEGY & QUANT RESEARCH

# 5. Strategy Isolation

## 5.1 Tujuan

Satu strategi tidak boleh membuat seluruh trading engine gagal. Strategi
harus memiliki lifecycle dan batas resource sendiri.

## 5.2 Persyaratan

-   Setiap strategi mempunyai `strategy_id`, versi immutable,
    konfigurasi, status, dan environment.
-   Jalankan strategi dalam subprocess atau container terisolasi bila
    memungkinkan.
-   Batasi CPU, memory, wall-clock execution time, file access, dan
    network access.
-   Strategy runtime tidak diberi database credential, broker
    credential, atau akses langsung ke execution endpoint.
-   Strategi hanya mengembalikan `OrderIntent` atau `None`.
-   Semua output divalidasi terhadap schema.
-   Timeout, exception, output malformed, NaN/Inf, volume tidak valid,
    atau runtime crash menghasilkan reject.
-   Satu strategi yang gagal masuk `DEGRADED`/`DISABLED`; strategi lain
    tetap berjalan jika shared services sehat.
-   Circuit breaker menonaktifkan strategi setelah ambang error
    beruntun.
-   Restart strategi tidak otomatis mengaktifkan live; perlu status
    enable yang eksplisit.
-   Semua crash dan keputusan supervisor dicatat.

## 5.3 Status lifecycle

`DRAFT → VALIDATING → BACKTEST_APPROVED → SHADOW → PAPER → LIVE_APPROVED → LIVE → DEGRADED → DISABLED → ARCHIVED`

Transisi tertentu hanya dapat dilakukan owner atau release workflow yang
diotorisasi.

## 5.4 Acceptance criteria

-   Crash satu strategi tidak menghentikan API atau strategi lain.
-   Timeout strategi tidak menahan order path melebihi batas yang
    ditetapkan.
-   Strategi tidak dapat membuka koneksi jaringan atau membaca secret.
-   Invalid output selalu ditolak.
-   Circuit breaker dan recovery diuji dengan fault injection.

# 6. Market Regime Detection

## 6.1 Tujuan

Mengidentifikasi kondisi pasar agar strategi hanya aktif pada kondisi
yang telah diuji. Regime detection adalah filter risiko/kelayakan
strategi, bukan prediksi pasti arah harga.

## 6.2 Regime awal

-   `TREND_UP`
-   `TREND_DOWN`
-   `RANGE`
-   `HIGH_VOLATILITY`
-   `LOW_LIQUIDITY`
-   `NEWS_OR_EVENT_RISK` (hanya bila ada kalender/sumber data yang
    tervalidasi)
-   `UNKNOWN`

`UNKNOWN` harus menjadi kondisi aman: strategi yang mensyaratkan regime
tertentu tidak boleh entry.

## 6.3 Fitur kandidat

-   realized volatility/ATR;
-   ADX atau ukuran trend;
-   moving average slope;
-   range expansion/contraction;
-   spread median dan p95;
-   tick rate dan data freshness;
-   sesi Asia/London/NY;
-   gap dan lonjakan harga.

Hindari terlalu banyak fitur pada versi awal. Pilih fitur yang bisa
dihitung ulang secara deterministik dan tersedia di backtest.

## 6.4 Persyaratan

-   Regime classifier memiliki versi dan parameter.
-   Output memuat label, confidence, timestamp, data quality, dan
    alasan.
-   Ambang confidence **\[USULAN\]** harus dikalibrasi.
-   Regime tidak boleh mengubah risk limit.
-   Strategi mendefinisikan regime yang diizinkan.
-   Perubahan regime tidak boleh menyebabkan flip-flop berlebihan;
    gunakan hysteresis/cooldown.
-   Bila data tidak lengkap atau stale, hasil menjadi `UNKNOWN`.
-   Catat regime saat sinyal, saat order, dan selama posisi terbuka.
-   Evaluasi confusion matrix, stabilitas label, dan performa strategi
    per regime.

## 6.5 Acceptance criteria

-   Label dapat direproduksi pada dataset yang sama.
-   Tidak ada look-ahead leakage.
-   Regime `UNKNOWN` memblokir entry yang memerlukan klasifikasi.
-   Backtest dan live menggunakan definisi regime yang sama.
-   Dampak regime filter dibanding baseline dilaporkan out-of-sample.

# 7. Portfolio Risk Manager

## 7.1 Tujuan

Mengukur risiko seluruh portofolio, bukan hanya order individual.

## 7.2 Input

-   equity dan balance;
-   margin/free margin;
-   posisi terbuka;
-   pending orders;
-   volume, entry, SL, contract size, tick value;
-   estimasi loss sampai SL;
-   spread/slippage buffer;
-   order yang sedang `SENT`/belum terkonfirmasi;
-   batas risiko owner;
-   status broker dan data.

## 7.3 Aturan

-   Hitung worst-case loss setiap posisi sampai SL, termasuk biaya dan
    buffer.
-   Hitung aggregate open risk.
-   Sertakan order pending dan order `SENT` agar tidak terjadi
    oversubscription.
-   Batasi risiko per trade, total open risk, gross exposure, volume,
    margin utilization, dan konsentrasi.
-   Tolak order bila contract specification/tick value tidak dapat
    diverifikasi.
-   Jangan mengasumsikan dua posisi saling meng-hedge kecuali model
    broker dan netting/hedging account telah diverifikasi.
-   Jangan menggunakan korelasi historis sebagai jaminan bahwa posisi
    akan saling melindungi.
-   Terapkan stress scenario untuk gap, spread melebar, slippage, dan
    beberapa SL terkena bersamaan.
-   Saat equity/margin feed stale, jangan membuka posisi baru.
-   Posisi yang sudah terbuka tidak otomatis ditutup hanya karena risk
    metric berubah; jalankan policy owner yang eksplisit.

## 7.4 Parameter awal

Nilai berikut adalah **\[USULAN\]**, bukan rekomendasi finansial
universal: - risiko per trade maksimum: 0,5% equity; - daily drawdown
halt: 3%; - peak-to-trough drawdown halt: 8%; - volume maksimum per
order: 0,10 lot; - total volume maksimum: 0,30 lot.

Semua harus dikalibrasi berdasarkan modal, contract specification HFM,
leverage, akun, dan toleransi risiko owner. Jangan mengaktifkan nilai
default tanpa persetujuan tertulis.

## 7.5 Acceptance criteria

-   Uji perhitungan risiko dengan fixture contract specification yang
    benar.
-   Uji beberapa posisi dan pending order bersamaan.
-   Uji race condition dua sinyal simultan.
-   Uji saat equity/margin data hilang.
-   Uji saat SL tidak terpasang/ditolak broker.
-   Tidak ada order yang lolos ketika total risk melewati limit.

# 8. Backtesting & eksperimen

## 8.1 Prinsip

Backtest harus realistis, reproducible, dan dapat diaudit. Hasil
backtest bukan jaminan hasil live.

## 8.2 Persyaratan

-   Satu implementasi `decide()` untuk backtest, shadow, paper, dan
    live.
-   Perbedaan hanya pada adapter data dan execution simulator/adapter.
-   Data provenance: sumber, periode, simbol, timezone, versi, checksum,
    dan tanggal unduh.
-   Deteksi gap, duplicate, missing bars, bad ticks, dan
    survivorship/selection bias yang relevan.
-   Simulasikan spread, komisi, swap bila berlaku, slippage, latency,
    rejection, partial fill, dan market closure.
-   Hindari look-ahead bias, future leakage, dan penggunaan candle yang
    belum close tanpa definisi eksplisit.
-   Walk-forward split ditentukan sebelum eksperimen.
-   Simpan seluruh parameter yang dicoba, bukan hanya hasil terbaik.
-   Simpan commit hash kode, versi dependency, data hash, config hash,
    dan random seed.
-   Catat baseline sederhana untuk pembanding.
-   Laporkan performa per sesi, regime, hari, dan kondisi spread.

## 8.3 Metrik wajib

-   net profit/loss setelah biaya;
-   profit factor;
-   expectancy per trade;
-   max drawdown dan durasi drawdown;
-   Sharpe dan Sortino dengan metodologi dijelaskan;
-   win rate dan average win/loss;
-   jumlah trade;
-   exposure time;
-   average holding time;
-   spread/slippage distribution;
-   tail loss dan worst day;
-   hasil per regime dan sesi;
-   confidence interval/ketidakpastian bila metodologinya memadai.

Jangan memakai win rate sebagai metrik tunggal.

## 8.4 Gerbang strategi

Ambang awal **\[USULAN\]**: - sekurangnya 2 tahun data yang sesuai; -
walk-forward window dan test window ditetapkan sebelum eksperimen; -
sekurangnya 100 trade paper untuk evaluasi awal; - paper sekurangnya 20
hari kerja; - profit factor paper minimal 1,3 setelah biaya; - max
drawdown paper maksimal 5%.

Angka ini bukan bukti statistik yang otomatis cukup. Owner dan QA harus
menilai jumlah sampel, distribusi hasil, ketidakpastian, dan kesesuaian
kondisi pasar.

# 9. Shadow Strategy

## 9.1 Definisi

Shadow strategy menerima data live yang sama dan menghasilkan sinyal,
tetapi tidak mengirim order ke broker.

## 9.2 Persyaratan

-   Sinyal shadow dicatat lengkap dengan harga referensi, spread,
    timestamp, regime, dan alasan.
-   Simulasikan fill dengan model biaya konservatif.
-   Bandingkan sinyal shadow dengan strategi live dan baseline.
-   Shadow tidak boleh mengakses endpoint order.
-   Tandai hasil sebagai simulasi, bukan realized P&L.
-   Dukung beberapa versi strategi bersamaan.
-   Beri label perubahan kode/parameter yang diuji.

## 9.3 Gerbang promosi

Strategi hanya boleh maju dari shadow ke paper bila: - tidak ada error
kritis; - perilaku sinyal sesuai spesifikasi; - hasil out-of-sample dan
biaya masuk akal; - tidak ada indikasi data leakage; - owner menyetujui
eksperimen paper.

# 10. Strategy Degradation Detection

## 10.1 Tujuan

Mendeteksi perubahan performa strategi dari baseline yang tervalidasi,
tanpa bereaksi berlebihan terhadap variasi acak.

## 10.2 Indikator

-   rolling expectancy;
-   rolling profit factor;
-   drawdown;
-   average adverse/favorable excursion;
-   spread dan slippage aktual;
-   fill/rejection rate;
-   distribusi regime;
-   perubahan frekuensi sinyal;
-   perbedaan paper/live dari ekspektasi;
-   drift fitur/data.

## 10.3 Status

`NORMAL → WATCH → DEGRADED → HALTED`

-   `WATCH`: notifikasi dan peningkatan pemantauan.
-   `DEGRADED`: strategi tidak boleh menambah risiko baru atau masuk
    policy pembatasan yang ditetapkan owner.
-   `HALTED`: strategi berhenti membuka posisi baru; posisi yang ada
    mengikuti policy pengelolaan posisi.
-   Re-enable memerlukan review dan approval owner.

## 10.4 Anti false alarm

-   Minimum sample size.
-   Cooldown.
-   Evaluasi per regime.
-   Pisahkan kerugian acak dari perubahan struktural.
-   Jangan otomatis mengoptimalkan parameter untuk mengejar data
    terbaru.
-   Semua threshold terversi dan diuji.

# 11. Strategy Versioning, Approval & Rollback

## 11.1 Immutable release

Setiap versi strategi menyimpan: - strategy ID dan version; - kode dan
commit hash; - parameter/config hash; - data version/hash; - backtest
report; - walk-forward report; - shadow/paper report; - risk profile; -
reviewer dan approval; - tanggal aktivasi/nonaktif; - alasan perubahan.

Versi yang pernah live tidak boleh ditimpa. Buat versi baru.

## 11.2 Promotion workflow

`DRAFT → BACKTEST → REVIEW → SHADOW → PAPER → OWNER_APPROVAL → CANARY/LOW_RISK_LIVE → FULL_APPROVED_LIVE`

Setiap transisi memiliki bukti dan aktor yang berwenang.

## 11.3 Rollback

-   Owner dapat memilih versi terakhir yang disetujui.
-   Rollback menghentikan sinyal baru dari versi bermasalah.
-   Jangan otomatis menghapus atau menutup posisi yang sudah terbuka.
-   Posisi terbuka mengikuti policy exit/management yang ditentukan
    owner.
-   Rollback tercatat sebagai event.
-   Lakukan rekonsiliasi setelah rollback.

## 11.4 Acceptance criteria

-   Tidak dapat mengubah artifact versi yang sudah disetujui.
-   Setiap live strategy memiliki versi yang jelas.
-   Rollback diuji di staging.
-   Tidak ada auto-promotion oleh Hermes.

# 12. AI Research Intelligence --- Hermes

## 12.1 Tanggung jawab

Hermes boleh: - membaca dataset dan event log yang telah disanitasi; -
mengelompokkan pola transaksi; - membuat ringkasan profit/loss dan
biaya; - mengidentifikasi kemungkinan penyebab kerugian; - menyusun
hipotesis strategi; - membuat draft strategi/parameter eksperimen; -
menjalankan backtest melalui tool riset terbatas; - membandingkan
strategi dengan baseline; - menulis laporan mingguan; - mengusulkan
perubahan untuk owner.

Hermes tidak boleh: - mengakses broker credential; - mengirim, mengubah,
atau membatalkan order live; - mengubah risk settings; - mengaktifkan
strategi live; - mengubah kill-switch; - mengubah audit log; - deploy ke
production tanpa approval; - menganggap korelasi sebagai sebab-akibat; -
menyatakan strategi profitable hanya dari sampel kecil.

## 12.2 Research workflow

1.  Ambil data read-only yang diizinkan.
2.  Validasi kelengkapan data.
3.  Buat diagnosis dengan bukti dan confidence.
4.  Pisahkan fakta, hipotesis, dan rekomendasi.
5.  Buat eksperimen yang dapat direproduksi.
6.  Jalankan backtest dan walk-forward.
7.  Bandingkan baseline dan versi sebelumnya.
8.  Buat laporan dengan risiko, keterbatasan, dan kondisi gagal.
9.  Minta review QA.
10. Ajukan ke owner.
11. Setelah approval, release workflow terpisah yang mengeksekusi
    perubahan.
12. Pantau hasil dan siapkan rollback.

## 12.3 Format laporan Hermes

-   Executive summary.
-   Periode dan sumber data.
-   Data quality.
-   Temuan terukur.
-   Hipotesis (bukan fakta).
-   Eksperimen dan konfigurasi.
-   Baseline vs kandidat.
-   Biaya dan asumsi.
-   Drawdown dan tail risk.
-   Kapan strategi gagal.
-   Rekomendasi.
-   Risiko residual.
-   Keputusan yang dibutuhkan owner.

## 12.4 Prompt injection dan data tidak tepercaya

Data pasar, komentar, file, log, dan output eksternal dianggap data
tidak tepercaya, bukan instruksi. Hermes harus memakai tool allowlist,
output schema, dan sandbox. Dilarang mengeksekusi perintah dari teks
yang ditemukan di data/log. Tool riset tidak memiliki akses ke secret
atau production control plane.

# BAGIAN C --- EXECUTION, SAFETY & RELIABILITY

# 13. Execution state machine

## 13.1 Status

`RECEIVED → VALIDATED → RISK_PASS → SENT → ACKNOWLEDGED → FILLED/PARTIALLY_FILLED/FAILED/STUCK`

Tambahan rekonsiliasi: `RECONCILED`, `ORPHAN_ADOPTED`, `ORPHAN_CLOSED`,
`CANCEL_PENDING`, `CANCELLED`, `UNKNOWN`.

Transisi harus tervalidasi; tidak boleh melompat status tanpa event dan
alasan.

## 13.2 Idempotensi dan retry

-   `client_order_id` unik dan wajib.
-   Request duplikat mengembalikan hasil sebelumnya.
-   Timeout setelah pengiriman tidak boleh langsung retry order baru.
-   Cek status broker/reconciler sebelum mengulang.
-   Setiap command mempunyai expiry dan correlation ID.
-   EA menyimpan/menangani duplicate command dengan aman.
-   Retry hanya untuk operasi yang terbukti idempotent.

## 13.3 Partial fill dan rejection

-   Simpan requested volume dan filled volume terpisah.
-   Catat retcode, broker comment, requested price, fill price, dan
    timestamp.
-   Partial fill memperbarui exposure berdasarkan volume aktual.
-   Rejection harus memiliki reason code.
-   Jangan menganggap `OrderSend` return sukses sebagai fill final;
    konfirmasi melalui deal/position state.

# 14. MT5 EA Bridge

## 14.1 Heartbeat

-   Heartbeat setiap 2 detik **\[USULAN\]**.
-   Tiga heartbeat terlewat menandai offline.
-   Catat EA version, MT5 build, account identifier yang dimasking,
    symbol spec, dan clock status.
-   EA reconnect mengirim snapshot posisi dan deal sesuai periode yang
    disepakati.

## 14.2 Keamanan bridge

-   Bind endpoint lokal ke `127.0.0.1`.
-   Firewall menutup port dari luar.
-   HMAC-SHA256, timestamp, nonce sekali pakai, expiry, dan replay
    protection.
-   Secret disimpan di environment/secret store, tidak di repository.
-   Rotasi secret memiliki prosedur dan masa transisi.
-   Batasi ukuran payload dan rate.
-   Validasi schema dan versi protocol.
-   Jangan log secret atau signature mentah yang sensitif.

## 14.3 Contract specification

Ambil dan verifikasi dari broker/MT5: - digits/point; - tick
size/value; - contract size; - min/max/step volume; - stop level/freeze
level; - trading sessions; - margin requirements; - execution/filling
mode.

Jika data ini tidak tersedia atau berubah, risk gate menolak order baru
sampai validasi selesai.

# 15. Reconciliation & disconnect

## 15.1 Skenario

-   API restart.
-   EA restart.
-   MT5 terminal crash.
-   VPS reboot.
-   Internet putus.
-   Broker menolak order.
-   Command terkirim tetapi acknowledgement hilang.
-   Fill terjadi tetapi event tidak sampai ke API.
-   Posisi broker tidak dikenal database.
-   Posisi database tidak ada di broker.
-   Partial close atau manual intervention.

## 15.2 Prosedur reconnect

1.  Tandai bridge `RECOVERING`.
2.  Blokir order baru.
3.  Ambil snapshot posisi, pending orders, dan deal history dari broker.
4.  Validasi timestamp dan account/symbol.
5.  Bandingkan dengan ledger.
6.  Klasifikasikan mismatch.
7.  Jangan membuat asumsi atas order yang statusnya tidak jelas.
8.  Buat event rekonsiliasi.
9.  Jika mismatch kritis, aktifkan kill-switch dan minta owner.
10. Setelah konsisten, owner/aturan recovery mengizinkan kembali ke
    `ONLINE`.

## 15.3 Orphan policy

-   Posisi broker yang tidak dikenal: adopsi sebagai external/orphan
    position untuk monitoring, jangan otomatis menambah posisi.
-   Jika tidak memiliki SL, kirim alert kritis dan jalankan kebijakan
    darurat yang telah disetujui owner; jangan mengarang jarak SL.
-   Posisi database yang tidak ada di broker: cocokkan deal history
    sebelum ditandai closed/failed.
-   Ketidakcocokan yang tidak dapat dijelaskan: kill-switch, alert, dan
    blokir entry.

# 16. Kill-switch & emergency control

Mode: - `STOP_NEW_ORDERS`: menolak order baru. - `STOP_AND_FLATTEN`:
menolak order baru dan meminta penutupan seluruh posisi; memerlukan
konfirmasi eksplisit dan penjelasan risiko slippage. - `PAUSE_STRATEGY`:
menghentikan strategi tertentu. - `GLOBAL_HALT`: menghentikan semua
entry.

Pemicu otomatis yang dapat dikonfigurasi: - drawdown limit; - EA
offline; - data stale; - posisi/ledger mismatch; - beberapa order gagal
beruntun; - latency atau rejection abnormal; - spread ekstrem; -
database/event ledger tidak tersedia.

Kill-switch harus persisten melewati restart. Pengaktifan dan pelepasan
tercatat. Pelepasan global halt memerlukan owner dan checklist recovery.

# 17. Disaster Recovery & Business Continuity

## 17.1 Tujuan

Memastikan sistem dapat dipulihkan tanpa menciptakan order duplikat atau
kehilangan pemahaman tentang posisi broker.

## 17.2 Backup

-   Backup database harian dan sebelum deployment besar.
-   Backup konfigurasi non-secret.
-   Secret backup mengikuti kebijakan secret management terpisah.
-   Parquet dan dataset memiliki checksum serta manifest.
-   Retensi **\[USULAN\]** 30 hari untuk backup harian; owner menetapkan
    retensi lebih panjang sesuai kebutuhan.
-   Backup terenkripsi dan akses terbatas.
-   Simpan salinan di lokasi/volume berbeda dari disk utama bila
    anggaran memungkinkan.

## 17.3 Restore drill

-   Restore ke staging terisolasi.
-   Verifikasi schema/migration.
-   Verifikasi jumlah event dan rentang timestamp.
-   Verifikasi checksum dataset.
-   Jalankan query integritas.
-   Bandingkan state hasil restore dengan snapshot sumber.
-   Catat durasi restore dan error.
-   Jangan pernah mengarahkan hasil restore staging ke broker live.

## 17.4 RTO/RPO

Tetapkan sebelum live: - RPO database **\[USULAN awal\]** maksimum 24
jam untuk backup harian; lebih kecil bila WAL/PITR tersedia. - RTO
layanan **\[USULAN awal\]** 4 jam. - RTO bridge dan rekonsiliasi
ditetapkan terpisah. Nilai final harus realistis terhadap VPS, storage,
koneksi, dan proses manual yang tersedia.

## 17.5 Recovery sequence

1.  Pastikan sumber masalah dan keamanan host.
2.  Pastikan trading halt aktif.
3.  Pulihkan API/database dari sumber tervalidasi.
4.  Verifikasi integritas ledger.
5.  Nyalakan MT5/EA tanpa mengirim order baru.
6.  Ambil broker snapshot.
7.  Jalankan reconciliation.
8.  Review posisi dan pending orders.
9.  Uji heartbeat dan command channel di demo/staging.
10. Owner menyetujui resume.

# 18. Security

-   Password Argon2id.
-   Session cookie HttpOnly, Secure, SameSite sesuai arsitektur.
-   CSRF protection bila menggunakan cookie auth.
-   Rate limit login dan aksi sensitif.
-   2FA untuk perubahan risk settings, live approval, flatten, dan
    release.
-   RBAC dan least privilege.
-   Audit trail untuk login, perubahan konfigurasi, approval,
    deployment, dan emergency action.
-   HMAC + nonce untuk EA bridge.
-   TLS untuk akses eksternal melalui Caddy.
-   Firewall default-deny.
-   Secret tidak disimpan di Git, log, prompt, screenshot, atau artefak
    build.
-   Dependency pinning, vulnerability scan, dan update policy.
-   Backup terenkripsi.
-   Log redaction.
-   Session expiry dan revoke.
-   Proteksi brute force dan account lockout yang tidak mudah
    disalahgunakan.
-   Security review sebelum live.
-   Penetration test sederhana untuk auth, authorization, bridge,
    replay, CSRF, injection, dan privilege escalation.

# BAGIAN D --- DATA, DATABASE & OBSERVABILITY

# 19. Data pipeline

## 19.1 Data live

-   EA mengirim tick batch dan candle.
-   Tick ditahan di ring buffer dan di-flush ke Parquet.
-   PostgreSQL menyimpan candle M1+, agregat likuiditas, transaksi,
    posisi, event, dan metadata eksperimen.
-   Order path tidak boleh menunggu penulisan tick.
-   Backpressure boleh mengurangi sampel analitik, tetapi tidak boleh
    membuang order event.
-   Jika event ledger tidak dapat ditulis, sistem tidak boleh mengklaim
    order berhasil tercatat; masuk safe halt sesuai policy.

## 19.2 Kualitas data

-   Data completeness.
-   Duplicate rate.
-   Timestamp monotonicity.
-   Gap detection.
-   Spread validity.
-   Candle OHLC consistency.
-   Symbol mapping.
-   Broker-vs-historical source differences.
-   Data version and checksum.

## 19.3 Database logical tables

Minimal: - `users` - `sessions` - `settings` - `settings_audit` -
`orders` - `order_events` - `positions` - `position_snapshots` -
`candles` - `liquidity_samples` - `signals` - `strategies` -
`strategy_versions` - `strategy_approvals` - `backtest_runs` -
`paper_runs` - `shadow_runs` - `regime_observations` -
`risk_decisions` - `system_events` - `reconciliation_runs` -
`deployment_records` - `research_reports`

Gunakan migration versioning. Retensi dan partitioning ditetapkan
berdasarkan volume aktual.

## 19.4 Append-only ledger

`order_events` tidak boleh diubah/dihapus oleh aplikasi normal. Gunakan
DB permission, trigger/policy, backup, dan audit. Koreksi dilakukan
dengan event kompensasi, bukan mengedit sejarah.

# 20. Observability & alerting

## 20.1 Metrics

-   API availability dan latency.
-   T0→T2 p50/p95/p99.
-   T2→T3 broker latency.
-   T0→T4 end-to-end.
-   EA heartbeat age.
-   Tick age dan data gaps.
-   Spread median/p95.
-   Slippage distribution.
-   Order state counts.
-   Rejection/failure rate.
-   Reconciliation mismatch count.
-   Strategy runtime/error/timeout.
-   Database connections, disk, backup age.
-   CPU, RAM, swap, disk I/O.
-   Drawdown, exposure, margin, kill-switch status.

## 20.2 Alert severity

-   **SEV-1:** risiko posisi tidak terlindungi, ledger mismatch kritis,
    order tidak diketahui, credential compromise. Global halt dan owner
    alert.
-   **SEV-2:** EA offline saat posisi terbuka, database unavailable,
    repeated execution failures. Halt entry dan investigasi.
-   **SEV-3:** latency/spread/degradation warning. Watch atau pause
    strategi.
-   **SEV-4:** laporan harian, backup sukses, informasi operasional.

Alert harus actionable: apa yang terjadi, dampak, waktu, tindakan
otomatis, dan langkah manual.

# BAGIAN E --- USER EXPERIENCE & CONTROL PLANE

# 21. UI requirements

## 21.1 Login

-   Auth aman, session expiry, rate limit.
-   Status environment terlihat jelas: DEV / DEMO / LIVE.
-   LIVE menggunakan visual warning yang tidak mungkin tertukar dengan
    DEMO.
-   Aksi sensitif memerlukan re-authentication/2FA.

## 21.2 Dashboard

Tampilkan: - environment dan akun yang dimasking; - status API,
database, EA, dan broker; - harga bid/ask dan timestamp; - spread saat
ini, median, p95; - sesi pasar; - posisi terbuka, SL/TP, floating P&L; -
total open risk dan margin; - daily/overall drawdown; - strategi aktif
dan versinya; - regime saat ini dan confidence; - latency p50/p95/p99; -
kill-switch dan alert aktif.

Tidak boleh menampilkan data stale seolah-olah live. Timestamp dan
indikator stale wajib terlihat.

## 21.3 Riwayat / Event Ledger

-   Filter tanggal, strategi, status, symbol, dan reason code.
-   Timeline per order.
-   Requested vs filled price.
-   Slippage, latency, volume, SL/TP.
-   Risk decision dan alasan reject.
-   Export CSV dengan audit.
-   Data ledger read-only.

## 21.4 Strategy Lab

-   Daftar strategi dan lifecycle.
-   Version diff.
-   Backtest/walk-forward reports.
-   Shadow dan paper performance.
-   Regime suitability.
-   Degradation status.
-   Approval history.
-   Enable/disable dengan konfirmasi.
-   Rollback ke versi yang disetujui.
-   Tidak ada tombol "AI auto trade".

## 21.5 Operations & Recovery

-   Health status.
-   Backup age dan restore drill result.
-   Reconciliation status.
-   Pending/stuck/orphan orders.
-   Kill-switch control.
-   Runbook shortcut.
-   Audit history.

## 21.6 UX safety

-   Konfirmasi dua langkah untuk live, flatten, perubahan risiko, dan
    release.
-   Tampilkan konsekuensi tindakan.
-   Tidak mengandalkan warna saja; gunakan teks/status.
-   Mobile dapat memonitor dan menghentikan entry, tetapi aksi berisiko
    tinggi tetap memerlukan autentikasi kuat.
-   Tidak ada default action berbahaya.

# BAGIAN F --- TESTING & QUALITY GATES

# 22. Test strategy

## 22.1 Test levels

1.  Static analysis, lint, type checking.
2.  Unit tests.
3.  Property-based tests untuk risk calculation/state transitions.
4.  Integration tests dengan database dan mock EA.
5.  Contract tests API↔EA.
6.  End-to-end demo tests.
7.  Backtest parity tests.
8.  Load/soak tests.
9.  Fault injection/chaos tests.
10. Security tests.
11. Restore/recovery drills.
12. User acceptance tests.

## 22.2 Test cases minimum

### Order/execution

-   Order valid.
-   SL hilang/invalid.
-   Duplicate client order ID.
-   EA acknowledgement hilang.
-   Partial fill.
-   Rejection.
-   Order stuck.
-   Broker fill diterima setelah API restart.
-   Manual order di MT5.
-   Cancel/close event.
-   Race condition dua sinyal.

### Risk

-   Risiko per trade melebihi batas.
-   Total exposure melebihi batas.
-   Drawdown harian dan total.
-   Spread di atas ambang.
-   Tick stale.
-   EA offline.
-   Margin tidak cukup.
-   Contract specification hilang.
-   Beberapa posisi mencapai SL bersamaan.
-   Risk setting berubah saat ada order in-flight.

### Recovery

-   API restart saat order SENT.
-   VPS reboot saat posisi terbuka.
-   Database restart.
-   Disk penuh.
-   EA reconnect.
-   Snapshot tidak cocok.
-   Backup restore.
-   Network partition.

### Strategy

-   Timeout dan crash.
-   Output NaN/Inf.
-   Invalid schema.
-   Repeated signal.
-   Regime UNKNOWN.
-   Degradation trigger.
-   Version rollback.
-   Shadow/live divergence.

### Security

-   Brute force.
-   Session hijack/revoke.
-   CSRF.
-   Unauthorized risk change.
-   HMAC invalid.
-   Replay nonce.
-   Expired command.
-   Secret leakage scan.
-   Prompt injection dalam data riset.

## 22.3 Coverage dan quality

Target **\[USULAN\]**: - 100% branch coverage untuk fungsi risk gate
kritis. - Coverage keseluruhan bukan satu-satunya ukuran kualitas. -
Semua state transition punya test. - Tidak ada critical/high severity
bug terbuka. - Semua test flaky diselesaikan atau dikarantina dengan
alasan. - Build dan deployment reproducible.

# BAGIAN G --- DELIVERY PLAN DARI NOL SAMPAI RILIS

# 23. Fase dan urutan kerja

Jadwal adalah estimasi awal, bukan janji. Durasi harus disesuaikan
setelah P0 mengukur kapasitas tim, kondisi VPS, MT5, dan kualitas data.
Paper trading 20 hari kerja berjalan berdasarkan kalender pasar dan
tidak boleh dipersingkat untuk mengejar tanggal rilis.

  ---------------------------------------------------------------------------
  Fase             Fokus                    Estimasi awal Gerbang
  ---------------- ---------------- --------------------- -------------------
  P0               Discovery,                   2--3 hari Semua keputusan
                   audit, baseline,                       kritis dan data
                   pengukuran HFM                         awal tersedia

  P1               Fondasi repo,                5--7 hari E2E demo dan event
                   CI, DB, auth,                          ledger
                   bridge                                 

  P2               Risk, execution,             5--7 hari Risk dan disconnect
                   recovery dasar                         tests lulus

  P3               UI, Strategy                 5--7 hari UI dan paper mode
                   Lab, strategi                          berfungsi
                   rule #1                                

  P4               Data pipeline,              6--10 hari Paritas dan laporan
                   backtester,                            riset
                   walk-forward                           

  P5               Isolation,                   5--8 hari Isolasi dan risk
                   regime,                                aggregation lulus
                   portfolio risk                         

  P6               Shadow,                      5--8 hari Lifecycle strategi
                   degradation,                           lengkap
                   versioning                             

  P7               Hermes research              4--7 hari Batas akses AI
                   intelligence                           terbukti

  P8               Security,                    5--8 hari Security/recovery
                   observability,                         gates lulus
                   DR, soak test                          

  P9               Paper trading,   Minimal 20 hari kerja Semua go-live gates
                   UAT, release         paper; QA paralel 
                   candidate                              

  P10              Canary live      Berdasarkan keputusan Stabilitas memenuhi
                   terbatas dan                     owner kriteria
                   monitoring                             

  P11              General release     7 hari stabilisasi Owner sign-off
                   dan post-release                  awal 
                   review                                 
  ---------------------------------------------------------------------------

Fase dapat overlap hanya jika dependency dan acceptance criteria tidak
dikompromikan.

## 23.1 P0 --- Discovery & baseline

Tugas: - Audit repo v1 dan PRD v2.1. - Inventaris server, OS, disk, RAM,
CPU, firewall, Caddy, domain, backup. - Inventaris MT5 build, EA, broker
account type, symbol specification, trading session. - Verifikasi akun
demo. - Mulai merekam spread, slippage, tick, heartbeat, broker
retcode. - Tetapkan risk owner, approval workflow, dan emergency
contact. - Putuskan parameter \[USULAN\]. - Tetapkan data retention,
RTO/RPO, dan release criteria. - Buat architecture decision records
(ADR).

DoD: - Baseline infrastruktur dan broker terdokumentasi. - Feed data HFM
terekam dan tervalidasi. - Owner menyetujui parameter dan scope. - Tidak
ada credential masuk repository.

## 23.2 P1 --- Engineering foundation

Tugas: - Repo dan branch policy. - CI lint/type/test/security scan. -
Environment dev/staging/demo/live terpisah. - PostgreSQL migration. -
Auth, RBAC, session. - Event ledger append-only. - API schema dan
versioning. - HMAC bridge dan heartbeat. - Secret management. - Basic
metrics/logging.

DoD: - CI wajib lulus sebelum merge. - Auth/RBAC tests lulus. - EA
heartbeat dan HMAC valid. - Event ledger integrity lulus. - Staging
deploy repeatable.

## 23.3 P2 --- Execution & safety core

Tugas: - Order state machine. - Idempotency. - Risk gate. - Portfolio
exposure baseline. - Kill-switch. - Reconciler. - Partial fill/rejection
handling. - Disconnect handling. - Broker snapshot.

DoD: - Semua order state tests lulus. - Duplicate command tidak membuat
duplicate order. - 10/10 skenario disconnect yang ditentukan lulus. -
Kill-switch bertahan setelah restart. - Tidak ada order ketika safety
dependency unavailable.

## 23.4 P3 --- UI & strategy baseline

Tugas: - Login, dashboard, history, Strategy Lab. - Environment
indicator. - Stale data indicators. - Strategy #1 rule-based. - Paper
adapter. - Owner approval UI. - Mobile monitoring.

DoD: - UAT owner lulus. - Demo order terlihat utuh pada UI. - Strategi
tidak dapat live tanpa approval. - UI tidak menyembunyikan status
error/stale.

## 23.5 P4 --- Data & research engine

Tugas: - Historical crawler. - Dataset manifest/checksum. - Data quality
pipeline. - Backtester event-driven. - Spread/slippage/commission/swap
assumptions. - Walk-forward. - Experiment registry. - Baseline strategy
comparison. - Research reports.

DoD: - Dataset provenance lengkap. - Backtest reproducible dari
commit/config/data hash. - Paritas sinyal backtest dan paper sesuai
tolerance yang ditetapkan. - Laporan mencakup biaya dan kondisi gagal.

## 23.6 P5 --- Isolation, regime, portfolio risk

Tugas: - Strategy runtime supervisor. - CPU/memory/time/network
restrictions. - Circuit breaker. - Regime classifier deterministic. -
UNKNOWN safe behavior. - Portfolio aggregate risk. - Concurrent signal
race tests. - Risk stress tests.

DoD: - Crash satu strategi tidak menghentikan sistem. - Tidak ada akses
strategy runtime ke broker/secret. - Portfolio limit selalu
ditegakkan. - Regime output reproducible. - Regime filter tidak memakai
future data.

## 23.7 P6 --- Shadow, degradation, versioning

Tugas: - Shadow execution simulator. - Strategy lifecycle. - Rolling
performance metrics. - Degradation state machine. - Version registry dan
immutable artifact. - Owner approval. - Rollback workflow. - Audit semua
promosi.

DoD: - Shadow tidak bisa mengirim order. - Degradation memicu status
sesuai test. - Version live tidak dapat ditimpa. - Rollback staging
lulus. - Tidak ada auto-promotion.

## 23.8 P7 --- Hermes research intelligence

Tugas: - Read-only data tools. - Sanitized event log access. - Research
workflow. - Experiment proposal schema. - Backtest tool allowlist. -
Report template. - Prompt injection defenses. - QA akses negatif.

DoD: - Hermes dapat membuat laporan dan proposal. - Hermes tidak dapat
mengakses endpoint order atau risk write. - Proposal tidak dapat deploy
tanpa owner. - Semua klaim laporan mempunyai data/periode/konfigurasi
pendukung.

## 23.9 P8 --- Security, monitoring, disaster recovery

Tugas: - Threat model. - Security review. - Penetration tests. - Backup
encryption dan restore drill. - Disk/CPU/RAM monitoring. - Alert
severity. - Runbook. - Fault injection. - Load dan soak test. - Incident
simulation.

DoD: - Tidak ada critical/high security issue terbuka. - Restore
berhasil dan RTO/RPO terukur. - Runbook diuji oleh orang selain
pembuatnya. - Alert kritis sampai ke owner. - Fault injection tidak
menghasilkan duplicate order atau state corruption.

## 23.10 P9 --- Paper trading & release candidate

Tugas: - Paper trading minimal 20 hari kerja dan minimal 100 trade
sebagai batas evaluasi awal. - Catat semua biaya dan slippage. -
Bandingkan backtest, shadow, paper. - Review per regime dan sesi. -
Review degradation. - UAT dan sign-off QA. - Freeze code dan
dependency. - Buat release candidate. - Audit semua keputusan owner.

DoD: - Kriteria paper terpenuhi atau strategi ditolak/ditunda. - Tidak
ada defect kritis. - Semua release evidence tersimpan. - Owner
menyetujui atau menolak live secara tertulis.

## 23.11 P10 --- Canary live

Hanya setelah P9 lulus dan owner memberi persetujuan tertulis.

-   Gunakan modal/lot paling kecil yang sesuai contract specification
    dan risk policy.
-   Batasi strategi yang diaktifkan.
-   Aktifkan monitoring intensif.
-   Jangan menaikkan exposure otomatis.
-   Tetapkan durasi dan jumlah trade canary.
-   Stop jika ada mismatch, abnormal slippage, drawdown threshold,
    latency anomaly, atau data quality issue.
-   Review harian owner dan QA.
-   Pastikan prosedur rollback dan flatten dipahami.

DoD: - Periode canary memenuhi target yang ditetapkan sebelum mulai. -
Tidak ada critical incident. - Broker/database reconciliation
konsisten. - Owner menyetujui perluasan atau memutuskan kembali ke
paper.

## 23.12 P11 --- General release

-   Freeze release artifact.
-   Tag versi.
-   Backup pre-release.
-   Deploy pada window yang disetujui.
-   Smoke test read-only.
-   Verifikasi bridge dan snapshot.
-   Pastikan kill-switch berfungsi.
-   Pantau minimal 7 hari stabilisasi awal.
-   Tutup release dengan postmortem dan daftar pekerjaan berikutnya.

DoD: - Release checklist lengkap. - Rollback teruji. - Dokumentasi
operasional final. - Owner menandatangani release acceptance.

# BAGIAN H --- RELEASE MANAGEMENT

# 24. Definition of Done untuk setiap task

Task tidak dianggap selesai hanya karena kode dibuat. Setiap task wajib
mempunyai: - requirement/issue ID; - implementasi; - unit/integration
test; - review oleh agent/manusia lain; - bukti test; - logging/metrics
bila relevan; - dokumentasi; - security consideration; - failure
behavior; - acceptance criteria; - status QA; - commit hash.

## 24.1 Definition of Done fase

Fase selesai bila semua DoD fase lulus, bukti disimpan, critical defects
nol, dan owner/QA menyetujui perpindahan fase.

# 25. Release checklist

## Product & strategy

-   [ ] Scope rilis disetujui.
-   [ ] Strategi dan versi tercatat.
-   [ ] Backtest/walk-forward tersedia.
-   [ ] Shadow/paper selesai.
-   [ ] Biaya dan asumsi tervalidasi.
-   [ ] Tidak ada klaim profit terjamin.

## Execution & risk

-   [ ] Risk gate tests lulus.
-   [ ] Portfolio exposure tests lulus.
-   [ ] Idempotency lulus.
-   [ ] Partial fill/rejection lulus.
-   [ ] Kill-switch lulus.
-   [ ] Reconciliation lulus.
-   [ ] SL broker-side diverifikasi.

## Reliability

-   [ ] API/DB/EA restart tests lulus.
-   [ ] Backup dan restore lulus.
-   [ ] Disk alert lulus.
-   [ ] Monitoring dan Telegram alert lulus.
-   [ ] Runbook tersedia.
-   [ ] Rollback teruji.

## Security

-   [ ] RBAC dan auth lulus.
-   [ ] Secret scan bersih.
-   [ ] HMAC/replay test lulus.
-   [ ] Tidak ada critical/high finding terbuka.
-   [ ] Hermes access boundary terbukti.

## Release

-   [ ] UAT owner lulus.
-   [ ] Paper gate lulus.
-   [ ] QA sign-off.
-   [ ] Owner approval tertulis.
-   [ ] Backup pre-release.
-   [ ] Release artifact dan commit tag.
-   [ ] Canary plan dan rollback plan.
-   [ ] Monitoring pasca-rilis.

# 26. Rollback plan

Trigger: - order duplicate/unknown; - mismatch posisi; - SL tidak
terpasang; - event ledger corrupt/unavailable; - kill-switch gagal; -
credential compromise; - drawdown threshold; - abnormal
spread/slippage; - API/EA instability.

Langkah: 1. Aktifkan global halt. 2. Hentikan order baru. 3. Tentukan
apakah posisi perlu tetap dikelola atau flatten sesuai keputusan owner.
4. Simpan snapshot broker dan database. 5. Rollback aplikasi ke artifact
sebelumnya. 6. Jangan rollback schema secara destruktif; gunakan
migration compatibility/forward fix. 7. Reconcile broker state. 8. Uji
read-only dan bridge demo. 9. Owner menyetujui resume. 10. Buat incident
report dan corrective action.

# 27. Incident management

Setiap insiden mencatat: - severity; - waktu mulai/selesai; - dampak
terhadap posisi dan order; - timeline; - penyebab langsung dan akar
masalah; - tindakan otomatis/manual; - keputusan owner; - bukti ledger
dan broker; - corrective/preventive action; - pemilik tindakan dan
tenggat.

Tidak boleh menghapus log insiden untuk mempercantik metrik.

# BAGIAN I --- RISIKO DAN KEPUTUSAN OWNER

# 28. Risk register

  -----------------------------------------------------------------------
  Risiko                  Dampak                  Mitigasi
  ----------------------- ----------------------- -----------------------
  Data historis berbeda   Backtest terlalu        Kalibrasi HFM, haircut
  dari HFM                optimis                 konservatif, paper

  Slippage ekstrem        Kerugian melebihi       Buffer, filter, stop
                          asumsi                  entry

  MT5/EA disconnect       State tidak diketahui   Heartbeat, snapshot,
                                                  reconciler, halt

  Duplicate order         Exposure tak terkendali Idempotency dan broker
                                                  reconciliation

  Strategy crash          Sinyal hilang/abnormal  Isolation dan circuit
                                                  breaker

  Regime salah            Strategi aktif pada     UNKNOWN safe, evaluasi
                          kondisi buruk           out-of-sample

  Portfolio risk salah    Kerugian agregat        Contract spec test dan
  hitung                  berlebih                stress test

  Overfitting             Live gagal              Walk-forward, shadow,
                                                  paper, experiment
                                                  registry

  Hermes hallucination    Rekomendasi salah       Bukti, schema, review
                                                  QA/owner

  Prompt injection        Akses tool tidak sah    Tool allowlist,
                                                  sandbox, no secrets

  VPS/disk failure        Downtime/kehilangan     Backup, restore drill,
                          data                    disk alert

  Secret leak             Order tidak sah         Secret management,
                                                  rotation, least
                                                  privilege

  Jadwal molor            Rilis tertunda          Gate-based schedule, P3
                                                  opsional

  False degradation alert Strategi sering         Minimum sample,
                          berhenti                cooldown, review
  -----------------------------------------------------------------------

# 29. Keputusan wajib dari owner sebelum live

1.  Modal live dan batas kerugian absolut.
2.  Parameter risiko final setelah verifikasi contract specification.
3.  Maksimum lot per order dan total exposure.
4.  Policy posisi saat disconnect.
5.  Policy orphan position tanpa SL.
6.  Policy `STOP_AND_FLATTEN`.
7.  RTO/RPO final.
8.  Retensi data dan backup.
9.  Strategi yang boleh live.
10. Kriteria canary dan durasinya.
11. Siapa yang dapat mengaktifkan/menghapus halt.
12. Kanal alert dan emergency contact.
13. Jam deployment/cutover.
14. Persetujuan risiko residual.

# 30. Roadmap setelah rilis

Hanya setelah core stabil: - multi-strategy portfolio optimization; -
model ML sebagai challenger, bukan pengganti baseline secara otomatis; -
RL dalam eksperimen terisolasi; - multi-broker; - multi-asset; -
advanced regime modeling; - data vendor berbayar jika manfaat terukur; -
high availability dan database failover bila kebutuhan bisnis
membenarkan biaya.

Jangan menambahkan kompleksitas sebelum ada bukti bottleneck atau
kebutuhan yang jelas.

# 31. Rekomendasi final

Urutan yang paling sehat bagi Lumine adalah:

1.  Buktikan data dan eksekusi benar.
2.  Pastikan risiko dan recovery bekerja.
3.  Buktikan satu strategi sederhana setelah biaya.
4.  Tambahkan isolasi, portfolio risk, dan regime.
5.  Tambahkan shadow, degradation, versioning, dan rollback.
6.  Beri Hermes kemampuan riset dengan akses read-only.
7.  Jalankan paper trading dan canary secara disiplin.
8.  Rilis hanya setelah seluruh bukti dan approval lengkap.

**Ukuran keberhasilan Lumine bukan seberapa banyak agent atau model AI
yang digunakan. Ukurannya adalah apakah setiap keputusan dapat
dijelaskan, setiap order dapat dilacak, risiko dapat dibatasi, kegagalan
dapat dipulihkan, dan strategi dapat dibuktikan secara out-of-sample.**

------------------------------------------------------------------------

# Lampiran A --- Struktur repository yang disarankan

``` text
fund2/
├── apps/
│   ├── api/
│   └── web/
├── ea/
│   ├── MQL5/
│   └── protocol/
├── core/
│   ├── execution/
│   ├── risk/
│   ├── portfolio/
│   ├── reconciliation/
│   ├── kill_switch/
│   └── events/
├── market_data/
│   ├── adapters/
│   ├── validation/
│   ├── regime/
│   └── storage/
├── strategies/
│   ├── runtime/
│   ├── supervisor/
│   ├── registry/
│   └── examples/
├── research/
│   ├── backtest/
│   ├── walk_forward/
│   ├── shadow/
│   ├── paper/
│   └── reports/
├── hermes/
│   ├── tools_readonly/
│   ├── workflows/
│   └── report_schemas/
├── infra/
│   ├── caddy/
│   ├── systemd/
│   ├── backup/
│   └── monitoring/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── fault_injection/
│   └── security/
├── docs/
│   ├── ADR/
│   ├── runbooks/
│   ├── threat_model/
│   └── release/
├── scripts/
├── .env.example
└── README.md
```

Struktur ini adalah usulan; jangan memindahkan seluruh repository
sekaligus tanpa audit dependensi dan kompatibilitas.

# Lampiran B --- Artefak wajib sebelum rilis

-   PRD yang disetujui.
-   Architecture diagram dan ADR.
-   Threat model.
-   Data dictionary dan API/EA protocol spec.
-   Risk policy yang ditandatangani owner.
-   Test plan dan test evidence.
-   Backtest/walk-forward reports.
-   Paper/shadow report.
-   Security review.
-   Backup/restore evidence.
-   Runbook dan incident playbook.
-   Release notes.
-   Rollback plan.
-   Owner release approval.

# Lampiran C --- Prinsip keputusan

Jika ada konflik antara kecepatan rilis dan keselamatan modal, pilih
keselamatan modal. Jika data tidak cukup, tandai belum diketahui. Jika
status order tidak jelas, rekonsiliasi sebelum retry. Jika strategi
belum terbukti, tetap di shadow/paper. Jika Hermes tidak yakin, ia harus
melaporkan ketidakpastian, bukan mengarang kepastian.
