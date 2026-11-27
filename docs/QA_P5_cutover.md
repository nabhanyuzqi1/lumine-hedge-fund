# QA P5 — Kesiapan Cutover: 7 Gerbang Go-Live

Kartu: [FUND2-P5] t_f2p5a1 · Tanggal: 2026-11-25 (WIB) · QA: hf-qa
PRD: `docs/PRD_v2.1_Fund_Core.md` §9 (gerbang go-live) & P5 hari 1; ambang B2/G1 `docs/KEPUTUSAN_OWNER.md`.

## Verdict ringkas

| # | Gerbang (PRD §9) | Status | Bukti |
| --- | --- | --- | --- |
| 1 | QA paritas penuh v1 vs v2 | **BLOCKED — keputusan owner** | §1 |
| 2 | Latensi T0→T2 p95 < 300 ms pada ≥ 200 order demo | **LULUS** (rerun v11: n=207, p95 182,8 ms, p99 215,5 ms; run v10 sebelumnya FAIL 311,6 ms) | §2 |
| 3 | Disconnect (EA mati saat posisi terbuka) → rekonsiliasi 10/10 | **LULUS** | §3 |
| 4 | Kill-switch & auto-halt drawdown berfungsi | **LULUS** | §4 |
| 5 | Paper ≥ 20 hari kerja, ≥ 100 trade, PF ≥ 1,3, DD ≤ 5% | **BELUM TERPENUHI** | §5 |
| 6 | Restore backup teruji | **LULUS** | §6 |
| 7 | Owner approve tertulis (baseline risk policy) | **LULUS (baseline)**; approval live (D1) terpisah | §7 |

**Kesimpulan cutover:** gerbang 2, 3, 4, 6, 7 lulus; gerbang 2 lulus lewat rerun
v11 (p95 T0→T2 182,8 ms, p99 215,5 ms, n=207, setelah fix backend poll 50 ms;
run v10 sempat FAIL 311,6 ms, riwayat & akar di §2); gerbang 5 belum terpenuhi
(kebutuhan waktu, PRD §10: "cutover menunggu gerbang 5, bukan dipaksa");
gerbang 1 tidak dapat diuji literal karena kode v1 sudah dihapus, butuh
keputusan owner/direktur (opsi di §1). **Cutover tetap TIDAK direkomendasikan
sampai gerbang 5 terpenuhi dan gerbang 1 ada keputusannya. Live uang nyata
TIDAK dibuka oleh QA ini.**

## 1. Gerbang 1 — Paritas v1 vs v2: BLOCKED (keputusan owner)

Kode aplikasi v1 (`lumine-hedge-fund`: frontend 3106 + API 3107) **sudah tidak ada**:

- `~/lumine-hedge-fund/` tinggal `logs/`, `mt5.env/`, `scripts/` (kode app dihapus ±21-22 Nov saat migrasi ke fund2 v2) — diverifikasi ulang 2026-11-25.
- Bukan repo git, tidak ada di backup (`fund2-backups/` kosong untuk app), tidak ada docker image v1.
- Riwayat git `~/fund2` hanya berisi kode v2 (commit P0/P1 ke atas).

Konsekuensi: paritas literal v1 vs v2 tidak dapat dieksekusi. Detail kondisi dan opsi
rollback sudah didokumentasikan di `docs/ROLLBACK_P5.md` §5.

**Keputusan yang dibutuhkan (owner/direktur):**
1. Sediakan source v1 (mesin lain / repo upstream) → dipasang di subdomain cadangan
   (`fund-v1.lumine.biz.id`) → QA jalankan paritas literal; **atau**
2. Terima v1 tidak dapat dipulihkan → DoD-2 direvisi menjadi "rollback ke build v2
   sebelumnya via git" dan gerbang 1 ditutup dengan keputusan tertulis.

## 2. Gerbang 2 — Latensi T0→T2 p95 < 300 ms pada ≥ 200 order demo: **LULUS (rerun v11)**

