import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  USE_CASES,
  CATEGORIES,
  STATUS_LABELS,
  type Status,
  type UseCaseType,
  type Category,
} from '../data/usecases'
import { resolveAppUrl } from '../data/deployment'

// Apps default to ship-ready (✦ badge, sorted to top). Listing an id below
// flips it to "for-later" — useful for demos that aren't polished enough
// for an unattended end-to-end run yet — or "exploratory" — work-in-progress
// experiments that aren't on the demo track yet.
const FOR_LATER_IDS = new Set([
  'bird-invocable-api',
  'api-doc-gen',
  'box-qa',
  'code-reviewer',
  'deck-forge',
  'smart-todo',
  'drop-summarizer',
])

const EXPLORATORY_IDS = new Set([
  'chief-of-staff',
  'code-engine-deployer',
  'video-qa',
  'voice-journal',
  'ibm-whats-new',
  'brief-budget',
  'trip-designer',
])

type Stage = 'ship-ready' | 'for-later' | 'exploratory'

const stageOf = (id: string): Stage =>
  EXPLORATORY_IDS.has(id) ? 'exploratory'
  : FOR_LATER_IDS.has(id) ? 'for-later'
  : 'ship-ready'

const STAGE_BADGE: Record<Stage, { glyph: string; cls: string } | null> = {
  'ship-ready':  { glyph: '✦', cls: 'text-amber-500' },
  'exploratory': { glyph: '⚗', cls: 'text-purple-500' },
  'for-later':   null,
}

function StageGlyph({ id, ml }: { id: string; ml: string }) {
  const badge = STAGE_BADGE[stageOf(id)]
  if (!badge) return null
  return <span className={`${badge.cls} ${ml} font-bold`}>{badge.glyph}</span>
}

type ShipFilter = 'all' | Stage

const SHIP_FILTER_LABEL: Record<ShipFilter, string> = {
  'all':         'All',
  'ship-ready':  '✦ Ship-ready',
  'for-later':   'For later',
  'exploratory': '⚗ Exploratory',
}

function ShipFilterChips({
  value,
  onChange,
}: {
  value: ShipFilter
  onChange: (v: ShipFilter) => void
}) {
  const options: ShipFilter[] = ['all', 'ship-ready', 'for-later', 'exploratory']
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <span className="text-sm text-t4 font-semibold uppercase tracking-wider w-20 shrink-0">Stage</span>
      {options.map((opt) => {
        const active = value === opt
        const activeCls =
          opt === 'ship-ready'
            ? 'bg-amber-500 text-white border-amber-500'
            : opt === 'for-later'
            ? 'bg-slate-500 text-white border-slate-500'
            : opt === 'exploratory'
            ? 'bg-purple-600 text-white border-purple-600'
            : 'bg-indigo-600 text-white border-indigo-600'
        return (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            className={`text-sm px-3.5 py-1.5 rounded-full font-medium border transition-all ${
              active ? activeCls : 'bg-tsurf border-tborder text-t3 hover:text-t1 hover:border-t2'
            }`}
          >
            {SHIP_FILTER_LABEL[opt]}
          </button>
        )
      })}
    </div>
  )
}

// URL resolution moved to ../data/deployment.ts (resolveAppUrl) — handles
// localhost rewrite for local dev AND CE rewrite for Hugging Face deploys.

const TYPE_CONFIG: Record<UseCaseType, { label: string; icon: string; activeCls: string }> = {
  'event-driven':          { label: 'Event-driven',          icon: '⚡', activeCls: 'bg-amber-500 text-white border-amber-500' },
  'document-intelligence': { label: 'Document Intelligence', icon: '📄', activeCls: 'bg-cyan-500 text-white border-cyan-500' },
  'audio-video':           { label: 'Audio / Video',         icon: '🎬', activeCls: 'bg-violet-500 text-white border-violet-500' },
  'other':                 { label: 'Other',                 icon: '✦',  activeCls: 'bg-t2 text-tsurf border-t2' },
}

