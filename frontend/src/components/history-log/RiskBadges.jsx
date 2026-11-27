// Kolom RISK tabel Riwayat: MAKSIMUM dua badge pendek per baris + tombol
// "+N" untuk alasan selebihnya. Tidak ada lagi teks alasan panjang yang
// membungkus belasan baris: seluruh alasan hanya ada di drawer detail.
import { analyzeOrder } from './reasons'

export default function RiskBadges({ order, onOpen }) {
  const analysis = analyzeOrder(order)
  const { verdict, groups, badges, hidden } = analysis
  if (!verdict) {
    return <span className="lh-risk-empty" aria-hidden="true">·</span>
  }
  const pass = verdict === 'LULUS'
  const labels = groups.length ? badges.map((badge) => badge.label) : [pass ? 'Lulus' : 'Ditolak']
  const summary = pass
    ? 'Risiko: lulus'
    : `Risiko: ditolak, ${groups.length} alasan`

  return (
    <span className={`lh-risk ${pass ? 'is-pass' : 'is-reject'}`} aria-label={summary}>
      {labels.map((label) => (
        <span key={label} className={`lh-badge ${pass ? 'is-pass' : 'is-reject'}`} title={label}>
          {label}
        </span>
      ))}
      {hidden > 0 && (
        <button
          type="button"
          className="lh-more"
          onClick={(event) => {
            event.stopPropagation()
            onOpen()
          }}
          aria-label={`Lihat ${hidden} alasan lain`}
        >
          +{hidden}
        </button>
      )}
    </span>
  )
}
