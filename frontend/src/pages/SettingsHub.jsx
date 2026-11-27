// Pusat konfigurasi & kontrol darurat: satu halaman, empat sub-tab.
// Sub-tab aktif disimpan di query string (?tab=risiko|darurat|agent|sistem) agar
// tautan langsung dan tombol back/forward bekerja.
//
// Halaman ini menggabungkan tiga area yang sebelumnya terpisah:
//   1. batas risiko & guardrail (nilai aktif + form ubah),
//   2. kontrol darurat & recovery (aksi nyata + checklist dari kondisi sistem),
//   3. konfigurasi agent & kalender, dan
//   4. sistem & backup (kesehatan, backup terakhir, sesi login).
// Tidak ada panel baca-saja yang terpisah dari form ubahnya.
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import SubTabs from '../components/SubTabs'
import RiskGuardrailTab from '../components/settings/RiskGuardrailTab'
import EmergencyTab from '../components/settings/EmergencyTab'
import AgentCalendarTab from '../components/settings/AgentCalendarTab'
import SystemBackupTab from '../components/settings/SystemBackupTab'
import { DEMO } from '../lib/api'
import '../styles/settings-hub.css'

const TABS = [
  {
    id: 'risiko',
    label: 'Batas Risiko',
    lead: 'Batas risiko dan penghentian otomatis yang ditegakkan pada setiap order.',
  },
  {
    id: 'darurat',
    label: 'Kontrol Darurat',
    lead: 'Hentikan entry atau tutup semua posisi, plus status pemulihan setelah penghentian.',
  },
  {
    id: 'agent',
    label: 'Agent & Kalender',
    lead: 'Setelan siklus agent, prompt yang dipakai, dan filter blackout kalender ekonomi.',
  },
  {
    id: 'sistem',
    label: 'Sistem & Backup',
    lead: 'Kesehatan database dan EA, kondisi backup terakhir, serta sesi login aktif.',
  },
]

export default function SettingsHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('tab')
  const tab = TABS.some((t) => t.id === requested) ? requested : 'risiko'
  const active = TABS.find((t) => t.id === tab)

  // Parameter lain (mis. ?demo=1) dipertahankan saat sub-tab berganti.
  const setTab = useCallback((next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params)
  }, [searchParams, setSearchParams])

  return (
    <div className="sh-page">
      <header className="sh-head">
        <div className="sh-head-main">
          <h1 className="sh-title">Pengaturan</h1>
          <p className="sh-sub">
            Satu pusat konfigurasi dan kontrol darurat. Setiap perubahan nilai
            dikonfirmasi dengan kode 2FA dan tercatat di riwayat audit.
          </p>
        </div>
        <div className="sh-head-chips">
          {DEMO && <span className="chip">DEMO · DATA CONTOH</span>}
          <span className="sh-head-note">2FA wajib untuk menyimpan</span>
        </div>
      </header>

      <SubTabs tabs={TABS} value={tab} onChange={setTab} ariaLabel="Sub-tab pengaturan" />

      <p className="sh-lead">{active?.lead}</p>

      <div role="tabpanel" aria-label={active?.label} className="sh-panel">
        {tab === 'risiko' && <RiskGuardrailTab />}
        {tab === 'darurat' && <EmergencyTab />}
        {tab === 'agent' && <AgentCalendarTab />}
        {tab === 'sistem' && <SystemBackupTab />}
      </div>
    </div>
  )
}
