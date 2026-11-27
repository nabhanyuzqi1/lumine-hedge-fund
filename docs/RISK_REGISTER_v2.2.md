# Risk Register & Threat Model — Fund2 v2.2

Status: DRAFT untuk review owner. Sumber utama: PRD v2.2 §28 (risk register), Lampiran B (artefak wajib rilis, termasuk threat model), Lampiran C (prinsip keputusan).
Tanggal: 2026-11-25. Pemilik dokumen: hf-ceo. Review wajib: owner.

Dokumen ini menggabungkan:

1. **Risk register 14 item** (PRD §28) dengan penyebab, dampak, rating, mitigasi preventif/detektif/korektif, owner, dan status bukti.
2. **Threat model** (Lampiran B) berbasis STRIDE + ancaman khusus AI (LLM), per trust boundary.

Aturan pemakaian (mengikuti Lampiran C): risiko residual yang tersisa setelah mitigasi wajib diketahui owner; keputusan live (PRD §29) menunggu persetujuan owner terpisah. Risk register bukan pengganti risk policy yang ditandatangani owner (Lampiran B).

---

## 1. Metodologi rating

- **P (Peluang)**: 1 = sangat jarang, 2 = jarang, 3 = mungkin, 4 = sering, 5 = hampir pasti (periode 6 bulan operasi).
- **D (Dampak)**: 1 = dapat diabaikan, 2 = minor, 3 = materi (loss terukur / downtime jam), 4 = berat (loss besar / data rusak), 5 = fatal (loss modal signifikan / integritas ledger pecah).
- **Skor = P × D**. Level: 1–4 Rendah, 5–9 Sedang, 10–14 Tinggi, 15–25 Kritis.
- Rating "awal" = sebelum mitigasi; "residual" = perkiraan setelah mitigasi terpasang dan terverifikasi. Residual ditinjau ulang tiap rilis dan tiap insiden SEV-1/SEV-2.

## 2. Risk register (PRD §28, 14 item)

### R-01 — Data historis berbeda dari HFM
- **Penyebab**: feed historis (mis. Dukascopy/eksport broker) tidak identik dengan HFM: spread, tick granularity, gap, komisi, swap, dan aturan fill berbeda. Backtest memakai data yang "terlalu bersih".
- **Dampak**: backtest terlalu optimis; ekspektasi profit/walk-forward tidak terbawa ke live; ukuran posisi dan stop salah kalibrasi.
- **Rating awal**: P4 × D4 = 16 (Kritis).
- **Mitigasi**:
  - Preventif: kalibrasi data ke HFM (spread/komisi/swap), haircut konservatif pada hasil backtest (PRD §8, §19).
  - Detektif: validasi ingest + data quality test (`test_ingest_validation.py`, `test_data_quality.py`, `test_feed.py`); paritas metrik backtest vs paper (`test_backtest_metrics.py`).
  - Korektif: paper trading sebagai gerbang sebelum live (PRD §9); setiap selisih tercatat dan menjadi input haircut baru.
- **Owner**: hf-backend (pipeline) + hf-qa (paritas).
- **Status/bukti**: pipeline ingest + validasi terdokumentasi (LAPORAN_DOD_DATAPIPE_v22.md); walk-forward reports ada di docs/wf2_*.md. Kalibrasi HFM penuh belum terbukti — residual: P3 × D4 = 12 (Tinggi).

### R-02 — Slippage ekstrem
- **Penyebab**: news/volatility spike, likuiditas tipis (sesi Asia, rollover), eksekusi market order saat spread melebar.
- **Dampak**: kerugian melebihi asumsi backtest; stop loss tereksekusi jauh di bawah harga; R multiple rusak.
- **Rating awal**: P4 × D4 = 16 (Kritis).
- **Mitigasi**:
  - Preventif: buffer risk per trade, filter entry (spread maksimum, jam trading), stop entry saat kondisi tidak normal (PRD §28).
  - Detektif: monitoring slippage realisasi vs asumsi per order (`test_costs.py`, metrics eksekusi OBSERVABILITY_v2.2.md).
  - Korektif: kill-switch / halt otomatis saat slippage melampaui ambang (PRD §16); order ditolak, bukan diikuti pasar.
