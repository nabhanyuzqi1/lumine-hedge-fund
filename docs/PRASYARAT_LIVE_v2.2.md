# Prasyarat Live Terpisah v2.2: D1, Kill Switch, Guardrail, Approval

Kartu: **t_128a9dee** (paket kesiapan operasional dan rollback rilis) · Tanggal: 25 Nov 2026 (WIB)
Pemilik: hf-devops · Referensi: PRD v2.2 §16, §18, §20.2, §29; `KEPUTUSAN_OWNER.md` (A1-A12, D1-D16, H1)
Dokumen pendamping: `RELEASE_PACKET_v2.2.md`, `CANARY_PLAN_v2.2.md`, `GENERAL_RELEASE_PLAN_v2.2.md`, `ROLLBACK_PLAN_v2.2.md`

> **Dokumen ini tidak memberi izin apa pun.** Status live: **OFF**. Dokumen ini hanya menetapkan apa yang harus benar dan terbukti sebelum modal nyata dipakai, dan siapa yang berwenang.

## 0. Tiga gerbang yang terpisah dan tidak saling menggantikan

| Gerbang | Isi | Kewenangan | Status 25 Nov 2026 |
| --- | --- | --- | --- |
| **G1 · Kesiapan teknik** | Semua kartu engineering v2.2 selesai, P9 lulus, QA sign-off, rollback teruji penuh | Direktur + QA | BELUM (P9: 8/20 hari, 8/100 trade, PF 1,211) |
| **G2 · D1** | Modal live dan batas kerugian absolut diisi owner | **Owner saja** | **DEFER** (`KEPUTUSAN_OWNER.md` bagian E) |
| **G3 · Approval live tertulis** | Persetujuan eksplisit untuk mengaktifkan uang nyata, terpisah dari approval gate P2 (H1) | **Owner saja** | BELUM ADA |

Aturan: G1 lulus **tidak** membuka G2/G3. G2 terisi **tidak** membuka G3. Tidak ada kombinasi parsial yang mengizinkan order uang nyata.

Bukti live masih OFF (diverifikasi 25 Nov 2026, read-only):

| Bukti | Nilai |
| --- | --- |
| `GET /health` | `{"ok":true,"subscribers":1,"env":"demo"}` |
| `FUND2_ENV` (`api/app/config.py`) | `demo` (label UI; bukan `live`) |
| `settings.kill_switch` | `{"mode": null, "active": false}` (tidak ada halt aktif) |
| `settings.halted` | `false` |
| `settings.strategy_mode_ml_gbm` | `paper` |
| `paper_state.is_simulation` | `true` untuk seluruh key shadow dan paper |
| `fund2-paper-runner.service` | active, unit description: PAPER mode |
| `AUDIT` keputusan | `KEPUTUSAN_OWNER.md`: D1 DEFER, F2 live OFF, H1 menahan release-path |

## 1. Prosedur D1: modal live dan batas kerugian absolut

D1 tidak punya nilai default di PRD (`KEPUTUSAN_OWNER.md` baris D1; PRD v2.2 §29.1). Wajib diisi owner, bukan agent, bukan DevOps.

### 1.1 Data yang wajib diisi owner

| Field | Satuan | Batas / catatan | Diisi |
| --- | --- | --- | --- |
| Modal live awal | USD | Harus konsisten dengan `portfolio_risk.max_total_volume_lot` dan margin broker | kosong |
| Batas kerugian absolut | USD | Angka mati, bukan persen. Menjadi penghenti bisnis bila tersentuh | kosong |
| Batas kerugian per hari | USD | Turunan dari A6 (3% modal) atau angka owner | kosong |
| Lot maksimum per order | lot | Selaras A3 (0,10 lot), per simbol | kosong |
| Eksposur total maksimum | lot | Selaras A4 (0,30 lot), agregat akun | kosong |
| Simbol dan strategi yang diizinkan | daftar | Selaras D9/D15/F1 (mulai 1 strategi) | kosong |
| Tanggal mulai canary | tanggal | Setelah G1 lulus dan approval G3 | kosong |
| Nama dan tanda tangan owner | teks | Ditulis di `KEPUTUSAN_OWNER.md` bagian baru + chat kantor | kosong |