const TYPE_BADGE_CLS: Record<UseCaseType, string> = {
  'event-driven':          'bg-amber-500/10 text-amber-600 border-amber-500/30',
  'document-intelligence': 'bg-cyan-500/10 text-cyan-600 border-cyan-500/30',
  'audio-video':           'bg-violet-500/10 text-violet-600 border-violet-500/30',
  'other':                 'bg-tsurf2 text-t3 border-tborder',
}

function TypeBadge({ type }: { type: UseCaseType }) {
  const { label, icon } = TYPE_CONFIG[type]
  return (
    <span className={`text-sm px-2.5 py-1 rounded-md font-medium border ${TYPE_BADGE_CLS[type]}`}>
      {icon} {label}
    </span>
  )
}

const ALL_TYPES = Object.keys(TYPE_CONFIG) as UseCaseType[]
const ALL_CATEGORIES = Object.keys(CATEGORIES) as Category[]

function TypeFilterChips({
  value,
  onChange,
}: {
  value: UseCaseType | 'all'
  onChange: (v: UseCaseType | 'all') => void
}) {
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <span className="text-sm text-t4 font-semibold uppercase tracking-wider w-20 shrink-0">Type</span>
      {ALL_TYPES.map((t) => {
        const { label, icon, activeCls } = TYPE_CONFIG[t]
        const active = value === t
        return (
          <button
            key={t}
            onClick={() => onChange(active ? 'all' : t)}
            className={`text-sm px-3.5 py-1.5 rounded-full font-medium border transition-all ${
              active ? activeCls : 'bg-tsurf border-tborder text-t3 hover:text-t1 hover:border-t2'
            }`}
          >
            {icon} {label}
          </button>
        )
      })}
    </div>
  )
}

function CategoryFilterChips({
  value,
  onChange,
}: {
  value: Category | 'all'
  onChange: (v: Category | 'all') => void
}) {
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <span className="text-sm text-t4 font-semibold uppercase tracking-wider w-20 shrink-0">Category</span>
      {ALL_CATEGORIES.map((cat) => {
        const active = value === cat
        return (
          <button
            key={cat}
            onClick={() => onChange(active ? 'all' : cat)}
            className={`text-sm px-3.5 py-1.5 rounded-full font-medium border transition-all ${
              active
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-tsurf border-tborder text-t3 hover:text-t1 hover:border-t2'
            }`}
          >
            {CATEGORIES[cat].label}
          </button>
        )
      })}
    </div>
  )
}

const STATUS_ICON: Record<Status, string> = {
  working:       '✅',
  partial:       '🔧',
  'not-working': '🚫',
  gap:           '❌',
}

// ── Domain buckets (mirrors docs/apps_overview.svg) ───────────────────────────

type BucketAccent = 'indigo' | 'emerald' | 'amber' | 'pink' | 'cyan' | 'violet' | 'slate'

interface Bucket {
  id: string
  title: string
  ids: string[]
  accent: BucketAccent
}

const BUCKETS: Bucket[] = [
  { id: 'research',     title: 'Research & Knowledge',  accent: 'indigo',
    ids: ['paper-scout','wiki-dive','web-researcher','youtube-research','webpage-summarizer','hiking-research','movie-recommender'] },
  { id: 'content',      title: 'Content Creation',      accent: 'emerald',
    ids: ['newsletter','deck-forge','arch-diagram','api-doc-gen'] },
  { id: 'documents',    title: 'Documents & Media Q&A', accent: 'amber',
    ids: ['box-qa','video-qa','drop-summarizer','voice-journal'] },
  { id: 'productivity', title: 'Productivity',          accent: 'pink',
    ids: ['smart-todo','travel-agent'] },
  { id: 'ops',          title: 'Ops & Alerts',          accent: 'cyan',
    ids: ['server-monitor','stock-alert'] },
  { id: 'developer',    title: 'Developer & Eval Tools', accent: 'violet',
    ids: ['code-reviewer','bird-invocable-api'] },
  { id: 'ibm',          title: 'IBM Stack',             accent: 'slate',
    ids: ['ibm-cloud-advisor','ibm-docs-qa','ibm-whats-new'] },
]