- **Owner**: hf-backend.
- **Status/bukti**: kill-switch + bridge teruji (test_kill_switch + test_bridge, laporan P1); preflight check (`test_prefill.py`, `test_preflight.py`). Residual: P3 × D3 = 9 (Sedang).

### R-03 — MT5/EA disconnect
- **Penyebab**: koneksi VPS ke broker putus, terminal MT5 crash, EA reload, network flap.
- **Dampak**: state posisi tidak diketahui; order menggantung; SL/TP tidak termonitor; exposure tak terkendali selama gap.
- **Rating awal**: P4 × D4 = 16 (Kritis).
- **Mitigasi**:
  - Preventif: heartbeat dan snapshot state (PRD §14–15); EA idempotent, semua event append-only ke `order_events`.
  - Detektif: reconciler membandingkan state lokal vs broker; alert disconnect (OBSERVABILITY_v2.2.md, RUNBOOK_v2.2.md).
  - Korektif: halt otomatis saat state tidak jelas; rekonsiliasi sebelum retry (Lampiran C); policy posisi saat disconnect adalah keputusan owner (PRD §29 poin 4).
- **Owner**: hf-backend + hf-devops.
- **Status/bukti**: test_bridge, test_state_machine, test_reconciliation ada; insiden STUCK pernah terjadi dan diselesaikan via rekonsiliasi manual (log insiden 2026-11-25). Residual: P3 × D3 = 9 (Sedang).

### R-04 — Duplicate order
- **Penyebab**: retry API setelah timeout tanpa idempotency key; EA reconnect mengirim ulang request; user/klien double-submit.
- **Dampak**: exposure berlipat tanpa disadari; margin terpakai ganda; kerugian agregat melebihi limit.
- **Rating awal**: P3 × D4 = 12 (Tinggi).
- **Mitigasi**:
  - Preventif: idempotency key pada order request (PRD §13 state machine, §14); unique constraint di ledger.
  - Detektif: broker reconciliation (posisi vs order_events) dan alert mismatch (PRD §15); test duplicate (`test_orders_api.py`, `test_execution.py`).
  - Korektif: order duplikat ditandai dan dinegasi via rekonsiliasi; kill-switch menghentikan aliran order baru.
- **Owner**: hf-backend.
- **Status/bukti**: state machine + bridge teruji; paritas QA order events (LAPORAN_DOD_P1a2_KILLSWITCH.md). Residual: P2 × D4 = 8 (Sedang).

### R-05 — Strategy crash
- **Penyebab**: bug di kode strategi, exception tak tertangani, OOM, dependensi data hilang (bar tidak lengkap), loop tak berhingga.
- **Dampak**: sinyal hilang (posisi tidak dikelola) atau sinyal abnormal (order liar); posisi terbuka tanpa pengelolaan.
- **Rating awal**: P3 × D4 = 12 (Tinggi).
- **Mitigasi**:
  - Preventif: strategy isolation — satu strategi tidak boleh menjatuhkan yang lain (PRD §5); supervisor + resource limit.
  - Detektif: heartbeat strategi; test supervisor dan fault injection (`test_supervisor.py`, fault_injection suite).
  - Korektif: circuit breaker per strategi; strategi crash diisolasi, posisi yang dikelolanya diambil alih atau di-flatten sesuai runbook (INCIDENT_PLAYBOOK_v2.2.md).
- **Owner**: hf-backend.
- **Status/bukti**: t_f2v22a1 (strategy isolation + fault injection) diklaim lulus DoD, dalam review. Residual: P2 × D3 = 6 (Sedang).

### R-06 — Regime salah
- **Penyebab**: deteksi regime keliru (false positive/negative), flip-flop antar regime, fitur look-ahead saat riset.
- **Dampak**: strategi aktif pada kondisi pasar yang buruk; performa menyimpang jauh dari backtest per regime.
- **Rating awal**: P3 × D4 = 12 (Tinggi).
- **Mitigasi**:
  - Preventif: fitur hanya dari bar CLOSED tanpa look-ahead (REGIME_v2.2.md); hysteresis + cooldown anti flip-flop; UNKNOWN memblokir entry yang butuh regime (PRD §6.2/§6.5).
  - Detektif: evaluasi out-of-sample per regime (`test_regime.py`, `test_regime_current.py`); recording keputusan regime untuk audit (PRD §6.4).
  - Korektif: fallback ke regime UNKNOWN = safe (tidak trading); review manual saat mismatch regime vs performa.
