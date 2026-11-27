// Banner drift proses: prompt yang di-import saat API start berbeda dari isi
// file di disk. Kasus nyata 26 Nov 2026: UI menampilkan 2.0.0 karena
// fund2-api belum direstart setelah PROMPT_VERSION dinaikkan.
//
// Sumber: GET /version (login wajib). Poll 60 s; tidak memblokir render.
import { useEffect, useState } from 'react'
import { DEMO, fetchVersion } from '../lib/api'

export default function StaleCodeBanner() {
  const [ver, setVer] = useState(null)

  useEffect(() => {
    if (DEMO) return undefined
    let alive = true
    const load = () => {
      fetchVersion()
        .then((body) => { if (alive) setVer(body) })
        .catch(() => { if (alive) setVer(null) })
    }
    load()
    const timer = setInterval(load, 60000)
    return () => { alive = false; clearInterval(timer) }
  }, [])

  if (!ver?.stale_code) return null
  return (
    <div
      role="alert"
      style={{
        background: 'var(--warn-bg, #4a2d00)',
        color: 'var(--warn-fg, #ffce7a)',
        borderBottom: '1px solid rgba(255, 206, 122, 0.35)',
        padding: '8px 16px',
        fontSize: 13,
        lineHeight: 1.4,
      }}
    >
      <strong>Proses API basi.</strong>{' '}
      Berjalan dengan prompt {ver.running_prompt_version || '·'}, kode di disk{' '}
      {ver.disk_prompt_version || '·'}.
      Restart <code>fund2-api</code> dan <code>fund2-llm-agent</code> agar setelan
      yang tersimpan benar-benar dipakai.
    </div>
  )
}