### 1.2 Cara mencatat (urutan wajib)

1. Owner menulis keputusan di chat kantor dengan format: `D1 = modal <USD>, batas kerugian absolut <USD>, lot maks <lot>, exposure <lot>, simbol <...>, strategi <...>`.
2. CEO menambahkan bagian baru di `KEPUTUSAN_OWNER.md` (mis. bagian I) berisi angka tersebut, tanggal, dan kanal keputusan. Commit dengan pesan `docs(owner): D1 terisi`.
3. DevOps memverifikasi bahwa nilai `settings`/`portfolio_risk` di DB konsisten dengan D1 sebelum canary (lihat §3).
4. Selama langkah 1 belum ada, **tidak ada perubahan kode, konfigurasi, atau order yang boleh mengasumsikan modal**.

### 1.3 Larangan

- Agent dan worker tidak boleh mengisi D1, mengarang angka modal, atau menurunkan batas kerugian agar canary "muat".
- Perubahan parameter risiko setelah D1 terkunci hanya lewat UI dengan konfirmasi ulang password + audit (PRD §14), bukan `psql` langsung.
- D1 tanpa approval G3 tetap berarti live OFF.

## 2. Kill switch: otorisasi, bukti, dan syarat sebelum canary

### 2.1 Mode dan kewenangan

| Aksi | Mode | Kewenangan | Syarat |
| --- | --- | --- | --- |
| Halt darurat (entry ditolak) | `GLOBAL_HALT` | OPS/admin on-call | Tanpa 2FA demi kecepatan (PRD §18); dicatat di `kill_switch_events` |
| Stop order baru | `STOP_NEW_ORDERS` | OPS/admin atau auto-trigger | Idempotent |
| Flatten posisi | `STOP_AND_FLATTEN` | **Owner saja** | `confirm=true` + 2FA + TOTP (D6); risiko slippage dijelaskan lebih dulu |
| Lepas halt / resume | release | **Owner saja** | 2FA + 7 butir `RECOVERY_CHECKLIST` (D11) |
| Pause strategi scoped | per strategi | Owner/admin | Tidak melepas halt global |

Auto-trigger tidak pernah flatten (D6). Auto-trigger hanya `GLOBAL_HALT` dan `STOP_NEW_ORDERS`.

### 2.2 Bukti fungsi (bukan klaim)

| Bukti | Isi | Sumber |
| --- | --- | --- |
| Uji suite | `api/tests/test_kill_switch.py` 30+ kasus, termasuk anti-auto-flatten | `RELEASE_CHECKLIST_v2.2.md` butir 2.5 |
| Insiden nyata 1 | `auto:ea_offline`, EA offline 63 s dengan 2 posisi, halt terpicu | `kill_switch_events` id 98 (24 Nov 22:05 UTC) |
| Insiden nyata 2 | `auto:ea_offline`, 1 posisi terbuka, halt terpicu | `kill_switch_events` id 138 (25 Nov 06:45 WIB) |
| Uji activate/release 25 Nov | id 219 ACTIVATE dan id 220 RELEASE, lalu 221/222, sumber `kanban:t_baeb3ce4`, aktor `svc-qa-driver`, alasan `auto:daily_drawdown_risk_gate` | `kill_switch_events` (harness QA, state kini `active: false`) |
| Uji release wajib checklist | release tanpa `checklist_ack` ditolak | `QA_P5_cutover.md` §4 |

### 2.3 Syarat yang belum terpenuhi sebelum canary

