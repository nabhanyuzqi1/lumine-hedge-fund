# Log Insiden — Fund2 (append-only)

Referensi: `INCIDENT_PLAYBOOK_v2.2.md` (template §3, aturan §4).
**Aturan: entri tidak pernah dihapus/diedit untuk mempercantik metrik (PRD §27). Koreksi = entri baru yang merujuk entri lama. Tambahkan entri baru di bawah garis terakhir.**

Format ID: `INS-<YYYYMMDD>-<nn>` (urut waktu). Status: OPEN / MITIGATED / CLOSED.

---

## INS-20261122-01 — Live DB ter-truncate oleh run pytest dengan DATABASE_URL produksi

| Field | Isi |
| --- | --- |
| Severity | SEV-1 (kehilangan data DB live) |
| Waktu mulai / selesai | 2026-11-22 05:34 WIB / 22 Nov 2026 (perbaikan isolasi selesai hari yang sama) |
| Terdeteksi oleh | manual (worker) |
| Dampak posisi & order | DB fund2 live ter-truncate 2x oleh suite pytest; era paper (belum ada posisi live) |
| Timeline | 05:34 WIB pytest dijalankan dengan env `DATABASE_URL` menunjuk DB live → TRUNCATE tabel live; 2x terulang; isolasi conftest dirancang ulang |
| Penyebab langsung | `DATABASE_URL` live terekspor di shell saat pytest dijalankan |
| Akar masalah | Tidak ada pengaman URL di conftest; TRUNCATE guard tidak memverifikasi DB tujuan |
| Tindakan otomatis | Tidak ada (belum ada guard) |
| Tindakan manual | Stop run; rebuild schema; rancang isolasi 3 lapis |
| Keputusan owner | (rekonstruksi) lanjut dengan isolasi keras |
| Bukti ledger | docstring `api/tests/conftest.py` (dokumentasi insiden) |
| Bukti broker | N/A (belum ada posisi live) |
| Corrective action | conftest menolak URL non-`fund2_test*` (layer 1) + DB per-run sekali pakai (layer 2) + TRUNCATE guard verifikasi `current_database()`/port (layer 3) — pemilik: hf-backend — SELESAI |
| Preventive action | Aturan kerja: ad-hoc script yang import app code wajib `TELEGRAM_ALERTS_OFF=1` dan URL test — SELESAI (docstring conftest) |
| Status | CLOSED |

## INS-20261122-02 — Spam Telegram owner oleh test bridge/reconciler dengan kredensial produksi

| Field | Isi |
| --- | --- |
| Severity | SEV-2 (integritas kanal alert; tanpa dampak posisi) |
| Waktu mulai / selesai | 2026-11-22 10:40-12:22 WIB / 22 Nov 2026 |
| Terdeteksi oleh | owner (menerima spam) |
| Dampak posisi & order | Tidak ada; test cycle memanggil `notify_owner()` produksi berulang ("ORPHAN ADOPTED" / "REKONSILIASI") |
| Timeline | 10:40 WIB worker menguji bridge/reconciler dengan snapshot sintetik terhadap API LIVE; tiap siklus kirim Telegram nyata; 12:22 WIB selesai ditangani |
| Penyebab langsung | Test memakai token produksi dari `api/.env` |
| Akar masalah | Tidak ada isolasi kredensial Telegram di jalur test/ad-hoc |
| Tindakan otomatis | Tidak ada |
| Tindakan manual | Hentikan test; bersihkan guard |
| Keputusan owner | (rekonstruksi) kunci kredensial produksi dari test |
| Bukti ledger | docstring `api/tests/conftest.py` |
| Bukti broker | N/A |
| Corrective action | conftest: drop `TELEGRAM_BOT_TOKEN`/`TELEGRAM_OWNER_ID`, blank config, `TELEGRAM_ALERTS_OFF=1` (notify no-op); fixture `fake_tg` untuk test kirim — pemilik: hf-backend — SELESAI |
| Preventive action | RULE: bridge/reconciler test tidak boleh memakai kredensial Telegram produksi — SELESAI |
| Status | CLOSED |

## INS-20261123-01 — Alert Telegram gagal diam-diam (underscore Markdown)