- **Owner**: hf-backend.
- **Status/bukti**: REGIME_v2.2.md v1.0.0 (t_f2v22a2) closed; keterbatasan v1 dinyatakan jujur di dokumen. Residual: P3 × D3 = 9 (Sedang).

### R-07 — Portfolio risk salah hitung
- **Penyebab**: bug di agregasi exposure (per symbol/strategi/arah), kontrak spec salah (lot size, tick value), korelasi antar posisi diabaikan.
- **Dampak**: kerugian agregat berlebih; limit risk dilanggar tanpa alarm; margin call.
- **Rating awal**: P2 × D5 = 10 (Tinggi).
- **Mitigasi**:
  - Preventif: contract specification test + stress test (PRD §28, §7); limit risiko tidak boleh diubah tanpa versi/approval.
  - Detektif: property-based test agregasi (`test_property_based.py`, `test_portfolio_risk.py`, `test_risk.py`); rekonsiliasi exposure vs broker.
  - Korektif: kill-switch global saat limit agregat tembus; posisi di-flatten sesuai policy owner (PRD §16, §29 poin 6).
- **Owner**: hf-backend.
- **Status/bukti**: LAPORAN_DOD_PORTFOLIO_RISK_v22.md (t_f2v22a3 closed); test portfolio risk + property-based ada. Residual: P2 × D4 = 8 (Sedang).

### R-08 — Overfitting
- **Penyebab**: parameter dioptimalkan pada data yang sama dengan evaluasi; terlalu banyak eksperimen dipilih terbaik (selection bias); walk-forward tidak benar.
- **Dampak**: performa live jauh di bawah backtest; strategi gagal setelah rilis.
- **Rating awal**: P4 × D3 = 12 (Tinggi).
- **Mitigasi**:
  - Preventif: walk-forward + out-of-sample wajib (PRD §8); haircut konservatif; experiment registry agar semua percobaan teraudit, bukan hanya yang menang.
  - Detektif: shadow mode (PRD §9) dan paper trading membandingkan live-vs-backtest; laporan walk-forward disimpan (docs/wf2_*.md).
  - Korektif: strategi tidak lolos shadow/paper tidak naik ke live; degradation detection menurunkan strategi yang tamat (PRD §10).
- **Owner**: hf-ceo (riset) + hf-qa (evidence).
- **Status/bukti**: walk-forward reports + LAPORAN_WALKFORWARD_P2.md + shadow tests (`test_shadow*.py`, `test_eval_gate_shadow.py`). Residual: P3 × D3 = 9 (Sedang).

### R-09 — Hermes hallucination
- **Penyebab**: LLM mengarang data pasar, metrik backtest, atau kesimpulan riset; confidence tinggi tanpa bukti; konteks tidak lengkap.
- **Dampak**: rekomendasi strategi/parameter salah; keputusan owner berdasarkan bukti palsu; eksperimen tidak bisa direproduksi.
- **Rating awal**: P4 × D3 = 12 (Tinggi).
- **Mitigasi**:
  - Preventif: Hermes hanya boleh mengusulkan; kandidat LLM lolos risk gate dan validasi sebelum jadi order (PRD §12); output wajib mengikuti schema + sitasi bukti (file/query yang benar-benar dijalankan).
  - Detektif: review QA/owner atas setiap rekomendasi; test LLM agent dan risk gate (`test_llm_agent.py`, `test_llm_risk.py`, `test_eval_gate_paper.py`).
  - Korektif: rekomendasi tanpa bukti ditolak; Hermes wajib melaporkan ketidakpastian, bukan mengarang kepastian (Lampiran C).
- **Owner**: hf-ceo + hf-qa.
- **Status/bukti**: QA_F2LLM4 eval gerbang + kriteria gerbang ada di docs; LLM tidak punya jalur order langsung. Residual: P3 × D3 = 9 (Sedang).

### R-10 — Prompt injection
- **Penyebab**: konten tidak tepercaya (berita, data pasar, teks halaman, file riset) menyisipkan instruksi ke Hermes; tool call di luar izin.
- **Dampak**: akses tool tidak sah, kebocoran secret, order tidak sah, data dimanipulasi.
- **Rating awal**: P3 × D5 = 15 (Kritis).
- **Mitigasi**:
  - Preventif: tool allowlist + sandbox read-only untuk Hermes (PRD §12, §18); tidak ada secret di konteks LLM; injection guard (`test_llm_injection_guard.py`, `test_llm_injection_guard_phase_b.py`, QA_F2LLM3_plan_uji_injection.md).
  - Detektif: security review + pentest berkala (docs/pentest.py, test_security_v22.py); log semua tool call.
  - Korektif: tool call mencurigakan diblokir dan di-alert; kill-switch memutus aliran order; rotasi secret bila terindikasi bocor.