1. **Drill aktivasi + release oleh owner** di jendela terkontrol, bukan hanya oleh harness QA. Release harus dilakukan owner (2FA), lalu dicatat sebagai bukti canary readiness.
2. **Alert pipeline sehat.** Temuan `RUNBOOK_v2.2_UJI.md` F1 (daemon `fund2-alerts` beku 06:45-07:42 WIB, alert SEV-2/RELEASE/rekap tidak terkirim) dan F2 (teks `paper_state` tidak di-escape sehingga 400 `can't parse entities`). Mitigasi sementara: restart 07:42 WIB, daemon aktif dan mengirim (log 19:46 WIB `sendMessage 200 OK`). Akar masalah (`db.pool().connection()` tanpa timeout saat Postgres belum siap) **belum diperbaiki**; wajib ditutup sebelum canary.
3. **Ambang auto-trigger disetel ke nilai yang disetujui** (§3, drift G-01 sampai G-04).
4. **Uji flatten tidak dilakukan dengan posisi nyata** sebelum approval G3; cukup drill di akun demo dengan 1 posisi minimum, keputusan owner.

### 2.4 Verifikasi read-only (aman dijalankan kapan saja)

```bash
curl -s http://127.0.0.1:3110/health
# mode & status (butuh sesi admin)
curl -s -b /tmp/f2cookie http://127.0.0.1:3110/kill-switch
systemctl --user is-active fund2-alerts fund2-api fund2-postgres
journalctl --user -u fund2-alerts -n 20 --no-pager
```

## 3. Guardrail: angka final vs nilai runtime

Angka **final** ditetapkan di `KEPUTUSAN_OWNER.md` §I (26 Nov 2026, dasar keputusan tertulis A1-A12 bagian E: SETUJU SEMUA). Nilai runtime dibaca read-only dari tabel `settings` DB `fund2` lewat `scripts/validate_release_packet.py`. Kolom **Awal 01:33** mencatat drift yang ditemukan halaman `/admin/guardrail` (kartu `t_2d1f6d33`); kolom **Runtime 06:39** adalah hasil penerapan §I.4 lewat `PUT /admin/risk-settings` (kartu `t_bf4b85f9`) dan sudah diverifikasi ulang read-only.

| ID | Guardrail | Final (§I) | Awal 26 Nov 01:33 | Runtime 26 Nov 06:39 | Status |
| --- | --- | --- | --- | --- | --- |
| G-01 | Volume maksimum per order (A3) | 0,10 lot | `max_volume = 1.0` | `max_volume = 0.1` | SESUAI (sebelumnya DRIFT 10x) |
| G-02 | Order per menit (A8) | 5 | `max_orders_per_min = 10` | `max_orders_per_min = 5` | SESUAI (sebelumnya DRIFT 2x) |
| G-03 | DD harian auto-halt (A6) | 3% | `daily_drawdown_pct = 10.0`; `max_daily_drawdown = 100.0` | `daily_drawdown_pct = 3.0`; `max_daily_drawdown = 292.02` (= 3% x 9.733,86) | SESUAI (sebelumnya DRIFT) |
| G-04 | DD total auto-halt (A7) | 8% | `total_drawdown_pct = 15.0` | `total_drawdown_pct = 8.0` | SESUAI (sebelumnya DRIFT ~2x) |
| G-05 | Order FAILED beruntun | 3 | `consecutive_failed_orders = 100` | `consecutive_failed_orders = 3` | SESUAI (sebelumnya DRIFT 33x) |
| G-06 | EA offline: tanda offline + tolak entry + alert (A11/A12) | 6 s | `ea_offline_seconds = 60.0` | `ea_offline_seconds = 6.0` | SESUAI (sebelumnya DRIFT 10x) |
| G-06b | EA offline: ambang `GLOBAL_HALT` (v2.1 §5.7) | 60 s | belum ada di DB; fallback kode 60 s | `ea_offline_halt_seconds = 60.0` di DB; `/metrics` `ea.offline_halt_threshold_s = 60` | SESUAI, peran terpisah dari G-06 |
| G-07 | Eksposur total (A4) | 0,30 lot | `portfolio_risk.max_total_volume_lot = 0.3` | `portfolio_risk.max_total_volume_lot = 0.3` | SESUAI |
| G-08 | Risiko per trade (A5) | 0,5% equity | `portfolio_risk.max_risk_per_trade_pct = 0.5`, `risk_per_trade_pct = 0.5` | idem | SESUAI |
| G-09 | Spread absolute filter (A9) | 0,50 USD | `max_spread = 0.5` + `symbol_specs.XAUUSD.spread_abs_max_usd = 0.5` | idem | SESUAI |
| G-10 | SL wajib broker-side (A1) | Wajib, tolak tanpa SL | risk gate deterministik (`test_risk.py`) | idem | SESUAI (uji) |
| G-11 | Jarak SL (A2) | XAUUSD 0,50-15,00 USD; BTCUSD 10,00-1.000,00 USD | `symbol_specs[SYMBOL].sl_min_usd/sl_max_usd`, `spec_verified=true` | idem | SESUAI, terpetakan per simbol (bukan satu key `settings`) |
| G-12 | Data basi / tick age (A10) | 3 s | `max_tick_age_s = 3.0` | `max_tick_age_s = 3.0`, dibaca risk gate (`risk.py`) | SESUAI (`/metrics` proses berjalan memuat kode baru) |
| G-13 | Margin utilization | 20% | `max_margin_utilization_pct = 20.0` | idem | SESUAI |
| G-14 | Feed equity/margin basi (**bukan** A10) | 60 s (dikaji ulang saat canary) | `max_feed_age_s = 60.0` | idem | SESUAI sebagai konteks feed |

