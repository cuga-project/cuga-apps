import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { USE_CASES, CATEGORIES, type Category, type UseCase } from '../data/usecases'
import { resolveAppUrl, resolveServiceUrl, trackedLink } from '../data/deployment'
import { BHARAT_SERVICES, BHARAT_CORE } from '../data/bharatServices'

// Source lives in the public cuga-apps repo; each app's `demoPath` is a tree
// path under the repo's inner `cuga-apps/` source dir.
const REPO_TREE = 'https://github.com/cuga-project/cuga-apps/tree/main/cuga-apps'
const githubUrl = (demoPath: string | null) =>
  demoPath ? `${REPO_TREE}/${demoPath}` : 'https://github.com/cuga-project/cuga-apps'

// Apps default to ship-ready ("Showcase"). Listing an id below moves it to the
// "Additional apps" group: for-later (not polished enough for an unattended
// end-to-end run) or exploratory (work in progress).
const FOR_LATER_IDS = new Set([
  'bird-invocable-api', 'api-doc-gen', 'box-qa', 'code-reviewer', 'deck-forge',
  'smart-todo', 'drop-summarizer',
])
const EXPLORATORY_IDS = new Set([
  'chief-of-staff', 'code-engine-deployer', 'video-qa', 'voice-journal',
  'ibm-whats-new', 'brief-budget', 'trip-designer',
])
const isShowcase = (id: string) => !FOR_LATER_IDS.has(id) && !EXPLORATORY_IDS.has(id)

// Display order for the showcase: the enterprise-flavoured apps first, the
// consumer ones last. Ids not listed fall to the end in source order.
const SHOWCASE_ORDER = [
  // Lead row (by request)
  'web-researcher', 'youtube-research', 'arch-diagram',
  'hiking-research', 'paper-scout', 'github-trending',
  // More enterprise
  'dependency-drift-watcher', 'ibm-cloud-advisor', 'ibm-docs-qa', 'server-monitor',
  'stock-alert', 'newsletter', 'webpage-summarizer', 'wiki-dive', 'ouroboros', 'city-beat',
  'ai-labs-news',   // moved down by request
  // More personal
  'find-a-doctor', 'meetup-finder', 'travel-agent', 'recipe-composer', 'movie-recommender',
]
// Additional apps, ranked by how well they work × capability.
const ADDITIONAL_ORDER = [
  'code-reviewer', 'video-qa', 'bird-invocable-api', 'trip-designer', 'api-doc-gen',
  'voice-journal', 'brief-budget', 'drop-summarizer', 'smart-todo', 'ibm-whats-new',
  'chief-of-staff', 'box-qa', 'deck-forge', 'code-engine-deployer',
]
const rank = (list: string[], id: string) => {
  const i = list.indexOf(id)
  return i === -1 ? Number.MAX_SAFE_INTEGER : i
}

type Group = 'showcase' | 'additional' | 'all'
const GROUP_LABEL: Record<Group, string> = { showcase: 'Showcase', additional: 'Additional', all: 'All' }

const SERVER_LABEL: Record<string, string> = {
  tavily: 'Tavily', web: 'Web', knowledge: 'Knowledge', geo: 'Geo', finance: 'Finance',
  code: 'Code', local: 'Host', text: 'Text', invocable_apis: 'Invocable APIs',
}

const pad = (n: number) => String(n).padStart(2, '0')

// ── Small building blocks ─────────────────────────────────────────────────────

function Eyebrow({ children, dot = true, className = '' }: { children: React.ReactNode; dot?: boolean; className?: string }) {
  return (
    <div className={`eyebrow flex items-center gap-2.5 text-t2 ${className}`}>
      {dot && <span className="w-1.5 h-1.5 bg-indigo-600" aria-hidden="true" />}
      {children}
    </div>
  )
}

function Tabs<T extends string>({ value, options, labels, onChange }: {
  value: T; options: T[]; labels: Record<T, string>; onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex border border-tborder rounded bg-tsurf">
      {options.map((o, i) => (
        <button key={o} onClick={() => onChange(o)}
                className={`px-3.5 h-9 text-[13px] transition-colors ${i > 0 ? 'border-l border-tborder' : ''} ${
                  value === o ? 'bg-indigo-600 text-white font-medium' : 'text-t2 hover:text-indigo-600'}`}>
          {labels[o]}
        </button>
      ))}
    </div>
  )
}

const ArrowUR = () => <span aria-hidden="true" className="inline-block">↗</span>

// ── App card ──────────────────────────────────────────────────────────────────

