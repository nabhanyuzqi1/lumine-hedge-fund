# Architecture Decision Records (ADR): Fund2 v2.2

Kartu: **t_f2v22a18** · Artefak Lampiran B butir "architecture diagram dan ADR" · Penyusun: hf-ceo
Tanggal: 26 Nov 2026 · Status kumpulan: **FINAL untuk rilis v2.2**

Format: satu keputusan per ADR, dengan konteks, keputusan, konsekuensi (positif dan negatif),
alternatif yang ditolak, dan bukti. ADR yang berstatus *Accepted* mengikat implementasi; mengubahnya
butuh ADR baru, bukan edit di tempat. Yang berstatus *Accepted with deviation* mencatat jarak antara
kontrak dan kenyataan, dan siapa yang harus menutupnya.

| ID | Judul | Status |
| --- | --- | --- |
| ADR-001 | PostgreSQL native di host, bukan container | Accepted |
| ADR-002 | Satu service FastAPI melayani API dan SPA | Accepted |
| ADR-003 | EA pull-based long-poll, antrean di tabel Postgres | Accepted |
| ADR-004 | Ledger append-only ditegakkan trigger DB | Accepted |
| ADR-005 | Risk gate deterministik murni + settings di DB | Accepted |
| ADR-006 | Auth: Argon2id + sesi cookie + CSRF + 2FA; bridge HMAC dengan fallback Bearer | Accepted with deviation |
| ADR-007 | LLM boleh memutuskan order, tetapi tidak pernah melewati risk gate | Accepted |
| ADR-008 | Edge proxy untuk Caddy docker, API tetap loopback | Accepted |
| ADR-009 | Siklus hidup strategi: versi immutable + approval + shadow→paper→live | Accepted |
| ADR-010 | Paper dan shadow runner terpisah, memakai `decide()` yang sama | Accepted |
| ADR-011 | Backup harian terenkripsi + restore drill ke instance terisolasi | Accepted |
| ADR-012 | Alembic satu-satunya sumber skema | Accepted |
| ADR-013 | Multipair XAUUSD + BTCUSD, parameter per simbol, limit agregat akun | Accepted |
| ADR-014 | Model chain LLM: primary relay dengan fallback `lucif → lucif-flash` | Accepted with deviation |
| ADR-015 | Satu host, tanpa HA, dengan RTO/RPO terukur | Accepted (risiko diterima owner) |

---

## ADR-001: PostgreSQL native di host, bukan container

**Konteks.** Iterasi awal memakai Docker untuk seluruh stack. Pada praktiknya, MT5 wajib berjalan di
Wine dengan akses terminal, dan DB harus tetap hidup ketika container runtime bermasalah.

**Keputusan.** PostgreSQL 16 dijalankan sebagai unit systemd (`fund2-postgres`) dengan PGDATA
`~/fund2/data/pg`, listen `127.0.0.1:5433`, binary dari `~/fund2/runtime/pg16`.

**Konsekuensi.**
- Positif: tidak ada lapisan container pada jalur data kritis; restart terkontrol systemd; backup
  `pg_dump` langsung ke filesystem host.
- Negatif: tidak ada image immutability; upgrade PG manual; dependensi host (user `tekka`, socket,
  permission direktori) menjadi bagian dari kontrak operasional.

**Alternatif ditolak.** Docker Compose untuk DB: menambah titik gagal pada host yang sama tanpa
keuntungan HA. Managed DB: menambah latensi dan biaya, serta keluar dari lingkup VPS tunggal.

**Bukti.** `systemctl --user status fund2-postgres`, `ps aux | grep pg16`, `ss -tlnp` port 5433,
kartu `t_749dcc90` (migrasi native penuh), `docs/DR_v2.2.md` §2.

---

## ADR-002: Satu service FastAPI melayani API dan SPA

**Keputusan.** `app.main` melayani REST, SSE, dan SPA build (`frontend/dist`) dari proses uvicorn
yang sama di `127.0.0.1:3110`.

**Konsekuensi.**
- Positif: satu origin (tidak ada CORS produksi), satu proses untuk di-restart, deploy frontend =
  ganti `dist` + restart API; tidak ada server statis terpisah yang bisa desinkron.
