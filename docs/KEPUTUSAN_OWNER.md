# KEPUTUSAN OWNER — Angka [USULAN] & Keputusan Wajib Pra-Live Lumine Fund v2

| | |
| --- | --- |
| Tanggal | 2026-11-21 |
| Status | **MENUNGGU PERSETUJUAN OWNER** — P0 tidak lanjut sebelum approval tertulis |
| Sumber | `PRD_v2.1_Fund_Core.md` §14 + semua titik [USULAN]; `PRD_v2.2_End_to_End.md` §29 + semua titik [USULAN] |
| Disusun | hf-ceo |
| Prinsip | Semua angka di bawah adalah **default awal**, wajib dikalibrasi dengan data HFM dari P0. Bukan rekomendasi finansial. |

## Cara memberi keputusan

Balas di chat kantor dengan salah satu:

1. **"SETUJU SEMUA"** → semua nilai default dikunci sebagai baseline risk policy.
2. **"SETUJU, kecuali: `<ID>` = `<nilai baru>`"** → yang disebut diubah, sisanya dikunci.
3. Untuk D1 (modal live): wajib diisi angka oleh owner, tidak ada default di PRD.

Keputusan tercatat di bagian E dokumen ini. Setelah disetujui, perubahan parameter hanya lewat UI dengan konfirmasi ulang password + audit (LLM/Hermes read-only).

---

## A. Risk gate & eksekusi (PRD v2.1 §5.2, §5.5, §5.6, §5.8; PRD v2.2 §7.4, §14.1)

| ID | Parameter | Nilai usulan | Aksi bila dilanggar | Catatan kalibrasi |
| --- | --- | --- | --- | --- |
| A1 | SL wajib, dipasang di sisi broker | Ya | Tolak order | Non-negotiable, tanpa SL order ditolak di risk gate |
| A2 | Jarak SL minimum / maksimum | 0,50 / 15,00 USD dari harga | Tolak | Final setelah verifikasi contract specification HFM |
| A3 | Volume maksimum per order | 0,10 lot | Tolak | Kalibrasi terhadap modal live (D1) & contract spec |
| A4 | Eksposur total terbuka maksimum | 0,30 lot | Tolak | Idem |
| A5 | Risiko per trade maksimum | 0,5% equity | Tolak | Idem |
| A6 | Drawdown harian maksimum | 3% equity | **Auto-halt** sampai reset manual owner | Reset hanya owner |
| A7 | Drawdown total dari puncak equity | 8% | Auto-halt + notifikasi Telegram | Reset hanya owner |
| A8 | Order per menit maksimum | 5 | Tolak | Pelindung anti runaway/loop |
| A9 | Ambang absolut spread filter | 0,50 USD (filter: spread > max(2 × median 15 menit, 0,50 USD) → tolak) | Tolak | Dikalibrasi ulang setelah 2 minggu data HFM |
| A10 | Data basi (tick) | Usia tick > 3 detik → tolak | Tolak | |
| A11 | EA OFFLINE | Tolak order baru; posisi tetap dilindungi SL broker-side | Tolak order baru | Posisi tidak auto-close saat disconnect (D4) |
| A12 | EA heartbeat | Setiap 2 detik; 3 heartbeat terlewat (6 detik) = EA OFFLINE | Menandai offline | Sudah dipakai sebagai acuan EA v0 (kartu P0) |

Angka A2–A7 diidentik dengan parameter awal Portfolio Risk Manager PRD v2.2 §7.4 (0,5% / 3% / 8% / 0,10 lot / 0,30 lot) — kedua PRD konsisten, cukup satu keputusan.

## B. Gerbang strategi & riset (PRD v2.1 §5.4, §9; PRD v2.2 §6.4, §8.4, §22.3)

| ID | Parameter | Nilai usulan | Catatan |
| --- | --- | --- | --- |
| B1 | Walk-forward window | Latih 6 bulan / uji 1 bulan, geser 1 bulan | Window ditetapkan sebelum eksperimen (v2.2 §8.4) |
| B2 | Gerbang strategi ke live / paper gate | Data ≥ 2 tahun; paper ≥ 20 hari kerja; ≥ 100 trade; profit factor ≥ 1,3 setelah biaya; max drawdown ≤ 5% | Identik di v2.1 §9 gerbang 5 dan v2.2 §8.4. Bukan bukti statistik otomatis — owner + QA menilai sampel & distribusi |
| B3 | Ambang confidence regime classifier | **Belum ada angka di PRD.** Usulan pendekatan: dikalibrasi dari data P0/P2; sampai kalibrasi selesai regime = `UNKNOWN`, strategi hanya jalan di regime yang diizinkan eksplisit | v2.2 §6.4 hanya menandai [USULAN] tanpa default |
| B4 | Target coverage test | 100% branch coverage fungsi risk gate kritis; semua state transition punya test; nol bug critical/high terbuka | v2.2 §22.3 |