Run v10 (`scripts/_p5_latency_driver_v9.py` + kelanjutan `p5_extend_to_200.py`,
label `p5-latency-gate-v10-b*`, 25 Nov 2026 11:19-12:47 WIB): 33 burst × 8 order
dengan 201 sampel **valid** (T0, T1, T2 tercatat lengkap) via API live
(127.0.0.1:3110), synthetic EA harness mengisi fill, flatten antar burst, SL/TP
mengikuti harga referensi M1, 0 order ditolak risk gate.

Run bersih: EA MT5 real (fund2 EA v0, autentikasi HMAC) dihentikan sementara
(`systemctl --user stop lumine-hedge-fund-mt5.service`, 11:43-12:48 WIB, start ulang
setelah run). Tanpa ini EA real ikut mengonsumsi /bridge/poll dan mengeksekusi order
QA di akun broker demo (ticket 9 digit asli) sehingga T1/T2/T3 tidak tercatat —
seluruh run sebelumnya (final, v5-v9) terkontaminasi dan dibuang sebagai bukti
gerbang. Dari 64 sampel pertama yang terkontaminasi, hanya 14 yang valid; burst
b12-b33 (pasca-MT5 stop) 100% valid (8/8 per burst).

Hasil (dihitung dari `order_events.payload->'latency'`, clock mono_us,
`scripts/p5_latency_v10_stats.json`, n = 201):

| Segmen | n | p50 | p95 | p99 | max | SLO |
| --- | --- | --- | --- | --- | --- | --- |
| T0→T1 pickup EA | 201 | 163,7 | 308,9 | 400,5 | 689,3 | — |
| T1→T2 EA pre-send | 201 | 2,1 | 3,6 | 4,4 | 5,3 | — |
| **T0→T2 (SLO PRD §6)** | **201** | **165,8** | **311,6** | **402,6** | **691,4** | **p95 < 300 ms: FAIL; p99 < 500 ms: PASS** |
| T2→T3 broker OrderSend | 201 | 177,6 | 244,6 | 248,4 | 249,8 | dilaporkan terpisah (PRD §6) |
| T3→T4 konfirmasi DB | 201 | 23,3 | 130,9 | 201,7 | 251,8 | — |

Order ditolak: 0; order tanpa status terminal: 2 dari 256 order (1 STUCK b11 —
diambil EA real di detik terakhir sebelum service di-stop, auto-reconciler
men-transisi FAILED; 1 TIMEOUT lain — keduanya di luar 201 sampel valid).

**Analisis akar (temuan QA):** p95 T0→T2 meleset 11,6 ms (3,9%) dan didominasi
T0→T1 (pickup). `/bridge/poll` (app/bridge.py) melakukan long-poll dengan loop
internal `asyncio.sleep(0.25)` — server memeriksa command baru maksimal 4×/detik,
sehingga pickup rata-rata ±125 ms dan p95 ±250-300 ms + overhead HTTP. Ini latensi
sistem yang sesungguhnya (EA real mengalami cycle yang sama), bukan artefak
harness. **Rekomendasi (kartu backend terpisah):** turunkan poll sleep ke ±50 ms
(atau ganti mekanisme push/NOTIFY), lalu rerun harness ≥ 200 order — perkiraan
p95 T0→T2 turun ke ±100-150 ms. Verdict tetap FAIL sampai rerun membuktikan
sebaliknya; QA tidak mengubah kode backend untuk membuat gerbang lulus.

Catatan metode: 3 bug harness diperbaiki sebelum run final — (1) query harga referensi
`timeframe='1m'` → `'M1'` (fallback 2648 vs pasar ±3555 membuat semua order ditolak
risk gate), (2) SL/TP dihitung ulang per order mengikuti harga real, (3) burst 8 order
+ flatten antar burst agar limit stress portofolio tidak terlampaui. Attempt sebelumnya
gagal bukan karena sistem, melainkan: halt otomatis (orphan legacy EA, EA offline saat
worker QA crash) yang tidak kunjung di-release — driver v7 menangani siklus
flatten → tunggu bersih → release halt → verifikasi sebelum tiap burst.

### 2a. Rerun v11: LULUS (p95 182,8 ms, p99 215,5 ms, n=207)