- Negatif: restart API juga memutus UI; build frontend harus dibuat sebelum deploy; cache-busting
  bergantung pada `index.html` yang dihasilkan Vite.

**Alternatif ditolak.** Nginx statis terpisah: dua artefak deploy yang harus sinkron, dan deviasi
origin. SSR: tidak perlu untuk dashboard internal.

**Bukti.** `api/app/main.py`, 65 path OpenAPI, `docs/ARTEFAK_RILIS_v2.2.md` §1 (frontend build),
`README.md` bagian Struktur.

---

## ADR-003: EA pull-based long-poll, antrean di tabel Postgres

**Konteks.** EA berjalan di MT5/Wine; koneksi masuk ke terminal tidak dapat diandalkan, dan broker
memutus koneksi saat maintenance. Push dari server ke EA (WebSocket) tidak bisa dijamin.

**Keputusan.** EA menarik perintah dengan `GET /bridge/poll?timeout_s=25` (long-poll). Antrean adalah
tabel `orders` (`status='SENT' AND delivered_at IS NULL`) dengan `FOR UPDATE SKIP LOCKED`; antrean
reconciler adalah `bridge_commands` (`status='QUEUED'`). Tidak ada Redis/broker pesan.

**Konsekuensi.**
- Positif: EA tidak butuh port terbuka; tidak ada state hilang saat broker disconnect; antrean bisa
  diaudit dengan SQL biasa; idempotensi hasil (`command_id`) mencegah duplikasi.
- Negatif: latensi T1→T2 ditentukan interval poll (diturunkan dari 0,25 s ke **0,05 s**, terukur
  p95 T0→T2 182,8 ms, n=207); satu EA = satu consumer (belum ada sharding); beban DB ~0,52 ms
  per iterasi poll.

**Alternatif ditolak.** Redis queue: komponen baru tanpa kebutuhan; kehilangan durability ledger.
WebSocket: tidak tahan reconnect MT5/Wine. Webhook broker: tidak tersedia.

**Bukti.** `api/app/bridge.py` (`BRIDGE_POLL_INTERVAL_S`, `SKIP LOCKED`), `qa_p5` rerun v11
(`docs/QA_P5_cutover.md` §2a), commit `40f9f09`.

---

## ADR-004: Ledger append-only ditegakkan trigger DB

**Keputusan.** Tabel `order_events`, `strategy_approvals`, `kill_switch_events`, `llm_introspections`,
dan `degradation_events` dipasangi trigger `fund2_deny_mutation()` yang menolak `UPDATE`/`DELETE`.
Aplikasi hanya boleh `INSERT`; koreksi dilakukan dengan baris baru.

**Konsekuensi.**
- Positif: audit dan rekonsiliasi tidak bisa "dirapikan" oleh bug aplikasi; bukti insiden tetap utuh.
- Negatif: pembersihan data uji harus menghapus seluruh rantai (atau memakai DB uji terpisah);
  penambahan kolom wajib lewat migrasi, tidak bisa backfill in-place pada baris lama.

**Alternatif ditolak.** Append-only sebagai konvensi kode: terbukti tidak cukup, karena satu query
manual bisa menghapus jejak.

**Bukti.** Trigger pada `DATA_DICTIONARY_v2.2.md` (`*_append_only`), `api/app/state_machine.py`,
PRD v2.2 §19.4, kartu `t_f2v22a11`.

---

## ADR-005: Risk gate deterministik murni + settings di DB

**Keputusan.** Risk gate adalah fungsi murni (`app/risk.py`, `app/portfolio_risk.py`) yang menerima
state + settings dan mengembalikan keputusan; parameter disimpan di tabel `settings` (JSONB) dan
`portfolio_risk`, bukan konstanta tersebar. Auto-halt menulis state persisten dan event audit.

**Konsekuensi.**
- Positif: bisa diuji unit tanpa DB; keputusan dapat direproduksi dari input yang tercatat di
  `risk_decisions`; angka risiko bisa diubah owner lewat UI dengan audit.
- Negatif: nilai di DB bisa melenceng dari nilai yang disetujui owner (terbukti: drift G-01..G-06 di
  `PRASYARAT_LIVE_v2.2.md` §3) sehingga perlu alat pembanding dan gate rilis.