- **Owner**: hf-backend (guard) + hf-qa (pentest).
- **Status/bukti**: injection guard phase B teruji; Hermes tools read-only. Residual: P2 × D4 = 8 (Sedang).

### R-11 — VPS/disk failure
- **Penyebab**: hardware/host failure, disk penuh (log/arsip tumbuh), corrupt filesystem, OOM host.
- **Dampak**: downtime layanan trading; kehilangan data ledger/event; kill-switch tidak dapat dijangkau.
- **Rating awal**: P3 × D4 = 12 (Tinggi).
- **Mitigasi**:
  - Preventif: backup pipeline + offsite (DR_v2.2.md §2), disk alert (PRD §28), kapasitas log dirotasi.
  - Detektif: monitoring disk/mem/service (OBSERVABILITY_v2.2.md); restore drill terukur (DR_v2.2.md §3).
  - Korektif: recovery sequence runbook (PRD §17.5, DR_v2.2.md §5); RTO/RPO final ditetapkan owner (PRD §29 poin 7).
- **Owner**: hf-devops.
- **Status/bukti**: restore drill 2x LULUS ter-commit (7e00fa7); backup script + checksum manifest. Residual: P2 × D3 = 6 (Sedang).

### R-12 — Secret leak
- **Penyebab**: API key/token masuk ke log, konteks LLM, repo, atau chat; kredensial dipakai berlebih (least privilege dilanggar); rotasi tidak jalan.
- **Dampak**: order tidak sah oleh pihak lain; akun broker/API dibajak; akses database.
- **Rating awal**: P2 × D5 = 10 (Tinggi).
- **Mitigasi**:
  - Preventif: secret management (env/secret store, bukan repo), least privilege, tidak ada secret ke LLM (PRD §18); HMAC auth antar komponen (`test_hmac_auth.py`).
  - Detektif: audit akses, scan repo/log untuk pola secret (security review), alert auth gagal berulang.
  - Korektif: rotasi secret segera; cabut sesi/token; insiden SEV-1 sesuai playbook (INCIDENT_PLAYBOOK_v2.2.md).
- **Owner**: hf-devops + hf-backend.
- **Status/bukti**: HMAC + TOTP teruji (`test_totp.py`, `test_hmac_auth.py`, `test_auth.py`); aturan no-secret di injection guard. Residual: P2 × D4 = 8 (Sedang).

### R-13 — Jadwal molor
- **Penyebab**: scope creep, dependensi antar kartu, gate belum lulus, kapasitas worker terbatas (RAM/host), insiden mendadak.
- **Dampak**: rilis tertunda; tekanan untuk melompati gate (bahaya laten); biaya kesempatan.
- **Rating awal**: P4 × D2 = 8 (Sedang).
- **Mitigasi**:
  - Preventif: gate-based schedule — jadwal mengikuti kelulusan gate, bukan tanggal (PRD §28); P3 opsional; scope v2.2 dibekukan.
  - Detektif: review progres mingguan di board; kartu terpotong dihitung ulang, tidak dipaksakan.
  - Korektif: turunkan scope, bukan standar; keputusan owner untuk trade-off waktu vs cakupan.
- **Owner**: hf-ceo.
- **Status/bukti**: wave P2 berjalan bertahap; gate rilis P1 lulus (VERDICT_RELEASE_P1.md). Residual: P3 × D2 = 6 (Sedang).

### R-14 — False degradation alert
- **Penyebab**: ambang degradation terlalu sensitif, sample kecil, noise pasar normal, alert tanpa cooldown.
- **Dampak**: strategi sering berhenti (halt berulang); performa hilang karena strategi bagus dimatikan; alert fatigue.
- **Rating awal**: P3 × D3 = 9 (Sedang).
- **Mitigasi**:
  - Preventif: minimum sample size + cooldown sebelum degradasi dinyatakan (PRD §10); DEGRADED hanya memblokir risiko baru, HALTED menghentikan entry (keputusan berjenjang).
  - Detektif: test degradation (`test_degradation.py`); review metrik alert vs kejadian nyata.
  - Korektif: re-enablement butuh review dan approval owner (PRD §10); kalibrasi ulang ambang dari data alert.
