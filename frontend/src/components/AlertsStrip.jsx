// Strip alert aktif (PRD v2.2 §20.2/§21.2, UI-D1): data {SEV, what, since}
// dari GET /alerts/active. Bentuk tampilan = SATU baris ringkas yang bisa
// dibuka, bukan panel besar: halaman Terminal adalah workstation, alert harus
// terbaca tanpa mengambil alih layar.
//
// Aturan tampilan:
//   - Tidak ada alert (dan tidak ada error) -> tidak merender apa pun.
//   - Ada alert -> satu tombol: "<n> peringatan · <pesan pertama>" + chevron.
//     Panel daftar alert hanya terbuka saat user meminta, kecuali SEV-1 baru
//     (satu kali, supaya insiden kritis tidak tersembunyi).
//   - SEV-3/SEV-4 (informasi) tidak pernah terbuka otomatis: panel selalu
//     mulai tertutup untuk tingkat itu. Ini permintaan pemilik, sekaligus
//     menjaga warna amber hanya untuk yang benar-benar perlu.
//   - Semua alert hilang -> panel otomatis menutup.
//   - Koneksi alert putus: satu baris amber "Alert tertunda (…)" dengan
//     umur data berjalan; saat pasar tutup status itu ditahan (bukan merah),
//     karena tidak ada data baru secara normal.
import { useEffect, useRef, useState } from 'react'
import { fetchAlertsActive } from '../lib/api'
import { isMarketClosed, useMarketStatus } from '../lib/market'
import { useDesk } from '../lib/useDesk'

const POLL_MS = 30000

function sevNumber(sev) {
  const n = Number(sev)
  return [1, 2, 3, 4].includes(n) ? n : 4
}

function fmtSince(iso) {
  if (!iso) return ''
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return String(iso)
  return t.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })
}

// Ringkas pesan alert menjadi satu baris: buang spasi ganda dan titik akhir,
// potong di batas kata supaya tidak ada elipsis di tengah kata.
function oneLine(text, max = 90) {
  const s = String(text || '').replace(/\s+/g, ' ').replace(/\s*\.$/, '').trim()
  if (s.length <= max) return s
  const cut = s.slice(0, max)
  return `${cut.slice(0, Math.max(0, cut.lastIndexOf(' ')))}…`
}

export default function AlertsStrip() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [lastOk, setLastOk] = useState(null)
  const [now, setNow] = useState(() => Date.now())
  const [open, setOpen] = useState(false)
  // Panel hanya boleh dibuka otomatis sekali per insiden SEV-1: setelah user
  // menutupnya, kita tidak memaksa buka lagi di setiap poll.
  const autoOpenedRef = useRef(false)
  const state = useDesk()
  const market = useMarketStatus(state?.symbol)
  const marketClosed = isMarketClosed(market)

  useEffect(() => {
    let alive = true
    async function poll() {
      try {
        const body = await fetchAlertsActive()
        if (alive) {
          setData(body)
          setErr(null)
          setLastOk(Date.now())
          // Auto-buka HANYA untuk SEV-1 pertama (sekali per insiden). Ini
          // dikerjakan di callback poll (event), bukan di effect, supaya tidak
          // ada setState sinkron di dalam effect. SEV-3/4 tidak pernah dibuka.
          const list = Array.isArray(body?.alerts) ? body.alerts : []
          const hasSev1 = list.some((a) => sevNumber(a.sev) === 1)
          if (!list.length) {
            autoOpenedRef.current = false
            setOpen(false)
          } else if (hasSev1 && !autoOpenedRef.current) {
            autoOpenedRef.current = true
            setOpen(true)
          }
        }
      } catch (ex) {
        if (alive) setErr(ex.message)
      }
    }
    poll()
    const t = setInterval(poll, POLL_MS)
    const tk = setInterval(() => setNow(Date.now()), 1000)
    return () => {
      alive = false
      clearInterval(t)
      clearInterval(tk)
    }
  }, [])

  const alerts = Array.isArray(data?.alerts) ? data.alerts : []
  // Urut dari paling berat: baris ringkas selalu menyebut yang paling penting.
  // Daftar alert pendek (biasanya 0-3), jadi salin+sort langsung tanpa memo.
  const sorted = [...alerts].sort((a, b) => sevNumber(a.sev) - sevNumber(b.sev))
  const topSev = sorted.length ? sevNumber(sorted[0].sev) : null
  const ageS = lastOk != null ? Math.max(0, Math.round((now - lastOk) / 1000)) : null

  // Tidak ada alert dan koneksi alert sehat: nol ruang di layar.
  if (!sorted.length && !err) return null

  if (!sorted.length) {
    // Hanya error: tetap satu baris, tanpa daftar (tidak ada isi).
    return (
      <div className="term-alert term-alert-msg is-warn" role="status">
        <i className="term-alert-dot" aria-hidden="true" />
        <span className="term-alert-text">
          {marketClosed
            ? 'Alert tertahan · pasar tutup'
            : `Alert tertunda${ageS != null ? ` · data ${ageS}s` : ''}`}
        </span>
        <span className="term-alert-sub">{err}</span>
      </div>
    )
  }

  const panelId = 'term-alert-panel'
  const tone = topSev <= 1 ? 'is-sev1' : topSev === 2 ? 'is-sev2' : 'is-sev3'
  const firstMsg = oneLine(sorted[0].what || 'alert tanpa deskripsi')

  return (
    <div className={`term-alert ${tone} ${err ? 'is-stale' : ''}`.trim()}>
      <button
        type="button"
        className="term-alert-btn"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        title={err ? `Koneksi alert terputus: ${err}` : 'Buka daftar alert'}
      >
        <i className="term-alert-dot" aria-hidden="true" />
        <span className="term-alert-text">
          <b>
            {sorted.length} peringatan
          </b>
          <span className="term-alert-first"> · {firstMsg}</span>
        </span>
        <svg
          className="term-alert-chev"
          viewBox="0 0 24 24"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
        </svg>
      </button>

      <div className={`term-alert-wrap ${open ? 'is-open' : ''}`.trim()} aria-hidden={!open}>
        <ul className="term-alert-list" id={panelId}>
          {sorted.map((a, i) => (
            <li key={`${a.key || 'alert'}-${i}`} className="term-alert-item">
              <span className={`term-alert-sev sev-${sevNumber(a.sev)}`}>SEV-{sevNumber(a.sev)}</span>
              <span className="term-alert-what" title={a.impact || a.what}>
                {a.what || 'Alert tanpa deskripsi'}
              </span>
              {a.since && <span className="term-alert-time">{fmtSince(a.since)}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
