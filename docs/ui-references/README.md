# UI References — Lumine Fund (Director, 25 Nov 2026)

16 screenshot + 1 HTML referensi untuk seluruh permukaan UI Lumine Fund.
**WAJIB Amati → Tiru → Modifikasi sebelum menulis UI.** Jangan mengarang layout dari imajinasi.

## Keputusan warna FINAL (Director, kartu t_b3d90649, 25 Nov 10:49)

**IKUT reference — ganti skema ke near-black + hijau.** Keputusan ini MENGANTIKAN arahan
"pertahankan arang hangat + emas #d9a648" (kartu t_ca307d2d, 10:43). Sumber palet: HTML referensi
di folder ini (monochrome glass institutional risk ops).

| Peran | Nilai | Catatan |
| --- | --- | --- |
| Latar halaman | `#06070A` | near-black |
| Surface kartu/panel | `#0D0F15` / `#161922` | elevated surface |
| Teks utama | `#F4F5F8` | |
| Teks sekunder/muted | `#8B909E` | |
| Hijau (up / aktif / sehat / aksen) | `#10B981` | |
| Merah (down / critical / breach) | `#EF4444` | |
| Amber (warning / watch) | `#F59E0B` | |
| CTA primer | pill putih `#F4F5F8`, teks `#06070A` | satu elemen kontras tinggi per region |
| Font | Inter (UI) + Plus Jakarta Sans (display) + mono (JetBrains Mono / IBM Plex Mono) `tabular-nums` untuk semua angka | |

Pola komponen referensi: nav pill melayang; kartu radius 12–16px dengan hairline border
`rgba(255,255,255,~0.08)`; badge & micro-label mono uppercase letter-spacing lebar; glass /
backdrop-blur; starfield halus; warna semantik HANYA untuk status. Nama token CSS existing
dipertahankan, nilainya dipetakan ke tabel di atas (mis. `--gold` → peran aksen → `#10B981`,
`--up` → `#10B981`, `--down` → `#EF4444`, `--warn` → `#F59E0B`, `--bg` → `#06070A`,
`--text` → `#F4F5F8`, `--text-muted` → `#8B909E`).

## Inventaris

### Referensi inti Lumine — tiru layout, struktur, hierarchy, komponen

| File | Permukaan | Isi |
| --- | --- | --- |
| `img_ec7c44664aba.jpg` | Landing · Pipeline | "Three-Gate Optical Pipeline": 3 spec card (Signal Ingestion 142K TICKS/S, Pre-Trade Risk Gate TERM INTERLOCK, Sub-Millisecond Execution 0.42ms ROUTING) + visual 3D tiga gerbang kaca dengan signal dots |
| `img_265d21d10516.jpg` | Landing · Strategies | "Uncorrelated Volatility Regimes": 3 strategy card (London Breakout, Mean Reversion, BTC Range Breakout) + equity curve hijau tanpa axis |
| `img_03add4036941.jpg` | Landing · Risk | "Automated Risk Gyroscope": Drawdown Stress Simulator (slider 0 → −3.5%, WATCH −1.5%, HARD LOCK −3.0%, status RING 01/02 + ORDER GATE) + icosahedron 3 cincin |
| `img_20c2cdb5ae90.jpg` | Landing · Investors | "Built for Active Investors & Allocators": stats card (investors / AUM / retention), avatar row, session clocks JST/GMT/EST, wireframe globe |
| `img_d0014dfca1b3.jpg` | Landing · Liquidity | "Institutional Liquidity Depth": L2 data card (BEST BID/ASK, BOOK DEPTH, SPREAD badge) + 3D order-book depth chart |
| `img_4a23ad1efc59.jpg` | Landing · Hero alternatif | "Beyond Market Noise": frosted-glass pane membelah candlestick 3D (kacau → bersih) |
| `img_9081e468d7c0.jpg` | Terminal (Live Terminal) | Struktur lengkap: nav pill (Live Terminal · Strategy Lab · Ops & Logs + badge alert), market strip (BID/ASK/SPREAD + pill stale/alert), 4 KPI card (EQUITY, DAILY PNL + LIMIT BREACHED, TOTAL DRAWDOWN, POSISI/EKSPOSUR), chart candlestick + EMA-20 + toolbar timeframe, Safety Interlock card (TERARM · Halt Global + Ack Checklist), Order Baru terkunci (lock overlay), Portfolio Risk Summary, tab bawah + strategy cards |
| `img_0d6eb5fbe045.jpg` | Ops & Logs | Header telemetry, daftar 9 alert aktif (badge severity per row), Order Execution Latency 24 jam (T0→T2 / T0→T4 p50/p95/p99, FAILED vs SENT, Stuck SENT), Resource & Database Telemetry (CPU/RAM/Disk bar + DB status/pool) |
| `doc_0fd2ef08a331_...html` | Login + token desain | "Allocator Authentication" + sumber palet/token (lihat tabel di atas). Font Inter + Plus Jakarta Sans |

### Referensi pendukung — pakai POLA komponennya saja, BUKAN paletnya

`img_1ea573af0981.jpg` (Olympus, foto+glass), `img_358dd2dbc4ad.jpg` (Corvus, cube wireframe +
section rail), `img_5741db6a9688.jpg` (ClearMark, terminal biru), `img_687acc718751.jpg`
(DeXchanger, DEX terminal), `img_d33d11e82921.jpg` (copy-trading ungu), `img_d4126db3f820.jpg`
(CE Web Platform portfolio), `img_f1bb2784a3bd.jpg` (LUMINA agent status card), `img_208b072dc53d.jpg`
(HIDO multi-device showcase).Contoh pola yang layak diadopsi: tabel aset + sparkline, order book
ladder, kartu status agent, empty-state jujur ("connect dulu"), donut alokasi.

## Aturan adaptasi (Amati → Tiru → Modifikasi)

- **TIRU**: layout, struktur, hierarchy, komponen (cards, tabs, badge, chart panel, alert list,
  stress simulator panel), gaya tipografi (display + mono tabular-nums), pattern 3D / visual hero
  bila feasible.
- **MODIFIKASI**: konten & data WAJIB data REAL dari API fund2. Semua angka marketing pada
  screenshot ($148.4M AUM, 1,240+ investors, 99.2% retention, 142K ticks/s, 0.42ms, equity
  $9,734.00, PnL −$127.89, drawdown 3.074%, dst) adalah copy reference — ganti dengan data asli
  atau hilangkan bila belum ada.
- **JANGAN**: mengubah backend; memajang data dummy sebagai data asli; menampilkan fitur yang
  belum ada di backend seolah berjalan (tampilkan "belum tersedia" yang jujur).