const BUCKET_ACCENT: Record<BucketAccent, { bar: string; badge: string; pill: string; ring: string }> = {
  indigo:  { bar: 'bg-indigo-500',  badge: 'text-indigo-500',
             pill: 'border-indigo-500/30 hover:border-indigo-500 hover:bg-indigo-500/5',
             ring: 'ring-indigo-500/40' },
  emerald: { bar: 'bg-emerald-500', badge: 'text-emerald-500',
             pill: 'border-emerald-500/30 hover:border-emerald-500 hover:bg-emerald-500/5',
             ring: 'ring-emerald-500/40' },
  amber:   { bar: 'bg-amber-500',   badge: 'text-amber-500',
             pill: 'border-amber-500/30 hover:border-amber-500 hover:bg-amber-500/5',
             ring: 'ring-amber-500/40' },
  pink:    { bar: 'bg-pink-500',    badge: 'text-pink-500',
             pill: 'border-pink-500/30 hover:border-pink-500 hover:bg-pink-500/5',
             ring: 'ring-pink-500/40' },
  cyan:    { bar: 'bg-cyan-500',    badge: 'text-cyan-500',
             pill: 'border-cyan-500/30 hover:border-cyan-500 hover:bg-cyan-500/5',
             ring: 'ring-cyan-500/40' },
  violet:  { bar: 'bg-violet-500',  badge: 'text-violet-500',
             pill: 'border-violet-500/30 hover:border-violet-500 hover:bg-violet-500/5',
             ring: 'ring-violet-500/40' },
  slate:   { bar: 'bg-slate-500',   badge: 'text-t3',
             pill: 'border-tborder hover:border-slate-400 hover:bg-tsurf2',
             ring: 'ring-slate-500/40' },
}