## C. Operasional & disaster recovery (PRD v2.2 §17.2, §17.4)

| ID | Parameter | Nilai usulan | Catatan |
| --- | --- | --- | --- |
| C1 | Retensi backup harian | 30 hari | Owner boleh menetapkan lebih panjang |
| C2 | RPO database (awal) | Maksimum 24 jam (backup harian); lebih kecil bila WAL/PITR tersedia | Final realistis terhadap VPS, storage, koneksi |
| C3 | RTO layanan (awal) | 4 jam | RTO bridge & rekonsiliasi ditetapkan terpisah, final setelah restore drill |

## D. Keputusan wajib owner non-angka (PRD v2.1 §14; PRD v2.2 §29)

| ID | Keputusan | Usulan / opsi | Sumber |
| --- | --- | --- | --- |
| D1 | **Modal live dan batas kerugian absolut** | **Wajib diisi owner** (tidak ada angka di PRD). Kerangka: canary pakai modal/lot terkecil yang sesuai contract spec + risk policy; batas kerugian absolut ditetapkan owner | v2.2 §29.1; v2.1 §14.2 |
| D2 | Parameter risiko final setelah verifikasi contract specification | Setuju angka A; final dikunci setelah contract spec HFM diverifikasi di P0/P1 | v2.2 §29.2 |
| D3 | Maksimum lot per order dan total exposure | = A3 / A4 | v2.2 §29.3 |
| D4 | Policy posisi saat disconnect | Posisi tetap terbuka, dilindungi SL di sisi broker; tidak auto-close; rekonsiliasi saat EA reconnect (snapshot + reconciler) | v2.2 §29.4; v2.1 §5.8 |
| D5 | Policy orphan position tanpa SL | Adopsi sebagai posisi termonitor + alert kritis; SL darurat dipasang memakai jarak A2 hanya jika owner setuju di sini; tanpa persetujuan: monitoring + alert saja, tidak mengarang jarak SL | v2.2 §29.5; v2.2 §15.3 |
| D6 | Policy `STOP_AND_FLATTEN` | Hanya manual oleh owner dengan konfirmasi eksplisit (risiko slippage dijelaskan). Auto-trigger hanya `STOP_NEW_ORDERS`/`GLOBAL_HALT`, tidak pernah auto-flatten | v2.2 §29.6; v2.2 §16 |
| D7 | RTO/RPO final | = C2/C3, dikunci setelah restore drill staging lulus | v2.2 §29.7 |
| D8 | Retensi data dan backup | Backup harian 30 hari (C1); dataset parquet HFM disimpan terus (checksum + manifest) karena dasar kalibrasi biaya backtest | v2.2 §29.8 |
| D9 | Strategi yang boleh live | Hanya strategi yang lolos seluruh gerbang B2 + approve tertulis owner; mulai 1 strategi | v2.2 §29.9 |
| D10 | Kriteria canary dan durasi | PRD belum menetapkan angka. Usulan CEO: durasi min. 10 hari kerja, ≥ 30 trade, exposure terkecil, review harian owner+QA, stop bila mismatch/slippage abnormal/DD threshold/latensi anomali | v2.2 §29.10; §23.11 |
| D11 | Siapa yang dapat mengaktifkan/menghapus halt | Hanya owner (UI + konfirmasi password / Telegram 2FA). Pelepasan global halt wajib checklist recovery. Agent tidak berhak | v2.2 §29.11; v2.2 §2, §16 |
| D12 | Kanal alert dan emergency contact | Telegram kanal primer; tambah email sebagai kanal kedua. Emergency contact: owner. (v2.1 §14.5: Telegram saja atau tambah email) | v2.2 §29.12; v2.1 §14.5 |
| D13 | Jam deployment/cutover | Weekend saat pasar tutup (domain switch); aktivasi live awal sesi Asia hari Senin pagi WIB. Rollback ke v1 < 5 menit | v2.2 §29.13; v2.1 §14.6, P5 |
| D14 | Persetujuan risiko residual | Owner menandatangani risk policy (dokumen ini setelah diisi) sebagai bagian release acceptance | v2.2 §29.14; Lampiran B |
| D15 | Strategi pertama: breakout sesi London | Setuju breakout London (filter spread), atau sebutkan pengganti | v2.1 §14.3 |
| D16 | P3 (ML/RL): dikerjakan setelah P2 atau ditunda? | Usulan: ditunda sampai v2 live stabil (P3 memang opsional, di luar jalur kritis) | v2.1 §14.4 |

