// Tabel jejak audit ringkas: waktu, aktor, aksi, objek.
// Dipisah dari panel supaya bisa dipakai ulang/diuji tanpa memuat data.
import { auditAction, auditObject, auditSource } from './labels'
import { formatFull, toMs } from './reasons'

export default function AuditTable({ rows }) {
  return (
    <div className="lh-table-wrap">
      <table className="lh-table">
        <caption className="sr-only">Jejak audit aktivitas akun</caption>
        <thead>
          <tr>
            <th scope="col">Waktu</th>
            <th scope="col">Aktor</th>
            <th scope="col">Aksi</th>
            <th scope="col">Objek</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const stamp = toMs(row?.created_at)
            const source = auditSource(row)
            return (
              <tr key={row?.id ?? index}>
                <td className="num lh-col-time">{stamp === null ? '·' : formatFull(stamp)}</td>
                <td>
                  <span className="lh-actor">{row?.actor || '·'}</span>
                  {source && <span className="lh-actor-sub">{source}</span>}
                </td>
                <td>{auditAction(row?.action)}</td>
                <td>{auditObject(row)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
