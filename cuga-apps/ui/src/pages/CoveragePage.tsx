import { useState, useMemo } from 'react'
import {
  OPENCLAW_USE_CASES, OPENCLAW_CATEGORIES,
  MANUS_USE_CASES_COVERAGE,
  type UseCaseType,
} from '../data/coverage'

// ── Type badge ────────────────────────────────────────────────────────────────

const TYPE_BADGE_CLS: Record<UseCaseType, string> = {
  'event-driven':  'bg-amber-500/10 text-amber-600 border-amber-500/30',
  'multimodal':    'bg-purple-500/10 text-purple-600 border-purple-500/30',
  'both':          'bg-teal-500/10 text-teal-600 border-teal-500/30',
  'conversational':'bg-blue-500/10 text-blue-600 border-blue-500/30',
}

const TYPE_ACTIVE_CLS: Record<UseCaseType, string> = {
  'event-driven':  'bg-amber-500 text-white border-amber-500',
  'multimodal':    'bg-purple-500 text-white border-purple-500',
  'both':          'bg-teal-500 text-white border-teal-500',
  'conversational':'bg-blue-500 text-white border-blue-500',
}

const TYPE_LABEL: Record<UseCaseType, { icon: string; label: string }> = {
  'event-driven':  { icon: '⚡', label: 'Event-driven' },
  'multimodal':    { icon: '🎨', label: 'Multimodal' },
  'both':          { icon: '✨', label: 'Both' },
  'conversational':{ icon: '💬', label: 'Conversational' },
}

const ALL_TYPES = Object.keys(TYPE_LABEL) as UseCaseType[]

