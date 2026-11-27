// Sub-tab 2 · Kontrol Darurat & Recovery.
// Tombol darurat selalu lewat dialog konfirmasi + kode 2FA: tidak ada aksi yang
// menembak langsung. Checklist recovery dihitung dari kondisi sistem saat ini,
// bukan centang manual.
import { useCallback, useEffect, useMemo, useState } from 'react'
import ConfirmDialog from '../ConfirmDialog'
import { DEMO, desk, fetchKillSwitchStatus, toast } from '../../lib/api'
import { useDesk } from '../../lib/useDesk'
import { DebugOnly } from '../../lib/debug'
import { EmptyLine, HubCard, MetaRow, StatusPill } from './ui'
import { fmtAge, fmtTime } from './format'

const MODE_LABEL = {
  STOP_NEW_ORDERS: 'Entry baru dihentikan',
  GLOBAL_HALT: 'Semua entry dihentikan',
  PAUSE_STRATEGY: 'Strategi dijeda',
  STOP_AND_FLATTEN: 'Dihentikan dan posisi ditutup',
}

const DEMO_STATUS = {
  state: { active: false, mode: null, reason: null, actor: null, activated_at: null },
  paused_strategies: [],
  recovery_checklist: [
    'Sumber masalah sudah ditemukan dan host aman',
    'Penghentian masih aktif selama verifikasi',
    'EA sudah hidup kembali tanpa mengirim order baru',
    'Snapshot posisi broker sudah diambil',
    'Rekonsiliasi posisi dan order cocok',
    'Heartbeat sudah diuji di staging',
    'Owner menyetujui resume trading',
  ],
}

const CHECK_TONE = {
  ok: 'is-up',
  todo: 'is-warn',
  manual: '',
  unknown: '',
}

const CHECK_TEXT = {
  ok: 'terpenuhi',
  todo: 'belum',
  manual: 'perlu keputusan',
  unknown: 'data belum ada',
}

