import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = 'http://127.0.0.1:3110'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': API,
      '/orders': API,
      '/positions': API,
      '/strategies': API,
      '/kill-switch': API,
      '/improve': API,
      '/health': API,
      '/metrics': API,
      '/audit': API,
      // Admin Guardrail Risiko (t_2d1f6d33): GET/PUT /admin/* hanya di dev
      // server; produksi same-origin lewat fund2-api.
      '/admin': API,
      // UI-D1 (PRD §21.2): endpoint widget audit-review dashboard.
      '/regime': API,
      '/risk': API,
      '/alerts': API,
      // FONDASI UI (chart candle): GET /candles?symbol=&tf=&limit=.
      '/candles': API,
      // UI-D2 (gap API): proxy untuk endpoint yang baru terwakali —
      // research, shadow, llm-agent, improve sudah ada; shadow + llm-agent
      // belum diproxy sebelumnya.
      '/research': API,
      '/shadow': API,
      '/llm-agent': API,
      '/stream': { target: API, changeOrigin: true },
    },
  },
})
