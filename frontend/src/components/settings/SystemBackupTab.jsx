// Sub-tab 4 · Sistem & Backup.
// Kesehatan database & EA, kondisi backup terakhir, dan sesi login aktif.
// Aksi yang belum punya kanal di aplikasi tampil nonaktif dengan alasan singkat:
// tidak ada tombol yang berpura-pura bisa dijalankan.
import { useCallback, useEffect, useState } from 'react'
import ConfirmDialog from '../ConfirmDialog'
import { DebugOnly } from '../../lib/debug'
import { DEMO, fetchAuthSessions, revokeAllSessions, toast } from '../../lib/api'
import { EmptyLine, HubCard, LockedNote, MetaRow, StatusPill } from './ui'
import { fmtAge, fmtBytes, fmtTime } from './format'

const DRILL_LABEL = {
  ok: 'Lulus',
  failed: 'Gagal',
  error: 'Gagal',
}

export default function SystemBackupTab() {
  const [metrics, setMetrics] = useState(null)
  const [sessions, setSessions] = useState(() => (DEMO ? [] : null))
  const [sessErr, setSessErr] = useState('')
  const [metricsErr, setMetricsErr] = useState('')
  const [dlgOpen, setDlgOpen] = useState(false)
  const [revokeErr, setRevokeErr] = useState('')

  const load = useCallback(async () => {
    if (DEMO) return
    try {
      const res = await fetch('/metrics', { credentials: 'include' })
      if (res.ok) {
        setMetrics(await res.json())
        setMetricsErr('')
      } else {
        setMetricsErr('Status sistem belum bisa dimuat.')
      }
    } catch {
      setMetricsErr('Status sistem belum bisa dimuat.')
    }
    try {
      const rows = await fetchAuthSessions()
      setSessions(Array.isArray(rows) ? rows : [])
      setSessErr('')
    } catch {
      setSessErr('Daftar sesi belum bisa dimuat.')
    }
  }, [])

  useEffect(() => { Promise.resolve().then(load) }, [load])

  async function onRevoke() {
    setRevokeErr('')
    try {
      const res = await revokeAllSessions()
      toast('Sesi lain dicabut', `${res?.revoked ?? 0} sesi lain dikeluarkan`)
      setDlgOpen(false)
      await load()
    } catch (ex) {
      const message = ex?.message === 'DEMO'
        ? 'Aksi tidak tersedia di mode demo.'
        : 'Sesi lain belum bisa dicabut. Coba lagi.'
      setRevokeErr(message)
      throw new Error(message)
    }
  }

  const db = metrics?.db
  const ea = metrics?.ea || {}
  const backup = metrics?.backup || {}
  const drill = metrics?.drill || {}
  const services = metrics?.api?.services || {}
  const serviceEntries = Object.values(services)
  const servicesActive = serviceEntries.filter((s) => s === 'active').length
  const eaOnline = ea.last_seen_age_s != null && ea.last_seen_age_s <= (ea.offline_threshold_s || 60)
  const backupAge = backup.age_s
  // Verdict dari server: satu definisi (max_age_s) dipakai gate dan UI.
  const backupFresh = typeof backup.fresh === 'boolean'
    ? backup.fresh
    : backupAge != null && backupAge < 86400
  const lastSessions = sessions || []

  return (
    <div className="sh-grid sh-grid-main">
      <HubCard
        title="Kesehatan sistem"
        badge={(
          <StatusPill tone={metricsErr ? 'is-down' : db?.available ? 'is-up' : 'is-warn'}>
            {metricsErr ? 'TIDAK TERSEDIA' : db?.available ? 'SEHAT' : 'PERLU DIPERIKSA'}
          </StatusPill>
        )}
      >
        {metricsErr ? (
          <EmptyLine>{metricsErr}</EmptyLine>
        ) : !metrics ? (
          <EmptyLine>Memuat status sistem…</EmptyLine>
        ) : (
          <div className="sh-meta-list">
            <MetaRow
              label="Database"
              value={db?.available ? `terhubung · ${db.latency_ms != null ? `${Math.round(db.latency_ms)} ms` : '·'}` : 'tidak terhubung'}
            />
            <MetaRow
              label="Koneksi database"
              value={db?.connections != null ? `${db.connections} dari ${db.max_connections ?? '·'}` : '·'}
            />
            <MetaRow label="Ukuran database" value={fmtBytes(db?.size_bytes)} />
            <MetaRow
              label="Koneksi EA"
              value={ea.last_seen_age_s == null
                ? 'belum pernah terhubung'
                : eaOnline ? `online · ${fmtAge(ea.last_seen_age_s)} lalu` : `offline · ${fmtAge(ea.last_seen_age_s)} lalu`}
            />
            <MetaRow label="Uptime API" value={fmtAge(metrics.api?.uptime_s)} />
            <MetaRow
              label="Layanan internal"
              value={serviceEntries.length ? `${servicesActive} dari ${serviceEntries.length} aktif` : '·'}
            />
          </div>
        )}
      </HubCard>

      <HubCard
        title="Backup & pemulihan"
        badge={(
          <StatusPill tone={backupFresh ? 'is-up' : backupAge != null ? 'is-warn' : ''}>
            {backupFresh ? 'BACKUP SEGAR' : backupAge != null ? 'BACKUP LAMA' : 'BELUM ADA'}
          </StatusPill>
        )}
        note="Backup berjalan otomatis setiap hari. Yang ditampilkan adalah kondisi backup terakhir yang tercatat."
      >
        <div className="sh-meta-list">
          <MetaRow label="Umur backup terakhir" value={backupAge != null ? fmtAge(backupAge) : 'belum ada'} />
          <MetaRow label="Batas dianggap basi" value={backup.max_age_s ? fmtAge(backup.max_age_s) : '26 jam'} />
          <MetaRow label="Waktu backup" value={backup.last?.ts ? fmtTime(backup.last.ts) : '·'} />
          <MetaRow label="Ukuran" value={fmtBytes(backup.last?.bytes)} />
          <MetaRow
            label="Salinan luar lokasi"
            value={backup.last?.offsite == null ? '·' : backup.last.offsite ? 'terkirim' : 'gagal'}
          />
          <MetaRow
            label="Uji pemulihan terakhir"
            value={drill.status ? `${DRILL_LABEL[drill.status] || 'selesai'} · ${fmtTime(drill.ts)}` : 'belum pernah'}
          />
        </div>
        <div className="sh-actions">
          <button type="button" className="btn btn-primary sh-btn" disabled>Jalankan backup</button>
          <button type="button" className="btn sh-btn" disabled>Pulihkan dari backup</button>
        </div>
        <LockedNote>
          Menjalankan backup dan memulihkan data belum punya kanal dari aplikasi ini: keduanya
          berjalan lewat prosedur server. Status di atas hanya untuk pemantauan.
        </LockedNote>
        {drill.error && <p className="sh-field-hint">Uji pemulihan terakhir mencatat kegagalan yang perlu ditinjau.</p>}
        <DebugOnly label="backup">{JSON.stringify({ archive: backup.last?.archive, drill: drill.status })}</DebugOnly>
      </HubCard>

      <HubCard
        title="Sesi login aktif"
        badge={<StatusPill>{lastSessions.length ? `${lastSessions.length} sesi` : '·'}</StatusPill>}
        note="Perangkat tidak dilaporkan aplikasi; urutan di bawah berdasarkan aktivitas terakhir."
      >
        {sessErr ? (
          <EmptyLine>{sessErr}</EmptyLine>
        ) : sessions == null ? (
          <EmptyLine>Memuat sesi…</EmptyLine>
        ) : lastSessions.length === 0 ? (
          <EmptyLine>Belum ada sesi login lain yang tercatat.</EmptyLine>
        ) : (
          <div className="sh-table-wrap">
            <table className="sh-table sh-sessions">
              <thead>
                <tr>
                  <th scope="col">Sesi</th>
                  <th scope="col">Dibuat</th>
                  <th scope="col">Terakhir aktif</th>
                  <th scope="col">Kedaluwarsa</th>
                  <th scope="col">2FA</th>
                </tr>
              </thead>
              <tbody>
                {lastSessions.map((s, i) => (
                  <tr key={s.id}>
                    <td>Sesi {i + 1}</td>
                    <td className="sh-num">{fmtTime(s.created_at)}</td>
                    <td className="sh-num">{fmtTime(s.last_seen_at)}</td>
                    <td className="sh-num">{fmtTime(s.expires_at)}</td>
                    <td>{s['2fa_passed_at'] ? 'terverifikasi' : 'belum'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="sh-actions">
          <button type="button" className="btn sh-btn" onClick={() => { setRevokeErr(''); setDlgOpen(true) }} disabled={DEMO}>
            Cabut sesi lain
          </button>
          <button type="button" className="btn sh-btn" onClick={load} disabled={DEMO}>Muat ulang</button>
        </div>
        {DEMO && <LockedNote>Mode demo: daftar sesi dan pencabutan sesi tidak tersedia.</LockedNote>}
        <DebugOnly label="sesi">{JSON.stringify(lastSessions.slice(0, 2).map((s) => s.id))}</DebugOnly>
      </HubCard>

      <ConfirmDialog
        open={dlgOpen}
        title="Cabut semua sesi lain?"
        description="Semua sesi login selain sesi saat ini akan diakhiri."
        consequences={[
          'Perangkat lain yang masih login akan keluar dan perlu login ulang',
          'Sesi saat ini tetap aktif',
          'Pencabutan tercatat permanen di riwayat audit',
        ]}
        ackLabel="Saya paham perangkat lain akan keluar"
        requires2fa
        confirmLabel="Cabut sesi lain"
        onCancel={() => { setDlgOpen(false); setRevokeErr('') }}
        onConfirm={onRevoke}
      >
        {revokeErr && <p className="sh-field-err">{revokeErr}</p>}
      </ConfirmDialog>
    </div>
  )
}
