# BUKTI UI-D2 — Redesign login + terminal + landing (monochrome glass) + gap API

Kartu: `t_9a632610` · Assignee: `hf-frontend` · Tanggal verifikasi: 26 Nov 2026 03:5x WIB
Repo: `~/fund2/frontend` (Vite + React). Backend tidak disentuh.

## 1. DoD dan hasil

| # | Kriteria | Hasil | Bukti |
| --- | --- | --- | --- |
| 1 | `npm run build` lolos | PASS | `✓ built in 754ms`, `dist/index.html` 03:52 WIB |
| 2 | `dist` yang disajikan adalah build baru | PASS | `find src -newer dist/index.html` kosong (tidak ada source lebih baru dari dist) |
| 3 | Tidak ada hex emas / arang hangat di frontend | PASS | `grep -rniE 'd9a648|f0c36b|8a6a2f|2a2010|11100e|0b0a09|edeae1|a89f8e|847b69' src/ index.html` = **0** baris; `rgba(217,166,72)`/`rgba(17,16,14)` = 0 |
| 4 | Palet sesuai referensi | PASS | `tokens.css`: `--bg #06070a`, `--surface #0d0f15`, `--text #f4f5f8`, `--text-muted #8b909e`, `--up #10b981`, `--down #ef4444`, `--warn #f59e0b` |
| 5 | Judul `font-display`, angka mono + `tabular-nums` | PASS | `--font-display: 'Plus Jakarta Sans'`; `--font-mono: 'IBM Plex Mono'`; `getComputedStyle('.num').fontVariantNumeric` = `tabular-nums` di /, /ops, /landing |
| 6 | Screenshot 1280px + 390px tiap permukaan | PASS | 8 file di `docs/evidence/ui_d2_t_9a632610/` (lihat §4) |
| 7 | Tanpa console error | PASS | kolektor `window.__errs` (error + unhandledrejection + `console.error`): `[]` di `/`, `/ops`, `/landing`, `/login` |
| 8 | Tanpa overflow horizontal | PASS | `documentElement.scrollWidth <= clientWidth` di 6 kombinasi (3 route x 2 viewport); 390px: `sw = cw = 390` |
| 9 | Semua endpoint gap dipanggil dengan `credentials: 'include'` + CSRF | PASS | `labGet`/`labPost` di `src/lib/api.js` (GET `credentials:'include'`, POST `authHeaders()` → `x-csrf-token`) |

## 2. Tiga permukaan

1. **Login — "Allocator Authentication"** (`src/pages/Login.jsx`, `.auth-*`)
   Satu kartu kaca di tengah: brand + badge TLS, segmented tab (Masuk allocator / Minta akses),
   form mono, CTA pill putih, panel "Kontrol akses" (sesi/2FA/jejak), footer nota sesi.
   Kaca diverifikasi terukur: rata-rata luminans interior kartu 25.9 vs latar 10.8, gradasi vertikal 9→30 (bukan fill rata).
2. **Terminal / risk ops** (`src/pages/Dashboard.jsx` + shell `src/App.jsx`)
   Strip instrumen + nav kaca, grid KPI mono besar, chart, rel pengaman. Slot `PnlHero` disiapkan
   (komentar di `Dashboard.jsx:176`), `SystemMetrics` tetap 1 import + 1 pemanggilan (`:5`, `:266`) untuk UI-D4.
3. **Landing Lumine Fund** (route publik `/landing`, `src/pages/Landing.jsx`)
   Signature moment kanvas "optical gate": noise (coretan abu) → garis ambang bertick berlabel `GATE`
   → gelombang sinyal halus hijau berlabel `CLEAN SIGNAL`. Kanvas dimask agar kolom teks kiri bersih.
   Tanpa angka marketing palsu (AUM/investor/uptime); hanya klaim yang bisa dipertanggungjawabkan.

## 3. Gap API yang diwujudkan di UI (halaman `/ops`)