| Field | Isi |
| --- | --- |
| Severity | SEV-3 (alert tidak terkirim; monitoring gap) |
| Waktu mulai / selesai | 2026-11-23 / 23 Nov 2026 (fix commit) |
| Terdeteksi oleh | manual |
| Dampak posisi & order | Tidak ada; alert berisi underscore (nilai dinamis) ditolak parser Telegram |
| Timeline | Pesan alert dengan underscore di luar backtick → HTTP 400 dari Telegram API; dilaporkan sukses padahal gagal |
| Penyebab langsung | Teks tidak di-escape untuk Markdown Telegram |
| Akar masalah | `send_message` tidak memeriksa `ok=false` sehingga kegagalan diam-diam |
| Tindakan otomatis | Tidak ada |
| Tindakan manual | Review semua path kirim alert |
| Keputusan owner | (rekonstruksi) perbaiki + raise saat gagal |
| Bukti ledger | `docs/OBSERVABILITY_v2.2.md` (catatan insiden) |
| Bukti broker | N/A |
| Corrective action | fungsi `_esc` untuk nilai dinamis; `send_message` raise saat `ok=false` (commit `d853c02`) — SELESAI |
| Preventive action | Validasi teks sebelum kirim: underscore di luar backtick, jumlah bintang/backtick genap — SELESAI |
| Status | CLOSED |

## INS-20261124-01 — Auto GLOBAL_HALT: EA offline 63 s dengan 2 posisi terbuka

| Field | Isi |
| --- | --- |
| Severity | SEV-1 (auto-halt dengan posisi terbuka) |
| Waktu mulai / selesai | 2026-11-24 22:05:16 UTC / MITIGATED 25 Nov (halt masih aktif, release menunggu owner) |
| Terdeteksi oleh | auto-trigger `auto:ea_offline` (kill_switch_events id 98) |
| Dampak posisi & order | 2 posisi XAUUSD 0.01 lot terbuka saat EA offline; tidak ada order baru masuk selama halt |
| Timeline | 22:05:16 UTC EA offline 63 s (threshold 60 s) dengan 2 posisi → GLOBAL_HALT otomatis; 22:0x-23:xx UTC flatten manual bertahap via dashboard (kill_switch_events id 99-101); posisi OPEN tersisa 0 per 25 Nov |
| Penyebab langsung | EA/terminal tidak mengirim heartbeat > 60 s |
| Akar masalah | (menyusul bila pola berulang; dugaan: koneksi terminal/VPS) |
| Tindakan otomatis | `GLOBAL_HALT` source `auto:ea_offline` + alert owner — bekerja sesuai desain |
| Tindakan manual | Flatten bertahap oleh admin via dashboard (3 FLATTEN_REQUEST) |
| Keputusan owner | Posisi ditutup (flatten); halt tidak dilepas otomatis |
| Bukti ledger | `kill_switch_events` id 98-101; `settings.kill_switch` (active GLOBAL_HALT) |
| Bukti broker | snapshot positions via `/bridge/positions` (flatten requests) |
| Corrective action | (menyusul) investigasi penyebab EA offline |
| Preventive action | (menyusul) pertimbangkan watchdog terminal/heartbeat kedua |
| Status | MITIGATED (posisi aman; halt aktif menunggu checklist recovery + release owner per D11) |

## INS-20261125-01 — Order flatten CLOSE tertinggal STUCK, breaker menghentikan LLM paper trading

| Field | Isi |
| --- | --- |
| Severity | SEV-2 (trading halting tanpa posisi nyata) |
| Waktu mulai / selesai | 2026-11-24/25 (rekonstruksi dari kartu t_f2llm4) / 25 Nov 2026 (fix) |
| Terdeteksi oleh | monitor gerbang LLM + manual |
| Dampak posisi & order | 1 order CLOSE status STUCK; gate menolak semua order; breaker menghentikan LLM paper trading |
| Timeline | EA flatten menutup posisi di broker → hasil CLOSE tidak terekonsiliasi (posisi sudah tidak ada) → order STUCK; manual reconciliation menutup order & record DB; trading dibuka lagi |
| Penyebab langsung | CLOSE untuk posisi yang sudah tidak ada tidak dipetakan ke status terminal |
| Akar masalah | Reconciler belum menangani CLOSE-late + profit close 0.0 dari EA |
| Tindakan otomatis | Breaker halt (sesuai desain) |
| Tindakan manual | Reconcile manual: tutup order STUCK + record DB |
| Keputusan owner | (rekonstruksi) tambah auto-reconcile |
| Bukti ledger | Kartu t_f2llm4; commit `20e6e80`, `1e6e361d` |
| Bukti broker | snapshot positions saat reconcile (kartu t_f2llm4) |
| Corrective action | Auto-reconcile order STUCK > 15 menit via posisi target + alert (commit `1e6361d`); recompute profit close dari harga saat EA lapor 0.0 (commit `20e6e80`) — SELESAI |
| Preventive action | (menyusul) monitor khusus order STUCK di dashboard |
| Status | CLOSED |

## INS-20261125-02 — Endpoint flatten menerima TOTP tidak valid selama jendela 2FA sesi