**Bukti.** `api/app/risk.py`, `api/tests/test_risk.py`, `risk_decisions` di DB, `PRASYARAT_LIVE_v2.2.md` §3.

---

## ADR-006: Auth dan otorisasi (Accepted with deviation)

**Keputusan.**
- Dashboard: sesi cookie + token CSRF per sesi wajib pada semua mutasi; password **Argon2id**
  (hash bcrypt legacy diverifikasi lalu di-rehash); **2FA/TOTP** wajib untuk aksi berbahaya
  (kill-switch flatten, approval strategi).
- Bridge EA: **HMAC-SHA256** (header `X-Fund2-Timestamp/-Nonce/-Signature`, toleransi ±5 s, nonce
  sekali pakai) sesuai `ea/HMAC_CONTRACT.md`; **Bearer token** tetap diterima sebagai jalur legacy
  untuk harness latensi, simulator, dan test.

**Deviasi.** Kontrak awal menyebut HMAC sebagai satu-satunya jalur. Realisasinya dual-auth: HMAC
utama (EA v5.03), Bearer fallback. Risikonya terbatas karena API hanya bind loopback dan token Bearer
disimpan di `settings.bridge_token`; namun jalur Bearer tidak memiliki anti-replay.

**Penutup deviasi.** Hapus fallback Bearer untuk produksi live (atau batasi ke alamat loopback +
flag env) sebelum canary; tiket lanjutan milik hf-backend. Sampai itu selesai, deviasi dicatat di
`RELEASE_CHECKLIST_v2.2.md` sebagai non-kritis.

**Bukti.** `api/app/auth.py` (Argon2id, CSRF), `api/app/bridge.py` (`require_bridge_token`), `ea/HMAC_CONTRACT.md`,
`api/tests/test_totp.py`, `test_hmac_auth.py`, `test_security_v22.py`.

---

## ADR-007: LLM boleh memutuskan order, tetapi tidak pernah melewati risk gate

**Konteks.** Prinsip awal v2.1: LLM hanya riset, tidak memegang tombol order. Owner membalik keputusan
itu (KEPUTUSAN_OWNER §G G1: full LLM trading).

**Keputusan.** Agent LLM (`fund2-llm-agent`) boleh mengusulkan dan mengeksekusi order, dengan syarat:
(1) semua order melewati risk gate deterministik yang sama; (2) kill-switch/auto-halt menghentikan
agent; (3) setiap keputusan tercatat di `order_events` + `llm_introspections` beserta reasoning;
(4) gate paper 20 hari/100 trade dan approval live tetap berlaku; (5) injection guard untuk konten
tidak tepercaya; (6) budget LLM dibatasi dan dimonitor; (7) tidak ada secret di konteks LLM.

**Konsekuensi.**
- Positif: keputusan bisnis owner terpenuhi tanpa melepas kontrol risiko ke model.
- Negatif: permukaan serang baru (prompt injection, hallucination metrik, biaya LLM); butuh evaluasi
  gerbang sendiri; kualitas keputusan masih harus dibuktikan lewat paper trading.

**Bukti.** `docs/KEPUTUSAN_OWNER.md` §G, `api/app/llm_agent_loop.py`, `api/app/llm_risk.py`,
`docs/QA_F2LLM3_plan_uji_injection.md`, `docs/QA_F2LLM4_kriteria_gerbang.md`.

---

## ADR-008: Edge proxy untuk Caddy docker, API tetap loopback

**Konteks.** Caddy berjalan di container (jaringan bridge `172.19.0.1`) dan tidak bisa menjangkau
`127.0.0.1` host. PRD §7 melarang API terbuka ke publik karena EA menembak loopback.

**Keputusan.** Proses kecil `edge_proxy.py` (unit `fund2-edge-proxy`) meneruskan `172.19.0.1:3110` →
`127.0.0.1:3110` tanpa logika tambahan. API tetap bind loopback.

**Konsekuensi.**
- Positif: bind API tidak berubah; tidak ada port publik baru; proxy tidak menyimpan state.
- Negatif: satu komponen tambahan pada jalur UI; harus ikut di-restart saat perubahan jaringan docker.

**Bukti.** `edge_proxy.py` (docstring), unit `fund2-edge-proxy.service`, `ss -tlnp`.

