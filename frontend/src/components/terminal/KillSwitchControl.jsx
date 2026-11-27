// Kontrol kill-switch versi "tenang" untuk header Terminal.
//
// Satu chip kecil yang selalu terlihat: hijau "AMAN · order diizinkan" atau
// merah "HALT · <mode>". Tidak ada paragraf penjelasan di layar utama; semua
// konsekuensi, alasan, dan checklist hidup di dialog konfirmasi.
//
// Kontrak keamanan (mengikuti backend, tidak diubah di sini):
//   - Aktivasi halt = emergency stop -> TANPA 2FA (PRD §18 mensyaratkan 2FA
//     untuk flatten/release, bukan aktivasi) supaya proteksi posisi tidak
//     pernah tertahan enrolment/challenge. Konfirmasi tetap dua sadar:
//     daftar konsekuensi + checkbox pengakuan di ConfirmDialog.
//   - Lepas halt = aksi sensitif -> ConfirmDialog dengan 2FA wajib, plus
//     checklist recovery saat halt global.
import { useState } from 'react'
import { desk, toast } from '../../lib/api'
import ConfirmDialog from '../ConfirmDialog'
import { useKillState, MODE_LABEL } from './killState'

export default function KillSwitchControl({ compact = false }) {
  const { armed, mode, reason, paused, checklist } = useKillState()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const isGlobalHalt = armed && mode === 'GLOBAL_HALT'

  const modeLabel = armed ? MODE_LABEL[mode] || 'order diblokir' : 'order diizinkan'
  const chipText = armed ? 'HALT' : 'AMAN'
  const title = armed
    ? `Kill-switch aktif: ${modeLabel}${reason ? ` · ${reason}` : ''}`
    : 'Kill-switch aman: order baru diizinkan selama pasar buka. Klik untuk menghentikan order baru.'

  async function arm() {
    setBusy(true)
    try {
      await desk.setKillSwitch(true, { mode: 'STOP_NEW_ORDERS' })
      setOpen(false)
      toast('HALT aktif', 'Semua order baru diblokir', 'down')
    } catch (ex) {
      toast('Gagal mengaktifkan kill-switch', ex.message, 'down')
      throw ex
    } finally {
      setBusy(false)
    }
  }

  async function release() {
    setBusy(true)
    try {
      await desk.setKillSwitch(false, { checklistAck: isGlobalHalt })
      setOpen(false)
      toast('Kill-switch dilepas', 'Order baru diizinkan kembali')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className={`term-kill ${compact ? 'term-kill--hdr' : ''} ${armed ? 'is-armed' : 'is-safe'}`.trim()}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={`Kill-switch ${chipText} · ${modeLabel}. Buka konfirmasi`}
        title={title}
      >
        <i className="term-kill-dot" aria-hidden="true" />
        {compact ? (
          <>
            <b>Kill Switch</b>
            {armed && <span className="term-kill-state">HALT</span>}
          </>
        ) : (
          <>
            <b>{chipText}</b>
            <span className="term-kill-sub"> · {armed ? modeLabel : 'order diizinkan'}</span>
          </>
        )}
      </button>

      {open && !armed && (
        <ConfirmDialog
          open={open}
          title="Hentikan semua order baru?"
          description="Kill-switch memblokir order baru untuk semua simbol dan strategi. Posisi yang sudah terbuka tidak ditutup."
          consequences={[
            'Order baru dari Terminal, strategi, dan LLM agent ditolak sampai kill-switch dilepas',
            'Posisi terbuka tetap berjalan; SL/TP yang sudah terpasang tetap berlaku',
            'Melepas kembali butuh konfirmasi dua langkah + 2FA',
          ]}
          ackLabel="Saya paham semua order baru akan diblokir sampai kill-switch dilepas"
          confirmLabel="Aktifkan HALT"
          busy={busy}
          onCancel={() => { if (!busy) setOpen(false) }}
          onConfirm={arm}
        />
      )}

      {open && armed && (
        <ConfirmDialog
          open={open}
          title={isGlobalHalt ? 'Lepas halt global' : 'Lepas kill-switch'}
          description={
            isGlobalHalt
              ? `Halt global aktif${reason ? ` · ${reason}` : ''}. Lepas hanya setelah seluruh checklist recovery terpenuhi.`
              : `Order baru akan diizinkan kembali (selama pasar buka)${reason ? ` · alasan halt: ${reason}` : ''}.`
          }
          consequences={
            isGlobalHalt
              ? [
                  'Order baru diizinkan kembali untuk semua strategi (selama pasar buka)',
                  'Halt global dilepas meski penyebabnya belum tentu selesai: pastikan checklist recovery sudah dipenuhi',
                  'Pelepasan tercatat di audit log (owner + 2FA + checklist ack)',
                ]
              : [
                  'Order baru diizinkan kembali (selama pasar buka)',
                  'Strategi aktif langsung bisa mengirim entry baru',
                  'Pelepasan tercatat di audit log (owner + 2FA)',
                ]
          }
          checklist={isGlobalHalt ? checklist : null}
          ackLabel={
            isGlobalHalt
              ? 'Saya paham halt global dilepas dan order baru diizinkan kembali'
              : 'Saya paham order baru akan diizinkan kembali'
          }
          requires2fa
          confirmLabel={isGlobalHalt ? 'Lepas halt global' : 'Lepas kill-switch'}
          busy={busy}
          onCancel={() => { if (!busy) setOpen(false) }}
          onConfirm={release}
        >
          {paused.length > 0 && (
            <p className="term-kill-note">Strategi dijeda: {paused.join(', ')}</p>
          )}
        </ConfirmDialog>
      )}
    </>
  )
}