### 3.1 Kenapa drift itu ada dan cara menutupnya

Nilai runtime yang longgar konsisten dengan kebutuhan pengujian: harness latensi P5 mengirim ratusan order demo dan QA mengaktifkan/mematikan halt berulang. Jejak `settings_audit` menunjukkan nilai itu masuk lewat tulisan langsung ke DB (`changed_by = fund2`, `source = db`, tanpa `audit_log CONFIG_CHANGED`), jadi tidak pernah ada persetujuan owner atas pelonggaran tersebut. Nilai itu **tidak boleh** ikut ke live.

Penutupan (26 Nov 2026, kartu `t_bf4b85f9`): runtime dev/staging disamakan ke §I lewat `PUT /admin/risk-settings` (2FA + password ulang), tercatat di `settings_audit` #356-#359 dan `audit_log` #716. Aturan paritas dan larangan meninggalkan nilai uji longgar ada di `KEPUTUSAN_OWNER.md` §I.4.

### 3.2 Tindakan wajib sebelum canary

1. **Angka final** ditetapkan → `KEPUTUSAN_OWNER.md` §I (selesai 26 Nov 2026, kartu `t_d3ab9839`).
2. **Penegakan kode** (selesai di kartu yang sama): `max_tick_age_s` dibaca risk gate (bukan hardcoded 10 s); ambang EA offline dipisah (`ea_offline_seconds` 6 s untuk tanda offline/blokir entry, `ea_offline_halt_seconds` 60 s untuk `GLOBAL_HALT`); endpoint ter-audit `PUT /admin/risk-settings` (sesi 2FA + password ulang). Proses `fund2-api` yang berjalan (pid 738424, start 05:21 WIB) sudah memuat kode ini: `/metrics` melaporkan `ea.offline_threshold_s = 6` dan `ea.offline_halt_threshold_s = 60`. Tidak perlu restart khusus untuk dua key ini; restart window tetap mengikuti kartu rilis.
3. **Penerapan nilai** hanya lewat kanal ter-audit: `PUT /admin/risk-settings` untuk guardrail inti dan `PUT /kill-switch/triggers` untuk auto-trigger. `psql` langsung dilarang (PRD §14, §18). Lalu verifikasi read-only dan catat di tiket. **Selesai 26 Nov 2026 06:39 WIB** (kartu `t_bf4b85f9`, `KEPUTUSAN_OWNER.md` §I.4).
4. **Gate**: `scripts/validate_release_packet.py` harus memberi `guardrails_sesuai_policy = PASS` sebelum canary. **Status 26 Nov 2026 06:39 WIB: PASS** (`docs/VALIDASI_PAKET_RILIS_20261126T063940Z.json`).