Fix backend (hf-backend, kartu t_baeb3ce4) dan rerun memakai pola run v10 yang sama
(driver `_p5_latency_driver_v11.py`, label `p5-latency-gate-v11-b*`, harness
`latency_harness.py` TIDAK diubah sehingga angkanya sebanding dengan v10):

1. `40f9f09` — interval poll internal `/bridge/poll` `asyncio.sleep(0.25)` → 0.05
   (konstanta `BRIDGE_POLL_INTERVAL_S`). Beban DB terukur 0,52 ms per iterasi
   (2 SELECT FOR UPDATE SKIP LOCKED + transaksi), jadi 20 iter/s = ~1% satu core
   per consumer EA; koneksi pool dilepas sebelum sleep. LISTEN/NOTIFY dipilih
   TIDAK dipakai: rewrite listener + trigger + reconnect tanpa keuntungan
   berarti untuk 1-2 consumer.
2. `1dfea07` — daily_pnl mengecualikan semua order user role 'qa' (mirror
   `anomaly.SQL_EXCLUDE_QA`). Percobaan rerun pertama (18:10-18:40 WIB) diblokir
   halt palsu: 56 posisi QA belum tertandai ikut terhitung sehingga daily_pnl
   -121.36 <= -100 (rugi live sebenarnya -70.33). Bug kontaminasi metrik, bukan
   gate yang diakali; terverifikasi live: daily_pnl jadi -70.33 (0,72% < 3%).
3. `f0334cb` — legacy flag `settings.halted` ikut dibersihkan saat release
   kill-switch (dulu hanya di-set, tidak pernah dihapus: setelah satu auto-halt
   semua order ditolak selamanya dengan pesan fallback STOP_NEW_ORDERS).