function DomainBuckets({
  useCases,
  activeBucket,
  onSelectBucket,
}: {
  useCases: typeof USE_CASES
  activeBucket: string | null
  onSelectBucket: (id: string | null) => void
}) {
  const navigate = useNavigate()

  const ucById = useMemo(() => {
    const m = new Map<string, (typeof USE_CASES)[number]>()
    for (const uc of useCases) m.set(uc.id, uc)
    return m
  }, [useCases])

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-t1">Browse by domain</h3>
          <p className="text-sm text-t3">
            7 capability domains · {BUCKETS.reduce((n, b) => n + b.ids.length, 0)} apps · click a bucket to filter the table below
          </p>
        </div>
        {activeBucket && (
          <button
            onClick={() => onSelectBucket(null)}
            className="text-sm font-medium text-t3 hover:text-t1 px-3 py-1.5 bg-tsurf border border-tborder rounded-lg transition-colors"
          >
            ← Show all apps
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {BUCKETS.map((bucket) => {
          const active = bucket.id === activeBucket
          const dimmed = activeBucket !== null && !active
          const a = BUCKET_ACCENT[bucket.accent]
          const apps = bucket.ids
            .map((id) => ucById.get(id))
            .filter(Boolean) as (typeof USE_CASES)
          return (
            <div
              key={bucket.id}
              className={`bg-tsurf border border-tborder rounded-xl overflow-hidden shadow-sm transition-all ${
                active ? `ring-2 ${a.ring} shadow-md` : ''
              } ${dimmed ? 'opacity-50 hover:opacity-100' : ''}`}
            >
              <button
                onClick={() => onSelectBucket(active ? null : bucket.id)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-tsurf2 transition-colors"
              >
                <div className={`w-1.5 h-9 rounded-full ${a.bar}`} />
                <div className="flex-1 text-left">
                  <div className="text-sm font-semibold text-t1 leading-tight">{bucket.title}</div>
                  <div className="text-xs text-t4 mt-0.5">
                    {apps.length} {apps.length === 1 ? 'app' : 'apps'}
                    {active && <span className={`ml-1.5 font-semibold ${a.badge}`}>· filtering ↓</span>}
                  </div>
                </div>
                <span className={`text-xs font-bold px-2 py-1 rounded-full bg-tsurf2 ${a.badge}`}>
                  {apps.length}
                </span>
                <svg
                  className={`w-4 h-4 text-t4 transition-transform ${active ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 20 20"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8l5 5 5-5" />
                </svg>
              </button>
              {active && (
                <div className="px-4 pb-4 pt-3 border-t border-tborder/60 bg-tsurf2/40">
                  <div className="flex flex-wrap gap-1.5">
                    {apps.map((uc) => (
                      <button
                        key={uc.id}
                        onClick={(e: React.MouseEvent) => { e.stopPropagation(); navigate(`/use-case/${uc.id}`) }}
                        className={`text-xs font-medium px-2.5 py-1.5 rounded-md bg-tsurf border ${a.pill} text-t1 transition-colors whitespace-nowrap`}
                        title={uc.tagline}
                      >
                        {uc.name}
                        <StageGlyph id={uc.id} ml="ml-1" />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Use case table ────────────────────────────────────────────────────────────

interface TableProps {
  useCases: typeof USE_CASES
  search: string
  filterStatus: Status | 'all'
  filterType: UseCaseType | 'all'
  filterCategory: Category | 'all'
  filterBucket: string | null
  filterShip: ShipFilter
}

function UseCaseTable({ useCases, search, filterStatus, filterType, filterCategory, filterBucket, filterShip }: TableProps) {
  const navigate = useNavigate()

  const bucketAppIds = useMemo(() => {
    if (!filterBucket) return null
    const b = BUCKETS.find((x) => x.id === filterBucket)
    return b ? new Set(b.ids) : null
  }, [filterBucket])

  const filtered = useCases
    .filter((uc) => {
      if (bucketAppIds && !bucketAppIds.has(uc.id)) return false
      const matchesSearch =
        !search ||
        uc.name.toLowerCase().includes(search.toLowerCase()) ||
        uc.tagline.toLowerCase().includes(search.toLowerCase())
      const matchesStatus = filterStatus === 'all' || uc.status === filterStatus
      const matchesType = filterType === 'all' || uc.type === filterType
      const matchesCategory = filterCategory === 'all' || uc.category === filterCategory
      const matchesShip = filterShip === 'all' || stageOf(uc.id) === filterShip
      return matchesSearch && matchesStatus && matchesType && matchesCategory && matchesShip
    })
    // Stable sort: ship-ready first, then for-later, then exploratory.
    .sort((a, b) => {
      const order: Record<Stage, number> = { 'ship-ready': 0, 'for-later': 1, 'exploratory': 2 }
      return order[stageOf(a.id)] - order[stageOf(b.id)]
    })

  if (filtered.length === 0) {
    return <div className="py-12 text-center text-t3 text-base">No use cases match your filters.</div>
  }

  const UNIVERSAL_VARS = ['LLM_PROVIDER', 'LLM_MODEL', 'RITS_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'AGENT_SETTING_CONFIG']

  return (
    <div className="bg-tsurf border border-tborder rounded-2xl overflow-hidden shadow-sm">
      <table className="w-full">
        <thead>
          <tr className="border-b-2 border-tborder bg-tsurf2">
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-6 py-4 w-10">#</th>
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-4 py-4">Use Case</th>
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-4 py-4 hidden md:table-cell">Type</th>
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-4 py-4 hidden lg:table-cell">Category</th>
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-4 py-4 hidden xl:table-cell">Tools</th>
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-4 py-4 hidden xl:table-cell">ENV Vars</th>
            <th className="text-left text-sm font-semibold text-t4 uppercase tracking-wider px-4 py-4">Status</th>
            <th className="px-4 py-4 w-10"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-tborder">
          {filtered.map((uc, i) => {
            const statusInfo = STATUS_LABELS[uc.status]
            const catInfo = CATEGORIES[uc.category]
            const visibleTools = uc.tools.slice(0, 3)
            const extraTools = uc.tools.length - visibleTools.length
            const appEnvs = uc.howToRun.envVars.filter(v => !UNIVERSAL_VARS.includes(v))
            const visibleEnvs = appEnvs.slice(0, 3)
            const extraEnvs = appEnvs.length - visibleEnvs.length
            // null on Hugging Face when the app isn't deployed to CE; null
            // on local when uc.appUrl itself is null.
            const launchUrl = uc.comingSoon ? null : resolveAppUrl(uc)
            return (
              <tr
                key={uc.id}
                onClick={() => navigate(`/use-case/${uc.id}`)}
                className="hover:bg-tsurf2 cursor-pointer transition-colors group"
              >
                <td className="px-6 py-5 text-t4 text-sm font-mono">{i + 1}</td>
                <td className="px-4 py-5">
                  <div className="font-semibold text-t1 text-lg group-hover:text-indigo-500 transition-colors leading-snug">
                    {uc.name}<StageGlyph id={uc.id} ml="ml-1.5" />
                  </div>
                  <div className="text-sm text-t3 mt-1 leading-relaxed">{uc.tagline}</div>
                </td>
                <td className="px-4 py-5 hidden md:table-cell">
                  <TypeBadge type={uc.type} />
                </td>
                <td className="px-4 py-5 hidden lg:table-cell">
                  <span className="text-sm px-2.5 py-1 rounded-full font-medium bg-tsurf2 text-t3 border border-tborder">
                    {catInfo.label}
                  </span>
                </td>
                <td className="px-4 py-5 hidden xl:table-cell">
                  {(!uc.mcpUsage || uc.mcpUsage.length === 0) && (uc.inlineTools?.length ?? 0) === 0 && uc.tools.length === 0 ? (
                    <span className="text-sm text-t4">—</span>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      {uc.mcpUsage?.map((u) => (
                        <div key={u.server} className="flex flex-wrap items-center gap-1">
                          <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-md font-semibold bg-emerald-900/30 text-emerald-300 border border-emerald-800/40 whitespace-nowrap">
                            mcp-{u.server}
                          </span>
                          {u.tools.slice(0, 3).map((t) => (
                            <span key={t} className="text-xs px-2 py-1 rounded-md font-mono bg-tsurf2 text-t3 border border-tborder whitespace-nowrap">
                              {t}
                            </span>
                          ))}
                          {u.tools.length > 3 && (
                            <span className="text-xs px-2 py-1 rounded-md bg-tsurf2 text-t4 border border-tborder">+{u.tools.length - 3}</span>
                          )}
                        </div>
                      ))}
                      {(uc.inlineTools?.length ?? 0) > 0 && (
                        <div className="flex flex-wrap items-center gap-1">
                          <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-md font-semibold bg-amber-900/30 text-amber-300 border border-amber-800/40 whitespace-nowrap">
                            inline
                          </span>
                          {uc.inlineTools!.slice(0, 3).map((t) => (
                            <span key={t} className="text-xs px-2 py-1 rounded-md font-mono bg-tsurf2 text-t3 border border-tborder whitespace-nowrap">
                              {t}
                            </span>
                          ))}
                          {uc.inlineTools!.length > 3 && (
                            <span className="text-xs px-2 py-1 rounded-md bg-tsurf2 text-t4 border border-tborder">+{uc.inlineTools!.length - 3}</span>
                          )}
                        </div>
                      )}
                      {/* Fallback: legacy `tools` for entries that haven't been migrated yet */}
                      {(!uc.mcpUsage || uc.mcpUsage.length === 0) && (uc.inlineTools?.length ?? 0) === 0 && uc.tools.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {visibleTools.map((t) => (
                            <span key={t} className="text-xs px-2 py-1 rounded-md font-mono bg-tsurf2 text-t3 border border-tborder whitespace-nowrap">
                              {t}
                            </span>
                          ))}
                          {extraTools > 0 && (
                            <span className="text-xs px-2 py-1 rounded-md bg-tsurf2 text-t4 border border-tborder">+{extraTools}</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </td>
                <td className="px-4 py-5 hidden xl:table-cell">
                  {appEnvs.length === 0 ? (
                    <span className="text-sm text-t4">—</span>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {visibleEnvs.map((v) => (
                        <span key={v} className="text-xs px-2 py-1 rounded-md font-mono bg-amber-500/10 text-amber-600 border border-amber-500/20 whitespace-nowrap">
                          {v}
                        </span>
                      ))}
                      {extraEnvs > 0 && (
                        <span className="text-xs px-2 py-1 rounded-md bg-tsurf2 text-t4 border border-tborder">
                          +{extraEnvs}
                        </span>
                      )}
                    </div>
                  )}
                </td>
                <td className="px-4 py-5">
                  <span className={`text-sm font-medium text-${statusInfo.color}-500`}>
                    {STATUS_ICON[uc.status]} {statusInfo.label}
                  </span>
                </td>
                <td className="px-4 py-5 text-right" onClick={(e) => e.stopPropagation()}>
                  {uc.comingSoon ? (
                    <span className="inline-block px-3 py-1.5 text-sm font-medium bg-tsurf2 text-t4 border border-tborder rounded-lg whitespace-nowrap">
                      Coming soon
                    </span>
                  ) : launchUrl ? (
                    <a
                      href={launchUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block px-3.5 py-1.5 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors whitespace-nowrap shadow-sm"
                    >
                      Try it →
                    </a>
                  ) : (
                    <span className="text-t4 text-base">→</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState<Status | 'all'>('all')
  const [filterType, setFilterType] = useState<UseCaseType | 'all'>('all')
  const [filterCategory, setFilterCategory] = useState<Category | 'all'>('all')
  const [filterBucket, setFilterBucket] = useState<string | null>(null)
  const [filterShip, setFilterShip] = useState<ShipFilter>('ship-ready')

  const visible = USE_CASES.filter((u) => !u.hidden)

  const counts = useMemo(() => ({
    working:      visible.filter((u) => u.status === 'working').length,
    partial:      visible.filter((u) => u.status === 'partial').length,
    notWorking:   visible.filter((u) => u.status === 'not-working').length,
    gap:          visible.filter((u) => u.status === 'gap').length,
  }), [])

  const tableProps = { search, filterStatus, filterType, filterCategory, filterBucket, filterShip }

  return (
    <div className="p-6 md:p-8 max-w-screen-2xl mx-auto">

      {/* ── Hero ── */}
      <div className="mb-10">
        <h2 className="text-4xl font-bold text-t1 mb-1 tracking-tight">CUGA Apps</h2>
        <p className="text-base text-t3 mb-8">AI-powered demo apps built on the CUGA agent framework</p>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 max-w-3xl">
          <div className="bg-emerald-500/10 border border-emerald-500/25 rounded-2xl p-5">
            <div className="text-4xl font-bold text-emerald-500 mb-1">{counts.working}</div>
            <div className="text-sm font-medium text-emerald-600/80">Working demos</div>
          </div>
          <div className="bg-amber-500/10 border border-amber-500/25 rounded-2xl p-5">
            <div className="text-4xl font-bold text-amber-500 mb-1">{counts.partial}</div>
            <div className="text-sm font-medium text-amber-600/80">Partial / setup needed</div>
          </div>
          <div className="bg-orange-500/10 border border-orange-500/25 rounded-2xl p-5">
            <div className="text-4xl font-bold text-orange-500 mb-1">{counts.notWorking}</div>
            <div className="text-sm font-medium text-orange-600/80">Not working</div>
          </div>
          <div className="bg-tsurf2 border border-tborder rounded-2xl p-5">
            <div className="text-4xl font-bold text-t3 mb-1">{counts.gap}</div>
            <div className="text-sm font-medium text-t4">On roadmap</div>
          </div>
        </div>
      </div>

      {/* ── Universal env vars ── */}
      <div className="mb-8 px-5 py-4 bg-tsurf border border-tborder rounded-2xl">
        <div className="text-base font-semibold text-t1 mb-3">Required for all apps</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { key: 'AGENT_SETTING_CONFIG', value: 'settings.rits.toml' },
            { key: 'LLM_MODEL', value: 'gpt-oss-120b' },
            { key: 'LLM_PROVIDER', value: 'rits' },
          ].map(({ key, value }) => (
            <div key={key} className="flex flex-col gap-1 bg-tsurf2 border border-tborder rounded-xl px-3.5 py-2.5">
              <span className="font-mono text-sm font-semibold text-amber-600">{key}</span>
              <span className="font-mono text-sm text-t2">{value}</span>
            </div>
          ))}
          <div className="flex flex-col gap-1 bg-tsurf2 border border-tborder rounded-xl px-3.5 py-2.5">
            <span className="font-mono text-sm font-semibold text-amber-600">RITS_API_KEY</span>
            <span className="text-sm text-t3">
              TunnelAll VPN →{' '}
              <a href="http://rits.fmaas.res.ibm.com/" target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">
                rits.fmaas.res.ibm.com
              </a>
            </span>
          </div>
        </div>
      </div>

      {/* ── Domain buckets (mirrors docs/apps_overview.svg; click filters table) ── */}
      <DomainBuckets useCases={visible} activeBucket={filterBucket} onSelectBucket={setFilterBucket} />

      {/* ── Filters ── */}
      <div className="flex flex-col gap-4 mb-6">
        <div className="flex flex-wrap gap-3 items-center">
          <input
            type="text"
            placeholder="Search use cases..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-4 py-2 bg-tsurf border border-tborder rounded-xl text-base text-t1 placeholder-t4 focus:outline-none focus:border-indigo-500 w-72"
          />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as Status | 'all')}
            className="px-4 py-2 bg-tsurf border border-tborder rounded-xl text-base text-t2 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All statuses</option>
            <option value="working">Working</option>
            <option value="partial">Partial</option>
            <option value="not-working">Not working</option>
            <option value="gap">Gap</option>
          </select>
          {(search || filterStatus !== 'all' || filterType !== 'all' || filterCategory !== 'all' || filterBucket || filterShip !== 'ship-ready') && (
            <button
              onClick={() => { setSearch(''); setFilterStatus('all'); setFilterType('all'); setFilterCategory('all'); setFilterBucket(null); setFilterShip('ship-ready') }}
              className="px-4 py-2 text-sm font-medium text-t3 hover:text-t1 bg-tsurf2 border border-tborder rounded-xl transition-colors"
            >
              Clear all
            </button>
          )}
        </div>
        <ShipFilterChips value={filterShip} onChange={setFilterShip} />
        <TypeFilterChips value={filterType} onChange={setFilterType} />
        <CategoryFilterChips value={filterCategory} onChange={setFilterCategory} />
      </div>

      {/* ── Use cases table ── */}
      <UseCaseTable useCases={visible} {...tableProps} />

      <p className="mt-5 text-sm text-t4">
        Click any row to see architecture, run instructions, and how CUGA powers it.{' '}
        <span className="text-amber-500">✦</span> ship-ready ·{' '}
        <span className="text-purple-500">⚗</span> exploratory · everything else is for-later
      </p>
    </div>
  )
}
