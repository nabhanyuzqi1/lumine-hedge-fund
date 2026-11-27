// Primitif tampilan untuk pusat Pengaturan. Semua label berbahasa operator:
// tidak ada nama field, nama endpoint, atau path yang tampil di UI normal.
// Detail teknis hanya lewat <DebugOnly> di file pemanggil.

export function HubCard({ title, badge, note, tone = '', children }) {
  return (
    <section className={`sh-card ${tone}`.trim()}>
      <header className="sh-card-head">
        <h2 className="sh-card-title">{title}</h2>
        {badge}
      </header>
      {note && <p className="sh-card-note">{note}</p>}
      <div className="sh-card-body">{children}</div>
    </section>
  )
}

// Chip nilai AKTIF yang menempel di label field.
export function ActiveChip({ children, tone = '' }) {
  return <span className={`sh-active ${tone}`.trim()}>aktif: {children}</span>
}

export function StatusPill({ tone = '', children }) {
  return <span className={`sh-pill ${tone}`.trim()}>{children}</span>
}

// Keterangan kenapa sebuah kontrol belum bisa dipakai. Bukan tombol palsu.
export function LockedNote({ children }) {
  return (
    <p className="sh-locked">
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="4" y="10" width="16" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </svg>
      <span>{children}</span>
    </p>
  )
}

export function MetaRow({ label, value, hint }) {
  return (
    <div className="sh-meta" title={hint || undefined}>
      <span className="sh-meta-k">{label}</span>
      <span className="sh-meta-v">{value}</span>
    </div>
  )
}

// Saklar on/off. `checked` selalu nilai aktif atau draf, tidak pernah tebakan.
export function Switch({ checked, onChange, disabled = false, label, hint }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={hint || undefined}
      disabled={disabled}
      className={`sh-switch ${checked ? 'is-on' : ''}`.trim()}
      onClick={() => onChange(!checked)}
    >
      <span className="sh-switch-track" aria-hidden="true">
        <span className="sh-switch-thumb" />
      </span>
      <span className="sh-switch-text">{checked ? 'ON' : 'OFF'}</span>
    </button>
  )
}

export function EmptyLine({ children }) {
  return <p className="sh-empty">{children}</p>
}