- **Owner**: hf-backend + hf-qa.
- **Status/bukti**: test_degradation ada; kebijakan DEGRADED/HALT + sample size/cooldown terdokumentasi (t_f2v22a5). Residual: P2 × D3 = 6 (Sedang).

## 3. Matriks prioritas (ringkasan)

| ID | Risiko | Awal | Residual | Level residual |
| --- | --- | --- | --- | --- |
| R-01 | Data historis ≠ HFM | 16 Kritis | 12 Tinggi | Prioritas 1: kalibrasi HFM + haircut |
| R-02 | Slippage ekstrem | 16 Kritis | 9 Sedang | buffer + filter + stop entry |
| R-03 | MT5/EA disconnect | 16 Kritis | 9 Sedang | heartbeat + snapshot + reconciler |
| R-04 | Duplicate order | 12 Tinggi | 8 Sedang | idempotency + reconciliation |
| R-05 | Strategy crash | 12 Tinggi | 6 Sedang | isolation + circuit breaker |
| R-06 | Regime salah | 12 Tinggi | 9 Sedang | UNKNOWN safe + out-of-sample |
| R-07 | Portfolio risk salah hitung | 10 Tinggi | 8 Sedang | contract spec + stress test |
| R-08 | Overfitting | 12 Tinggi | 9 Sedang | walk-forward + shadow + paper |
| R-09 | Hermes hallucination | 12 Tinggi | 9 Sedang | bukti + schema + review |
| R-10 | Prompt injection | 15 Kritis | 8 Sedang | allowlist + sandbox + no secret |
| R-11 | VPS/disk failure | 12 Tinggi | 6 Sedang | backup + restore drill + disk alert |
| R-12 | Secret leak | 10 Tinggi | 8 Sedang | secret mgmt + rotation + least privilege |
| R-13 | Jadwal molor | 8 Sedang | 6 Sedang | gate-based schedule, P3 opsional |
| R-14 | False degradation alert | 9 Sedang | 6 Sedang | minimum sample + cooldown + review |

Catatan: rating residual adalah estimasi engineer, bukan jaminan. Dua risiko dengan residual "Tinggi" (R-01) dan seluruh keputusan live tetap menunggu persetujuan owner (PRD §29).

## 4. Threat model (Lampiran B)

### 4.1 Ruang lingkup

Sistem yang dimodelkan: Fund2 v2.2 end-to-end — MT5 + EA bridge, fund2-api (FastAPI), Postgres append-only ledger, paper runner, strategi + supervisor, portfolio risk, regime detection, Hermes (AI research, read-only), UI kontrol plane, Telegram alert, VPS host (tekka) dan backup.

Di luar lingkup: broker/MT5 server side (diasumsikan tepercaya untuk eksekusi, tapi diverifikasi via rekonsiliasi), penyedia data pasar pihak ketiga, infrastruktur Hermes platform (LLM provider).

### 4.2 Aset yang dilindungi

| Aset | Kenapa berharga | Dampak bila hilang |
| --- | --- | --- |
| A1. Modal & posisi live | Tujuan akhir sistem | Kerugian finansial langsung |
| A2. Integritas ledger `order_events` | Sumber kebenaran audit & rekonsiliasi | Order tidak bisa dilacak, rekonsiliasi gagal |
| A3. Secret (kredensial MT5, API key, HMAC, TOTP) | Akses ke broker & kontrol | Order tidak sah, pembajakan akun |
| A4. Kill-switch & kontrol emergency | Satu-satunya rem darurat | Tidak bisa menghentikan loss |
| A5. Data pasar & hasil riset | Dasar keputusan strategi | Keputusan salah, overfitting tak terdeteksi |
| A6. Ketersediaan layanan (API, runner, alert) | Pemantauan & respons insiden | Disconnect tanpa alarm, SL tidak termonitor |
| A7. Reputasi/kepatuhan | Kepercayaan owner & batang tubuh | ToS/resiko hukum (resale, dsb.) |

### 4.3 Trust boundaries

