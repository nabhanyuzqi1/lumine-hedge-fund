# API & EA Protocol Specification: Fund2 v2.2

Kartu: **t_f2v22a18** · Artefak wajib Lampiran B ("data dictionary dan API/EA protocol spec") ·
Penyusun: hf-ceo · Tanggal: 26 Nov 2026 · Status: **FINAL untuk rilis v2.2**
Turunan langsung dari kode berjalan: 65 path OpenAPI (`app.openapi()["paths"]`), model Pydantic
`api/app/bridge.py`, state machine `api/app/state_machine.py`, dan `ea/HMAC_CONTRACT.md`.
Versi EA acuan: **`LumineEA.mq5` v5.03** (`#property version "5.03"`). Versi schema didukung:
`{"v5","5","v0","0"}` (`api/app/validate.py::SUPPORTED_SCHEMA_VERSIONS`).

## 1. Konvensi umum

| Aspek | Aturan |
| --- | --- |
| Base URL EA | `http://127.0.0.1:3110` (loopback host; WAJIB, PRD §7) |
| Base URL UI | `https://<domain>` → Caddy 443 → edge proxy `172.19.0.1:3110` → API |
| Format | JSON UTF-8; angka harga `float`, volume `float`, id `string` (UUID) |
| Error | `{"detail": "<pesan>"}` dengan status HTTP yang sesuai (FastAPI) |
| Auth UI | Cookie sesi `HttpOnly` + `SameSite`; header `x-csrf-token` wajib pada semua mutasi |
| Auth EA | HMAC-SHA256 (utama) atau Bearer (legacy, lihat §4) |
| Auth agent LLM | Login sesi sebagai user role `agent`; kontrol (kill-switch/approval) ditolak untuk role ini |
| Role | `admin` (owner/operator), `qa` (order uji terpisah dari P&L), `agent` (order LLM, tanpa kontrol) |
| Idempotensi | `/bridge/result` idempoten per `command_id`; `POST /orders` tidak idempoten (setiap panggilan = order baru) |
| Audit | Setiap mutasi order/kontrol menulis `order_events` + `audit_log`; tidak ada jalur tulis tanpa jejak |

## 2. Peta endpoint (65 path)