## E. Catatan persetujuan owner

> **STATUS: DISETUJUI OWNER — 2026-11-21**

| | |
| --- | --- |
| Keputusan owner | **SETUJU SEMUA** — A1–A12, B1–B4, C1–C3, D2–D16 dikunci sebagai baseline risk policy. **D1 = DEFER**: modal live belum diisi owner; live trading tetap **OFF** sampai owner mengisi D1 (modal + batas kerugian absolut) dan memberi approval live terpisah. |
| Tanggal keputusan | 2026-11-21 (disetujui via chat oleh owner) |
| Catatan perubahan | Tidak ada perubahan angka; semua nilai default dikunci tanpa modifikasi. |

Format persetujuan: `SETUJU SEMUA` atau `SETUJU, kecuali: <ID> = <nilai>`. Setelah tercatat, dokumen ini menjadi baseline risk policy dan gerbang D1 (modal live) menjadi prasyarat canary.

---

## F. Keputusan owner tambahan (2026-11-22)

| ID | Keputusan | Isi | Dampak |
| --- | --- | --- | --- |
| F1 | **Multipair: XAUUSD + BTCUSD** | Owner memutuskan sistem mendukung BTCUSD selain XAUUSD ("support multipair biar bisa trade 24/7"). XAUUSD tetap instrumen live utama; BTCUSD menambah cakupan sehingga trading/pengujian bisa jalan saat market XAUUSD tutup (weekend). | Angka A2/A3/A4/A9 menjadi **per-simbol** (BTCUSD diisi dari contract spec MT5, dikalibrasi data); eksposur total & order per menit tetap akun-level agregat lintas simbol. Direalisasikan lewat batch kartu FUND2-MP (t_f2mp1..t_f2mp5) + plumbing t_f2devbtc. |
| F2 | Live trading | Tetap **OFF** sampai D1 diisi owner + approval live terpisah. Multipair tidak mengubah gerbang ini. | Tidak ada perubahan |

## G. Keputusan owner tambahan (22 Nov 2026, sesi kedua)

| ID | Keputusan | Isi | Syarat pengaman (tetap berlaku) |
| --- | --- | --- | --- |
| G1 | **Full LLM trading** | Owner memilih LLM (Hermes agent) mengambil keputusan order langsung — bukan hanya riset. Membatalkan prinsip "LLM tidak pernah memegang tombol order" (v2.1 §2.1, §5.9; v2.2 §0.2, §12). | (1) Semua order LLM tetap melewati risk gate deterministik yang sama (SL wajib, lot maks, eksposur, drawdown auto-halt, spread filter, data basi). (2) Kill-switch + auto-halt tetap menghentikan segalanya termasuk agent LLM. (3) Setiap keputusan LLM tercatat di order_events beserta reasoning. (4) Gerbang paper 20 hari/100 trade dan approval live owner (D1) TIDAK berubah — LLM harus lulus paper dulu. (5) Guard prompt injection untuk data tak tepercaya (v2.2 §12.4). (6) Budget LLM: rate limit order khusus + biaya panggilan dipantau. |

## Lampiran: angka operasional tetap (bukan [USULAN], konteks saja — tidak perlu keputusan)

