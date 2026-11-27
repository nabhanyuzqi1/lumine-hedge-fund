# Gerbang DoD P4 — Koordinasi & Verifikasi (t_f2co_p4)

Tanggal: 23 Nov 2026 · Verifikator: hf-ceo (koordinasi) · PRD v2.1 §11 fase P4

Metode gerbang: pengukuran diulang sendiri, tidak menerima laporan kartu
sebagai bukti. Kriteria dideklarasikan sebelum pengukuran.

## Kriteria & hasil

| DoD | Kriteria | Hasil | Bukti |
| --- | --- | --- | --- |
| 1 | 1 laporan mingguan otomatis terkirim | **LULUS** (setelah perbaikan) | `fund2-selfimprove.service` dieksekusi ulang via systemd: exit 0, `"sent": true` DENGAN kode terverifikasi (lihat temuan 1). Timer aktif, next Senin 30 Nov 2026 07:30 WIB. |
| 2 | 1 usulan strategi ter-approve melewati seluruh alur | **BELUM** (menunggu keputusan owner) | DB live: `improvement_proposals` 3 baris semua `PROPOSED`; `strategy_approvals` 0; `deployment_records` 0; `strategies` 0. |
| 3 | Uji garis merah lulus | **LULUS** | Pentest dieksekusi ulang langsung terhadap fund2-api live: 42 percobaan, semua probe keamanan DITOLAK (detail bawah). |

## Temuan gerbang (dua bug integritas pengiriman, sudah diperbaiki)

1. **`notify_owner` melaporkan sukses palsu.** `tg_api` hanya me-log respons
   `ok=false` dari Telegram; `send_message` mengabaikannya, sehingga pesan
   yang DITOLAK Telegram tetap terhitung "terkirim". Diperbaiki:
   `send_message` raise saat `ok=false` (commit d853c02) + 2 tes regresi.
2. **Laporan mingguan W48 ditolak Telegram karena Markdown.** Template
   menanam literal `t_f2p4a1` dan nama kriteria berunderscore
   (`net_profit_usd_gt`, dst.) → "can't parse entities" → laporan TIDAK
   pernah sampai ke owner sejak siklus pertama, walau dilaporkan sukses.
   Diperbaiki: escape karakter Markdown pada semua nilai dinamis + kriteria
   digarisi backtick + referensi kartu memtak dihapus dari template
   (commit f96c1bb) + 1 tes regresi. Siklus diulang via systemd:
   laporan W48 kini benar-benar terkirim (terverifikasi oleh kode yang
   sudah terbukti melaporkan gagal saat Telegram menolak).

## DoD 1 — Laporan mingguan (LULUS, setelah perbaikan)

- Siklus W48 menghasilkan 3 usulan dengan backtest otomatis tercatat di
  `backtest_runs`: P1 `w47-p1-lb-minsl5` GAGAL, P2 `w47-p2-mr-numstd3` GAGAL,
  P3 `w47-p3-mlgbm-paper` LULUS semua kriteria.
- Pengiriman diverifikasi ulang dengan menjalankan unit systemd yang sama
  dengan yang akan dipicu timer mingguan. CATATAN: pengiriman pertama
  (worker, 19:43) dan verifikasi pertama (23:02) ternyata GAGAL diam-diam
  karena dua bug di atas; setelah keduanya diperbaiki, siklus diulang
  23:17 dan laporan benar-benar diterima Telegram owner (`sent: true`
  pada kode yang terbukti melaporkan gagal saat pengiriman ditolak).
- Timer aktif, next Senin 30 Nov 2026 07:30 WIB; unit service teruji jalan
  (exit 0) dari jalur penjadwal, bukan lagi dari tangan worker.

## DoD 2 — Alur approve end-to-end (BELUM; blokir gerbang)

Yang sudah ada:

- Kode + test lengkap: endpoint UI/HTTP (`GET /improve/proposals`,
  `POST /improve/proposals/{id}/decision`; admin + CSRF + 2FA step-up +
  username == `settings.owner_username`) dan perintah Telegram
  (`/proposals`, `/approve`, `/reject`; hanya `TELEGRAM_OWNER_ID`).
  57 test alur approve lulus; matriks penolakan non-owner terverifikasi.
- Kandidat tunggal untuk approve: `w47-p3-mlgbm-paper` (ML LightGBM v1.0.0
  registrasi paper), LULUS semua kriteria: net +256.50 USD, PF 1.31,
  DD 2%, 51 trade, 3/18 window PF<1.

Yang menghalangi (semua di luar wewenang koordinator):

1. **Keputusan owner belum ada** (garis merah PRD §5.9: hanya owner boleh
   memutuskan; koordinator/agent dilarang memutuskan atau mengisi baris
   approval secara langsung).
2. **2FA akun owner (`admin`) belum aktif** (`totp_enabled=false`):
   `require_2fa` pasti 403. Owner perlu enroll dulu: login →
   `POST /auth/2fa/setup` → `POST /auth/2fa/enable` →
   `POST /auth/2fa/challenge` → baru keputusan.
3. **Seksi UI approve/reject belum dibangun** (kartu `t_6252ca2d`, status
   ready, hf-frontend). Sementara itu jalurnya HTTP/curl.
4. **Jalur Telegram butuh bot dedicated**: poller perintah sengaja OFF
   (`TELEGRAM_POLLER_OFF=1`) karena token bot di host ini dipakai Hermes
   gateway (getUpdates bersamaan = 409). Butuh keputusan owner membuat bot
   via @BotFather (tertunda sejak P1B3).

Jalur tert cepat setelah keputusan owner: enroll 2FA → challenge →
`POST /improve/proposals/w47-p3-mlgbm-paper/decision` dengan
`{"decision": "APPROVED", "rationale": "..."}`. Deploy otomatis tercatat
append-only (`strategy_approvals`, `deployment_records`, settings audit).

## DoD 3 — Garis merah (LULUS)

Pentest ulang 23 Nov 23:01 WIB terhadap fund2-api live (persona LLM/anon
tanpa kredensial fund2):

- Anon: 401 di semua endpoint sensitif: `/orders` (POST/GET),
  `/positions`, `/stream`, `/kill-switch` (semua aksi), `/strategies/*/mode`,
  `/bridge/*`, `/improve/*`.
- Cookie/bearer/HMAC palsu: 401. Sesi valid tanpa CSRF: 403.
  Admin valid tanpa 2FA: 403 (release, flatten, triggers, mode).
- Lockout berantai (401×5 lalu 429), IP rate limit 429, replay nonce HMAC
  401 (baseline HMAC valid 200).
- 1 "GAGAL" pada skrip = assertion internal hitung user (harap 5, aktual 4)
  karena user `llm-agent` tidak pernah dibuat; artefak skrip, bukan temuan
  keamanan. Detail: `docs/qa_security_v22_attempts.json`.

Catatan di luar lingkup P4: `fund2-llm-agent` gagal login berulang
(LOGIN_FAILED tiap ±5 menit di `audit_log`, sesekali ter-lock) karena user
`llm-agent` tidak ada di tabel users — layak dicek pemilik kartu v2.2 LLM.

## Status gerbang

DoD 1 dan 3 lulus; DoD 2 menunggu keputusan owner. Kartu gerbang diblokir
`needs_input`; anak-anak P5 tetap tertahan sesuai PRD §12 (fase tidak
lanjut sebelum DoD lulus). Setelah approve/reject tereksekusi dan deploy
tercatat, gerbang diverifikasi ulang lalu ditutup.