```
[Internet/Owner device] ⟷ (TB1: HTTPS/Caddy) ⟷ [UI kontrol plane]
[UI/API] ⟷ (TB2: auth owner + 2FA/TOTP) ⟷ [fund2-api]
[fund2-api] ⟷ (TB3: HMAC + DB role) ⟷ [Postgres ledger]
[fund2-api] ⟷ (TB4: HMAC + allowlist command) ⟷ [MT5 EA bridge]
[EA bridge] ⟷ (TB5: kredensial broker) ⟷ [Broker/MT5 server]
[Hermes LLM] ⟷ (TB6: tool allowlist + sandbox read-only) ⟷ [Host/riset tools]
[Konten tidak tepercaya: berita/data/file] ⟷ (TB7: injection guard) ⟷ [Hermes konteks]
[VPS host] ⟷ (TB8: backup/offsite) ⟷ [Backup storage]
```

Prinsip per boundary: setiap lintas boundary wajib diautentikasi, di-log, dan dibatasi haknya (least privilege). Kredensial tidak pernah melewati TB6/TB7 (tidak masuk konteks LLM).

### 4.4 Analisis STRIDE per trust boundary

| ID | Boundary | Kategori | Skenario ancaman | Kontrol yang ada | Residual |
| --- | --- | --- | --- | --- | --- |
| TM-01 | TB1 | Spoofing | Penyerang meniru UI/hosting untuk mencuri kredensial owner | HTTPS via Caddy, domain resmi, tidak ada mirror | Rendah |
| TM-02 | TB2 | Spoofing/Elevation | Session hijack untuk akses kontrol trading | Auth owner + 2FA/TOTP untuk aksi berbahaya (`test_auth.py`, `test_totp.py`, TOTP server-side t_57103cf5) | Rendah |
| TM-03 | TB2/TB4 | Tampering | Manipulasi request order/flatten di jalur | HMAC antar komponen (`test_hmac_auth.py`), allowlist command bridge | Rendah |
| TM-04 | TB3 | Tampering/Repudiation | Edit/hapus event ledger untuk menutupi kesalahan | Append-only guard + DB role terbatas (`test_migrations.py`, t_f2v22a11) | Rendah |
| TM-05 | TB4 | Spoofing | Perintah palsu dikirim ke EA_bridge sebagai API | HMAC + pairing, EA hanya menerima perintah terautentikasi | Sedang |
| TM-06 | TB5 | Info disclosure | Kredensial broker bocor dari terminal/konfigurasi | Secret di env/secret store, tidak di repo/log (PRD §18) | Sedang |
| TM-07 | TB6 | Elevation | Hermes memanggil tool di luar izin (write/order) | Tool allowlist + sandbox read-only (PRD §12); LLM tanpa jalur order langsung | Rendah |
| TM-08 | TB7 | Tampering | Prompt injection via konten riset/berita/data | Injection guard phase B + test (`test_llm_injection_guard*.py`), QA_F2LLM3 | Sedang |
| TM-09 | TB7 | Info disclosure | Secret bocor ke konteks LLM lalu ke provider | Aturan no-secret-in-context; scan log; least privilege | Sedang |
| TM-10 | TB2 (aset A4) | DoS | Flood endpoint API/flatten menonaktifkan kontrol | Rate limit, auth, TOTP; akses SSH langsung untuk emergency | Sedang |
| TM-11 | TB8 | Tampering/DoS | Backup dimusnahkan/dikunci (ransomware) | Backup offsite + checksum manifest (DR_v2.2.md §2) | Sedang |
| TM-12 | TB3 | Repudiation | Order dilakukan tanpa jejak yang bisa dipertanggungjawabkan | Semua order + event append-only dengan actor/role (`test_agent_role.py`, `test_provenance.py`) | Rendah |
| TM-13 | TB4 | DoS | Bridge hang menyebabkan state tidak diketahui | Heartbeat + snapshot + reconciler + halt (PRD §14–15) | Sedang |
| TM-14 | TB1–TB4 | Info disclosure | Log menampung secret/token | Redaction log, scan secret di security review (`test_security_v22.py`) | Sedang |

### 4.5 Ancaman khusus AI (LLM)

