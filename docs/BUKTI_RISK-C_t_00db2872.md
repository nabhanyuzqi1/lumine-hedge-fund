# Bukti RISK-C (t_00db2872) — fib tool + keputusan descope partial close

Tanggal: 26 Nov 2026 (WIB). Assignee: hf-backend. Parent: RISK-D (t_a172bb7b).

## Ringkasan

| Item DoD | Status | Bukti |
| --- | --- | --- |
| Probe EA partial close terdokumentasi + keputusan | SELESAI, keputusan **DESCOPE** partial close | `docs/PROBE_PARTIAL_CLOSE_t_00db2872.md` (5 blok bukti, line-referenced) + tripwire test 3 kasus |
| Partial close deterministic + flag + audit + test | TIDAK DIKERJAKAN (descope sesuai instruksi kartu) | prasyarat desain di dokumen probe bagian akhir |
| Fib tool: level benar matematis, tidak mengubah trading | SELESAI backend (matematika + API + penyimpanan + konteks LLM); overlay UI = kartu anak t_6175d3a6 (hf-frontend, gated UI-D5) | `api/app/fib_levels.py` + `api/tests/test_fib_levels.py` (25 test) |
| Full pytest + build hijau | lihat bagian Hasil test di bawah | log di kartu |

## Keputusan TAHAP 0

Partial close TP1/TP2/TP3 **didescope**. Tiga alasan teknis yang saling menguatkan:

1. EA `LumineEA.mq5` v5.03 yang berjalan (md5 source repo == source di folder
   Experts MT5, heartbeat EA aktif) menutup **seluruh** volume posisi:
   `ExecuteClose()` memakai `PositionGetDouble(POSITION_VOLUME)` dan
   `ProcessCommand()` tidak meneruskan field `volume` ke cabang CLOSE.
2. Bridge/reconciler menandai posisi `CLOSED` untuk **setiap** result CLOSE
   FILLED, dan tabel `positions` tidak punya ledger volume sisa. Partial close
   dengan kode hari ini = DB bilang tutup, broker masih pegang sisa, trailing
   RISK-B berhenti mengawal posisi nyata.
3. Batas lot broker 0.01/0.01/0.10 (XAUUSD & BTCUSD): ladder 50/30/20 tidak
   feasible untuk posisi 0.01-0.02 lot, jadi aturan pembulatan harus bagian
   desain, bukan detail.

Keputusan dicatat ke Director di kartu sumber t_ca307d2d (komentar, 26 Nov 2026).
Tripwire `api/tests/test_ea_partial_close_capability.py` akan gagal begitu EA
sungguh mendukung partial close, memaksa probe dibuka ulang sebelum fitur
diaktifkan.

## Yang dibangun (fib tool)

### Matematika (`api/app/fib_levels.py`, modul murni, tanpa I/O)

- Retracement `0.236 / 0.382 / 0.5 / 0.618 / 0.786` (fraksi **mundur** dari ujung swing):
  `UP: high - range*r`, `DOWN: low + range*r`.
- Extension `1.272 / 1.618 / 2.618` (kelanjutan melewati ujung swing):
  `UP: low + range*x`, `DOWN: high - range*x`.
- Contoh terverifikasi test (XAUUSD low 2000 high 2100): UP 0.618 = 2038.20,
  1.272 = 2127.20, 1.618 = 2161.80, 2.618 = 2261.80; DOWN 0.618 = 2061.80,
  1.272 = 1972.80.
- Pembulatan `digits` diturunkan dari `symbol_specs[symbol].tick_size`
  (XAUUSD/BTCUSD = 0.01 -> 2 desimal), fallback 2 bila spec hilang.
- Validasi fail-closed: harga berhingga, `swing_high > swing_low`, direction
  `UP|DOWN`, digits 0..8 → selain itu `FibLevelError` (HTTP 400).
- Modul hanya mengimpor `math` (dikunci test), jadi tidak bisa menyentuh jalur
  order/gate/trailing.

### API (`api/app/fib_routes.py`)

| Endpoint | Akses | Catatan |
| --- | --- | --- |
| `GET /chart/fib/preview` | sesi login | hitung level tanpa tulis DB (preview saat drag) |
| `GET /chart/fib/zones` | sesi login | daftar swing tersimpan (filter symbol + TF opsional) |
| `POST /chart/fib/zones` | CSRF + role admin/user | level dihitung server (bukan kiriman client), audit `FIB_ZONE_CREATED`, retensi maks 50/TF |
| `DELETE /chart/fib/zones/{id}` | CSRF + role admin/user | pembuat atau admin; audit `FIB_ZONE_DELETED` |

