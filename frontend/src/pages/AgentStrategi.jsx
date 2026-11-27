// Halaman gabungan "Agent & Strategi" (rute /agent).
//
// Tiga sub-tab, satu bahasa: keputusan agent, performa strategi, dan usulan
// perbaikan. Semua data berasal dari endpoint yang sudah dipakai halaman lama
// (konfigurasi agent, katalog model, keputusan agent, daftar strategi, usulan
// self-improve). Tidak ada form batas order di sini: itu pindah ke Pengaturan.
//
// Tab aktif disimpan di query string (?tab=live|strategi|usulan) supaya bisa
// di-deep-link dan tetap hidup setelah reload.
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DEMO, desk, fetchMe, getAgentConfig } from '../lib/api'
import { useDesk } from '../lib/useDesk'
import { DebugOnly } from '../lib/debug'
import SubTabs from '../components/SubTabs'
import RoleStatus from '../components/agent/RoleStatus'
import AgentModelsPanel from '../components/agent/AgentModelsPanel'
import CycleCard from '../components/agent/CycleCard'
import DecisionFeed from '../components/agent/DecisionFeed'
import StrategyCards from '../components/agent/StrategyCards'
import ProposalCards from '../components/agent/ProposalCards'
import '../styles/agent-strategi.css'

const TABS = [
  { id: 'live', label: 'Live' },
  { id: 'strategi', label: 'Strategi' },
  { id: 'usulan', label: 'Usulan' },
]

const CONFIG_POLL_MS = 30000
const PROPOSAL_POLL_MS = 60000

export default function AgentStrategi() {
  const [params, setParams] = useSearchParams()
  const tabParam = params.get('tab')
  const tab = TABS.some((t) => t.id === tabParam) ? tabParam : 'live'

  const setTab = (id) => {
    const next = new URLSearchParams(params)
    next.set('tab', id)
    setParams(next, { replace: true })
  }

  const deskState = useDesk()
  const strategies = deskState?.strategies || []
  const [strategiesLoaded, setStrategiesLoaded] = useState(DEMO)

  const [cfg, setCfg] = useState(null)
  const [me, setMe] = useState(null)
  const [proposals, setProposals] = useState(() => (DEMO ? [] : null))
  const [proposalError, setProposalError] = useState(() => (DEMO ? 'DEMO' : null))

  const loadStrategies = useCallback(() => {
    const task = desk.loadStrategies()
    return (task || Promise.resolve()).catch(() => [])
  }, [])

  const loadConfig = useCallback(() => {
    if (DEMO) return Promise.resolve()
    return getAgentConfig()
      .then((body) => setCfg(body))
      .catch(() => {})
  }, [])

  const loadProposals = useCallback(() => {
    if (DEMO) return Promise.resolve()
    return desk
      .proposals()
      .then((body) => {
        setProposals(Array.isArray(body?.proposals) ? body.proposals : [])
        setProposalError(null)
      })
      .catch((ex) => {
        setProposals([])
        setProposalError(ex?.code || 'ERROR')
      })
  }, [])

  useEffect(() => {
    let alive = true
    loadStrategies().then(() => {
      if (alive) setStrategiesLoaded(true)
    })
    return () => {
      alive = false
    }
  }, [loadStrategies])

  useEffect(() => {
    loadConfig()
    const t = setInterval(loadConfig, CONFIG_POLL_MS)
    return () => clearInterval(t)
  }, [loadConfig])

  useEffect(() => {
    if (DEMO) return undefined
    let alive = true
    fetchMe()
      .then((body) => {
        if (alive) setMe(body)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    loadProposals()
    const t = setInterval(loadProposals, PROPOSAL_POLL_MS)
    return () => clearInterval(t)
  }, [loadProposals])

  const pending = (proposals || []).filter((p) => p.status === 'PROPOSED').length
  const tabs = TABS.map((t) => (t.id === 'usulan' && pending > 0 ? { ...t, count: pending } : t))

  return (
    <div className="agx-page">
      <div className="page-head agx-head">
        <div>
          <h1 className="page-title">Agent &amp; Strategi</h1>
          <p className="page-sub">
            Keputusan agent, performa strategi, dan usulan perbaikan dalam satu tempat.
          </p>
        </div>
        <div className="agx-head-chips">
          {DEMO && <span className="agx-chip is-idle">Mode demo</span>}
          {!DEMO && cfg && (
            cfg.pause?.active
              ? <span className="agx-chip is-warn">Agent dijeda</span>
              : <span className="agx-chip is-up">Agent aktif</span>
          )}
          {!DEMO && cfg?.kill_switch?.active && <span className="agx-chip is-down">Kill-switch aktif</span>}
        </div>
      </div>

      <SubTabs tabs={tabs} value={tab} onChange={setTab} ariaLabel="Bagian agent dan strategi" />

      {tab === 'live' && (
        <div className="agx-tab">
          <RoleStatus />
          <div className="agx-split">
            <DecisionFeed />
            <div className="agx-stack">
              <CycleCard
                interval={cfg?.interval_s ?? null}
                range={cfg?.interval_range_s}
                isAdmin={me?.role === 'admin'}
                onSaved={loadConfig}
              />
              <AgentModelsPanel />
            </div>
          </div>
        </div>
      )}

      {tab === 'strategi' && (
        <StrategyCards strategies={strategies} loaded={strategiesLoaded} onReload={loadStrategies} />
      )}

      {tab === 'usulan' && (
        <ProposalCards
          rows={proposals}
          loading={proposals === null}
          errorCode={proposalError}
          onRefresh={loadProposals}
        />
      )}

      <DebugOnly label="halaman">
        src/pages/AgentStrategi.jsx · ?tab=live|strategi|usulan · data: /llm-agent/config, /llm-agent/models,
        /llm-agent/decisions, /strategies, /improve/proposals
      </DebugOnly>
    </div>
  )
}