| Angka | Konteks | Sumber |
| --- | --- | --- |
| Tick batch 250 ms; flush parquet 60 detik; backpressure > 5 detik buang sampel likuiditas | Alur data | v2.1 §5.1 |
| Spread diagregat min/avg/max per 5 detik | Modul likuiditas | v2.1 §5.2 |
| Haircut keamanan 20% pada kalibrasi biaya backtest | Modul likuiditas | v2.1 §5.2 |
| SLO internal T0→T2 p95 < 300 ms, p99 < 500 ms, diukur ≥ 200 order paper/demo | Latensi | v2.1 §6 |
| Uptime bridge ≥ 99,5% (jam pasar); 0 order hilang/nyangkut | SLO | v2.1 §6 |
| Toleransi jam HMAC 5 detik; nonce sekali pakai | Keamanan | v2.1 §7, v2.2 §14.2 |
| Order `SENT` > 60 detik tanpa konfirmasi → `STUCK` | Reconciler | v2.1 §5.8 |
| EA offline > 60 detik dengan posisi terbuka; 3 order FAILED beruntun | Auto-trigger kill-switch | v2.1 §5.7 |
| Uji disconnect rekonsiliasi benar 10/10 | Gerbang go-live | v2.1 §9 |
| Paper trading mulai akhir P1b, paralel, tak memperpanjang jalur kritis | Jadwal | v2.1 §10 |

## H. Keputusan owner (23 Nov 2026)

| ID | Keputusan | Isi | Dampak |
| --- | --- | --- | --- |
| H1 | **Approve gate P2 (buka wave v2.2/LLM/multipair)** | Owner menyetujui pembukaan gate P2 dengan PENGECAKLIAN: butir 1 DoD (1 strategi lolos backtest 2 thn biaya realistis + walk-forward) BELUM LULUS (verdict CEO `a857d75`, docs/LAPORAN_DOD_P2.md); butir 2 (paritas ≥99%) LULUS; butir 3 (laporan terbaca owner) terpenuhi di chat. | Wave v2.2/LLM/multipair berjalan bertahap (kapasitas 2 worker paralel). Kartu release-path (paper 20 hari, canary live, general release, checklist, artefak rilis, risk register, load/soak, runbook) ditahan sampai wave engineering selesai + P9 lulus + approval owner. Live trading tetap OFF sampai D1 + approval live terpisah. |

## I. Penetapan angka guardrail final (26 Nov 2026) — menutup F-03 / F-12

| | |
| --- | --- |
| Dasar keputusan | Bagian E dokumen ini: **SETUJU SEMUA** A1-A12, disetujui tertulis owner via chat kantor 21 Nov 2026. **Tidak ada revisi angka.** |
| Penetapan | hf-ceo, 26 Nov 2026 (kartu `t_d3ab9839`) |
| Konfirmasi owner 26 Nov | Pertanyaan konfirmasi akhir dikirim ke owner lewat kantor (DeskRPG) 26 Nov 2026. Owner belum menjawab dalam jendela kerja kartu. Karena angka yang berlaku **sudah tertulis dan disetujui** di bagian E, tidak ada angka baru yang ditetapkan tanpa owner: kartu ini mengikat ulang runtime ke A1-A12, bukan mengarang policy. Bila owner ingin revisi, tulis di chat kantor; bagian I direvisi dan seluruh dokumen turunan disinkronkan ulang. |
| Sifat | **BERLAKU** sebagai satu sumber kebenaran guardrail. Dokumen lain merujuk ke sini dan tidak mengulang angka sendiri. Live trading tetap **OFF** (F2, H1). |

### I.1 Angka final dan key runtime