- Whitelist simbol/timeframe = `XAUUSD`/`BTCUSD`, `M1`/`M5`/`M15` (sama dengan `/candles`).
- Kredensial `agent`/`research`/`qa` read-only untuk mutasi (postur sama dengan
  endpoint kontrol lain); baca terbuka untuk semua sesi login.
- Respons selalu membawa `informational_only: true`.

### Skema (`api/alembic/versions/n014_fib_levels.py`)

Tabel `fib_levels`: `symbol, timeframe, direction, swing_low, swing_high,
levels JSONB, note, created_by, created_at` + CHECK `swing_high > swing_low` +
index `(symbol, timeframe, created_at DESC)`. `levels` disimpan sebagai snapshot
hasil hitung server supaya level yang pernah dipakai chart/LLM tetap auditable
walau konstanta berubah kelak.

Migrasi `n014` **sudah diterapkan ke DB live** (`alembic upgrade head`:
`m013 -> n014`; `alembic_version = n014`, tabel 10 kolom, 0 baris). Restart
service API belum dilakukan: worktree bersama sedang berisi editan belum-commit
milik worker lain, dan restart akan mengaktifkan kode mereka (lihat skill
deploy). Route menyala pada restart API berikutnya; UI chart-nya sendiri belum
ada (gated UI-D5).

### Konteks LLM (`api/app/llm_agent_loop.py`)

- Per simbol, `fib_zones` = maks 2 swing terbaru (blok opsional).
- Isi: timeframe, direction, swing_low, swing_high, levels, created_at.
  Kolom `note` **tidak pernah** diambil (teks bebas user = permukaan injeksi;
  dikunci test `test_llm_context_includes_fib_zones_without_note`).
- Pembacaan dibungkus savepoint: tabel hilang/rusak -> `fib_zones: []`, siklus
  agent tetap jalan, koneksi tidak teracuni (dikunci test rename-table).
- SYSTEM_PROMPT menambah paragraf tegas: level fib = alat bantu, bukan sinyal
  wajib, bukan bagian gate risk, dilarang mengarang level.

## Hasil test

- `tests/test_fib_levels.py` (26 test: matematika, API/CSRF/RBAC/retensi, konteks
  LLM) + `tests/test_ea_partial_close_capability.py` (3 tripwire) = **29 passed**.
- Subset LLM `test_llm_agent.py, test_llm_agent_context_extras.py, test_llm_risk.py,
  test_llm_introspection.py` di **pristine HEAD + patch saya**: **66 passed**.
- Full suite **pristine HEAD (5c081b8) + patch saya**: **1487 passed, 0 failed**
  (16m18s). Ini otoritas: perubahan saya berdiri sendiri tanpa bergantung pada
  file belum-commit milik worker lain.
- Full suite **shared tree** (HEAD c0106e8 milik kartu t_2a1fbf01 + kode saya di
  worktree): **1519 passed, 1 failed** pada
  `test_llm_introspection.py::test_agent_loop_has_introspection_wiring`.
  Triage: file test itu milik kartu lain dan `app/llm_agent_loop.py` sedang
  diedit worker tersebut saat suite berjalan; test yang sama + seluruh file
  hijau saat dijalankan ulang (22 passed). Bukan dari perubahan saya.
- Replay **commit final ef26a00** (checkout bersih): 61 passed
  (`test_fib_levels` 26 + tripwire 3 + `test_llm_introspection` 22 +
  `test_llm_parallel_pipeline` 10 milik kartu tetangga).
- `npm run build` (frontend, tanpa perubahan dari kartu ini): hijau,
  `index-B6FAvHaj.js 526.40 kB`, `index-CAuBIgId.css 122.20 kB`.

Commit: **ef26a00** `feat(fib): tool level fibonacci chart + konteks LLM opsional
(RISK-C t_00db2872)`. Hunk `api/app/llm_agent_loop.py` (blok fib_zones + paragraf
prompt) terbawa lebih dulu ke commit c0106e8 kartu t_2a1fbf01 karena file itu
di-stage saat tree bersama berisi pekerjaan saya; isinya terverifikasi ada di
HEAD dan terverifikasi jalan di replay 1487 passed.

## Isolasi DB live

Snapshot read-only sebelum/sesudah pekerjaan (db `fund2`):
`positions = 251`, `orders = 1940`, `bridge_commands = 0` — tidak berubah.
Satu-satunya perubahan skema: tabel baru `fib_levels` (0 baris) via migrasi n014.

## Serahan / follow-up

- **t_6175d3a6** — `[RISK-C-UI]` overlay fib di chart candlestick (hf-frontend,
  gated t_33944f29 UI-D5), kontrak API + rumus + DoD lengkap di kartu.
- Bila partial close nanti dilanjutkan: prasyarat EA + ledger volume + flag +
  approval owner ada di `docs/PROBE_PARTIAL_CLOSE_t_00db2872.md` bagian akhir.
