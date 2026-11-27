// Filter bar Riwayat (PRD v2.2 §21.3): strategi, symbol, reason code,
// rentang tanggal + tombol clear. Opsi dropdown di-derive dari data
// /orders yang sudah ada (client-side, tanpa endpoint baru). Filter
// status tetap di page head (perilaku lama dipertahankan).
//
// Tata letak: satu baris `flex-wrap` dengan align-items:flex-end, jadi label
// kecil dan kontrol (select / segmen tanggal / tombol) duduk sejajar baseline
// dalam satu garis. Kelas `lld-` didefinisikan di styles/ledger-lab-guard.css.
const RANGES = [
  { id: 'hari', label: 'Hari ini' },
  { id: '7h', label: '7 hari' },
  { id: 'semua', label: 'Semua' },
]

function SelectField({ label, value, options, allLabel, onChange }) {
  return (
    <label className="lld-field">
      <span className="lld-field-label">{label}</span>
      <select
        className={`lld-select ${value ? 'is-active' : ''}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{allLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  )
}

export default function HistoryFilters({ filters, onChange, options, onClear, dirty }) {
  return (
    <div className="lld-toolbar" role="group" aria-label="Filter riwayat order">
      <SelectField
        label="Strategi"
        value={filters.strategi}
        options={options.strategi}
        allLabel="Semua strategi"
        onChange={(v) => onChange({ strategi: v })}
      />
      <SelectField
        label="Symbol"
        value={filters.symbol}
        options={options.symbol}
        allLabel="Semua symbol"
        onChange={(v) => onChange({ symbol: v })}
      />
      <SelectField
        label="Reason code"
        value={filters.reason}
        options={options.reason}
        allLabel="Semua reason"
        onChange={(v) => onChange({ reason: v })}
      />
      <div className="lld-field">
        <span className="lld-field-label">Tanggal</span>
        <div className="lld-tabs" role="group" aria-label="Rentang tanggal">
          {RANGES.map((r) => (
            <button
              key={r.id}
              type="button"
              className={`lld-tab ${filters.range === r.id ? 'is-active' : ''}`}
              aria-pressed={filters.range === r.id}
              onClick={() => onChange({ range: r.id })}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {/* spasi pengisi: Clear menempel kanan selama baris masih muat, dan
          turun ke baris berikutnya (bukan mengecil) saat layar sempit */}
      <span className="lld-toolbar-spacer" aria-hidden="true" />
      <span className={`lld-count ${dirty ? 'is-on' : ''}`} aria-live="polite">{dirty ? 'Filter aktif' : ''}</span>
      <button
        type="button"
        className="btn btn-ghost btn-sm lld-clear"
        onClick={onClear}
        disabled={!dirty}
        title="Reset semua filter (termasuk status) ke nilai awal"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className="btn-icon">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
        Clear
      </button>
    </div>
  )
}
