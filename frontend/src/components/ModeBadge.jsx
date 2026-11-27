// UI-D3c · satu sumber semantik badge mode data (LIVE / PAPER / DEMO).
//
// Semantik (wajib konsisten lintas halaman, jangan dikarang ulang):
//   LIVE  = data akun broker: baris GET /orders dan GET /positions (dieksekusi
//           Bridge EA), plus equity snapshot /risk/portfolio. Di fund2 tidak
//           ada pemisahan "REAL": satu akun broker = LIVE.
//           PENTING: LIVE berarti "sumbernya akun broker", BUKAN otomatis
//           "dana riil". Status dana riil ditentukan FUND2_ENV (config.py):
//           selama env != "live", live trading belum diaktifkan dan eksekusi
//           ini bukan uang nyata. Tooltip + legenda menuliskan env aktual
//           supaya badge tidak pernah berbohong ke arah "uang nyata".
//   PAPER = ledger paper_orders: statistik strategi di Strategy Lab
//           (GET /strategies). Tidak ada uang berpindah.
//   DEMO  = mode demo frontend (?demo=1 / VITE_DEMO=1): data sintetis simulator.
//
// Named export + default export supaya bisa diimport ulang kartu lain
// (mis. UI-D4: P&L hero, PortfolioRiskCard, chip agregat).
import { getEnv } from '../lib/api'

export const MODE_INFO = {
  LIVE: {
    label: 'LIVE',
    legend: 'order & posisi akun broker (Bridge EA)',
  },
  PAPER: {
    label: 'PAPER',
    legend: 'statistik ledger simulasi strategi',
  },
  DEMO: {
    label: 'DEMO',
    legend: 'mode demo (?demo=1), data sintetis',
  },
}

const ORDER = ['LIVE', 'PAPER', 'DEMO']

// Env aplikasi (dev | demo | live) dari GET /health. Dipakai untuk memberi
// kualifikasi jujur pada badge LIVE: sumber broker, tapi dana riil hanya
// kalau env = live.
function liveTitle(env) {
  if (env === 'live') {
    return 'Dana broker nyata: setiap baris GET /orders dan GET /positions adalah eksekusi akun riil. Tidak ada badge REAL terpisah di fund2 (satu akun broker).'
  }
  return `Sumber data: akun broker via Bridge EA (bukan simulator, bukan ledger paper). Env aplikasi sekarang "${env}" — FUND2_ENV belum "live", jadi eksekusi ini belum memakai dana riil.`
}

function titleFor(key, env) {
  if (key === 'LIVE') return liveTitle(env)
  if (key === 'PAPER') {
    return 'Ledger paper (paper_orders): statistik strategi dari GET /strategies. Tidak ada uang berpindah; gerbang sebelum live.'
  }
  return 'Mode demo frontend (?demo=1 atau VITE_DEMO=1): data sintetis dari simulator, bukan data broker maupun ledger paper.'
}

export function ModeBadge({ mode = 'LIVE', className = '', showDot = true, label }) {
  const key = MODE_INFO[mode] ? mode : 'LIVE'
  const info = MODE_INFO[key]
  const title = titleFor(key, getEnv())
  return (
    <span
      className={`mode-badge mode-badge-${key.toLowerCase()} ${className}`.trim()}
      title={title}
      aria-label={`Sumber data ${key}: ${title}`}
    >
      {showDot && <i className="mode-badge-dot" aria-hidden="true" />}
      {label ?? info.label}
    </span>
  )
}

// Legenda arti badge: dipakai Dashboard & Riwayat agar pembaca tidak
// menyimpulkan angka paper/akun demo sebagai uang nyata (atau sebaliknya).
export function ModeLegend({ className = '' }) {
  const env = String(getEnv() || '').toLowerCase()
  const liveEnvNote = env && env !== 'live' ? ` · env aplikasi ${env}, dana riil belum aktif` : ''
  return (
    <p className={`mode-legend ${className}`.trim()}>
      <span className="mode-legend-title">Arti badge</span>
      {ORDER.map((k) => (
        <span className="mode-legend-item" key={k}>
          <ModeBadge mode={k} />
          <span className="mode-legend-text">
            {MODE_INFO[k].legend}
            {k === 'LIVE' ? liveEnvNote : ''}
          </span>
        </span>
      ))}
    </p>
  )
}

export default ModeBadge