---

## ADR-009: Siklus hidup strategi: versi immutable + approval + gate promosi

**Keputusan.** Strategi punya `strategy_versions` immutable (artefak + params hash + commit), alur
submit → review → approve (`strategy_approvals`, append-only), aktivasi versi, dan rollback ke versi
sebelumnya. Promosi mode mengikuti gate terukur (shadow → paper → live), bukan keputusan ad-hoc.

**Konsekuensi.**
- Positif: setiap perubahan strategi dapat diaudit dan dikembalikan; tidak ada "edit di tempat".
- Negatif: alur lebih panjang; butuh disiplin approval; rollback harus diuji (drill aplikasi penuh
  masih terbuka, lihat `CHECKLIST_ROLLBACK_v2.2.md`).

**Bukti.** `api/app/strategies/`, `api/tests/test_strategies_api.py`, 65 path OpenAPI
(`/strategies/{id}/versions/...`), `docs/RELEASE_CHECKLIST_v2.2.md`.

---

## ADR-010: Paper dan shadow runner terpisah, `decide()` sama

**Keputusan.** `paper.runner` dan `shadow.runner` adalah dua proses terpisah yang memanggil logika
`decide()` yang sama dengan mode berbeda; hasil ditulis ke ledger masing-masing (`paper_orders`,
`shadow_signals`) dengan konfigurasi, provenance data, commit hash, dan seed.

**Konsekuensi.**
- Positif: paritas perilaku bisa diuji (QA paritas v1 vs v2 dan backtest vs paper); kegagalan runner
  tidak memengaruhi API; shadow bisa berjalan tanpa order.
- Negatif: dua runner harus dipantau; hasil tidak otomatis naik ke live tanpa gate.

**Bukti.** Unit `fund2-paper-runner`, `fund2-shadow-runner`, tabel `paper_orders`/`shadow_signals`,
`docs/QA_P2_paritas.md`, `docs/QA_shadow_t_f2v22a4.md`.

---

## ADR-011: Backup harian terenkripsi + restore drill terisolasi

**Keputusan.** Backup harian 04:30 UTC: `pg_dump -Fc` + globals + config non-secret + parquet → tar →
age → `manifest.tsv` (sha256) → upload offsite. Restore drill memakai instance PostgreSQL terpisah
(port 5599, DB `fund2_drill`) dengan 8 tahap verifikasi, tidak menyentuh produksi.

**Konsekuensi.**
- Positif: backup terbukti dapat di-restore (3/3 drill LULUS), RPO 24 jam, RTO aplikasi terukur ~21 s.
- Negatif: RPO 24 jam berarti kehilangan data hingga sehari; drill tidak mencakup recovery host/OS;
  offsite pernah melaporkan `size mismatch` (verifikasi manual, lihat `RELEASE_NOTES_v2.2.md` §4).

**Bukti.** `scripts/fund2_backup.sh`, `scripts/fund2_restore_drill.sh`, `docs/DR_v2.2.md` §3-§4,
`~/fund2-backups/manifest.tsv` + `logs/backup-20261125T043315Z.json` (offsite=1, 122.418.552 bytes).

---

## ADR-012: Alembic satu-satunya sumber skema

**Keputusan.** Skema dikelola migrasi Alembic (`api/alembic/versions/`), dijalankan otomatis saat
startup (`app/db.py::apply_schema`). `schema.sql` dihapus; migrasi wajib idempotent dan mencatat
perubahan ke `deployment_records`.

**Konsekuensi.**
- Positif: DB dev/staging/produksi dapat disamakan (saat ini `l012` di keduanya); riwayat perubahan
  terbaca; review skema = review diff migrasi.
- Negatif: startup API menanggung waktu migrasi; migrasi yang salah bisa mengunci deploy; butuh
  disiplin satu kepala migrasi (head tunggal).

**Bukti.** `alembic_version = l012`, `docs/SCHEMA_v2.2.md` ("Kanon skema"), `api/tests/test_migrations.py`.

---

## ADR-013: Multipair XAUUSD + BTCUSD, parameter per simbol

**Konteks.** Owner memutuskan dukungan BTCUSD agar pengujian/trading bisa jalan saat XAUUSD tutup
(KEPUTUSAN_OWNER §F F1).

