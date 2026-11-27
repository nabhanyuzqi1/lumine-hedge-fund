// Badge environment (PRD v2.2 §21.1): DEV / DEMO / LIVE terlihat jelas.
// LIVE memakai visual yang tidak mungkin tertukar dengan DEMO: bidang merah
// bergetar + teks "LIVE · DANA NYATA" (bukan hanya warna — teks + ikon).
// Sumber label: /health (publik) sebelum login, /auth/me + login sesudahnya.
import { useEffect, useState } from 'react'
import { DEMO, getEnv, onEnv, fetchPublicEnv } from '../lib/api'

const LABEL = {
  dev: 'DEV',
  demo: 'DEMO',
  live: 'LIVE · DANA NYATA',
}

export default function EnvBadge() {
  const [env, setEnvLocal] = useState(getEnv())
  useEffect(() => {
    const off = onEnv(setEnvLocal)
    fetchPublicEnv()
    return off
  }, [])
  const key = DEMO ? 'demo' : env
  const isLive = !DEMO && key === 'live'
  return (
    <span
      className={`envbadge ${isLive ? 'envbadge-live' : key === 'dev' ? 'envbadge-dev' : 'envbadge-demo'}`}
      role="status"
      aria-label={`Environment: ${LABEL[key] || 'DEMO'}`}
      title={
        isLive
          ? 'Terhubung broker live: order memakai dana nyata'
          : key === 'dev'
            ? 'Environment pengembangan: bukan produksi'
            : 'Mode demo/paper: tidak ada dana nyata'
      }
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" className="envbadge-icon" fill="none" stroke="currentColor" strokeWidth="2">
        {isLive ? (
          <path d="M12 3 2.5 20h19L12 3Zm0 6v5m0 3v.5" strokeLinejoin="round" />
        ) : (
          <circle cx="12" cy="12" r="8.5" />
        )}
      </svg>
      {LABEL[key] || 'DEMO'}
    </span>
  )
}

// Strip peringatan live di bawah topbar, tampil di SEMUA halaman saat env
// live — pengingat permanen bahwa order memakai dana nyata (bukan warna
// saja: ada teks eksplisit).
export function LiveStrip() {
  const [env, setEnvLocal] = useState(getEnv())
  useEffect(() => onEnv(setEnvLocal), [])
  if (DEMO || env !== 'live') return null
  return (
    <div className="livestrip" role="alert">
      <strong>LIVE</strong> · Terhubung broker dana nyata: setiap order memakai uang sungguhan.
    </div>
  )
}
