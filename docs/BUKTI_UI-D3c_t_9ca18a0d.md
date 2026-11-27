# BUKTI — UI-D3c (t_9ca18a0d): Strategy Lab monochrome, badge mode, siklus usulan, sumber posisi, Risk Config Aktif

Tanggal: 26 Nov 2026 (WIB) · Eksekutor: hf-frontend · Env API: `FUND2_ENV=demo` (label UI, live trading belum aktif)
Backend: **tidak ada perubahan** (semua endpoint sudah ada). Build: `cd ~/fund2/frontend && npm run build` → lolos.

## 1. DoD vs hasil

| # | Butir DoD | Status | Bukti |
|---|---|---|---|
| 1 | Badge mode di semua order, posisi, P&L agregat, statistik strategi, equity + legenda | LULUS | `ModeBadge.jsx` (LIVE/PAPER/DEMO) dipakai di `History.jsx` (kolom Mode per order), `PositionsTable.jsx` (baris desktop + pcard mobile + chip agregat), `Dashboard.jsx` (baris Equity + `ModeLegend`), `StrategyLab.jsx` (badge PAPER di kepala statistik tiap strategi). Screenshot `after-hist-1280.png`, `after-dash-1280.png`, `after-lab-1280.png` |
| 2 | Strategy Lab penuh di design system monochrome (Ringkasan, Versi & Diff, Degradasi minimal) | LULUS | `StrategyLab.jsx` ditulis ulang (struktur: kepala halaman → status kill-switch → siklus usulan → daftar strategi dengan kartu metrik); blok CSS `/* UI-D3c */` di `pages.css`; `EquityCurve` memakai palet baru (`#10b981`/`#ef4444`/abu netral, bukan lagi `#d9a648`/`#847b69`). Screenshot `after-lab-ringkasan-1280.png`, `after-lab-versi-1280.png`, `after-lab-degradasi-1280.png`, `before-lab-1280.png` vs `after-lab-1280.png` |
| 3 | Panel siklus usulan perbaikan (PROPOSED/APPROVED/REJECTED/DEPLOYED + deployed_at + lifecycle strategi) | LULUS | `ProposalLifecyclePanel.jsx` di Lab; data real: 3 usulan, 4 strategi, `GET /improve/proposals` + `GET /strategies/lifecycle-summary` |
| 4 | Tabel posisi: kolom Strategi + Mode + tooltip sumber (order_id, Bridge EA) | LULUS | `PositionsTable.jsx`: join `p.orderId` → `state.orders[].strategy`, fallback jujur "warisan / dibuka langsung EA", tooltip memuat `order_id`. Diverifikasi render nyata dengan posisi demo BTCUSD (`F2-0001`): header tabel = `Order · Simbol · Strategi · Mode · Arah · Volume · Entry · SL · TP · P/L`, baris = `F2-0001 · BTCUSD · Manual · DEMO · …`, tooltip `order_id F2-0001 · strategi manual (tombol Order Baru / UI) · sumber data: Bridge EA (snapshot /positions)`; jalur pcard mobile memuat `Strategi Manual` + `order F2-0001 · sumber Bridge EA`. Akun live saat verifikasi 0 posisi terbuka (semua CLOSED), jadi jalur baris LIVE tidak bisa dipotret; badge LIVE pada kartu Posisi terbuka tetap terverifikasi di mode real (`0 aktif`, badge LIVE) |
| 5 | Panel Risk Config Aktif (limits + llm_risk + drawdown + pause + breaches) | LULUS | `ActiveRiskConfig` di `RiskConfigPanel.jsx`, tampil di Dashboard: 16 baris terisi (7 plafon portofolio, 5 batas agent, drawdown berjalan, order hari/menit, status pause/breach) |
| 6 | `npm run build` lolos, tanpa console error, screenshot 1280 + 390 (Dashboard, Riwayat, Lab) | LULUS | build `✓ built in 737ms`; `window.__errs` kosong di tiga halaman (1280 & 390); `documentElement.scrollWidth == clientWidth` (1280: 1274/1274, 390: 390/390) |
| 7 | Mode demo (`?demo=1`) tetap berfungsi, tanpa hardcode | LULUS | `dash-demo-1280.png`; badge otomatis DEMO; panel yang butuh data backend menampilkan pesan "tidak tersedia di mode demo" |
| 8 | E2E mengikuti pola `fund2-ui-e2e` | LULUS | build → dist dilayani `fund2-api` (tanpa restart), login via user QA sementara, CSRF untuk aksi, bukti di `docs/evidence/ui_d3c_t_9ca18a0d/` |

