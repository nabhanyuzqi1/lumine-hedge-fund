import Mark from './components/Mark.jsx';
import Ticker from './components/Ticker.jsx';
import Console from './components/Console.jsx';

/* ── content ─────────────────────────────────────────────────────────── */

const PATH_STEPS = [
  {
    n: '01',
    label: 'Scheduler → trade-core',
    text: 'Every market event opens a decision cycle. Nothing runs ad hoc.',
  },
  {
    n: '02',
    label: 'LLM Investment Committee',
    text: 'Technical, Macro, News and SMC analysts deliberate, then IC and CIO form a proposal. Reasoning only — no money moves here.',
  },
  {
    n: '03',
    label: 'RiskValidator — final veto',
    text: 'Deterministic Python checks exposure, drawdown and policy. A veto is absolute. No LLM sits above this line.',
  },
  {
    n: '04',
    label: 'PortfolioSizer',
    text: 'Position size is computed from risk budget and correlation, not from confidence scores.',
  },
  {
    n: '05',
    label: 'ExecutionRouter — ACID gate',
    text: 'Lineage records are inserted and committed before dispatch. If the transaction fails, the trade stops. Safe state by default.',
  },
  {
    n: '06',
    label: 'MT5 Bridge → journal',
    text: 'Order fills stream back into positions, the trade journal, and the performance reviewer.',
  },
];

const COMMITTEE = [
  { role: 'CEO', scope: 'Strategy, capital, kill switch' },
  { role: 'CIO', scope: 'Allocation, proposal approval' },
  { role: 'Investment Committee', scope: 'Technical · Macro · News · SMC analysts' },
  { role: 'Risk Officer', scope: 'Deterministic veto authority' },
  { role: 'Portfolio Manager', scope: 'Sizing, exposure, rebalance' },
  { role: 'Execution Controller', scope: 'Order routing, lineage gate' },
  { role: 'Trade Journal', scope: 'Fills, evidence chain' },
  { role: 'Performance Reviewer', scope: 'Learning, attribution' },
];

const INVARIANTS = [
  ['Reproducibility', 'Every decision pins model, prompt and policy versions. Decisions are replayable.'],
  ['Auditability', 'Every trade decision carries a full evidence chain — lineage before capital.'],
  ['Safe state', 'Failures stop the pipeline. The ACID lineage gate is blocking; no async worker dispatches a trade.'],
  ['LLMs only reason', 'Deterministic Python owns risk, sizing, and execution.'],
  ['Evidence before capital', 'No proposal reaches the bridge without a signed, versioned evidence record.'],
];

const PHASES = [
  ['00', 'Vision', 'done'],
  ['01', 'Architecture', 'done'],
  ['02', 'Departments', 'done'],
  ['03', 'Agents & contracts', 'done'],
  ['04', 'Communication & prompts', 'done'],
  ['05', 'Data architecture', 'done'],
  ['06', 'AI & LLM strategy', 'done'],
  ['07', 'AutoGen architecture', 'done'],
  ['08', 'Trading architecture', 'done'],
  ['09', 'API design', 'done'],
  ['10', 'Frontend design system', 'done'],
  ['11', 'Infrastructure', 'done'],
  ['12', 'Security', 'done'],
  ['13', 'Testing strategy', 'done'],
  ['14', 'Implementation plan', 'done'],
  ['15', 'Implementation', 'active'],
];

const STACK = [
  ['Python 3.12', 'FastAPI · SQLAlchemy 2 async · Pydantic v2'],
  ['Microsoft AutoGen', 'Agent orchestration, committee debates'],
  ['9router', 'LLM gateway — GPT-5.x · DeepSeek V4 · Kimi · Qwen · GLM'],
  ['MetaTrader 5', 'Expert Advisor bridge, fills, watchdog'],
  ['PostgreSQL · Redis', 'Lineage-first persistence, caching'],
  ['Docker', 'Containerized services, deploy-stack, noVNC'],
  ['React 18 (Phase 10)', 'Locked stack: Vite · Tailwind · shadcn/ui · Zustand'],
];

const NAV = [
  ['System', '#system'],
  ['Committee', '#committee'],
  ['Roadmap', '#roadmap'],
  ['Stack', '#stack'],
];

function Eyebrow({ children }) {
  return (
    <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">{children}</p>
  );
}

function SectionTitle({ id, no, title, sub }) {
  return (
    <div id={id} className="scroll-mt-24">
      <Eyebrow>{no}</Eyebrow>
      <h2 className="mt-3 font-display text-2xl font-700 tracking-tight text-ink sm:text-3xl">
        {title}
      </h2>
      {sub && <p className="mt-3 max-w-2xl text-[14.5px] leading-relaxed text-ink-dim">{sub}</p>}
    </div>
  );
}

/* ── page ────────────────────────────────────────────────────────────── */