**Perubahan guardrail dilarang dilakukan tanpa mengikuti §3.2 butir 3** dan tanpa angka §I yang tertulis.

## 4. Prasyarat approval live (G3): daftar periksa terpisah

Approval live adalah pernyataan tertulis owner bahwa uang nyata boleh dipakai, dengan ruang lingkup dan batas yang eksplisit. Approval gate P2 (H1) **bukan** approval live.

| # | Prasyarat | Bukti yang diterima | Status 25 Nov |
| --- | --- | --- | --- |
| A-01 | Semua kartu engineering v2.2 done dan terverifikasi | Laporan verifikasi engineering (kartu gate) | BELUM (`t_f2llm4` berjalan) |
| A-02 | P9 lulus: paper 20 hari kerja, 100 trade, PF >= 1,3 setelah biaya, DD <= 5% | `eval_gate_paper.py` verdict + laporan QA | BELUM (8 hari, 8 trade, PF 1,211, DD 1,38%) |
| A-03 | UAT owner lulus | Berita acara UAT (login, dashboard, kill switch, release) | BELUM |
| A-04 | QA sign-off rilis | Kartu QA + `RELEASE_CHECKLIST` blok Release | BELUM |
| A-05 | **D1 terisi owner** | `KEPUTUSAN_OWNER.md` bagian baru + chat kantor | BELUM (DEFER) |
| A-06 | **Approval live tertulis owner** | Pernyataan eksplisit, terpisah dari H1, dengan lingkup dan batas | BELUM |
| A-07 | Guardrail G-01..G-06, G-11, G-12 disetujui dan terpasang | Tabel §3 diperbarui + bukti query | BELUM |
| A-08 | Drill rollback aplikasi penuh lulus | Laporan drill (commit sebelum + restart + reconcile E2E) | BELUM (deviasi 3.6) |
| A-09 | Drill kill switch oleh owner (aktivasi + release) | `kill_switch_events` oleh aktor owner | BELUM |
| A-10 | Pipeline alert sehat dan F1/F2 ditutup | Uji `--send-test` 4x + bukti owner terima + kode diperbaiki | BELUM (mitigasi restart) |
| A-11 | Release artifact ter-freeze dan ter-tag | Tag `fund2-v2.2-rc<N>` pada commit bersih + checksum | BELUM (tree kotor, belum ada tag) |
| A-12 | Backup pre-release | `fund2_backup.sh pre-deploy` sukses + offsite | BELUM (dijalankan di window) |
| A-13 | Pentest dan pytest penuh di release window | Log hasil di kartu rilis | BELUM (pytest 1127 lulus 25 Nov, pentest perlu rerun) |
| A-14 | Persetujuan risiko residual (D14) | Tanda tangan owner pada risk policy dan `RISK_REGISTER_v2.2.md` | BELUM |

Aturan: jika satu baris A-01..A-14 masih BELUM, jawabannya **NO-GO**. Tidak ada pengecualian lisan; pengecualian harus tertulis dan menyebut baris mana yang dikecualikan, seperti pola H1.

## 5. Yang dilarang sampai G2 dan G3 selesai

- Deploy ke akun broker live, mengubah `FUND2_ENV` menjadi `live`, atau mengaktifkan auto-trading pada akun live.
- Mengubah `settings` risiko agar lebih longgar, atau mematikan kill switch auto-trigger.
- Menjalankan canary dengan "modal kecil dulu" tanpa D1 dan approval tertulis. Canary tetap live money.
- Menghapus atau mengedit baris `kill_switch_events`, `order_events`, atau log insiden (PRD §27).

## 6. Sign-off dokumen

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-devops | 25 Nov 2026 | Kartu `t_128a9dee` |
| Verifikasi guardrail | hf-devops | 25 Nov 2026 | Query read-only `settings`, lihat §3 |
| Review teknis | QA (hf-qa) | menunggu | F1/F2 dan angka G-11/G-12 |
| Keputusan angka risiko | Owner | menunggu | G-01..G-06, G-12 |
| Approval live | Owner | menunggu | G3, terpisah dari H1 |