| Kelompok | Path | Keterangan |
| --- | --- | --- |
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/2fa/setup`, `POST /auth/2fa/enable`, `POST /auth/2fa/disable`, `POST /auth/2fa/challenge`, `GET /auth/sessions`, `POST /auth/sessions/revoke-all` | Sesi, CSRF, TOTP |
| Order & posisi | `GET,POST /orders`, `GET /orders/{order_id}`, `GET /positions` | Order manual, detail + events, snapshot DB |
| Bridge EA | `GET /bridge/poll`, `POST /bridge/result`, `POST /bridge/tick`, `POST /bridge/positions`, `POST /bridge/heartbeat` | Kontrak EA §4 |
| Kill switch | `GET,POST /kill-switch`, `POST /kill-switch/flatten`, `POST /kill-switch/release`, `PUT /kill-switch/triggers` | Mode, flatten manual, release, ambang auto |
| Strategi | `GET /strategies`, `GET /strategies/lifecycle-summary`, `GET /strategies/degradation`, `GET /strategies/supervisor`, `POST /strategies/{id}/mode`, `POST /strategies/{id}/lifecycle`, `POST /strategies/{id}/rollback`, `GET,POST /strategies/{id}/versions`, `GET /strategies/{id}/versions/{v}`, `POST /strategies/{id}/versions/{v}/submit|review|activate|artifacts`, `GET /strategies/{id}/approvals`, `GET|POST /strategies/{id}/degradation*`, `GET /strategies/{id}/supervisor/events` | Versi immutable + approval + degradasi |
| LLM agent | `GET /llm-agent/status`, `GET /llm-agent/config`, `POST /llm-agent/cycle`, `POST /llm-agent/close`, `POST /llm-agent/modify`, `POST /llm-agent/resume`, `GET,POST /llm-agent/decisions`, `POST /llm-agent/introspect`, `GET /llm-agent/introspection` | Keputusan, breaker, introspeksi |
| Riset & self-improve | `GET /research/reports`, `GET /research/proposals`, `POST /research/proposals/{id}/decision`, `POST /research/proposals/{id}/deployed`, `GET /research/tools`, `POST /research/tools/{name}`, `GET /improve/proposals`, `POST /improve/proposals/{id}/decision` | Hermes read-only + approval |
| Pasar & regime | `GET /candles`, `GET /regime/current` | Chart + label regime |
| Risiko | `GET /risk/portfolio` | Eksposur agregat + stress test |
| Shadow | `GET /shadow/runs`, `GET /shadow/runs/{id}/signals` | Hasil sinyal shadow |
| Operasional | `GET /health`, `GET /metrics`, `GET /audit`, `GET /alerts/active`, `GET /stream` (SSE) | Health, metrik, audit, alert, event live |

SSE `/stream` mengirim event bertipe: `tick`, `order`, `positions`, `halt`, `kill_switch`, `orphan`,
`flatten`, `strategy_mode`, `strategy_lifecycle`, `agent_close`, `auto_sl_modify`.

## 3. Kontrak order (jalur UI/API)

`POST /orders` body:

```json
{"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "sl": 4012.50, "tp": 4025.00}
```

- `sl` **wajib** (A1). Tanpa SL → order tetap dicatat lalu `FAILED` dengan reason manusiawi.
- Validasi berlapis: schema (422) → risk gate deterministik (`RECEIVED → RISK_PASS` atau `FAILED`) →
  worker claim (`RISK_PASS → SENT`) → hasil EA (`SENT → FILLED|FAILED|STUCK`).
- Penolakan risk gate menyebut satu alasan terbaca (contoh: `spread 0,71 > max 0,50`,
  `tick age 12,4s > 3s`, `kill switch aktif: STOP_NEW_ORDERS`). Alasan tidak pernah berupa objek mentah
  (fix AUDIT-B, commit `1f6c390`).
- Respons sukses memuat `id`, `command_id`, `status`; status akhir diambil dari `GET /orders/{id}`.

## 4. Kontrak EA (TB4)

### 4.1 Autentikasi

**Utama: HMAC-SHA256** (spesifikasi lengkap di `ea/HMAC_CONTRACT.md`):

| Header | Isi |
| --- | --- |
| `X-Fund2-Timestamp` | unix epoch detik; toleransi server ±5 s |
| `X-Fund2-Nonce` | hex 8-64 char, sekali pakai (TTL 11 s, cache dibersihkan lazy > 4096 entri) |
| `X-Fund2-Signature` | hex lowercase `HMAC-SHA256(secret, ts \n nonce \n METHOD \n path-with-query \n sha256_hex(body))` |

Urutan verifikasi: header lengkap (401) → timestamp dalam toleransi (401) → nonce belum dipakai (401)
→ signature cocok dengan `compare_digest` (401). Secret: env `FUND2_HMAC_SECRET` di server, file
`MQL5/Files/fund2_hmac.secret` di EA (diisi out-of-band, bukan input chart).

**Legacy: `Authorization: Bearer <settings.bridge_token>`** diterima untuk harness latensi, simulator,
dan test. Jalur ini **tidak** memiliki anti-replay; lihat ADR-006 dan RR-2 di
`THREAT_MODEL_v2.2.md` (penutup sebelum canary).

### 4.2 `GET /bridge/poll?timeout_s=25`

Long-poll untuk satu command. Server memindai `orders` berstatus `SENT` dan `delivered_at IS NULL`
(`FOR UPDATE SKIP LOCKED`, urut `sent_at`), lalu antrean reconciler `bridge_commands` berstatus
`QUEUED`. Command yang diserahkan ditandai `delivered_at=now()`.

- `timeout_s`: default 25, di-clamp 0..30 (`BRIDGE_POLL_MAX_S`). Interval pemindaian internal 0,05 s.
- Respons command order:

```json
{"command_id":"<uuid>","order_id":"<uuid>","symbol":"XAUUSD","side":"BUY",
 "volume":0.01,"sl":4012.5,"tp":4025.0}
```

- Order penutupan menambah `{"action":"CLOSE","ticket":"123456"}`.
- Command reconciler: `{"command_id":"<id>","action":"MODIFY_SL","ticket":"...","sl":...,"tp":...}`.
- Tidak ada command sampai deadline → body `null` (EA langsung poll lagi).

### 4.3 `POST /bridge/result`

```json
{"command_id":"<uuid>","status":"FILLED","ticket":123456,"price":4013.2,"profit":0.0,"reason":null}
```

- `status` hanya `FILLED` atau `FAILED` (selain itu 422).
- `command_id` dicari di `orders`; bila tidak ada, dicari di `bridge_commands` (hasil `MODIFY_SL`);
  tidak ada di keduanya → 404 `unknown command_id`.
- Idempoten: hasil kedua untuk command yang sudah terminal mengembalikan
  `{"ok":true,"duplicate":true,"status":"<status>"}` tanpa menulis event baru.
- Transisi divalidasi `ALLOWED_TRANSITIONS`; transisi tidak sah ditolak, tidak dipaksa.
- Order CLOSE yang FILLED menutup order induk sesuai `CLOSE_OWNER_TARGETS`
  (`FILLED→FILLED_THEN_CLOSED`, `STUCK→FILLED_THEN_CLOSED`, `ORPHAN_ADOPTED→ORPHAN_CLOSED`).

### 4.4 `POST /bridge/tick` (batch 250 ms)

```json
{"symbol":"XAUUSD","schema_version":"v5",
 "ticks":[{"ts":1795630000123,"bid":4012.4,"ask":4012.9,"spread":0.5}],
 "candles":[{"symbol":"XAUUSD","timeframe":"M1","ts":"2026-11-25T18:00:00Z",
             "open":4012.0,"high":4013.0,"low":4011.5,"close":4012.6,"volume":120}]}
```

- `schema_version` tidak didukung → 422 dengan daftar versi yang didukung.
- Setiap tick divalidasi (timestamp di masa depan, harga tidak masuk akal, dsb). Tick yang ditolak
  **tidak** masuk market store, pipeline, maupun SSE; jumlahnya dilaporkan.
- Respons: `{"ok":true,"ticks":<diterima>,"rejected":<ditolak>,"flagged":<peringatan>}`.
- Endpoint ini **tidak menulis DB**; tick → ring buffer memori → parquet (flush 60 s) + agregat
  likuiditas 5 s + upsert candle di background. Backpressure hanya membuang sampel likuiditas,
  tidak pernah memblokir jalur order.
- Kontrak legacy EA v0 (single `bid`/`ask`) masih diterima; `candle`-only sah (seed history).

### 4.5 `POST /bridge/positions` (snapshot 5 s + saat reconnect)

```json
{"positions":[{"ticket":123456,"order_id":"<uuid>","symbol":"XAUUSD","side":"BUY","volume":0.01,
               "open_price":4012.4,"sl":4007.0,"tp":4025.0,"profit":-1.2,"status":"OPEN","raw":{}}],
 "deals":[{"ticket":9001,"position_id":123456,"symbol":"XAUUSD","volume":0.01,
           "price":4020.0,"profit":7.6,"time":"2026-11-25T17:59:00Z","entry":"OUT"}]}
```

Perilaku reconciler (PRD §5.8): posisi broker tanpa order DB → `ORPHAN_ADOPTED` (+ SL darurat bila
belum ada, notifikasi owner); posisi DB tanpa broker + ada deal penutup → `FILLED_THEN_CLOSED`,
tanpa deal → `FAILED`; tidak terjelaskan → kill-switch + alert; semua tercatat di `order_events`.
`order_id` non-UUID (comment broker terpotong ~31 char) dibuang dari kolom, disimpan di `raw` dan
dilog, posisi tetap ter-link lewat `ticket`.

### 4.6 `POST /bridge/heartbeat` (2 s)

```json
{"ts":1795630000,"symbol":"XAUUSD","bid":4012.4,"ask":4012.9,"ea":"5.03","schema_version":"v5"}
```

Menandai EA terlihat untuk monitor offline; tidak menulis tick dan tidak menyentuh DB kecuali
throttled persist `ea_last_seen_at`. Respons `{"ok":true,"ts":...}`.

## 5. Batas waktu dan angka kontrak

| Parameter | Nilai | Sumber |
| --- | --- | --- |
| Poll long timeout | maksimum 30 s | `config.BRIDGE_POLL_MAX_S` |
| Interval pemindaian poll | 50 ms | `bridge.BRIDGE_POLL_INTERVAL_S` |
| Batch tick | 250 ms | EA v5 / PRD §5.1 |
| Heartbeat | 2 s; 3 terlewat (6 s) = EA OFFLINE | KEPUTUSAN_OWNER A12 |
| Snapshot posisi | 5 s dan saat reconnect | PRD §5.8 |
| Toleransi jam HMAC | ±5 s, nonce TTL 11 s | `bridge.HMAC_TS_TOLERANCE_S` |
| Order `SENT` tanpa konfirmasi | 60 s → `STUCK` | reconciler / PRD §5.8 |
| Tick basi ditolak | `tick_age_s > 3` (settings `max_tick_age_s`, default 3.0) | `risk.py` baris 256-260, A10 |
| SLO T0→T2 | p95 < 300 ms (terukur 182,8 ms, n=207) | `QA_P5_cutover.md` §2a |
| Retensi sesi | 24 jam (`SESSION_TTL_HOURS`) | `config.py` |

## 6. Kode status yang dipakai

| HTTP | Kapan | Contoh body |
| --- | --- | --- |
| 200 | sukses, termasuk duplicate result | `{"ok":true,"duplicate":true,"status":"FILLED"}` |
| 401 | auth gagal (sesi/HMAC/Bearer), `detail` spesifik | `{"detail":"nonce replayed"}` |
| 403 | role tidak berhak (agent mencoba kontrol) | `{"detail":"admin role required ..."}` |
| 404 | order/command/proposal tidak ada | `{"detail":"unknown command_id"}` |
| 409 | konflik state (mis. versi strategi sudah aktif) | `{"detail":"..."}` |
| 422 | schema request tidak valid / versi schema tidak didukung | `{"detail":"status must be FILLED or FAILED"}` |
| 429 | rate limit (login, aksi sensitif) | `detail` menyebut waktu tunggu, mis. `account temporarily locked; retry in ~15 min` |

## 7. Kompatibilitas dan perubahan kontrak

- Perubahan field **aditif** boleh dilakukan dalam versi minor; EA wajib mengabaikan field tak dikenal.
- Perubahan yang memutus (rename/hapus field, ubah arti status) wajib menaikkan `schema_version`
  dan didaftarkan di `SUPPORTED_SCHEMA_VERSIONS` dengan masa transisi minimal satu rilis.
- EA mengirim `schema_version` pada `/bridge/tick` dan `/bridge/heartbeat`; server menolak versi yang
  tidak dikenal (fail-closed), tidak menebak.
- Semua perubahan kontrak dicatat di `RELEASE_NOTES_v2.2.md` dan diuji
  `api/tests/test_bridge.py` (termasuk roundtrip command) + `test_hmac_auth.py`.

## 8. Klien selain EA

| Klien | Cara autentikasi | Catatan |
| --- | --- | --- |
| UI dashboard | cookie + CSRF | SSE `/stream` butuh sesi |
| Agent LLM (`fund2-llm-agent`) | login sesi role `agent` ke `LLM_API_BASE` (default `http://127.0.0.1:3110`) lalu `POST /orders` | Risk gate penuh tetap di API; kontrol ditolak untuk role agent |
| QA driver | user role `qa` | Order QA dikecualikan dari P&L/drawdown nyata |
| Harness latensi | Bearer bridge token | Hanya endpoint `/bridge/*` |
| Script ops | user admin + CSRF | Backup, drill, verifikasi read-only |

## 9. Verifikasi

```bash
cd ~/fund2/api
.venv/bin/python -c "from app.main import app; print(len(app.openapi()['paths']))"   # 65
.venv/bin/python -m pytest -q tests/test_bridge.py tests/test_hmac_auth.py tests/test_orders_reasons.py
```

Hasil acuan: suite penuh 1.127 lulus (25 Nov 2026 08:42, `docs/QA_v22_pytest_25nov_fix_run2.log`);
lihat `TEST_PLAN_v2.2.md` untuk bukti terbaru dan catatan flakiness.

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-ceo | 26 Nov 2026 | Dari kode + OpenAPI live |
| Review | hf-backend | menunggu | kontrak bridge |
| Review | hf-qa | menunggu | test roundtrip |