| ID | Guardrail | Nilai final | Key runtime (`settings`) | Penegak |
| --- | --- | --- | --- | --- |
| A3 | Volume maksimum per order | 0,10 lot (per simbol) | `max_volume` = 0.10 | risk gate |
| A8 | Order per menit | 5 | `max_orders_per_min` = 5 | risk gate |
| A6 | Drawdown harian → auto-halt | 3% equity | `kill_switch_triggers.daily_drawdown_pct` = 3.0 | kill switch |
| A6 | Batas absolut harian (gate order) | 3% × saldo awal hari; demo `daily_start_balance` 9.733,86 → **292,02 USD** | `max_daily_drawdown` = 292.02 | risk gate |
| A7 | Drawdown total dari puncak equity → auto-halt | 8% | `kill_switch_triggers.total_drawdown_pct` = 8.0 | kill switch |
| — | Order FAILED beruntun → `STOP_NEW_ORDERS` | 3 | `kill_switch_triggers.consecutive_failed_orders` = 3 | kill switch |
| A12 | EA OFFLINE (3 heartbeat × 2 s) → tandai offline, alert, **tolak order baru** (A11) | 6 s | `kill_switch_triggers.ea_offline_seconds` = 6.0 | alerts, LLM risk gate |
| Lampiran / v2.1 §5.7 | Auto `GLOBAL_HALT` karena EA offline (hanya bila ada posisi terbuka) | 60 s | `kill_switch_triggers.ea_offline_halt_seconds` = 60.0 | kill switch |
| A10 | Data basi: usia tick → tolak order | 3 s | `max_tick_age_s` = 3.0 (key baru) | risk gate |
| A2 | Jarak SL per simbol | XAUUSD 0,50-15,00 USD; BTCUSD 10,00-1.000,00 USD | `symbol_specs[SYMBOL].sl_min_usd` / `sl_max_usd` | risk gate |
| A4 | Eksposur terbuka agregat | 0,30 lot | `portfolio_risk.max_total_volume_lot` = 0.30 (+ `exposure_max_usd`) | portfolio risk, risk gate |
| A5 | Risiko per trade | 0,5% equity | `risk_per_trade_pct` = 0.5, `portfolio_risk.max_risk_per_trade_pct` = 0.5 | risk gate, portfolio risk |
| A9 | Filter spread absolut | 0,50 USD (XAUUSD) | `max_spread` = 0.5 + `symbol_specs.*.spread_abs_max_usd` | risk gate |
| — | Feed equity/margin basi (**bukan** A10) | 60 s, dikaji ulang saat canary | `portfolio_risk.max_feed_age_s` = 60.0 | portfolio risk |

### I.2 Tiga angka yang dulu ambigu dan cara membacanya

1. **A6 punya dua wajah.** Persen (3%) untuk auto-halt kill switch; absolut (USD) untuk gate order. Absolut diturunkan dari 3% saldo awal hari, bukan angka bebas 100 USD. Saat D1 (modal live) diisi, `max_daily_drawdown` dan `daily_start_balance` dihitung ulang dari modal itu dan dicatat di bagian baru.
2. **A12 ≠ ambang halt.** 6 s adalah ambang *menandai* EA offline: alert + tolak order baru (A11), posisi tetap dilindungi SL broker-side. `GLOBAL_HALT` menunggu 60 s (v2.1 §5.7, ROLLBACK_PLAN T9). Memakai 6 s untuk halt berarti setiap hiccup jaringan 6 detik memicu halt yang hanya boleh dilepas owner (D11): risiko halt panjang tanpa tambahan keamanan.
3. **A10 ≠ `max_feed_age_s`.** A10 (tick 3 s) ditegakkan `max_tick_age_s` di risk gate. `max_feed_age_s` adalah usia feed equity/margin dan tidak boleh dipakai sebagai bukti A10.

### I.3 Kanal perubahan angka (mengikat)

| Perubahan | Kanal resmi | Syarat |
| --- | --- | --- |
| Guardrail inti: `max_volume`, `max_orders_per_min`, `max_daily_drawdown`, `max_spread`, `max_tick_age_s`, `portfolio_risk` | `PUT /admin/risk-settings` (UI admin, PRD §14) | sesi 2FA + konfirmasi ulang password + audit `audit_log` dan `settings_audit` |
| Auto-trigger kill switch: `kill_switch_triggers` | `PUT /kill-switch/triggers` (UI admin) | sesi 2FA + audit `kill_switch_events` + `settings_audit` |

`psql` langsung, CLI `set-setting`, atau edit file kode **bukan** kanal sah untuk mengubah guardrail. Dokumen turunan wajib diperbarui pada commit yang sama: `ROLLBACK_PLAN_v2.2.md` §1, `RELEASE_CHECKLIST_v2.2.md` 5.9, `PRASYARAT_LIVE_v2.2.md` §3, `RELEASE_PACKET_v2.2.md` F-03/F-12.

### I.4 Penerapan runtime dev/staging dan aturan paritas (26 Nov 2026, kartu `t_bf4b85f9`)