## 2. Perubahan file (frontend saja)

| File | Perubahan |
|---|---|
| `src/components/ModeBadge.jsx` (BARU) | Sumber tunggal semantik LIVE/PAPER/DEMO + `ModeLegend`. Named export untuk dipakai ulang UI-D4 |
| `src/components/ProposalLifecyclePanel.jsx` (BARU) | Dua kolom: pipeline usulan (status + verdict + reviewer + diputuskan + deploy) dan lifecycle strategi (versi aktif, registry, approval terakhir, degradasi, WF/Shadow) + tombol "Lihat approval" yang membuka view Approval strategi |
| `src/components/RiskConfigPanel.jsx` | Tambah `ActiveRiskConfig` (polling 30 s, stale > 60 s), baris plafon dari `GET /risk/portfolio.limits`, batas agent dari `GET /llm-agent/status.llm_risk`, drawdown berjalan, status pause, daftar breach. Unit dipindah ke setelah angka |
| `src/components/PositionsTable.jsx` | Ditulis ulang: kolom Strategi + Mode + P/L berwarna + chip agregat; join provenance lewat order |
| `src/pages/StrategyLab.jsx` | Restyle + struktur baru (kartu metrik dengan lead badge PAPER, sparkline equity paper dengan label "datar", tab segmented, view ringkasan lebih padat); logic 6 view + ConfirmDialog 2FA (live/rollback) tidak diubah |
| `src/pages/Dashboard.jsx` | Badge LIVE di baris Equity, `ModeLegend`, panel `ActiveRiskConfig` |
| `src/pages/History.jsx` | Kolom Mode di setiap baris order + `ModeLegend` di atas tabel |
| `src/styles/pages.css` | Blok append `/* UI-D3c */` (badge, legenda, kartu Lab, panel siklus, panel risk config, tabel, responsif ≤720 px) |

Catatan kolaborasi: `StrategyLab.jsx` dan `pages.css` **juga** disentuh kartu LLM-F1 `t_2a751a6c` pada saat yang sama (lihat komentar hotspot di kartu). Tidak ada kerja yang hilang; build akhir memuat komponen kedua kartu.

## 3. Temuan (untuk CEO / kartu lanjutan)

1. **Duplikasi panel governance di Lab.** `ProposalLifecyclePanel` (UI-D3c, baca-saja) menampilkan pipeline usulan + lifecycle; `SupervisorPanel` + `SelfImproveApprovalPanel` (LLM-F1) menampilkan data yang sama dengan aksi. Perlu satu kartu penggabungan: satu panel governance (ringkasan + aksi) menggantikan tiga.
2. **Semantik LIVE vs env.** `GET /health` mengembalikan `env=demo` (FUND2_ENV), jadi baris broker saat ini **bukan dana riil**. Badge tetap `LIVE` sesuai vocabulary kartu (sumber = akun broker, bukan simulator/paper), tetapi tooltip + legenda menyatakan `env aplikasi demo, dana riil belum aktif` supaya tidak menyesatkan. Bila env berubah ke `live`, teks otomatis berubah.
3. **`allowed_symbols` dan `exposure_max_usd` tidak terekspos** endpoint read-only mana pun. Panel menampilkan "Tidak terekspos via API" (bukan angka karangan). Butuh endpoint mikro backend bila ingin ditampilkan.
4. **Tabel versi/diff (komponen lama `VersionDiffTable.jsx`, di luar file yang boleh disentuh kartu ini)** masih punya kelemahan yang tidak bisa diperbaiki dari CSS Lab: tiga indikator seleksi (radio, badge A/B, label `aktif`) dan tombol rollback merah di dalam baris data. Perbaikan butuh kartu terpisah yang memiliki file itu.
5. **`1 ` kecil**: kartu `dash-chart` pada 390 px punya overflow internal 6 px (366 > 360) — bukan dari perubahan kartu ini (tidak ada elemen baru di dalam kartu itu); dicatat agar diperiksa pemilik Dashboard/Chart.
6. **Verifikasi tabel posisi live tidak mungkin saat ini**: `GET /positions` mengembalikan 0 posisi terbuka (semua CLOSED), jadi jalur render kolom Strategi/Mode diverifikasi lewat mode demo. Tidak ada INSERT baris OPEN ke DB live (aturan skill).