export default function EmergencyTab() {
  const deskState = useDesk()
  const [status, setStatus] = useState(() => (DEMO ? DEMO_STATUS : null))
  const [metrics, setMetrics] = useState(null)
  const [loadErr, setLoadErr] = useState('')
  const [dlg, setDlg] = useState(null)
  const [typed, setTyped] = useState('')
  const [actionErr, setActionErr] = useState('')

  const load = useCallback(async () => {
    if (DEMO) return
    try {
      const [ksBody, metricsBody] = await Promise.all([
        fetchKillSwitchStatus(),
        fetch('/metrics', { credentials: 'include' })
          .then((res) => (res.ok ? res.json() : null))
          .catch(() => null),
      ])
      setStatus(ksBody)
      setMetrics(metricsBody)
      setLoadErr('')
    } catch {
      setLoadErr('Status darurat belum bisa dimuat.')
    }
  }, [])

  useEffect(() => { Promise.resolve().then(load) }, [load])

  const state = status?.state || {}
  const armed = !!state.active
  const isGlobalHalt = armed && state.mode === 'GLOBAL_HALT'

  const openPositions = Array.isArray(deskState?.positions)
    ? deskState.positions.filter((p) => (p?.status || 'OPEN') === 'OPEN').length
    : null

  const checklist = useMemo(() => {
    const ea = metrics?.ea || {}
    const eaOnline = ea.last_seen_age_s != null
      && ea.last_seen_age_s <= (ea.offline_threshold_s || 60)
    const mismatch = metrics?.reconciliation?.mismatch_24h
    const stuck = metrics?.orders?.stuck_sent_60s
    const dbOk = metrics?.db?.available
    const known = (v) => v != null

    return [
      {
        key: 'halt',
        label: 'Penghentian entry masih aktif selama verifikasi',
        state: armed ? 'ok' : 'todo',
        detail: armed ? MODE_LABEL[state.mode] || 'aktif' : 'Sistem sedang menerima order baru',
      },
      {
        key: 'ea',
        label: 'EA terhubung kembali',
        state: known(ea.last_seen_age_s) ? (eaOnline ? 'ok' : 'todo') : 'unknown',
        detail: known(ea.last_seen_age_s)
          ? `Sinyal terakhir ${fmtAge(ea.last_seen_age_s)} lalu`
          : 'Belum ada laporan koneksi',
      },
      {
        key: 'positions',
        label: 'Tidak ada posisi terbuka',
        state: openPositions == null ? 'unknown' : openPositions === 0 ? 'ok' : 'todo',
        detail: openPositions == null ? 'Daftar posisi belum termuat' : `${openPositions} posisi terbuka`,
      },
      {
        key: 'recon',
        label: 'Posisi dan order cocok dengan broker',
        state: known(mismatch) ? (mismatch === 0 ? 'ok' : 'todo') : 'unknown',
        detail: known(mismatch) ? `${mismatch} selisih dalam 24 jam` : 'Data rekonsiliasi belum ada',
      },
      {
        key: 'stuck',
        label: 'Tidak ada order macet',
        state: known(stuck) ? (stuck === 0 ? 'ok' : 'todo') : 'unknown',
        detail: known(stuck) ? `${stuck} order macet` : 'Data order belum ada',
      },
      {
        key: 'db',
        label: 'Database sehat',
        state: known(dbOk) ? (dbOk ? 'ok' : 'todo') : 'unknown',
        detail: known(dbOk) ? (dbOk ? 'Terhubung' : 'Tidak terhubung') : 'Status database belum ada',
      },
      {
        key: 'owner',
        label: 'Owner menyetujui resume trading',
        state: 'manual',
        detail: 'Keputusan manusia, tidak dihitung otomatis',
      },
    ]
  }, [metrics, armed, state.mode, openPositions])

  const checked = checklist.filter((i) => i.state === 'ok').length
  const total = checklist.length

  function openAction(kind) {
    setTyped('')
    setActionErr('')
    setDlg(kind)
  }

  async function onConfirm() {
    try {
      if (dlg === 'stop') {
        await desk.setKillSwitch(true, {
          mode: 'STOP_NEW_ORDERS',
          reason: 'Dihentikan manual dari halaman Pengaturan',
        })
        toast('Entry baru dihentikan', 'Semua order baru diblokir sampai penghentian dilepas', 'down')
      } else if (dlg === 'flatten') {
        const res = await desk.flatten()
        toast('Posisi ditutup', `${res?.flatten?.requested ?? 0} posisi dikirim ke broker`, 'down')
      } else if (dlg === 'release') {
        await desk.setKillSwitch(false, { checklistAck: isGlobalHalt })
        toast('Penghentian dilepas', 'Order baru diizinkan kembali')
      }
      setDlg(null)
      await load()
    } catch (ex) {
      const message = ex?.message === 'DEMO'
        ? 'Aksi tidak tersedia di mode demo.'
        : 'Aksi gagal dijalankan. Status di layar belum berubah.'
      setActionErr(message)
      await load()
      throw new Error(message)
    }
  }

  const statusTone = armed ? 'is-down' : 'is-up'
  const statusText = armed ? (MODE_LABEL[state.mode] || 'Penghentian aktif') : 'Sistem menerima order'

  return (
    <div className="sh-grid sh-grid-main">
      <HubCard
        title="Status penghentian"
        badge={<StatusPill tone={statusTone}>{armed ? 'AKTIF' : 'AMAN'}</StatusPill>}
        tone={armed ? 'is-alert' : ''}
      >
        {loadErr ? (
          <EmptyLine>{loadErr}</EmptyLine>
        ) : !status ? (
          <EmptyLine>Memuat status…</EmptyLine>
        ) : (
          <>
            <p className="sh-status-line">{statusText}</p>
            <div className="sh-meta-list">
              <MetaRow label="Alasan" value={state.reason || (armed ? 'tidak dilaporkan' : '·')} />
              <MetaRow label="Sejak" value={armed ? fmtTime(state.activated_at) : '·'} />
              <MetaRow label="Diaktifkan oleh" value={state.actor || '·'} />
              <MetaRow
                label="Strategi dijeda"
                value={(status.paused_strategies || []).length
                  ? (status.paused_strategies || []).join(', ')
                  : 'tidak ada'}
              />
              <MetaRow
                label="Posisi terbuka"
                value={openPositions == null ? '·' : `${openPositions} posisi`}
              />
              <MetaRow
                label="Koneksi EA"
                value={metrics?.ea?.last_seen_age_s == null
                  ? '·'
                  : `sinyal ${fmtAge(metrics.ea.last_seen_age_s)} lalu`}
              />
            </div>
            <DebugOnly label="status darurat">{JSON.stringify({ mode: status.state?.mode, source: status.state?.source })}</DebugOnly>
          </>
        )}
      </HubCard>

      <HubCard
        title="Aksi darurat"
        badge={<StatusPill tone="is-warn">BUTUH KONFIRMASI 2FA</StatusPill>}
        tone="is-danger"
        note="Setiap tombol membuka dialog konsekuensi, lalu meminta kode 2FA. Tidak ada aksi yang langsung dieksekusi."
      >
        <div className="sh-danger-actions">
          <button
            type="button"
            className="sh-btn-danger"
            onClick={() => openAction('stop')}
            disabled={armed || DEMO}
          >
            <span className="sh-danger-title">Hentikan Entry Baru</span>
            <span className="sh-danger-sub">
              {armed ? 'Sudah aktif: order baru sedang diblokir' : 'Blokir semua order baru; posisi terbuka dibiarkan berjalan'}
            </span>
          </button>
          <button
            type="button"
            className="sh-btn-danger"
            onClick={() => openAction('flatten')}
            disabled={DEMO}
          >
            <span className="sh-danger-title">Flatten Semua Posisi</span>
            <span className="sh-danger-sub">Tutup semua posisi di harga pasar sekarang, tanpa bisa dibatalkan</span>
          </button>
          {armed && (
            <button type="button" className="sh-btn-release" onClick={() => openAction('release')} disabled={DEMO}>
              <span className="sh-danger-title">Lepas Penghentian</span>
              <span className="sh-danger-sub">
                {isGlobalHalt
                  ? 'Penghentian total: butuh checklist recovery dan persetujuan owner'
                  : 'Order baru diizinkan kembali melewati risk gate'}
              </span>
            </button>
          )}
        </div>
        {actionErr && <p className="sh-field-err">{actionErr}</p>}
        {DEMO && <p className="sh-field-hint">Mode demo: tombol darurat dinonaktifkan karena tidak ada eksekusi nyata.</p>}
      </HubCard>

      <HubCard
        title="Checklist recovery"
        badge={<StatusPill tone={armed ? 'is-warn' : ''}>{`${checked} dari ${total} terpenuhi`}</StatusPill>}
        note="Status tiap baris dihitung dari kondisi sistem saat ini, bukan centang manual."
      >
        <ul className="sh-checks">
          {checklist.map((item) => (
            <li key={item.key} className={`sh-check ${item.state}`.trim()}>
              <span className="sh-check-mark" aria-hidden="true">
                {item.state === 'ok' ? '✓' : item.state === 'todo' ? '!' : item.state === 'manual' ? '›' : '?'}
              </span>
              <span className="sh-check-body">
                <span className="sh-check-label">{item.label}</span>
                <span className="sh-check-detail">{item.detail}</span>
              </span>
              <StatusPill tone={CHECK_TONE[item.state]}>{CHECK_TEXT[item.state]}</StatusPill>
            </li>
          ))}
        </ul>
        {!armed && (
          <p className="sh-field-hint">
            Penghentian sedang tidak aktif. Checklist dipakai sebagai syarat sebelum order baru
            diizinkan kembali setelah halt.
          </p>
        )}
        <DebugOnly label="sumber checklist">
          {JSON.stringify((status?.recovery_checklist || []).length)} baris dari server
        </DebugOnly>
      </HubCard>

      <ConfirmDialog
        open={!!dlg}
        title={dlg === 'flatten'
          ? 'Flatten semua posisi'
          : dlg === 'release'
            ? (isGlobalHalt ? 'Lepas penghentian total' : 'Lepas penghentian entry')
            : 'Hentikan entry baru'}
        description={dlg === 'flatten'
          ? 'Semua posisi terbuka ditutup di harga pasar saat ini.'
          : dlg === 'release'
            ? 'Order baru akan diizinkan kembali melewati risk gate.'
            : 'Semua order baru diblokir sampai penghentian dilepas.'}
        consequences={dlg === 'flatten'
          ? [
              'Semua posisi terbuka ditutup dengan market order: laba/rugi terkunci sekarang',
              'Harga eksekusi bisa berbeda dari harga di layar, apalagi saat pasar cepat',
              'Tindakan ini tidak bisa dibatalkan setelah dijalankan',
            ]
          : dlg === 'release'
            ? [
                'Order baru akan diizinkan kembali setelah konfirmasi',
                'Pelepasan tercatat permanen di riwayat penghentian',
                isGlobalHalt ? 'Penghentian total mewajibkan checklist recovery diakui' : 'Risk gate tetap berlaku untuk order berikutnya',
              ]
            : [
                'Semua order baru ditolak sampai penghentian dilepas',
                'Posisi yang sudah terbuka tidak ditutup oleh aksi ini',
                'Aktivasi tercatat permanen dan mengirim notifikasi ke owner',
              ]}
        checklist={dlg === 'release' && isGlobalHalt ? (status?.recovery_checklist || []) : null}
        ackLabel={dlg === 'flatten'
          ? 'Saya paham semua posisi ditutup sekarang dan tidak bisa dibatalkan'
          : dlg === 'release'
            ? 'Saya paham order baru akan diizinkan kembali'
            : 'Saya paham semua order baru akan diblokir'}
        requires2fa
        confirmLabel={dlg === 'flatten' ? 'Flatten semua posisi' : dlg === 'release' ? 'Lepas penghentian' : 'Hentikan entry baru'}
        confirmDisabled={dlg === 'flatten' && typed.trim().toUpperCase() !== 'FLATTEN'}
        onCancel={() => { setDlg(null); setTyped('') }}
        onConfirm={onConfirm}
      >
        {dlg === 'flatten' && (
          <label className="sh-field-stack">
            <span className="sh-field-label">Ketik FLATTEN untuk mengaktifkan tombol konfirmasi</span>
            <input
              className="sh-input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder="FLATTEN"
              aria-label="Ketik FLATTEN"
              autoComplete="off"
            />
          </label>
        )}
      </ConfirmDialog>
    </div>
  )
}