function AppCard({ uc, index }: { uc: UseCase; index: number }) {
  const navigate = useNavigate()
  const showcase = isShowcase(uc.id)
  const launchUrl = uc.comingSoon || !showcase ? null : resolveAppUrl(uc)
  const repoUrl = githubUrl(uc.demoPath)
  const servers = (uc.mcpUsage ?? []).map((u) => u.server)
  const example = uc.examples?.[0]

  return (
    <article className="group relative flex flex-col bg-tsurf border border-tborder rounded hover:border-indigo-600 hover:shadow-[0_8px_30px_-12px_rgba(15,98,254,0.35)] transition-all">
      <div className="flex items-center justify-between px-6 pt-5">
        <span className="eyebrow text-t4">{pad(index + 1)}</span>
        <span className={`eyebrow ${uc.category === 'enterprise' ? 'text-indigo-600' : 'text-emerald-700'}`}>
          {uc.category === 'enterprise' ? 'Enterprise' : 'Personal'}
        </span>
      </div>

      <div className="px-6 pt-3 pb-5 flex-1 flex flex-col">
        <h3 className="font-display text-[22px] font-medium tracking-tight text-t1 leading-tight mb-2 group-hover:text-indigo-600 transition-colors">
          {uc.name}
        </h3>
        <p className="text-sm text-t3 leading-relaxed line-clamp-3 mb-4">{uc.tagline}</p>
        {example && (
          <p className="text-[13px] text-t2 bg-tsurf2 border-l-2 border-indigo-600 px-3 py-2 mb-4 line-clamp-2" title={example}>
            {example}
          </p>
        )}
        <div className="mt-auto flex flex-wrap gap-1.5">
          {servers.map((s) => (
            <button key={s} onClick={() => navigate(`/mcp-servers#mcp-${s}`)} title={`View the mcp-${s} server`}
                    className="font-mono text-[11px] px-2 py-0.5 rounded-sm border border-tborder text-t3 hover:text-indigo-600 hover:border-indigo-600 transition-colors">
              {SERVER_LABEL[s] ?? s}
            </button>
          ))}
          {servers.length === 0 && (uc.inlineTools?.length ?? 0) > 0 && (
            <span className="font-mono text-[11px] px-2 py-0.5 rounded-sm border border-tborder text-t3">inline tools</span>
          )}
        </div>
      </div>

      <div className="flex items-stretch border-t border-tborder">
        {uc.comingSoon ? (
          <span className="flex-1 px-6 py-3 text-[13px] text-t4">Coming soon</span>
        ) : launchUrl ? (
          <a href={launchUrl} target="_blank" rel="noopener noreferrer"
             className="flex-1 flex items-center justify-between px-6 py-3 text-[13px] font-medium text-indigo-600 hover:bg-indigo-600 hover:text-white rounded-bl transition-colors">
            Try it <ArrowUR />
          </a>
        ) : null}
        <a href={repoUrl} target="_blank" rel="noopener noreferrer"
           className={`flex items-center justify-between gap-3 px-6 py-3 text-[13px] text-t3 hover:text-indigo-600 transition-colors ${
             launchUrl ? 'border-l border-tborder' : 'flex-1'}`}>
          Code <ArrowUR />
        </a>
      </div>
    </article>
  )
}

// ── Bharat Core Services band (bharat-core-cuga-agent-app, outside the all-in-one) ──

