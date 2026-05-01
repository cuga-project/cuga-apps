import { useState, useMemo } from 'react'

const SECTIONS = [
  {
    domain: 'Finance & Investment',
    items: [
      { id: 1, title: 'Automated earnings call analysis + investor brief generation', flag: 'enterprise' },
      { id: 2, title: 'LBO target screening dashboard with scoring', flag: 'enterprise' },
      { id: 3, title: 'Accounts payable/receivable agent — invoice intake to approval', flag: 'enterprise' },
      { id: 4, title: 'Expense report automation — receipt → categorize → approve', flag: 'enterprise' },
      { id: 5, title: 'Real-time stock portfolio risk monitor with alert generation', flag: 'enterprise' },
      { id: 6, title: 'SOTP / DCF valuation model builder from public filings', flag: 'enterprise' },
      { id: 7, title: 'Regulatory filing tracker (SEC, SEBI, MAS) with change alerts', flag: 'enterprise' },
      { id: 8, title: 'Polymarket / prediction market autopilot', flag: 'productivity' },
      { id: 9, title: 'Personal net worth dashboard — auto-sync accounts, auto-categorize', flag: 'productivity' },
      { id: 10, title: 'Stock screening agent with custom thesis validation', flag: 'productivity' },
      { id: 11, title: 'Econometric model builder for macro analysis (GDP, inflation)', flag: 'researcher' },
      { id: 12, title: 'Alternative data pipeline (satellite, credit card) → alpha signal', flag: 'researcher' },
    ],
  },
  {
    domain: 'Legal',
    items: [
      { id: 13, title: 'Contract review agent — flag missing clauses, redline suggestions', flag: 'enterprise' },
      { id: 14, title: 'Lease agreement key terms extractor + risk scorer', flag: 'enterprise' },
      { id: 15, title: 'Litigation research agent — case law search + brief drafting', flag: 'enterprise' },
      { id: 16, title: 'Regulatory compliance tracker — new regulation → gap analysis', flag: 'enterprise' },
      { id: 17, title: 'NDA/MSA generation from deal parameters', flag: 'enterprise' },
      { id: 18, title: 'IP portfolio monitor — patent landscape + competitor filings', flag: 'enterprise' },
      { id: 19, title: 'Legal discovery assistant — document triage and relevance scoring', flag: 'enterprise' },
      { id: 20, title: 'Employment contract compliance checker by jurisdiction', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Healthcare & Life Sciences',
    items: [
      { id: 21, title: 'Clinical trial matching agent — patient profile → eligible trials', flag: 'enterprise' },
      { id: 22, title: 'Medical coding automation (ICD-10, CPT) from clinical notes', flag: 'enterprise' },
      { id: 23, title: 'Drug interaction checker integrated into EHR workflow', flag: 'enterprise' },
      { id: 24, title: 'Adverse event report drafting (FAERS / MedWatch)', flag: 'enterprise' },
      { id: 25, title: 'Tissue / biospecimen cryopreservation protocol generator', flag: 'enterprise' },
      { id: 26, title: 'Health optimization plan — labs + lifestyle → personalized protocol', flag: 'productivity' },
      { id: 27, title: 'Literature review agent for clinical research', flag: 'researcher' },
      { id: 28, title: 'Genomics data interpretation assistant for clinicians', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Sales & Marketing',
    items: [
      { id: 29, title: 'CRM enrichment agent — auto-update contact/account from web', flag: 'enterprise' },
      { id: 30, title: 'Lead scoring + prioritization from inbound signals', flag: 'enterprise' },
      { id: 31, title: 'Personalized outbound email sequence generator', flag: 'enterprise' },
      { id: 32, title: 'Competitive intelligence monitor — track competitor moves daily', flag: 'enterprise' },
      { id: 33, title: 'Campaign performance analyst — metrics → insights → next actions', flag: 'enterprise' },
      { id: 34, title: 'SEO audit + content gap analysis agent', flag: 'enterprise' },
      { id: 35, title: 'Influencer research and brand-fit scoring', flag: 'enterprise' },
      { id: 36, title: 'B2B intake form → scoped proposal generator', flag: 'enterprise' },
      { id: 37, title: 'Social media multi-source digest (Reddit, X, LinkedIn, news)', flag: 'productivity' },
      { id: 38, title: 'Content factory — brief → draft → schedule across platforms', flag: 'productivity' },
    ],
  },
  {
    domain: 'Human Resources & Operations',
    items: [
      { id: 39, title: 'Employee onboarding/offboarding lifecycle agent', flag: 'enterprise' },
      { id: 40, title: 'Job description writer + multi-board poster', flag: 'enterprise' },
      { id: 41, title: 'Resume screener with structured scorecard output', flag: 'enterprise' },
      { id: 42, title: 'Interview scheduling coordinator (calendar + comms)', flag: 'enterprise' },
      { id: 43, title: 'Performance review aggregator — 360 inputs → structured summary', flag: 'enterprise' },
      { id: 44, title: 'HR policy Q&A bot — employee self-service (payroll, PTO, benefits)', flag: 'enterprise' },
      { id: 45, title: 'Workforce planning model — headcount vs. growth scenarios', flag: 'enterprise' },
      { id: 46, title: 'Learning & development path generator per role + skill gaps', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Customer Experience & Support',
    items: [
      { id: 47, title: 'Tier-1 support agent with escalation routing', flag: 'enterprise' },
      { id: 48, title: 'Ticket sentiment analysis + SLA breach predictor', flag: 'enterprise' },
      { id: 49, title: 'Customer churn predictor with proactive outreach trigger', flag: 'enterprise' },
      { id: 50, title: 'Voice-of-customer synthesizer — reviews → themes → action items', flag: 'enterprise' },
      { id: 51, title: 'Returns/refund processing automation', flag: 'enterprise' },
      { id: 52, title: 'Multilingual support agent', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Real Estate & Construction',
    items: [
      { id: 53, title: 'Commercial real estate brokerage analysis across metros', flag: 'enterprise' },
      { id: 54, title: 'Property valuation agent — comps + market data → price estimate', flag: 'enterprise' },
      { id: 55, title: 'Construction project progress tracker — reports + photo analysis', flag: 'enterprise' },
      { id: 56, title: 'Zoning compliance checker by municipality', flag: 'enterprise' },
      { id: 57, title: '3D interactive room/floor plan visualizer from description', flag: 'productivity' },
      { id: 58, title: 'Rental lease management + renewal alert system', flag: 'productivity' },
    ],
  },
  {
    domain: 'Education',
    items: [
      { id: 59, title: 'Adaptive curriculum generator per student skill level', flag: 'enterprise' },
      { id: 60, title: 'Automated grading + detailed feedback agent', flag: 'enterprise' },
      { id: 61, title: 'Physics / math concept animator (SVG/interactive)', flag: 'productivity' },
      { id: 62, title: 'Interactive Transformer / ML architecture learning webpage', flag: 'productivity' },
      { id: 63, title: 'Quantum computing interactive explainer', flag: 'productivity' },
      { id: 64, title: 'LaTeX paper writing assistant', flag: 'productivity' },
      { id: 65, title: 'Reinforcement learning concept visualizer', flag: 'researcher' },
      { id: 66, title: 'Student academic progress monitor for institutions', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Research & Science',
    items: [
      { id: 67, title: 'arXiv / PubMed daily digest by topic + relevance scoring', flag: 'researcher' },
      { id: 68, title: 'Systematic literature review automation (search → screen → extract)', flag: 'researcher' },
      { id: 69, title: 'Research hypothesis generator from existing literature gaps', flag: 'researcher' },
      { id: 70, title: 'High-temperature superconductivity research summarizer + PhD direction finder', flag: 'researcher' },
      { id: 71, title: 'Climate change impact projection tool by region/sector', flag: 'researcher' },
      { id: 72, title: 'AI researcher collaboration matchmaker', flag: 'researcher' },
      { id: 73, title: 'Hugging Face model discovery + benchmark comparator', flag: 'researcher' },
      { id: 74, title: 'Experiment tracking + auto-report generator', flag: 'researcher' },
      { id: 75, title: 'Light exposure / circadian health research summarizer', flag: 'researcher' },
    ],
  },
  {
    domain: 'Developer Tools',
    items: [
      { id: 76, title: 'Self-healing server agent — detect anomaly → diagnose → fix', flag: 'developer' },
      { id: 77, title: 'n8n / Make workflow orchestration AI assistant', flag: 'developer' },
      { id: 78, title: 'Code review agent with security + performance flags', flag: 'developer' },
      { id: 79, title: 'Automated PR description + changelog generator', flag: 'developer' },
      { id: 80, title: 'Dependency vulnerability scanner + upgrade PR creator', flag: 'developer' },
      { id: 81, title: 'API documentation generator from codebase', flag: 'developer' },
      { id: 82, title: 'Test case generator from spec / acceptance criteria', flag: 'developer' },
      { id: 83, title: 'Incident post-mortem writer — logs + timeline → RCA draft', flag: 'developer' },
      { id: 84, title: 'CI/CD pipeline failure analyzer + fix suggester', flag: 'developer' },
      { id: 85, title: 'Local dev environment setup assistant (cross-platform)', flag: 'developer' },
      { id: 86, title: 'Database schema migration planner + risk assessor', flag: 'developer' },
      { id: 87, title: 'OpenAPI spec validator + mock server generator', flag: 'developer' },
      { id: 88, title: 'Autonomous game development pipeline (asset → code → test)', flag: 'developer' },
    ],
  },
  {
    domain: 'Supply Chain & Logistics',
    items: [
      { id: 89, title: 'Demand forecasting agent — historical + signals → reorder triggers', flag: 'enterprise' },
      { id: 90, title: 'Supplier risk monitor — news + financial data → risk score', flag: 'enterprise' },
      { id: 91, title: 'Freight audit + payment automation', flag: 'enterprise' },
      { id: 92, title: 'Last-mile delivery ETA predictor + proactive customer notification', flag: 'enterprise' },
      { id: 93, title: 'Inventory reconciliation agent — WMS vs. physical count', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Media, Content & Creative',
    items: [
      { id: 94, title: 'Podcast production pipeline — record → transcribe → chapters → show notes', flag: 'productivity' },
      { id: 95, title: 'YouTube content pipeline — idea → script → thumbnail brief → schedule', flag: 'productivity' },
      { id: 96, title: 'Multi-agent content factory — one brief → blog + social + email + video script', flag: 'enterprise' },
      { id: 97, title: 'AI video editing assistant via chat', flag: 'productivity' },
      { id: 98, title: 'News aggregator with personalized briefing email', flag: 'productivity' },
      { id: 99, title: 'Podcast episode summarizer → PowerPoint slide deck', flag: 'enterprise' },
      { id: 100, title: 'Fiction manuscript formatter + submission packager', flag: 'productivity' },
    ],
  },
  {
    domain: 'Travel & Lifestyle',
    items: [
      { id: 101, title: 'Multi-city travel itinerary planner with bookings', flag: 'productivity' },
      { id: 102, title: 'Corporate travel policy compliance checker + booking', flag: 'enterprise' },
      { id: 103, title: 'Long-haul family trip planner (visas, vaccines, logistics)', flag: 'productivity' },
      { id: 104, title: 'Restaurant / experience recommender by vibe + constraints', flag: 'productivity' },
    ],
  },
  {
    domain: 'Energy & Sustainability',
    items: [
      { id: 105, title: 'Self-sufficient solar home proposal generator', flag: 'productivity' },
      { id: 106, title: 'Carbon footprint tracker + reduction planner for enterprises', flag: 'enterprise' },
      { id: 107, title: 'Energy consumption anomaly detector for facilities', flag: 'enterprise' },
      { id: 108, title: 'EV fleet route optimizer with charging stop planning', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Government & Public Sector',
    items: [
      { id: 109, title: 'Constituent inquiry routing + response drafting agent', flag: 'enterprise' },
      { id: 110, title: 'Public policy impact analyzer — bill text → affected populations', flag: 'enterprise' },
      { id: 111, title: 'Grant application assistant — requirements → draft proposal', flag: 'enterprise' },
      { id: 112, title: 'FOIA request tracker + document redaction assistant', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Insurance',
    items: [
      { id: 113, title: 'Claims intake + triage automation', flag: 'enterprise' },
      { id: 114, title: 'Policy comparison agent — user profile → best product recommendation', flag: 'enterprise' },
      { id: 115, title: 'Underwriting data enrichment agent', flag: 'enterprise' },
      { id: 116, title: 'Fraud signal detection in claims submissions', flag: 'enterprise' },
    ],
  },
  {
    domain: 'Knowledge Management',
    items: [
      { id: 117, title: 'Company knowledge base (RAG) with source citations', flag: 'enterprise' },
      { id: 118, title: 'Meeting transcript → action items + decisions + follow-up drafts', flag: 'enterprise' },
      { id: 119, title: 'Semantic memory search across personal notes / Notion / Obsidian', flag: 'productivity' },
      { id: 120, title: 'Market research + product ideation factory', flag: 'enterprise' },
      { id: 121, title: 'Idea validator — concept → market size + competitive landscape + risks', flag: 'productivity' },
      { id: 122, title: 'Daily digest agent — newsletters + RSS + Slack → morning brief', flag: 'productivity' },
      { id: 123, title: 'Earnings tracker — portfolio companies → quarterly updates', flag: 'productivity' },
    ],
  },
  {
    domain: 'Original Ideas',
    items: [
      { id: 124, title: 'Board meeting prep agent — pull KPIs, recent incidents, prior minutes → board deck', flag: 'enterprise' },
      { id: 125, title: 'SaaS vendor consolidation analyzer — usage data → redundancy map + savings', flag: 'enterprise' },
      { id: 126, title: 'Employee pulse survey analyzer — open text → themes → leadership brief', flag: 'enterprise' },
      { id: 127, title: 'Technical due diligence agent — repo + docs → DD report', flag: 'enterprise' },
      { id: 128, title: 'Regulatory sandbox navigator — startup idea → jurisdiction risk map', flag: 'enterprise' },
      { id: 129, title: 'Data lineage tracer — query → upstream source map → quality flags', flag: 'developer' },
      { id: 130, title: 'Multi-jurisdiction tax filing preparation assistant', flag: 'enterprise' },
      { id: 131, title: 'Academic conference matcher — researcher profile → best submission targets', flag: 'researcher' },
      { id: 132, title: 'Peer reviewer assistant — draft paper → structured critique', flag: 'researcher' },
      { id: 133, title: 'Lab notebook digitizer — handwritten notes → structured entries', flag: 'researcher' },
      { id: 134, title: 'Open source project health monitor — GitHub metrics → maintainer alerts', flag: 'developer' },
      { id: 135, title: 'Developer relations content engine — changelog → blog + tweet + docs', flag: 'developer' },
      { id: 136, title: 'Privacy policy + ToS plain-English summarizer', flag: 'productivity' },
      { id: 137, title: 'Personal finance coach — transactions → insights + goal tracking', flag: 'productivity' },
      { id: 138, title: 'Founder fundraising CRM — investor tracking + warm intro path finder', flag: 'productivity' },
      { id: 139, title: 'Crisis communications draft generator — incident → press statement + internal comms', flag: 'enterprise' },
      { id: 140, title: 'Warranty / recall tracker — product purchases → alert on recalls', flag: 'productivity' },
    ],
  },
]

// Badge accent colors via CSS variables (defined per theme in index.css)
const BADGE_DOT: Record<string, string> = {
  enterprise:   'bg-blue-500',
  productivity: 'bg-emerald-500',
  developer:    'bg-violet-500',
  researcher:   'bg-amber-500',
}

const BADGE_LABEL: Record<string, string> = {
  enterprise:   'Enterprise',
  productivity: 'Productivity',
  developer:    'Developer',
  researcher:   'Researcher',
}

// Semi-transparent bg that works on any theme background
const BADGE_BG: Record<string, string> = {
  enterprise:   'bg-blue-500/10 border-blue-500/20',
  productivity: 'bg-emerald-500/10 border-emerald-500/20',
  developer:    'bg-violet-500/10 border-violet-500/20',
  researcher:   'bg-amber-500/10 border-amber-500/20',
}

const ALL_ITEMS = SECTIONS.flatMap((s) => s.items.map((item) => ({ ...item, domain: s.domain })))
const ALL_DOMAINS = SECTIONS.map((s) => s.domain)
const ALL_FLAGS = Object.keys(BADGE_LABEL)

function CategoryBadge({ flag }: { flag: string }) {
  if (!BADGE_LABEL[flag]) return null
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium border ${BADGE_BG[flag]}`}
      style={{ color: `var(--badge-${flag})` }}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${BADGE_DOT[flag]}`} />
      {BADGE_LABEL[flag]}
    </span>
  )
}

export default function UseCaseIdeasPage() {
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [domainFilter, setDomainFilter] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const isFiltered = !!(categoryFilter || domainFilter || search)

  const filteredItems = useMemo(() => {
    if (!isFiltered) return []
    return ALL_ITEMS.filter((item) => {
      if (categoryFilter && item.flag !== categoryFilter) return false
      if (domainFilter && item.domain !== domainFilter) return false
      if (search && !item.title.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
  }, [categoryFilter, domainFilter, search, isFiltered])

  const filteredSections = useMemo(() => {
    if (isFiltered) return []
    return SECTIONS
  }, [isFiltered])

  const stats = useMemo(() =>
    ALL_FLAGS.map((flag) => ({
      flag,
      count: ALL_ITEMS.filter((i) => i.flag === flag).length,
    })),
  [])

  const totalShown = isFiltered ? filteredItems.length : ALL_ITEMS.length

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-t1">Use Case Ideas</h2>
          <p className="text-t3 text-sm mt-1">
            {totalShown} ideas across {ALL_DOMAINS.length} domains
          </p>
        </div>

        {/* Category stat pills */}
        <div className="flex gap-2 flex-wrap shrink-0">
          {stats.map(({ flag, count }) => (
            <button
              key={flag}
              onClick={() => setCategoryFilter(categoryFilter === flag ? null : flag)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                categoryFilter === flag
                  ? `${BADGE_BG[flag]} border-current`
                  : 'bg-tsurf border-tborder text-t3 hover:border-t3 hover:text-t2'
              }`}
              style={categoryFilter === flag ? { color: `var(--badge-${flag})` } : undefined}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${BADGE_DOT[flag]}`} />
              {BADGE_LABEL[flag]}
              <span className="opacity-60 font-mono">{count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col gap-3">
        <div className="flex gap-2">
          <div className="relative flex-1 max-w-sm">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-t3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search ideas..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-tsurf border border-tborder rounded-lg pl-9 pr-3 py-2 text-sm text-t1 placeholder-t4 focus:outline-none focus:border-indigo-500"
            />
          </div>
          {isFiltered && (
            <button
              onClick={() => { setCategoryFilter(null); setDomainFilter(null); setSearch('') }}
              className="px-3 py-2 text-xs text-t3 hover:text-t2 border border-tborder rounded-lg bg-tsurf transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Domain chips */}
        <div className="flex gap-1.5 flex-wrap">
          {ALL_DOMAINS.map((domain) => (
            <button
              key={domain}
              onClick={() => setDomainFilter(domainFilter === domain ? null : domain)}
              className={`text-xs px-2.5 py-1 rounded-md font-medium transition-all border ${
                domainFilter === domain
                  ? 'bg-t1 text-tsurf border-t1'
                  : 'bg-tsurf border-tborder text-t3 hover:border-t3 hover:text-t2'
              }`}
            >
              {domain}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {isFiltered ? (
        /* Flat filtered list */
        <div className="space-y-1">
          {filteredItems.length === 0 ? (
            <div className="py-16 text-center text-t3 text-sm">No ideas match the current filters.</div>
          ) : (
            filteredItems.map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-3 px-4 py-3 rounded-xl bg-tsurf border border-tborder hover:border-t3 transition-all group"
              >
                <span className="text-xs text-t4 font-mono w-6 shrink-0 text-right">{item.id}</span>
                <span className="flex-1 text-sm text-t2 group-hover:text-t1 transition-colors">{item.title}</span>
                <span className="text-xs text-t4 shrink-0 hidden sm:block">{item.domain}</span>
                <CategoryBadge flag={item.flag} />
              </div>
            ))
          )}
        </div>
      ) : (
        /* Grouped by domain */
        <div className="space-y-8">
          {filteredSections.map((section) => (
            <div key={section.domain}>
              {/* Domain header */}
              <div className="flex items-center gap-3 mb-2">
                <button
                  onClick={() => setDomainFilter(section.domain)}
                  className="text-sm font-semibold text-t2 hover:text-indigo-500 transition-colors"
                >
                  {section.domain}
                </button>
                <div className="flex-1 h-px bg-tborder" />
                <span className="text-xs text-t4 font-mono">{section.items.length}</span>
              </div>

              {/* Items */}
              <div className="space-y-px pl-1">
                {section.items.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-tsurf2 transition-all group cursor-default"
                  >
                    <span className="text-xs text-t4 font-mono w-6 shrink-0 text-right">{item.id}</span>
                    <span className="flex-1 text-sm text-t3 group-hover:text-t1 transition-colors">{item.title}</span>
                    <CategoryBadge flag={item.flag} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