function TypeBadge({ type }: { type: UseCaseType }) {
  const { icon, label } = TYPE_LABEL[type]
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium border ${TYPE_BADGE_CLS[type]}`}>
      {icon} {label}
    </span>
  )
}

function TypeFilterChips({
  value,
  onChange,
}: {
  value: UseCaseType | 'all'
  onChange: (v: UseCaseType | 'all') => void
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-t4 font-medium uppercase tracking-wider">Type:</span>
      {ALL_TYPES.map((t) => {
        const { icon, label } = TYPE_LABEL[t]
        const active = value === t
        return (
          <button
            key={t}
            onClick={() => onChange(active ? 'all' : t)}
            className={`text-xs px-2.5 py-1 rounded-full font-medium border transition-all ${
              active ? TYPE_ACTIVE_CLS[t] : 'bg-tsurf border-tborder text-t3 hover:text-t2 hover:border-t3'
            }`}
          >
            {icon} {label}
          </button>
        )
      })}
    </div>
  )
}

// ── OpenClaw table ────────────────────────────────────────────────────────────

function OpenClawTable() {
  const [search, setSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState<string>('all')
  const [filterType, setFilterType] = useState<UseCaseType | 'all'>('all')

  const filtered = useMemo(() => {
    return OPENCLAW_USE_CASES.filter((uc) => {
      const q = search.toLowerCase()
      const matchSearch = !q || uc.name.toLowerCase().includes(q)
      const matchCat = filterCategory === 'all' || uc.category === filterCategory
      const matchType = filterType === 'all' || uc.type === filterType
      return matchSearch && matchCat && matchType
    })
  }, [search, filterCategory, filterType])

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-base font-semibold text-t1">OpenClaw — 82 Use Cases</h3>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-2 mb-4">
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="Search use cases..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="px-3 py-1.5 bg-tsurf border border-tborder rounded-lg text-sm text-t1 placeholder-t4 focus:outline-none focus:border-indigo-500 w-52"
          />
          <select
            value={filterCategory}
            onChange={e => setFilterCategory(e.target.value)}
            className="px-3 py-1.5 bg-tsurf border border-tborder rounded-lg text-sm text-t2 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All categories</option>
            {OPENCLAW_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          {(search || filterCategory !== 'all' || filterType !== 'all') && (
            <button
              onClick={() => { setSearch(''); setFilterCategory('all'); setFilterType('all') }}
              className="px-3 py-1.5 text-xs text-t3 hover:text-t2"
            >
              Clear all
            </button>
          )}
        </div>
        <TypeFilterChips value={filterType} onChange={setFilterType} />
      </div>

      <div className="bg-tsurf border border-tborder rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-tborder bg-tsurf2">
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-4 py-2.5 w-8">#</th>
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-3 py-2.5">Use Case</th>
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell">Category</th>
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-3 py-2.5 hidden md:table-cell">Type</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-tb2">
            {filtered.map(uc => (
              <tr key={uc.id} className="hover:bg-tsurf2">
                <td className="px-4 py-2.5 text-xs font-mono text-t4">{uc.id}</td>
                <td className="px-3 py-2.5 text-sm text-t2">{uc.name}</td>
                <td className="px-3 py-2.5 hidden lg:table-cell">
                  <span className="text-xs text-t3">{uc.category}</span>
                </td>
                <td className="px-3 py-2.5 hidden md:table-cell">
                  <TypeBadge type={uc.type} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="py-10 text-center text-t3 text-sm">No matching use cases.</div>
        )}
      </div>

      {/* Category breakdown */}
      <div className="mt-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
        {OPENCLAW_CATEGORIES.map(cat => {
          const inCat = OPENCLAW_USE_CASES.filter(u => u.category === cat)
          return (
            <button
              key={cat}
              onClick={() => setFilterCategory(filterCategory === cat ? 'all' : cat)}
              className={`text-left p-2.5 rounded-lg border text-xs transition-colors ${
                filterCategory === cat
                  ? 'border-indigo-500 bg-indigo-500/10'
                  : 'border-tborder bg-tsurf hover:border-t3 hover:bg-tsurf2'
              }`}
            >
              <div className="text-t2 font-medium mb-1 leading-tight">{cat}</div>
              <div className="font-mono text-t4">{inCat.length} use cases</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Manus table ───────────────────────────────────────────────────────────────

function ManusTable() {
  return (
    <div>
      <div className="mb-4">
        <h3 className="text-base font-semibold text-t1">Manus AI — 20 Use Cases</h3>
      </div>

      <div className="bg-tsurf border border-tborder rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-tborder bg-tsurf2">
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-4 py-2.5 w-8">#</th>
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-3 py-2.5">Use Case</th>
              <th className="text-left text-xs font-semibold text-t4 uppercase tracking-wider px-3 py-2.5 hidden md:table-cell">Type</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-tb2">
            {MANUS_USE_CASES_COVERAGE.map(uc => (
              <tr key={uc.id} className="hover:bg-tsurf2">
                <td className="px-4 py-2.5 text-xs font-mono text-t4">{uc.id}</td>
                <td className="px-3 py-2.5 text-sm text-t2">{uc.name}</td>
                <td className="px-3 py-2.5 hidden md:table-cell"><TypeBadge type={uc.type} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Tab = 'openclaw' | 'manus'

export default function CoveragePage() {
  const [tab, setTab] = useState<Tab>('openclaw')

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-t1 mb-1">OpenClaw / Manus</h2>
        <p className="text-t3 text-sm">
          Use cases from OpenClaw's benchmark (82) and Manus's publicly demonstrated scenarios (20).
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-tsurf2 border border-tborder rounded-lg p-1 w-fit">
        <button
          onClick={() => setTab('openclaw')}
          className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
            tab === 'openclaw'
              ? 'bg-tsurf text-t1 shadow-sm'
              : 'text-t3 hover:text-t2'
          }`}
        >
          OpenClaw (82)
        </button>
        <button
          onClick={() => setTab('manus')}
          className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
            tab === 'manus'
              ? 'bg-tsurf text-t1 shadow-sm'
              : 'text-t3 hover:text-t2'
          }`}
        >
          Manus (20)
        </button>
      </div>

      {tab === 'openclaw' ? <OpenClawTable /> : <ManusTable />}
    </div>
  )
}