## 4. Perintah verifikasi

```bash
cd ~/fund2/frontend && npx oxlint src/components/ModeBadge.jsx \
  src/components/ProposalLifecyclePanel.jsx src/components/RiskConfigPanel.jsx \
  src/components/PositionsTable.jsx src/pages/StrategyLab.jsx src/pages/Dashboard.jsx src/pages/History.jsx
npm run build
# runtime: fund2-api (systemd user) menyajikan dist tanpa restart
curl -s http://127.0.0.1:3110/healthz
```

Pengukuran E2E (1280x900 dan 390x844), dijalankan ulang 26 Nov 2026 05:58-06:05 WIB di atas build final `index-BNA8iNLf.js` (524.12 kB) / `index-DL-DhjD5.css` (120.93 kB):

- `documentElement.scrollWidth == clientWidth` di `/`, `/riwayat`, `/lab` untuk kedua viewport (1280: 1274/1274 · 390: 390/390).
- `window.__errs` kosong (tanpa console error / unhandled rejection) di tiga halaman.
- Lab: 3 kartu strategi, 6 tab view (`Ringkasan · Versi & Diff · Walk-forward · Shadow · Degradasi · Approval`), 4 badge (1 `STATISTIK PAPER` + 3 `PAPER`), pipeline 3 usulan (2 REJECTED + 1 DEPLOYED) dan lifecycle 4 strategi; 0 elemen dengan `overflow:hidden` yang memotong teks (`scrollWidth > clientWidth`) di 1280 maupun 390.
- Dashboard: 1 legenda badge (LIVE/PAPER/DEMO), 5 badge, 16 baris Risk Config Aktif (7 plafon portofolio + 5 batas agent + drawdown berjalan + order hari/menit + 2 baris "tidak terekspos"), 0 breach, 1 chip `GATE ON`, 1 chip `AGENT AKTIF`.
- Riwayat: 200 baris order, kolom `Mode` terisi badge LIVE per baris + legenda di atas tabel.
- Mode demo: badge otomatis DEMO, order demo `F2-0001` (BTCUSD) mengisi tabel posisi untuk menguji jalur provenance Strategi/Mode + tooltip.

## 5. Bukti gambar

`docs/evidence/ui_d3c_t_9ca18a0d/`:

| File | Isi |
|---|---|
| `before-lab-1280.png`, `before-lab-degradasi-1280.png`, `before-dash-1280.png` | Kondisi sebelum restyle |
| `after-lab-1280.png` | Lab 1280: kepala + status + siklus usulan + kartu strategi |
| `after-lab-ringkasan-1280.png`, `after-lab-versi-1280.png`, `after-lab-degradasi-1280.png` | View Ringkasan (kartu terbuka), Versi & Diff, Degradasi |
| `after-dash-1280.png` | Dashboard: legenda badge, Equity LIVE, panel Risk Config Aktif |
| `after-hist-1280.png` | Riwayat: kolom Mode per order + legenda |
| `after-lab-390.png`, `after-dash-390.png`, `after-hist-390.png` | Layout mobile 390x844 |
| `after-dash-demo-1280.png`, `after-dash-demo-390.png` | Mode demo (`?demo=1`): badge DEMO + tabel posisi demo dengan kolom Strategi/Mode (jalur provenance, desktop + pcard mobile) |

## 6. Revisi kecil pada run verifikasi akhir

1. **Chip `REAL ONLY` dihapus** dari placeholder `ActiveRiskConfig` mode demo → diganti `LIVE DATA`. Kartu melarang kosakata badge REAL; chip itu bisa terbaca sebagai mode keempat. Chip sekarang menyatakan "panel ini butuh data broker/settings", bukan mode data.
2. **User QA `ui_d3c_qa`** (admin, tanpa 2FA) dipakai untuk E2E lalu dihapus setelah verifikasi; tidak ada baris posisi OPEN yang disisipkan ke DB live.
3. **Tidak ada perubahan backend** pada kartu ini; seluruh angka di panel berasal dari `GET /risk/portfolio`, `GET /llm-agent/status`, `GET /improve/proposals`, `GET /strategies/lifecycle-summary`.
4. **Working tree bersama**: `StrategyLab.jsx` dan `pages.css` masih berbagi hunk dengan kartu LLM-F1 (t_f7aba864) dan tabel sesi ini tidak mengubah pekerjaan kartu lain.