| Field | Isi |
| --- | --- |
| Severity | SEV-2 (kontrol keamanan; posisi tertutup tanpa TOTP valid) |
| Waktu mulai / selesai | ditemukan 2026-11-25 / 25 Nov 2026 (fix commit `cea98c5`) |
| Terdeteksi oleh | QA UI-D6 (kasus `7_flatten_wrong_2FA`) |
| Dampak posisi & order | Flatten sukses dieksekusi meski `code` TOTP di body salah |
| Timeline | QA menemukan celah: verifikasi TOTP flatten hanya mengandalkan jendela 2FA sesi; code salah di body diabaikan → backend t_57103cf5 |
| Penyebab langsung | Server tidak memverifikasi `code` di body `POST /kill-switch/flatten` |
| Akar masalah | Verifikasi step-up 2FA tidak konsisten antar endpoint |
| Tindakan otomatis | Tidak ada |
| Tindakan manual | Follow-up backend t_57103cf5 |
| Keputusan owner | (rekonstruksi) wajibkan TOTP valid server-side |
| Bukti ledger | Commit `cea98c5`; test `test_flatten_wrong_totp_code_rejected` |
| Bukti broker | N/A (sesi QA) |
| Corrective action | Verifikasi TOTP server-side + anti-replay di endpoint flatten — SELESAI |
| Preventive action | Audit semua endpoint step-up 2FA agar pola verifikasinya sama — pemilik: hf-backend — terbuka |
| Status | CLOSED |

## INS-20261125-03 — EA offline berulang: auto GLOBAL_HALT kedua dalam 100 menit

| Field | Isi |
| --- | --- |
| Severity | SEV-2 (PRD §20.2: EA offline saat posisi terbuka). Catatan: INS-20261124-01 (kelas kejadian sama) tercatat SEV-1 — pemetaan severity perlu diseragamkan (lihat corrective action); log lama tidak diedit |
| Waktu mulai / selesai | 2026-11-25 06:45:23 WIB / MITIGATED 25 Nov 2026 (EA pulih 06:50:56 WIB; halt masih aktif menunggu release owner per D11) |
| Terdeteksi oleh | auto-trigger `auto:ea_offline` (`kill_switch_events` id 138) |
| Dampak posisi & order | 1 posisi XAUUSD 0.01 terbuka saat EA offline; tidak ada order baru masuk selama halt (risk gate menolak entry); 0 posisi terbuka per 06:51 WIB |
| Timeline | 06:38:01 RELEASE halt sebelumnya (id 102, actor dashboard) -> 06:39:10-06:39:56 8 order manual XAUUSD BUY 0.01 via dashboard (3 FILLED_THEN_CLOSED, 5 FILLED) -> 06:40:03-06:43:44 5 order flatten SELL via dashboard, semua FILLED (posisi manual tertutup) -> 06:45:23 EA offline 63 s (threshold 60 s) dengan 1 posisi terbuka -> auto GLOBAL_HALT (id 138, source auto:ea_offline) + alert owner -> 06:50:56 heartbeat EA kembali, 0 posisi, halt TETAP AKTIF |
| Penyebab langsung | EA/terminal tidak mengirim heartbeat > 60 s (kejadian kedua pagi ini setelah 05:05 WIB) |
| Akar masalah | (menyusul) pola berulang: 2x dalam 100 menit (05:05 & 06:45 WIB); dugaan koneksi terminal/VPS, belum terverifikasi |
| Tindakan otomatis | `GLOBAL_HALT` source `auto:ea_offline` (idempotent, ter-audit id 138) + alert owner — bekerja sesuai desain |
| Tindakan manual | Monitoring; tidak ada intervensi tambahan (kartu t_f2v22a17 fase dokumentasi) |
| Keputusan owner | (menunggu) release halt setelah checklist recovery 7 butir — agent tidak berhak melepas halt (D11) |
| Bukti ledger | `kill_switch_events` id 102 (RELEASE) dan id 138 (ACTIVATE); `orders` strategy `manual` (8x) dan `flatten` (5x) 06:39-06:43 WIB; `settings.kill_switch` (GLOBAL_HALT aktif); `settings.ea_last_seen_at` 2026-11-24T23:50:56 UTC |
| Bukti broker | snapshot posisi via `/bridge/positions` (0 terbuka per 06:51 WIB) |
| Corrective action | Investigasi akar masalah EA offline berulang (log recorder, koneksi terminal/broker) — pemilik: hf-devops — OPEN; seragamkan pemetaan severity insiden terhadap PRD §20.2 — pemilik: hf-ceo — OPEN |
| Preventive action | Watchdog terminal/heartbeat kedua (menyusul dari INS-20261124-01); eskalasi otomatis bila EA offline ≥ 2x dalam 24 jam — OPEN |
| Status | MITIGATED (containment selesai: halt aktif, EA online, posisi 0; akar masalah dan release halt menunggu) |
