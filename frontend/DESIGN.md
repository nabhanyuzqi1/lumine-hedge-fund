# DESIGN.md — Lumine Fund v2 UI

Dunia visual: **monochrome glass institutional** — ground near-black zinc, panel
kaca frosted, aksen putih monokrom, warna hanya untuk semantik pasar. Satu ide
gerak ("the pulse"). Mode Operate: presisi dan restraint, bukan ekspresi.

Palet emas hangat lama sudah diganti; token legacy (`--gold*`) dipertahankan
sebagai alias ke putih supaya aturan CSS lama tidak perlu disunting.

## Tokens (`src/styles/tokens.css`)

| Token | Nilai | Peran |
|---|---|---|
| `--bg-app` / `--bg` / `--bg-deep` | `#09090b` / `#09090b` / `#050506` | ground halaman / inset |
| `--surface-1` / `--surface-sub` / `--surface-3` | `#111113` / `#18181b` / `#212126` | panel, sub-panel, hover |
| `--border-subtle` / `--line` / `--line-strong` | `rgba(39,39,42,.8)` / `#27272a` / `#3f3f46` | hairline / border / border input |
| `--text` / `--text-muted` / `--text-faint` | `#f4f5f8` / `#8b909e` / `#838a9a` | teks primer/sekunder/tersier (abu netral, bukan krem) |
| `--accent` / `--gold*` | `#f4f5f8` / alias ke putih | aksen brand, CTA (monokrom) |
| `--emerald` / `--crimson` / `--amber` | `#10b981` / `#ef4444` / `#f59e0b` | naik / turun / peringatan |
| `--alert-bg` / `--alert-border` / `--alert-text` | `rgba(69,26,3,.3)` / `rgba(245,158,11,.3)` / `#fde68a` | strip alert amber-950/30 + amber-200 |
| `--font-sans` | IBM Plex Sans | UI |
| `--font-mono` | IBM Plex Mono | harga, angka tabel (tabular) |

## Tipografi

- Display: Plex Sans 700, tracking -0.035em, ukuran clamp.
- Harga: Plex Mono 600, tabular-nums, tracking -0.01em.
- Label chip: mono 10-11px, letter-spacing 0.08-0.2em.
- Skala: 10 / 11 / 12 / 13 / 14 / 15 / 17 / 21 / 24 / 30-42 (login) / 56-88 (harga login).

## Komponen

`btn` (primary emas, ghost, buy/sell), `card` + `card-head`, `chip` (up/down/gold),
`field` + `input` (mono, caret emas), `table.data` (header uppercase 11px),
`toast` (dot status, bukan border sisi), `dialog` (konfirmasi order),
`session` pill, `killswitch` (hold-to-arm 1.2s dengan progress fill),
`strategy` row (track badge, stats, equity curve canvas), `eventline` timeline,
`alerts-strip` (amber gelap, grid 1/2/4 kolom: badge SEV · pesan · waktu),
`candlechart` (lightweight-charts: candlestick + volume, price line LIVE dashed,
status loading/kosong/error sebagai overlay, fallback TF ditampilkan sebagai note).

Utility `.tnum` (`font-variant-numeric: tabular-nums`) wajib untuk semua harga,
P/L, volume, dan timestamp supaya digit tidak bergeser saat tick.

## Chart (`src/components/CandleChart.jsx`)

- Sumber data: `GET /candles?symbol&tf&limit` lewat `src/lib/candles.js`
  (M1/M5/M15/H1/H4/D1; tf tinggi yang belum aktif jatuh ke M15 + `fallback: true`).
- Realtime: tick SSE terakhir memperbarui high/low/close candle aktif; candle
  baru dibuka saat periode timeframe berganti.
- Scrollback: geser ke kiri memicu `limit` berikutnya (500 → 1000 → 2000),
  candle lama di-prepend, viewport digeser sebesar jumlah bar baru (zoom tetap).

## Motion

- Satu signature moment: **the pulse** — setiap tick, denyut radial lembut dari
  titik harga terakhir pada chart (PriceChart), plus flash arah pada harga topbar.
- Transisi lain: 180ms ease-out untuk hover/focus/dialog. Reduced-motion:
  animasi dimatikan, chart tetap digambar statis.
- Tanpa entrance animation per-section.

## Browser surfaces

Scrollbar, selection (emas), focus ring (emas 2px), caret, tabular numerals:
semua di-theme dari tokens (`styles/global.css`).

## Responsif

- ≤1080px: grid dashboard jadi 1 kolom.
- ≤900px: login jadi market band atas + form bawah.
- ≤720px: bottom nav tab; tabel posisi jadi tumpukan; kolom riwayat dipangkas;
  kill-switch full-width. Safe-area inset untuk bottom nav.

## Data

- Mode real: endpoint fund2-api (POST /auth/login, POST /orders, GET /orders,
  GET /positions, SSE /stream) via proxy Vite → 3110.
- Mode demo (`VITE_DEMO=1` atau `?demo=1`): simulator `src/lib/demo.js`,
  selalu ditandai badge DEMO/SIMULASI di UI. Build produksi default real.