export default function App() {
  return (
    <div className="min-h-screen bg-bg text-ink">
      {/* top bar */}
      <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-8 px-4 sm:px-6">
          <a href="#top" className="flex items-center gap-2.5" aria-label="Lumine — home">
            <Mark />
          </a>
          <nav className="ml-auto hidden items-center gap-6 md:flex" aria-label="Primary">
            {NAV.map(([label, href]) => (
              <a key={href} href={href} className="text-[13px] text-ink-dim transition-colors hover:text-ink">
                {label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <a
              href="https://github.com/nabhan/lumine-hedge-fund"
              className="hidden rounded-[var(--radius-chip)] border border-line px-3 py-1.5 font-mono text-[11.5px] text-ink-dim transition-colors hover:border-accent-soft hover:text-ink sm:block"
            >
              github
            </a>
            <a
              href="#architecture"
              className="rounded-[var(--radius-chip)] bg-accent px-3 py-1.5 text-[12px] font-600 text-abyss transition-opacity hover:opacity-90"
            >
              Architecture
            </a>
          </div>
        </div>
      </header>

      {/* hero */}
      <section id="top" className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
          style={{
            background:
              'radial-gradient(720px 380px at 12% -10%, rgba(77,141,255,0.10), transparent 60%), radial-gradient(560px 300px at 88% 0%, rgba(34,211,238,0.06), transparent 60%)',
          }}
        />
        <div className="relative mx-auto grid max-w-6xl gap-12 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:pt-20">
          <div>
            <Eyebrow>AI-native quantitative hedge fund</Eyebrow>
            <h1 className="mt-4 font-display text-[38px] font-800 leading-[1.04] tracking-tight text-ink sm:text-[52px]">
              LLMs reason.
              <br />
              <span className="text-ink-dim">Deterministic code</span>
              <br />
              decides.
            </h1>
            <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-ink-dim">
              Lumine is an institutional-grade platform where autonomous AI agents form an
              investment committee, and a deterministic Python layer — risk veto, sizing,
              execution — enforces the outcome. Starting with XAUUSD.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <a
                href="https://github.com/nabhan/lumine-hedge-fund"
                className="rounded-[var(--radius-chip)] bg-accent px-4 py-2.5 text-[13px] font-600 text-abyss transition-opacity hover:opacity-90"
              >
                View on GitHub
              </a>
              <a
                href="#architecture"
                className="rounded-[var(--radius-chip)] border border-line px-4 py-2.5 text-[13px] font-500 text-ink transition-colors hover:border-accent-soft hover:text-accent"
              >
                Read the architecture
              </a>
            </div>
            <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-line-soft pt-6 font-mono text-[11px]">
              <div>
                <dt className="text-ink-faint">status</dt>
                <dd className="mt-1 text-up">phase 15 · sprint 1</dd>
              </div>
              <div>
                <dt className="text-ink-faint">risk gate</dt>
                <dd className="mt-1 text-ink">deterministic</dd>
              </div>
              <div>
                <dt className="text-ink-faint">lineage</dt>
                <dd className="mt-1 text-ink">ACID · blocking</dd>
              </div>
            </dl>
          </div>

          <div className="relative">
            <Console />
            <p className="mt-3 text-center font-mono text-[10.5px] tracking-wide text-ink-faint">
              the critical path, as it runs — every cycle is versioned and replayable
            </p>
          </div>
        </div>
      </section>

      <Ticker />

      {/* architecture / critical path */}
      <section id="architecture" className="border-b border-line-soft">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <SectionTitle
            no="01 · system"
            title="How a decision is made"
            sub="Every trade decision travels one path. Reasoning happens above the risk line; money moves only below it."
          />
          <ol className="mt-12 grid gap-px overflow-hidden rounded-[var(--radius-panel)] border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {PATH_STEPS.map((s) => (
              <li key={s.n} className="group bg-bg p-6 transition-colors hover:bg-raised">
                <p className="font-mono text-[11px] text-accent">{s.n}</p>
                <h3 className="mt-2.5 font-display text-[15px] font-600 tracking-tight text-ink">
                  {s.label}
                </h3>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-dim">{s.text}</p>
              </li>
            ))}
          </ol>
          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-[var(--radius-panel)] border border-line bg-raised px-5 py-4 font-mono text-[11.5px]">
            <span className="text-ink-faint">invariant</span>
            <span className="text-ink">no LLM above RiskValidator</span>
            <span className="text-ink-faint">/</span>
            <span className="text-ink">no async worker on the critical path</span>
            <span className="text-ink-faint">/</span>
            <span className="text-up">kill switch read every cycle</span>
          </div>
        </div>
      </section>

      {/* committee */}
      <section id="committee" className="border-b border-line-soft">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <SectionTitle
            no="02 · hierarchy"
            title="A fund, not a chatbot"
            sub="Eight roles with typed contracts — purpose, inputs, outputs, KPIs, failure modes. Each agent is replaceable and auditable."
          />
          <div className="mt-10 overflow-x-auto rounded-[var(--radius-panel)] border border-line bg-abyss p-6">
            <pre className="font-mono text-[11.5px] leading-[1.9] text-ink-dim">{`CEO
 └── CIO
      └── Investment Committee
      │     ├── Technical Analyst
      │     ├── Macro Analyst
      │     ├── News Analyst
      │     └── SMC Analyst
      ├── Risk Officer            · deterministic veto
      └── Portfolio Manager
            └── Execution Controller
                  └── Trade Journal
                        └── Performance Reviewer`}</pre>
          </div>
          <ul className="mt-6 grid gap-px overflow-hidden rounded-[var(--radius-panel)] border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
            {COMMITTEE.map((r) => (
              <li key={r.role} className="bg-bg px-5 py-4">
                <p className="font-mono text-[12px] text-accent">{r.role}</p>
                <p className="mt-1.5 text-[12.5px] leading-snug text-ink-dim">{r.scope}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* invariants */}
      <section className="border-b border-line-soft">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <SectionTitle
            no="03 · discipline"
            title="Five invariants"
            sub="Safety properties the architecture refuses to trade away."
          />
          <ul className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {INVARIANTS.map(([name, text], i) => (
              <li key={name} className="rounded-[var(--radius-panel)] border border-line bg-raised p-6">
                <p className="font-mono text-[11px] text-ink-faint">0{i + 1}</p>
                <h3 className="mt-2 font-display text-[15px] font-600 text-ink">{name}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-dim">{text}</p>
              </li>
            ))}
            <li className="flex items-center justify-center rounded-[var(--radius-panel)] border border-dashed border-line p-6">
              <p className="max-w-[220px] text-center font-mono text-[11.5px] leading-relaxed text-ink-faint">
                documented in depth at
                <a href="#architecture" className="block text-accent hover:underline">
                  docs/01-architecture
                </a>
              </p>
            </li>
          </ul>
        </div>
      </section>

      {/* roadmap */}
      <section id="roadmap" className="border-b border-line-soft">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <SectionTitle
            no="04 · roadmap"
            title="Sixteen phases, one discipline"
            sub="Architecture before code. Every phase is documented and reviewed before the next begins."
          />
          <ol className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-panel)] border border-line bg-line sm:grid-cols-4 lg:grid-cols-8">
            {PHASES.map(([num, name, status]) => (
              <li
                key={num}
                className={`bg-bg px-4 py-5 ${status === 'active' ? 'outline outline-1 -outline-offset-1 outline-accent-soft' : ''}`}
              >
                <p className={`font-mono text-[11px] ${status === 'active' ? 'text-accent' : 'text-ink-faint'}`}>
                  {status === 'active' ? '▸ ' : ''}
                  {num}
                </p>
                <p className="mt-1.5 text-[12px] leading-snug text-ink-dim">{name}</p>
              </li>
            ))}
          </ol>
          <p className="mt-4 font-mono text-[11px] text-ink-faint">
            phase 15 — implementation · sprint 1 partial, sprint 2 pending. XAUUSD first; then
            Forex, indices, commodities, crypto, equities.
          </p>
        </div>
      </section>

      {/* stack */}
      <section id="stack" className="border-b border-line-soft">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <SectionTitle
            no="05 · stack"
            title="Chosen, not default"
            sub="Every component was evaluated in its phase, with alternatives and risks recorded."
          />
          <ul className="mt-12 grid gap-px overflow-hidden rounded-[var(--radius-panel)] border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {STACK.map(([name, detail]) => (
              <li key={name} className="bg-bg p-6 transition-colors hover:bg-raised">
                <h3 className="font-mono text-[13px] text-ink">{name}</h3>
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-dim">{detail}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* footer */}
      <footer className="bg-abyss">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-12 sm:px-6 md:flex-row md:items-end md:justify-between">
          <div>
            <Mark />
            <p className="mt-3 max-w-sm text-[12.5px] leading-relaxed text-ink-faint">
              An AI-native quantitative hedge fund platform. LLM agents reason; deterministic
              code enforces risk, sizing, and execution.
            </p>
          </div>
          <div className="flex flex-col gap-2 font-mono text-[11.5px]">
            <a href="https://github.com/nabhan/lumine-hedge-fund" className="text-ink-dim transition-colors hover:text-ink">
              github.com/nabhan/lumine-hedge-fund
            </a>
            <a href="#top" className="text-ink-dim transition-colors hover:text-ink">
              architecture · committee · roadmap · stack
            </a>
            <p className="text-ink-faint">XAUUSD first — evidence before capital.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
