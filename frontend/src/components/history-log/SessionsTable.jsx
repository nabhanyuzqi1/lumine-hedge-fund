// Tabel sesi login aktif: login, terakhir aktif, masa berlaku, verifikasi 2FA.
// Server tidak mengirim perangkat/IP, jadi kolom itu tidak dikarang.
import { formatFull, toMs } from './reasons'

function timeText(value) {
  const stamp = toMs(value)
  return stamp === null ? '·' : formatFull(stamp)
}

export default function SessionsTable({ rows }) {
  return (
    <div className="lh-table-wrap">
      <table className="lh-table">
        <caption className="sr-only">Sesi login aktif</caption>
        <thead>
          <tr>
            <th scope="col">Login</th>
            <th scope="col">Terakhir aktif</th>
            <th scope="col">Berlaku sampai</th>
            <th scope="col">Verifikasi 2FA</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((session, index) => (
            <tr key={session?.id ?? index}>
              <td className="num lh-col-time">{timeText(session?.created_at)}</td>
              <td className="num lh-col-time">{timeText(session?.last_seen_at)}</td>
              <td className="num lh-col-time">{timeText(session?.expires_at)}</td>
              <td>{session?.['2fa_passed_at'] ? 'Sudah' : 'Belum'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