Run v11: 18:47-19:38 WIB (52 menit), 26 burst × 8 order, EA MT5 real di-stop
sementara (18:06-19:44 WIB, start ulang setelah run), 207 order valid
(T0-T4 lengkap, semua FILLED), 1 order ditolak ("no fresh market data for
spread filter", di luar sampel), 0 timeout. Verdict (PRD §6 mengikat):
**p95 T0-T2 = 182,8 ms < 300 ms LULUS; p99 = 215,5 ms < 500 ms LULUS**
(`scripts/p5_latency_v11_stats.json`, dihitung `scripts/_p5_latency_stats.py`):

| Segmen | n | p50 | p95 | p99 | max | SLO |
| --- | --- | --- | --- | --- | --- | --- |
| T0→T1 pickup EA | 207 | 100,9 | 180,6 | 213,4 | 345,3 | — |
| T1→T2 EA pre-send | 207 | 2,1 | 2,9 | 4,3 | 6,7 | — |
| **T0→T2 (SLO PRD §6)** | **207** | **103,5** | **182,8** | **215,5** | **347,4** | **p95 < 300 ms: LULUS; p99 < 500 ms: LULUS** |
| T2→T3 broker OrderSend | 207 | 172,6 | 240,5 | 248,9 | 250,3 | dilaporkan terpisah (PRD §6) |
| T3→T4 konfirmasi DB | 207 | 14,5 | 23,1 | 27,9 | 29,5 | — |

Perbaikan vs v10 (n=201): p95 T0→T2 311,6 → 182,8 ms (-41%), p99 402,6 → 215,5 ms
(-46%), p50 165,8 → 103,5 ms (-38%). Pemetaan p95: pickup p95 308,9 → 180,6 ms.
Sisa pickup didominasi antrean pemrosesan berurutan harness EA (simulasi broker
100-250 ms per order, ditangani satu per satu) plus jeda 50 ms loop poll saat
kosong; komponen server (pemeriksaan command baru) kini maksimum 50 ms per
iterasi. Cadence penerima (EA real maupun harness) tetap sama dengan pola v10
sehingga perbandingan sah.

Setelah run: EA real `lumine-hedge-fund-mt5.service` dinyalakan ulang 19:44 WIB,
terverifikasi tick ~2/s dan candle M1/M5/M15 mengalir (candle terbaru 19:47).

## 3. Gerbang 3 — Disconnect 10/10: LULUS

Rerun `qa_p1b_v2` di DB live (2026-11-25 03:39-05:39 WIB, log `docs/qa_p1b_rerun.log`,
JSON `docs/qa_p1b_results.json`): 10/10 iterasi disconnect — selang-seling posisi
closed-with-deal dan open-preserved — semua `offline_reject=True recon=True events=True
ks_off=True`. Order baru ditolak saat EA offline; rekonsiliasi benar; event append-only
lengkap; kill-switch aktif saat EA offline.

## 4. Gerbang 4 — Kill-switch & auto-halt: LULUS

Run yang sama, 33 checks: **29 PASS, 0 FAIL, 4 deviasi known** (cookie `Secure` belum
diset untuk loopback — wajib flip saat cutover domain; kontrak HMAC real EA belum
aktif; endpoint heartbeat & format tick batch berbeda dari ekspektasi EA v5.00 —
terdokumentasi sebagai deviasi, bukan kegagalan gerbang). Yang diuji lulus:
mismatch posisi → auto GLOBAL_HALT + audit; auto-halt drawdown harian; auto-trigger
3× FAILED → STOP_NEW_ORDERS; auto-trigger EA offline; release GLOBAL_HALT wajib
checklist; flatten wajib confirm; pause strategi scoped; state persist di DB.

Bukti operasional live hari ini: auto-halt SEV-1 (orphan position) dan SEV-2 (EA
offline) benar-benar terpicu dan berfungsi (kill_switch_events #37, #52, #79, #98);
reconciler mengadopsi posisi orphan legacy EA dengan benar (ORPHAN_ADOPTED→ORPHAN_CLOSED).

## 5. Gerbang 5 — Paper trading: BELUM TERPENUHI (cutover menunggu)

Evaluasi `scripts/eval_gate_paper.py --strategy london_breakout --source paper`
(`docs/qa_p5_gate5_london_breakout.md`, 2026-11-25):

| Kriteria | Status | Detail |
| --- | --- | --- |
| Hari kerja ≥ 20 | FAIL | 8 hari kerja |
| Trade ≥ 100 | FAIL | 8 trade closed |
| PF ≥ 1,3 setelah biaya | FAIL | PF 1,211 (komisi 7 USD/lot) |
| Max DD ≤ 5% | PASS | 1,38% |

Verdict evaluator: **DATA_BELUM_CUKUP**. Paper runner forward berjalan sejak 2026-11-21
(paper_state `runner`: balance 10000, posisi nihil; sinyal PAPER terakhir ditolak
kill-switch saat halt aktif — 9 order PAPER berstatus REJECTED di `paper_orders`),
jadi sampel forward masih tipis; angka di atas dihitung dari trade replay strategi
london_breakout yang tersedia.

Sesuai PRD §10: "Jika paper belum mencapai 20 hari saat P5 siap, cutover menunggu
gerbang 5 (bukan dipaksa)." **Cutover menunggu ±12 hari kerja tambahan + PF naik ≥ 1,3
setelah biaya.** Catatan: PF 1,211 < 1,3 — belum lulus meskipun sampel diperluas;
perlu dipantau ulang setelah paper forward berjalan.

## 6. Gerbang 6 — Restore backup: LULUS

Backup `fund2-20261124T200724Z.tar.age` (125.603.976 byte, sha256 tercatat di
`~/fund2-backups/manifest.tsv`). Restore drill terisolasi (staging PG 16 port 5599,
tanpa sentuh broker): **LULUS 36 detik** (pg_restore 25s), 8/8 tahap — checksum
dataset 1538 file match, integritas ledger orphan=0 + trigger append-only aktif +
candle OHLC konsisten, 9 tabel identik jumlah & rentang timestamp dengan sumber,
settings (33 kunci) & paper_state identik. Laporan:
`~/fund2-backups/drill/20261124T201416Z/restore-drill-20261124T201416Z.md`.

## 7. Gerbang 7 — Owner approve tertulis: LULUS (baseline)

`docs/KEPUTUSAN_OWNER.md` §E: **DISETUJUI OWNER 2026-11-21 — "SETUJU SEMUA"**
(A1–A12, B1–B4, C1–C3, D2–D16 dikunci sebagai baseline risk policy). Baseline
terbukti aktif di sistem hidup: `portfolio_risk` enabled (max risk/trade 0,5%,
eksposur 0,30 lot, stress 3%), `max_daily_drawdown` 100 USD (1%), `llm_risk`
(20 order/hari, 2/menit, pause drawdown 1,5%, 3 FAILED beruntun), auto-halt aktif.

**Catatan:** D1 (modal live + batas kerugian absolut) sengaja DEFER owner —
approval live terpisah adalah prasyarat canary, bukan bagian gerbang 7 baseline.

## 8. Temuan operasional (di luar 7 gerbang)

- Posisi broker orphan tanpa order DB (trading legacy EA di akun yang sama) memicu
  SEV-1 auto-halt 3× hari ini; reconciler mengadopsi & menutup dengan benar. Konflik
  akun legacy-vs-fund2 perlu keputusan arsitektural sebelum live (host akun terpisah).
- Agent LLM sedang auto-pause sejak 2026-11-24 20:43 UTC (3 order FAILED beruntun,
  breaker `llm_agent_pause`) — tidak mengganggu pengukuran latensi.
- 1 sesuai rekomendasi ROLLBACK_P5 §4: mekanisme rollback Caddy teruji (validate +
  graceful reload 3-4s), tetapi rollback fungsional ke v1 menghasilkan 502 karena
  kode v1 hilang (lihat gerbang 1).

## 9. Keputusan & langkah berikutnya

1. **Gerbang 2: SELESAI (LULUS v11)** — interval poll `/bridge/poll` diturunkan
   250 ms → 50 ms (commit `40f9f09`) dan rerun v11 membuktikan p95 182,8 ms /
   p99 215,5 ms pada n=207 — lihat §2a. Sisa kerja gerbang 2: tidak ada; QA
   tinggal menandatangani verdict §2.
2. **Owner/direktur — gerbang 1:** sediakan source v1 (paritas literal) ATAU setujui
   revisi DoD-2 (rollback ke build v2 via git) — lihat §1.
3. **Menunggu waktu — gerbang 5:** lanjutkan paper forward (tanpa memaksa), evaluasi
   ulang saat ≥ 20 hari kerja & ≥ 100 trade; PF harus ≥ 1,3 setelah biaya.
4. **Prasyarat canary (D1):** owner mengisi modal live + batas kerugian absolut dan
   memberi approval live terpisah sebelum canary.
5. Cutover domain baru dilakukan setelah gerbang 2 lulus ulang, gerbang 1 ada
   keputusannya, dan gerbang 5 terpenuhi (PRD §10).

## Lampiran — file bukti

| File | Isi |
| --- | --- |
| `docs/qa_p1b_rerun.log` + `docs/qa_p1b_results.json` | Gerbang 3/4: 33 checks (29 pass, 0 fail, 4 deviasi known) |
| `docs/qa_p5_gate5_london_breakout.md` + `.json` | Gerbang 5: evaluasi paper |
| `~/fund2-backups/drill/20261124T201416Z/` | Gerbang 6: restore drill LULUS 36s |
| `docs/KEPUTUSAN_OWNER.md` | Gerbang 7: approval baseline 21 Nov |
| `docs/ROLLBACK_P5.md` | Gerbang 1: blocker v1 + opsi keputusan |
| `scripts/p5_latency_v10_rerun6.log`, `scripts/p5_latency_v10_extend.log`, `scripts/p5_latency_v10_status.json` | Gerbang 2: log koreografi driver v10 + kelanjutan b26-b33 |
| `scripts/p5_latency_v10_stats.json` | Gerbang 2: statistik final (n=201, p95 311,6 ms, FAIL) |
| `<workspace t_f2p5a1>/p5_extend_to_200.py` | Script kelanjutan run (sampel valid ≥ 200) |