**Keputusan.** Parameter jarak/spread/lot menjadi per simbol (`symbol_specs` di settings); limit
eksposur total dan order-per-menit tetap agregat level akun. Instrument live utama tetap XAUUSD.

**Konsekuensi.**
- Positif: cakupan waktu lebih luas; tidak ada risiko "jarak absolut" yang salah skala antar simbol
  (kasus EMERGENCY_SL: 15 USD = 0,42% XAUUSD tapi 0,025% BTCUSD).
- Negatif: dua contract spec harus dikalibrasi terpisah; biaya BTC berbeda; QA multipair menambah
  beban uji.

**Bukti.** `docs/KEPUTUSAN_OWNER.md` §F, `docs/KALIBRASI_BTCUSD.md`, `docs/QA_MP5.md`,
kode `_emergency_sl_distance()` (`api/app/bridge.py`), kartu `t_f2mp1..t_f2mp5`.

---

## ADR-014: Model chain LLM (Accepted with deviation)

**Keputusan.** Profil agent memakai primary model relay dengan rantai fallback berurutan
`lucif → lucif-flash`; urutan disimpan di config profil, bukan hardcode. Fallback hanya untuk
kegagalan teknis (timeout/429/5xx/koneksi/auth), tidak pernah karena jawaban tidak disukai.

**Deviasi.** Spesifikasi owner (primary berbeda per role) belum bisa dijalankan karena relay memakai
1 key = 1 model pin dan membatasi rotasi 1x/10 jam; konfigurasi live memakai mode `shared` dengan
primary tunggal. Penutup: terapkan mode `full` saat relay membebaskan multi-model
(`scripts/apply_model_chain.py --mode full`).

**Konsekuensi.** Positif: agent tetap hidup saat relay habis (transisi ke lucif). Negatif: semua role
berbagi model yang sama sampai kendala relay hilang.

**Bukti.** `docs/MODEL_CHAIN.md`, `scripts/apply_model_chain.py`, `~/.hermes/profiles/hf-*/config.yaml`.

---

## ADR-015: Satu host, tanpa HA, dengan RTO/RPO terukur

**Keputusan.** Rilis v2.2 berjalan di satu VPS (`tekka`: 6 vCPU, 7,8 GB RAM, swap file 4 GB yang
terpakai 1,5 GB saat pemeriksaan; GNOME, Xorg, AnyDesk, dan Hermes ikut memakai resource). Tidak ada replika DB atau failover broker. RTO aplikasi
diukur (~21 s untuk DB+API) dan RPO 24 jam diterima sebagai konsekuensi.

**Konsekuensi.**
- Positif: sederhana, murah, satu tempat untuk debugging; performa cukup untuk 1 EA dan 1 strategi.
- Negatif: host mati = trading berhenti; tidak ada HA; memori ketat (5,1 GB terpakai dari 7,8 GB dan
  swap sudah terpakai 1,5 GB) sehingga OOM masih bisa membunuh proses; VPS ini bukan host produksi
  bersih (ada desktop stack).
- Mitigasi wajib sebelum live: host produksi bersih, swap atau monitoring memori, dan drill recovery
  host. Sampai itu selesai, rekomendasi tertulis adalah **jangan live di host ini**.

**Bukti.** `docs/DR_v2.2.md` §4, `docs/ARCHITECTURE_v2.2.md` §8, pemeriksaan `free -h`/`nproc` di host.

---

## Cara menambah ADR

1. Nomor baru berurutan; jangan menulis ulang ADR lama.
2. Isi: konteks, keputusan, konsekuensi (positif, negatif), alternatif ditolak, bukti.
3. Status: `Proposed` → `Accepted` / `Rejected` / `Superseded by ADR-xxx`.
4. Perubahan yang membatalkan ADR lama wajib menyebut ADR yang digantikan.
5. Review minimal: pemilik komponen + QA untuk yang menyentuh jalur order.

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-ceo | 26 Nov 2026 | Kartu `t_f2v22a18`, 15 ADR |
| Review teknis | hf-devops / hf-backend | menunggu | ADR-001, 003, 006, 011, 015 |
| Review QA | hf-qa | menunggu | ADR-004, 005, 009, 010 |
