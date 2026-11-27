import { useEffect, useState } from 'react'
import { onToast } from '../lib/api'

export default function Toasts() {
  const [items, setItems] = useState([])
  useEffect(() =>
    onToast((t) => {
      setItems((xs) => [...xs, t])
      setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== t.id)), 5200)
    }), [])
  if (!items.length) return null
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast ${t.kind === 'down' ? 'toast-down' : t.kind === 'up' ? 'toast-up' : ''}`}>
          <div className="toast-title">{t.title}</div>
          {t.body && <div className="toast-body">{t.body}</div>}
        </div>
      ))}
    </div>
  )
}