| | |
| --- | --- |
| Temuan asal | Kartu `t_2d1f6d33` (halaman `/admin/guardrail`): 6 field runtime dev menyimpang dari §I.1, semuanya lebih longgar |
| Asal nilai longgar | `settings_audit` #12, #18, #29, #31, #76, #210, #216: penulis `changed_by = fund2` (koneksi DB), `source = db`, tanpa baris `audit_log` `CONFIG_CHANGED`. Artinya nilai itu masuk lewat tulisan langsung ke DB (sisa harness uji beban/latensi), **bukan** lewat kanal §I.3, sehingga tidak pernah ada persetujuan owner untuk melonggarkannya |
| Konfirmasi owner | Pertanyaan konfirmasi dikirim 26 Nov 2026 lewat kantor (DeskRPG) pada jendela kartu ini: **tidak ada user tersedia untuk menjawab**. Karena bagian E sudah mengunci A1-A12 dan tidak ada revisi tertulis, angka yang berlaku tetap §I. Bila owner ingin pelonggaran staging, tulis di chat kantor; §I.4 direvisi dan dokumen turunan disinkronkan ulang |
| Penetapan | hf-ceo, 26 Nov 2026. **Bukan angka baru**: runtime dev/staging/demo disamakan ke angka §I.1 yang sudah disetujui |
| Penerapan | `PUT /admin/risk-settings` (sesi 2FA + konfirmasi ulang password), 26 Nov 2026 06:39 WIB. Bukti: `settings_audit` #356-#359, `audit_log` #716 (`CONFIG_CHANGED`), `scripts/validate_release_packet.py` gate `guardrails_sesuai_policy = true`. Rincian: `docs/BUKTI_GUARDRAIL_PARITY_t_bf4b85f9.md` |

Nilai sebelum dan sesudah penerapan:

| Key | Sebelum (26 Nov 06:38) | Sesudah (26 Nov 06:39) | Final §I.1 |
| --- | --- | --- | --- |
| `max_volume` | 1,0 | **0,10** | 0,10 (A3) |
| `max_orders_per_min` | 10 | **5** | 5 (A8) |
| `kill_switch_triggers.daily_drawdown_pct` | 10,0 | **3,0** | 3,0 (A6) |
| `kill_switch_triggers.total_drawdown_pct` | 15,0 | **8,0** | 8,0 (A7) |
| `kill_switch_triggers.consecutive_failed_orders` | 100 | **3** | 3 |
| `kill_switch_triggers.ea_offline_seconds` | 60,0 | **6,0** | 6,0 (A12) |
| `kill_switch_triggers.ea_offline_halt_seconds` | 60,0 | 60,0 (tetap) | 60,0 (halt) |
| `max_daily_drawdown` | 100,0 | **292,02** | 292,02 (3% x 9.733,86) |

**Aturan paritas (mengikat).** Dev, staging, dan demo memakai angka §I yang sama dengan target live. Tidak ada status "staging boleh lebih longgar" yang sah. Uji beban atau QA yang butuh ambang berbeda hanya boleh memakainya sebagai **jendela uji eksplisit**: catat nilai sementara + alasan di tiket, jalankan uji, lalu kembalikan ke §I dan buktikan gate `guardrails_sesuai_policy` PASS sebelum sesi ditinggalkan. Nilai longgar yang tertinggal setelah uji dihitung sebagai drift (F-03) dan wajib ditutup lewat kanal §I.3, bukan dibiarkan.

**Pengaman pemeriksaan silang.** `scripts/validate_release_packet.py` (`check_db`) membaca `settings` read-only dan membandingkan 9 angka kunci + plafon A6 absolut + pemisahan `ea_offline_seconds` (6 s) vs `ea_offline_halt_seconds` (60 s). Gate ini wajib PASS sebelum canary; angka yang lebih ketat dari plafon dicatat sebagai `guardrail_open`, bukan dibiarkan lolos.

**Pengawas harian (26 Nov 2026, kartu `t_097ef2bb`).** Gate yang sama dijalankan
`fund2-guardrail-watch.timer` (systemd user, harian 05:10 UTC / 12:10 WIB,
`Persistent=true`) lewat `scripts/check_guardrail_runtime.py`: read-only,
menulis `~/fund2-backups/logs/guardrail-<tanggal>.json`, dan mengirim satu alert
Telegram ke owner saat `guardrail_drift` atau `guardrail_open` tidak kosong
(key, nilai aktif, nilai §I, rujukan §I). Timer **tidak** memperbaiki nilai
sendiri: semua perubahan tetap lewat kanal §I.3. Bukti:
`docs/BUKTI_GUARDRAIL_WATCH_t_097ef2bb.md`.