function BharatCoreServices() {
  if (BHARAT_SERVICES.length === 0) return null
  return (
    <section id="bharat-core" aria-labelledby="bharat-core-heading"
             className="scroll-mt-4 relative overflow-hidden bg-[#0b1530] text-white">
      {/* Saffron → white → green hairline across the top, and soft glows */}
      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#ff9933] via-white to-[#138808]" />
      <div aria-hidden="true" className="absolute -top-32 -left-24 w-[520px] h-[520px] rounded-full bg-[#ff9933]/[0.14] blur-3xl" />
      <div aria-hidden="true" className="absolute -bottom-40 right-0 w-[620px] h-[620px] rounded-full bg-[#0f62fe]/[0.25] blur-3xl" />
      <div aria-hidden="true" className="absolute inset-0 opacity-[0.5] [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:48px_48px]" />

      <div className="relative px-4 md:px-14 py-14 lg:py-16">
        <div className="grid lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-16 items-end mb-10">
          <div>
            <div className="eyebrow flex items-center gap-2.5 text-[#ffb366] mb-5">
              <span className="w-1.5 h-1.5 bg-[#ff9933]" aria-hidden="true" />
              Bharat Core Services · IBM Sovereign Core
            </div>
            <h2 id="bharat-core-heading" className="font-display font-medium tracking-[-0.02em] leading-[1.02] text-[40px] md:text-[52px]">
              Agents built for India.
              <br />
              <span className="text-[#ffb366]">In Indian languages.</span>
            </h2>
          </div>
          <div>
            <p className="text-lg text-white/75 leading-relaxed mb-5">
              <strong className="text-white font-medium">Bharat Core</strong> — {BHARAT_CORE.tagline}. Try its first
              CUGA-powered service below.
            </p>
            <a href={trackedLink('bharat-core', 'band', BHARAT_CORE.url)} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-10 h-12 px-5 rounded bg-[#ff9933] hover:bg-[#ff8a14] text-[#1a1205] text-[15px] font-semibold transition-colors">
              Check out Bharat Core <ArrowUR />
            </a>
          </div>
        </div>

        {/* Bharat Core in numbers (from ibmbharatcore.info) */}
        <div className="grid grid-cols-2 md:grid-cols-4 border-y border-white/10 mb-10">
          {BHARAT_CORE.stats.map((st, i) => (
            <a key={st.label} href={trackedLink('bharat-core', 'stats', BHARAT_CORE.url)} target="_blank" rel="noopener noreferrer"
               className={`group py-5 ${i > 0 ? 'md:border-l border-white/10 md:pl-8' : ''} ${i % 2 === 1 ? 'border-l md:border-l pl-6' : ''}`}>
              <div className="font-display text-4xl font-medium tracking-tight text-white group-hover:text-[#ffb366] transition-colors">{st.value}</div>
              <div className="eyebrow text-white/55 mt-1">{st.label}</div>
            </a>
          ))}
        </div>

        <ul className={`grid gap-5 ${BHARAT_SERVICES.length > 1 ? 'lg:grid-cols-2' : ''}`}>
          {BHARAT_SERVICES.map((svc) => {
            const href = resolveServiceUrl(svc.ceApp, svc.path, svc.localUrl, svc.url)
            return (
              <li key={svc.id} className="rounded-xl bg-white text-[#16181d] shadow-[0_30px_80px_-30px_rgba(0,0,0,0.6)] overflow-hidden">
                <div className="grid md:grid-cols-[1fr_auto] gap-6 p-6 md:p-8 items-center">
                  <div>
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {svc.facts.map((f, i) => (
                        <span key={f}
                              className={`font-mono text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-sm ${
                                i === 0 ? 'bg-[#ff9933] text-[#1a1205] font-semibold' : 'border border-[#e2e6ec] text-[#5d6677]'}`}>
                          {f}
                        </span>
                      ))}
                    </div>
                    <a href={href} target="_blank" rel="noopener noreferrer"
                       className="font-display text-2xl md:text-[28px] font-medium tracking-tight hover:text-[#0f62fe] transition-colors">
                      {svc.name}
                    </a>
                    <p className="text-[15px] text-[#5d6677] leading-relaxed mt-2 max-w-3xl">{svc.description}</p>
                  </div>
                  <div className="flex flex-col sm:flex-row md:flex-col gap-3 md:w-60">
                    <a href={href} target="_blank" rel="noopener noreferrer"
                       className="flex items-center justify-between gap-6 h-12 px-5 rounded bg-[#0f62fe] hover:bg-[#0353e9] text-white text-[15px] font-medium transition-colors">
                      Open <ArrowUR />
                    </a>
                    <a href={trackedLink('bharat-core', 'card', BHARAT_CORE.url)} target="_blank" rel="noopener noreferrer"
                       className="flex items-center justify-between gap-6 h-12 px-5 rounded border border-[#ff9933] text-[#b35900] hover:bg-[#ff9933] hover:text-[#1a1205] text-[15px] font-medium transition-colors">
                      Check out Bharat Core <ArrowUR />
                    </a>
                  </div>
                </div>
                <div className="px-6 md:px-8 py-3 border-t border-[#e2e6ec] bg-[#f5f7fa] text-xs text-[#5d6677]">
                  Opens in a new tab and asks you to sign in.
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}

// ── Hero ──────────────────────────────────────────────────────────────────────

function ProofPanel({ total, showcase }: { total: number; showcase: number }) {
  const rows = [
    { k: '#1', title: 'AppWorld', note: '750 tasks · 457 APIs', href: 'https://appworld.dev/' },
    { k: '#1', title: 'WebArena', note: 'Feb–Sep 2025', href: 'https://webarena.dev/' },
    { k: String(total), title: 'Working apps', note: `${showcase} in the showcase`, href: '#apps' },
  ]
  return (
    <div className="relative">
      <div aria-hidden="true" className="absolute -right-2 -bottom-2 inset-0 translate-x-2 translate-y-2 rounded-xl border border-tborder bg-tsurf2" />
      <div className="relative rounded-xl border border-tborder bg-tsurf shadow-[0_24px_60px_-30px_rgba(22,24,29,0.35)] overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-tborder">
          <Eyebrow>CUGA leaderboard</Eyebrow>
          <span className="eyebrow text-t4">Open source</span>
        </div>
        <ul>
          {rows.map((r, i) => (
            <li key={r.title} className={i > 0 ? 'border-t border-tborder' : ''}>
              <a href={r.href} target={r.href.startsWith('#') ? undefined : '_blank'} rel="noopener noreferrer"
                 className="group flex items-center gap-5 px-5 py-4 hover:bg-tsurf2 transition-colors">
                <span className="eyebrow text-t4 w-5">{pad(i + 1)}</span>
                <span className="font-display text-4xl font-medium tracking-tight text-indigo-600 w-20">{r.k}</span>
                <span className="flex-1">
                  <span className="block text-sm font-medium text-t1">{r.title}</span>
                  <span className="block text-xs text-t3">{r.note}</span>
                </span>
                <span className="text-t4 group-hover:text-indigo-600 transition-colors"><ArrowUR /></span>
              </a>
            </li>
          ))}
        </ul>
        <div className="px-5 py-3 border-t border-tborder bg-tsurf2">
          <code className="font-mono text-xs text-t2">$ pip install cuga</code>
        </div>
      </div>
    </div>
  )
}

const PILLARS = [
  { title: 'Your tools.', body: 'MCP servers, OpenAPI and Python tools — Tavily included' },
  { title: 'Your policies.', body: 'Intent guards, playbooks, tool guides and approvals' },
  { title: 'Your models.', body: 'watsonx, OpenAI, Anthropic, LiteLLM or local models' },
]

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<Category | 'all'>('all')
  const [group, setGroup] = useState<Group>('showcase')

  const visible = useMemo(() => USE_CASES.filter((u) => !u.hidden), [])
  const showcaseCount = visible.filter((u) => isShowcase(u.id)).length

  const apps = useMemo(() => {
    const q = search.trim().toLowerCase()
    return visible
      .filter((uc) =>
        (group === 'all' || (group === 'showcase') === isShowcase(uc.id)) &&
        (category === 'all' || uc.category === category) &&
        (!q || uc.name.toLowerCase().includes(q) || uc.tagline.toLowerCase().includes(q)))
      .sort((a, b) => {
        const sa = isShowcase(a.id), sb = isShowcase(b.id)
        if (sa !== sb) return sa ? -1 : 1
        return sa ? rank(SHOWCASE_ORDER, a.id) - rank(SHOWCASE_ORDER, b.id)
                  : rank(ADDITIONAL_ORDER, a.id) - rank(ADDITIONAL_ORDER, b.id)
      })
  }, [visible, search, category, group])

  const filtered = search || category !== 'all' || group !== 'showcase'

  return (
    <div>
      {/* ── Hero ── */}
      <section className="relative border-b border-tborder overflow-hidden">
        <div aria-hidden="true" className="absolute inset-0 bg-blueprint [mask-image:linear-gradient(to_right,transparent,black_45%)]" />
        <div aria-hidden="true" className="absolute -top-40 right-0 w-[640px] h-[640px] rounded-full bg-indigo-600/[0.07] blur-3xl" />
        <div className="relative grid lg:grid-cols-[1.15fr_1fr] gap-12 xl:gap-20 px-4 md:px-14 pt-16 pb-14 lg:pt-24 lg:pb-20 items-center">
          <div>
            {BHARAT_SERVICES.length > 0 && (
              <a href="#bharat-core"
                 className="group inline-flex items-center gap-3 mb-8 pl-1 pr-4 py-1 rounded-full border border-[#ff9933]/50 bg-[#ff9933]/[0.08] hover:bg-[#ff9933]/[0.16] transition-colors">
                <span className="font-mono text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-[#ff9933] text-[#1a1205]">New</span>
                <span className="text-[13px] text-t1">Bharat Core: an Indic voice agent, in 11 languages</span>
                <span className="text-[#b35900] group-hover:translate-y-0.5 transition-transform" aria-hidden="true">↓</span>
              </a>
            )}
            <Eyebrow className="mb-8">Open source. Enterprise ready.</Eyebrow>
            <h1 className="font-display font-medium tracking-[-0.03em] leading-[0.98] text-t1 text-[52px] sm:text-[68px] xl:text-[82px] mb-8">
              Agentic apps.
              <br />
              <span className="text-indigo-600">Built on CUGA.</span>
            </h1>
            <p className="text-lg text-t3 leading-relaxed max-w-xl mb-10">
              {visible.length} working apps from IBM Research — each a <code className="font-mono text-[15px] text-t1">CugaAgent</code>{' '}
              with real tools, real policies and a small web UI. Try one, then copy it.
            </p>
            <div className="flex flex-wrap gap-3">
              <a href="#apps"
                 className="flex items-center gap-10 h-12 px-5 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-[15px] font-medium transition-colors">
                Explore the apps <span aria-hidden="true">↓</span>
              </a>
              <a href="https://cuga.dev" target="_blank" rel="noopener noreferrer"
                 className="flex items-center gap-10 h-12 px-5 rounded border border-indigo-600 text-indigo-600 hover:bg-indigo-600 hover:text-white text-[15px] font-medium transition-colors">
                Get started with CUGA <ArrowUR />
              </a>
            </div>
          </div>
          <ProofPanel total={visible.length} showcase={showcaseCount} />
        </div>

        {/* Numbered pillars, as on cuga.dev */}
        <div className="relative border-t border-tborder bg-tsurf/70 backdrop-blur">
          <div className="grid md:grid-cols-3 px-4 md:px-14">
            {PILLARS.map((p, i) => (
              <div key={p.title} className={`flex gap-4 py-6 ${i > 0 ? 'md:border-l md:border-tborder md:pl-8' : ''} ${i < 2 ? 'md:pr-8' : ''}`}>
                <span className="eyebrow text-t4 pt-1">{pad(i + 1)}</span>
                <div>
                  <div className="text-[15px] font-medium text-t1">{p.title}</div>
                  <div className="text-sm text-t3">{p.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <BharatCoreServices />

      {/* ── Apps ── */}
      <section id="apps" className="scroll-mt-4 px-4 md:px-14 py-16 bg-tsurf2/60">
        <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-8 mb-10">
          <div>
            <Eyebrow className="mb-5 !text-indigo-600" dot={false}>Try CUGA Apps</Eyebrow>
            <h2 className="font-display font-medium tracking-[-0.02em] leading-[1.02] text-[40px] md:text-[56px]">
              <span className="text-t1">Find an app.</span>
              <br />
              <span className="text-t3">See what CUGA can do.</span>
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Tabs value={group} options={['showcase', 'additional', 'all']} labels={GROUP_LABEL} onChange={setGroup} />
            <Tabs value={category} options={['all', 'enterprise', 'personal'] as (Category | 'all')[]}
                  labels={{ all: 'Any', enterprise: 'Enterprise', personal: 'Personal' } as Record<Category | 'all', string>}
                  onChange={setCategory} />
            <div className="relative">
              <input type="search" placeholder="Search apps" value={search} onChange={(e) => setSearch(e.target.value)}
                     className="w-56 h-9 pl-9 pr-3 rounded border border-tborder bg-tsurf text-[13px] text-t1 placeholder-t4 focus:outline-none focus:border-indigo-600" />
              <svg aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-t4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <circle cx="11" cy="11" r="7" strokeWidth={2} /><path d="M20 20l-3.5-3.5" strokeWidth={2} strokeLinecap="round" />
              </svg>
            </div>
            {filtered && (
              <button onClick={() => { setSearch(''); setCategory('all'); setGroup('showcase') }}
                      className="text-[13px] text-t3 hover:text-indigo-600">Reset</button>
            )}
          </div>
        </div>

        <p className="eyebrow text-t4 mb-4">
          {apps.length} {apps.length === 1 ? 'app' : 'apps'} · {group === 'showcase' ? 'polished demos you can run end to end' : group === 'additional' ? 'earlier-stage — open the source' : `${CATEGORIES.enterprise.label.toLowerCase()} first`}
        </p>

        {apps.length === 0 ? (
          <div className="py-16 text-center text-t3 rounded border border-dashed border-tb2">No apps match your filters.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
            {apps.map((uc, i) => <AppCard key={uc.id} uc={uc} index={i} />)}
          </div>
        )}
      </section>
    </div>
  )
}