| ID | Ancaman | Skenario | Kontrol | Residual |
| --- | --- | --- | --- | --- |
| AI-01 | Hallucination metrik | Hermes melaporkan angka backtest yang tidak pernah dihitung | Output wajib sitasi bukti (query/file nyata), review QA/owner, eval gerbang (QA_F2LLM4) | Sedang |
| AI-02 | Prompt injection tidak langsung | Instruksi tersembunyi di data pasar/berita/file yang dibaca Hermes | Injection guard, tool read-only, tidak ada eksekusi instruksi dari konten (TB7) | Sedang |
| AI-03 | Tool abuse | Hermes mencoba tool di luar riset (order, file sensitif) | Allowlist + sandbox, log tool call, review berkala | Rendah |
| AI-04 | Overconfident rekomendasi | Hermes mendorong parameter agresif tanpa bukti out-of-sample | Risk gate + walk-forward + approval owner sebelum strategi naik (PRD §12, §11) | Sedang |
| AI-05 | Data exfiltration via prompt | Konten tidak tepercaya membujuk Hermes mengirim secret/posisi ke luar | Tidak ada secret di konteks; Hermes tanpa jalur keluar selain laporan schema | Sedang |

Pola pertahanan AI (mengikuti Lampiran C): Hermes tidak boleh mengarang kepastian; bila tidak yakin, wajib melaporkan ketidakpastian. Keputusan order selalu oleh komponen deterministik yang di-gate risk, bukan oleh LLM.

### 4.6 Pemetaan risk register ↔ threat model

| Risk | Ancaman terkait | Catatan |
| --- | --- | --- |
| R-03 disconnect | TM-13 | Bridge hang/state tidak diketahui |
| R-04 duplicate order | TM-03, TM-12 | Tampering jalur order + jejak audit |
| R-05 strategy crash | TM-13 | Supervisi & halt |
| R-09 hallucination | AI-01, AI-04 | Bukti + review + risk gate |
| R-10 prompt injection | TM-08, AI-02, AI-05 | Guard + sandbox + no-secret |
| R-11 VPS/disk failure | TM-11 | Backup + restore drill |
| R-12 secret leak | TM-06, TM-09, TM-14 | Secret mgmt + redaction log |
| R-14 false degradation alert | (non-aman) | Kontrol operasional, bukan ancaman adversary |

## 5. Risiko residual teratas & tindak lanjut

1. **R-01 (residual Tinggi, 12)**: kalibrasi penuh ke HFM belum terbukti. Tindak lanjut: ukur deviasi feed vs HFM (spread/komisi/swap/fill), dokumentasikan haircut, tambahkan paritas backtest-vs-paper sebelum live.
2. **R-03/R-02 (residual Sedang, 9)**: disconnect dan slippage sudah punya mitigasi teruji, tetapi belum pernah melalui insiden live berskala penuh. Tindak lanjut: fault injection berkala + review pasca setiap insiden.
3. **R-10 (residual Sedang, 8)**: injection guard teruji di suite, tetapi permukaan serang berubah tiap konten baru masuk konteks. Tindak lanjut: security review tiap penambahan tool/sumber data.

## 6. Review & approval

- Dokumen direview owner sebelum masuk release packet (Lampiran B: threat model + risk policy ditandatangani owner).
- Tinjauan ulang wajib: tiap rilis mayor, tiap insiden SEV-1/SEV-2, dan tiap perubahan permukaan serang (tool baru, integrasi baru, jalur order baru).
- Keputusan yang tetap di tangan owner (PRD §29): modal & loss limit, parameter risiko final, policy disconnect/orphan/flatten, RTO/RPO, strategi yang boleh live, kriteria canary, wewenang halt, kanal alert, jam cutover, dan persetujuan risiko residual.

## 7. Referensi

- PRD v2.2 §28 (risk register), §29 (keputusan owner), Lampiran B (artefak rilis), Lampiran C (prinsip keputusan).
- DR_v2.2.md (backup, restore drill, RTO/RPO), INCIDENT_PLAYBOOK_v2.2.md, OBSERVABILITY_v2.2.md, REGIME_v2.2.md, RUNBOOK_v2.2.md, VERDICT_RELEASE_P1.md.
- Bukti test di `api/tests/` (kill_switch, bridge, state_machine, portfolio_risk, regime, degradation, llm_injection_guard, totp, hmac_auth, security_v22, dan lainnya).

---

Disusun oleh: hf-ceo, 2026-11-25. Verdict: DRAFT — menunggu review owner.
