// Daftar usulan perbaikan strategi dengan aksi Setujui / Tolak. Alur
// keputusan sama dengan panel approval yang sudah ada: dialog konfirmasi
// dengan kode 2FA, keputusan permanen, daftar dimuat ulang setelahnya.
import { useState } from 'react'
import { desk, toast } from '../../lib/api'
import ConfirmDialog from '../ConfirmDialog'
import { DebugOnly } from '../../lib/debug'
import { dateLabel } from './format'

const STATUS = {
  PROPOSED: { label: 'Menunggu keputusan', tone: 'is-warn' },
  APPROVED: { label: 'Disetujui', tone: 'is-up' },
  REJECTED: { label: 'Ditolak', tone: 'is-down' },
  DEPLOYED: { label: 'Sudah diterapkan', tone: 'is-up' },
}

const VERDICT = { LULUS: 'Lulus', GAGAL: 'Gagal', PENDING: 'Belum dinilai' }

// Hanya field yang benar-benar dikirim backend yang ditampilkan. Strategi dan
// dampak tidak selalu ada pada respons usulan; baris kosong lebih berisik
// daripada tidak ditampilkan sama sekali.
function metaOf(proposal) {
  const rows = []
  const strategy = proposal.strategy_name || proposal.strategy
  if (strategy) rows.push({ label: 'Strategi', value: strategy })
  const impact = proposal.expected_impact || proposal.impact
  if (impact) rows.push({ label: 'Dampak diharapkan', value: impact })
  rows.push({ label: 'Hasil evaluasi', value: VERDICT[proposal.verdict] || 'Belum dinilai' })
  rows.push({ label: 'Reviewer', value: proposal.reviewer || '—' })
  return rows
}

function decisionErrorText(ex) {
  if (ex?.code === 'OWNER') return 'Hanya owner yang boleh memutuskan usulan.'
  if (ex?.code === 'FORBIDDEN') return 'Sesi ini tidak punya izin memutuskan usulan.'
  if (ex?.code === 'CONFLICT') return 'Usulan ini sudah diputuskan sebelumnya.'
  if (ex?.code === 'NOT_FOUND') return 'Usulan tidak ditemukan.'
  if (ex?.code === 'DEMO') return 'Keputusan usulan tidak tersedia di mode demo.'
  return ex?.message || 'Keputusan gagal disimpan.'
}

export default function ProposalCards({ rows, loading, errorCode, onRefresh }) {
  const [dialog, setDialog] = useState(null)
  const [rationale, setRationale] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const list = rows || []
  const approve = dialog?.decision === 'APPROVED'

  const openDecision = (proposal, decision) => {
    setMessage('')
    setRationale('')
    setDialog({ proposal, decision })
  }

  const submit = async () => {
    if (!dialog) return
    setBusy(true)
    try {
      const result = await desk.decideProposal(
        dialog.proposal.id,
        dialog.decision,
        rationale.trim() || null,
      )
      if (result?.status === 'DEPLOYED') {
        toast('Usulan disetujui', `${dialog.proposal.title || 'Usulan'} diterapkan`, 'up')
      } else {
        toast('Usulan ditolak', dialog.proposal.title || '', '')
      }
      setDialog(null)
      setMessage('')
      await onRefresh?.()
    } catch (ex) {
      if (['OWNER', 'FORBIDDEN', 'CONFLICT', 'NOT_FOUND'].includes(ex?.code)) {
        setDialog(null)
        setMessage(decisionErrorText(ex))
        await onRefresh?.()
      } else {
        setMessage(decisionErrorText(ex))
      }
    } finally {
      setBusy(false)
    }
  }

  let body
  if (loading) {
    body = <p className="agx-empty">Memuat usulan…</p>
  } else if (errorCode === 'DEMO') {
    body = <p className="agx-empty">Mode demo: daftar usulan hanya tersedia pada data nyata.</p>
  } else if (errorCode) {
    body = <p className="agx-empty">Daftar usulan belum bisa dimuat.</p>
  } else if (list.length === 0) {
    body = <p className="agx-empty">Belum ada usulan perbaikan strategi.</p>
  } else {
    body = (
      <div className="agx-proposals">
        {list.map((proposal) => {
          const status = STATUS[proposal.status] || { label: 'Tercatat', tone: 'is-idle' }
          return (
            <article className="agx-proposal" key={proposal.id}>
              <header className="agx-proposal-head">
                <span className={`agx-chip ${status.tone}`}>{status.label}</span>
                {proposal.week && <span className="agx-chip is-idle">Minggu {proposal.week}</span>}
                {(proposal.decided_at || proposal.deployed_at) && (
                  <span className="agx-time">{dateLabel(proposal.decided_at || proposal.deployed_at)}</span>
                )}
              </header>

              <h3 className="agx-proposal-title">{proposal.title || 'Usulan perbaikan strategi'}</h3>

              <dl className="agx-kv">
                {metaOf(proposal).map((row) => (
                  <div key={row.label}>
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>

              {proposal.status === 'PROPOSED' && (
                <div className="agx-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={busy}
                    onClick={() => openDecision(proposal, 'APPROVED')}
                  >
                    Setujui
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm agx-btn-danger"
                    disabled={busy}
                    onClick={() => openDecision(proposal, 'REJECTED')}
                  >
                    Tolak
                  </button>
                </div>
              )}

              <DebugOnly label="detail">
                {proposal.id} · status {proposal.status || '—'} · verdict {proposal.verdict || '—'}
              </DebugOnly>
            </article>
          )
        })}
      </div>
    )
  }

  return (
    <section className="agx-tab" aria-label="Usulan perbaikan strategi">
      <header className="agx-panel-head">
        <div>
          <h2 className="agx-h2">Usulan perbaikan</h2>
          <p className="agx-hint">
            Setujui atau tolak usulan; keputusan butuh kode 2FA dan tercatat permanen.
          </p>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onRefresh?.()}>
          Muat ulang
        </button>
      </header>

      {message && <p className="agx-note is-down" role="alert">{message}</p>}
      {body}
      <DebugOnly label="sumber">/improve/proposals · keputusan owner + 2FA</DebugOnly>

      <ConfirmDialog
        open={!!dialog}
        title={dialog ? `${approve ? 'Setujui' : 'Tolak'} usulan` : ''}
        description={dialog ? (dialog.proposal.title || 'Usulan perbaikan strategi') : ''}
        consequences={approve
          ? [
              'Perubahan dari usulan langsung diterapkan ke strategi terkait',
              'Keputusan bersifat permanen dan tercatat di riwayat',
              'Butuh kode 2FA yang masih berlaku',
            ]
          : [
              'Usulan ditutup tanpa mengubah strategi',
              'Keputusan bersifat permanen dan tercatat di riwayat',
            ]}
        ackLabel={approve
          ? 'Saya paham usulan ini akan diterapkan dan keputusannya permanen'
          : 'Saya paham usulan ini akan ditolak dan keputusannya permanen'}
        requires2fa
        confirmLabel={approve ? 'Setujui usulan' : 'Tolak usulan'}
        busy={busy}
        onCancel={() => {
          if (!busy) setDialog(null)
        }}
        onConfirm={submit}
      >
        <label className="agx-field">
          <span className="agx-label">Catatan keputusan (opsional)</span>
          <input
            className="agx-input"
            value={rationale}
            placeholder="Alasan singkat keputusan ini"
            onChange={(e) => setRationale(e.target.value)}
          />
        </label>
      </ConfirmDialog>
    </section>
  )
}