| Endpoint | Dipakai oleh | Fungsi di `api.js` |
| --- | --- | --- |
| `GET /strategies/degradation` + `POST /strategies/{id}/degradation/re-enable` | `DegradationPanel` | `fetchDegradationAll`, `reEnableDegradation` |
| `GET /strategies/{id}/degradation` | `DegradationPanel` | `fetchDegradation` |
| `GET /strategies/{id}/supervisor/events` | `SupervisorPanel` | `fetchSupervisorEvents` |
| `POST /strategies/{id}/lifecycle` | `SupervisorPanel` (dialog 2 langkah) | `labPost` |
| `GET /llm-agent/status` (+ resume breaker) | `LlmAgentPanel` | `fetchLlmStatus` |
| `GET /research/reports`, `GET /research/tools`, `GET /research/proposals` | `ResearchPanel` | `fetchResearchReports/Tools/Proposals` |
| `POST /research/proposals/{id}/deployed` | `ResearchPanel` | `markProposalDeployed` |
| `GET /auth/sessions`, `POST /auth/sessions/revoke-all` | `SessionsPanel` | `fetchAuthSessions`, `revokeAllSessions` |
| `GET /shadow/runs`, `GET /shadow/runs/{id}/signals` | `ShadowPanel` (Strategy Lab) | `fetchShadowRuns`, `fetchShadowSignals` |
| `POST /kill-switch/release` | `KillSwitchCard` | `killSwitch` (armed ? `/kill-switch` : `/kill-switch/release`) |
| `GET /strategies/lifecycle-summary`, versions activate/rollback/review/submit | wrapper siap di `api.js` | UI di kartu **UI-D3c** (file StrategyLab dicadangkan) |

Total 17 export fungsi gap di `src/lib/api.js`. `/poll` (long-poll bridge EA) sengaja **tidak** diekspos ke UI: itu kanal EA↔API, bukan aksi operator.

## 4. Screenshot (build final 03:52)

| Permukaan | 1280px | 390px |
| --- | --- | --- |
| Login | `docs/evidence/ui_d2_t_9a632610/login-1280.png` | `.../login-390.png` |
| Terminal | `.../terminal-1280.png` | `.../terminal-390.png` |
| Ops & Recovery (panel gap) | `.../ops-1280.png` | `.../ops-390.png` |
| Landing | `.../landing-1280.png` | `.../landing-390.png` |

Salinan kerja: `frontend/.impeccable/review2/`.

## 5. Perbaikan pada run ini

1. **Bug 1000× latency**: `SystemMetrics.jsx` mengalikan median `t0_t2_ms`/`t0_t4_ms` dengan 1000, sehingga 121 ms tampil `121136ms` dan terpotong ellipsis. Kini memakai nilai ms apa adanya (`121ms / 283ms / 390ms`), field `_s` tetap ×1000.
2. **Teks terpotong**: `.sm-value` diizinkan membungkus (`white-space: normal; overflow-wrap: anywhere`); `.copypath code` path runbook tidak lagi dipotong `max-width: 200px`. Hasil: elemen terpotong 2 → **0** di / dan /ops (1280 & 390).
3. **Panel riset 403**: `labGet` kini menyertakan `detail` + `status`; `ResearchPanel` menerjemahkan 403 peran jadi pesan "Butuh peran research atau admin untuk …" (sebelumnya "Gagal memuat: Gagal memuat …" ganda).
4. **Kanvas landing**: label `NOISE` dipindah ke dalam area terlihat, sinyal pasca-filter digambar analitik dengan frekuensi ternormalisasi (gelombang halus, bukan zigzag harga), noise hanya lahir di sisi kanan komposisi, mask kanvas memberi fade tepi kanan.
5. **Kaca login**: alpha kartu 0.42/0.30 + blur 14px + sheen `::before`; ditambah kolam cahaya radial di belakang kartu supaya translusensi punya objek untuk ditembus.

## 6. Deviasi / catatan

- `StrategyLab.jsx`, `PositionsTable.jsx`, `History.jsx` **tidak disentuh** pada run ini (cadangan UI-D3c), sesuai instruksi CEO.
- Backend (`api/app/*`) tidak diubah; perubahan backend yang terlihat di `git status` adalah pekerjaan kartu lain di working tree bersama.
- ui.js wrapper version `activate/review/submit` dan `lifecycle-summary` sudah tersedia tapi belum dipanggil UI: itu permukaan Strategy Lab milik UI-D3c.
