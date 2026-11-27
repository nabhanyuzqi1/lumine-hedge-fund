// Sub-tab 3: Audit & Sesi.
// Tabel audit ringkas (GET /audit) dan daftar sesi login (GET /auth/sessions).
// Tombol cabut sesi hanya muncul karena endpoint-nya memang ada
// (POST /auth/sessions/revoke-all) dan tetap lewat dialog konfirmasi.
import { useCallback, useEffect, useState } from 'react'
import { DEMO, desk, fetchAuthSessions, revokeAllSessions, toast } from '../../lib/api'
import ConfirmDialog from '../ConfirmDialog'
import { DebugOnly } from '../../lib/debug'
import AuditTable from './AuditTable'
import SessionsTable from './SessionsTable'

const AUDIT_LIMIT = 50

export default function AuditPanel() {
  const [audit, setAudit] = useState({ status: DEMO ? 'demo' : 'loading', rows: [] })
  const [sessions, setSessions] = useState({ status: DEMO ? 'demo' : 'loading', rows: [] })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const loadAudit = useCallback(() => {
    if (DEMO) return
    desk.audit(AUDIT_LIMIT)
      .then((rows) => {
        setAudit({ status: 'ready', rows: Array.isArray(rows) ? rows : [] })
      })
      .catch((error) => {
        const status = error.message === 'FORBIDDEN' ? 'forbidden' : error.message === 'DEMO' ? 'demo' : 'error'
        setAudit({ status, rows: [] })
      })
  }, [])

  const loadSessions = useCallback(() => {
    if (DEMO) return
    fetchAuthSessions()
      .then((body) => {
        const rows = Array.isArray(body) ? body : Array.isArray(body?.sessions) ? body.sessions : []
        setSessions({ status: 'ready', rows })
      })
      .catch(() => {
        setSessions({ status: 'error', rows: [] })
      })
  }, [])

  useEffect(() => {
    loadAudit()
    loadSessions()
  }, [loadAudit, loadSessions])

  async function revokeOthers() {
    setBusy(true)
    try {
      const result = await revokeAllSessions()
      const count = Number(result?.revoked ?? 0)
      toast('Sesi dicabut', count > 0 ? `${count} sesi lain dihentikan` : 'Tidak ada sesi lain yang aktif')
      setConfirmOpen(false)
      loadSessions()
    } catch (error) {
      toast('Gagal mencabut sesi', error.message === 'DEMO' ? 'Tidak tersedia di mode demo' : error.message)
      throw error
    } finally {
      setBusy(false)
    }
  }

  const auditRows = audit.rows.slice(0, AUDIT_LIMIT)
  const otherSessions = sessions.status === 'ready' ? Math.max(0, sessions.rows.length - 1) : 0

  return (
    <div className="lh-stack">
      <section className="lh-panel" aria-label="Jejak audit">
        <div className="lh-panel-head">
          <div className="lh-panel-title">
            <h2>Jejak audit</h2>
            <p>Aktivitas akun dan perubahan konfigurasi, terbaru dulu.</p>
          </div>
          <span className="lh-chip">{audit.status === 'ready' ? `${auditRows.length} baris` : '·'}</span>
        </div>

        {audit.status === 'loading' && <p className="lh-empty">Memuat jejak audit…</p>}
        {audit.status === 'demo' && <p className="lh-empty">Mode demo: jejak audit hanya tersedia di lingkungan operasional.</p>}
        {audit.status === 'forbidden' && <p className="lh-empty">Jejak audit hanya bisa dibuka oleh admin.</p>}
        {audit.status === 'error' && <p className="lh-empty">Jejak audit belum dapat dimuat. Coba muat ulang halaman.</p>}
        {audit.status === 'ready' && auditRows.length === 0 && <p className="lh-empty">Belum ada aktivitas tercatat.</p>}
        {audit.status === 'ready' && auditRows.length > 0 && <AuditTable rows={auditRows} />}

        <DebugOnly label="Data audit">
          <pre className="lh-debug">{JSON.stringify(auditRows.slice(0, 3), null, 2)}</pre>
        </DebugOnly>
      </section>

      <section className="lh-panel" aria-label="Sesi login">
        <div className="lh-panel-head">
          <div className="lh-panel-title">
            <h2>Sesi login</h2>
            <p>Sesi aktif untuk akun Anda. Cabut sesi lain bila ada perangkat yang tidak dikenal.</p>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setConfirmOpen(true)}
            disabled={sessions.status !== 'ready' || otherSessions === 0 || busy}
            title={otherSessions === 0 ? 'Tidak ada sesi lain yang aktif' : 'Cabut semua sesi selain sesi ini'}
          >
            Cabut sesi lain
          </button>
        </div>

        {sessions.status === 'loading' && <p className="lh-empty">Memuat daftar sesi…</p>}
        {sessions.status === 'demo' && <p className="lh-empty">Mode demo: daftar sesi hanya tersedia di lingkungan operasional.</p>}
        {sessions.status === 'error' && <p className="lh-empty">Daftar sesi belum dapat dimuat.</p>}
        {sessions.status === 'ready' && sessions.rows.length === 0 && <p className="lh-empty">Tidak ada sesi aktif.</p>}
        {sessions.status === 'ready' && sessions.rows.length > 0 && <SessionsTable rows={sessions.rows} />}

        <p className="lh-note">Server hanya mencatat waktu sesi, bukan perangkat atau alamat IP.</p>
      </section>

      <ConfirmDialog
        open={confirmOpen}
        title="Cabut sesi lain?"
        description="Semua sesi akun Anda selain sesi yang sedang dipakai akan dihentikan."
        consequences={[
          'Perangkat atau tab lain harus login ulang',
          'Sesi yang sedang Anda pakai tetap aktif',
          'Tindakan ini tidak bisa dibatalkan',
        ]}
        ackLabel="Saya paham sesi lain akan langsung berakhir"
        confirmLabel="Cabut sesi lain"
        busy={busy}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={revokeOthers}
      />
    </div>
  )
}
