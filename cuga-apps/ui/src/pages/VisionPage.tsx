import CodeBlock from '../components/CodeBlock'

// ─── Flywheel SVG ────────────────────────────────────────────────────────────

function FlywheelDiagram() {
  // Viewbox 800 × 440. Four pillar nodes at cardinal positions around a
  // central hub. Curved arrows connect them clockwise to show the cycle.
  const cx = 400   // center x
  const cy = 220   // center y
  const rx = 175   // orbit radius x
  const ry = 150   // orbit radius y

  // Node positions
  const top    = { x: cx,       y: cy - ry, label: 'Use Case Library',     sub: '100+ production tasks', color: '#818cf8' } // indigo
  const right  = { x: cx + rx,  y: cy,      label: 'Eval Environment',      sub: 'Benchmark for any agent', color: '#34d399' } // emerald
  const bottom = { x: cx,       y: cy + ry, label: 'Multimodal Leadership', sub: 'Every input modality', color: '#f472b6' }  // pink
  const left   = { x: cx - rx,  y: cy,      label: 'I/O Runtime',           sub: 'Channels · Tools · Host', color: '#60a5fa' } // blue

  const nodes = [top, right, bottom, left]

  // Curved arrow: a quadratic bezier from one node toward the next (clockwise),
  // offset slightly inward so the line doesn't go through the center.
  function arc(from: { x: number; y: number }, to: { x: number; y: number }, inward = 40) {
    const midX = (from.x + to.x) / 2
    const midY = (from.y + to.y) / 2
    // Pull control point toward center
    const cpX = midX + (cx - midX) * (inward / 100)
    const cpY = midY + (cy - midY) * (inward / 100)
    return `M ${from.x} ${from.y} Q ${cpX} ${cpY} ${to.x} ${to.y}`
  }

  // Clockwise arcs: top→right, right→bottom, bottom→left, left→top
  const arcs = [
    { path: arc(top, right, 35), color: '#818cf8' },
    { path: arc(right, bottom, 35), color: '#34d399' },
    { path: arc(bottom, left, 35), color: '#f472b6' },
    { path: arc(left, top, 35), color: '#60a5fa' },
  ]

  return (
    <svg
      viewBox="0 0 800 440"
      className="w-full max-w-3xl mx-auto"
      style={{ overflow: 'visible' }}
    >
      <defs>
        {/* Arrow markers per color */}
        {[
          { id: 'arr-indigo', color: '#818cf8' },
          { id: 'arr-emerald', color: '#34d399' },
          { id: 'arr-pink', color: '#f472b6' },
          { id: 'arr-blue', color: '#60a5fa' },
        ].map(({ id, color }) => (
          <marker
            key={id}
            id={id}
            markerWidth="8"
            markerHeight="8"
            refX="6"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L0,6 L8,3 z" fill={color} opacity="0.7" />
          </marker>
        ))}
        {/* Radial glow for center */}
        <radialGradient id="centerGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#4f46e5" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Orbit ellipse (subtle) */}
      <ellipse
        cx={cx} cy={cy}
        rx={rx + 30} ry={ry + 30}
        fill="none"
        stroke="#1e293b"
        strokeWidth="1"
        strokeDasharray="4 6"
      />

      {/* Center glow */}
      <circle cx={cx} cy={cy} r={70} fill="url(#centerGlow)" />

      {/* Arcs with arrows */}
      {arcs.map(({ path, color }, i) => {
        const markerIds = ['arr-indigo', 'arr-emerald', 'arr-pink', 'arr-blue']
        return (
          <path
            key={i}
            d={path}
            fill="none"
            stroke={color}
            strokeWidth="1.5"
            strokeOpacity="0.5"
            markerEnd={`url(#${markerIds[i]})`}
          />
        )
      })}

      {/* Center hub */}
      <circle cx={cx} cy={cy} r={52} fill="#0f172a" stroke="#312e81" strokeWidth="1.5" />
      <circle cx={cx} cy={cy} r={50} fill="#0f172a" stroke="#4338ca" strokeWidth="0.5" />
      <text x={cx} y={cy - 8} textAnchor="middle" fill="white" fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
        CUGA++
      </text>
      <text x={cx} y={cy + 8} textAnchor="middle" fill="#6366f1" fontSize="9" fontFamily="Inter, sans-serif">
        Platform
      </text>

      {/* Pillar nodes */}
      {nodes.map((node, i) => {
        const BOX_W = 148
        const BOX_H = 54
        const bx = node.x - BOX_W / 2
        const by = node.y - BOX_H / 2

        return (
          <g key={i}>
            {/* Glow behind box */}
            <rect
              x={bx - 2} y={by - 2}
              width={BOX_W + 4} height={BOX_H + 4}
              rx={10}
              fill={node.color}
              opacity="0.08"
            />
            {/* Box */}
            <rect
              x={bx} y={by}
              width={BOX_W} height={BOX_H}
              rx={8}
              fill="#0f172a"
              stroke={node.color}
              strokeWidth="1"
              strokeOpacity="0.5"
            />
            {/* Top accent line */}
            <rect
              x={bx + 8} y={by}
              width={BOX_W - 16} height={2}
              rx={1}
              fill={node.color}
              opacity="0.7"
            />
            {/* Label */}
            <text
              x={node.x} y={by + 20}
              textAnchor="middle"
              fill="white"
              fontSize="11"
              fontWeight="600"
              fontFamily="Inter, sans-serif"
            >
              {node.label}
            </text>
            {/* Subtitle */}
            <text
              x={node.x} y={by + 35}
              textAnchor="middle"
              fill={node.color}
              fontSize="9"
              opacity="0.8"
              fontFamily="Inter, sans-serif"
            >
              {node.sub}
            </text>
          </g>
        )
      })}

      {/* Flywheel label */}
      <text x={cx + rx + 20} y={cy - ry + 10} fill="#374151" fontSize="8" fontFamily="Inter, sans-serif" transform={`rotate(-25, ${cx + rx + 20}, ${cy - ry + 10})`}>
        reinforcing cycle
      </text>
    </svg>
  )
}

// ─── Pillar sections ──────────────────────────────────────────────────────────

const LANG_GRAPH_CODE = `# Today — plug in any .ainvoke() agent
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

langgraph_agent = create_react_agent(
    ChatAnthropic(model="claude-sonnet-4-6"),
    tools=[*make_github_tools(), *make_web_search_tool()],
)

# Drop it into CUGA++ — zero other changes
runtime = CugaRuntime(
    agent=langgraph_agent,          # ← any .ainvoke() works
    input_channels=[CronChannel(schedule="0 9 * * 1-5", message="Daily PR digest")],
    output_channels=[SlackChannel(webhook_url=os.getenv("SLACK_WEBHOOK_URL"))],
)
asyncio.run(runtime.start())`

const MOCK_HARNESS_CODE = `# The eval environment — reproducible, no live APIs needed
from cuga_eval import TaskRegistry, MockChannelHarness, run_benchmark

# Load the task suite
registry = TaskRegistry.load("cuga_benchmark_v1")  # 100+ task specs

# Bring your own agent — any .ainvoke() compatible
your_agent = YourAgent(model=..., tools=[...])

# Run against all tasks
results = run_benchmark(
    agent=your_agent,
    tasks=registry.all(),
    harness=MockChannelHarness(),   # replay recorded inputs, no live APIs
)

# Get scored results
print(results.summary())
# category        score    vs CugaAgent baseline
# documents       91%      +3%
# monitoring      78%      -5%
# communication   85%      +1%
# multimodal      62%      -14%   ← your weak spot`

const MULTIMODAL_CODE = `# What "multimodal" means in CUGA++ — extraction before reasoning
from cuga_channels import (
    DoclingChannel,   # PDF/Word/Excel/HTML/image → markdown
    AudioChannel,     # audio/video → Whisper transcript
    VideoChannel,     # video → sampled frames + transcript (roadmap)
    ScreenshotChannel # screenshot → structured description (roadmap)
)

# Example: mixed-modality task (no other framework handles this pipeline)
runtime = CugaRuntime(
    agent=agent,
    input_channels=[
        DoclingChannel(watch_dir="./contracts"),   # PDFs with tables + images
        AudioChannel(watch_dir="./voice_notes"),   # voice memos
        IMAPChannel(...),                          # emails with attachments
    ],
    output_channels=[SlackChannel(...)],
)
# Agent sees: clean markdown + clean transcript + clean email text
# Agent never touches: raw bytes, MIME, encoding, codec, page layout`

interface PillarProps {
  color: string
  borderColor: string
  bgColor: string
  icon: string
  number: string
  title: string
  tagline: string
  currentState: string[]
  buildingToward: string[]
  strategicWhy: string
  code?: string
  codeLanguage?: string
}

function Pillar({
  color, borderColor, bgColor, icon, number, title, tagline,
  currentState, buildingToward, strategicWhy, code, codeLanguage
}: PillarProps) {
  return (
    <div className={`rounded-2xl border ${borderColor} ${bgColor} p-6`}>
      <div className="flex items-start gap-3 mb-4">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl flex-shrink-0 bg-gray-950/60`}>
          {icon}
        </div>
        <div>
          <div className={`text-xs font-mono ${color} mb-0.5`}>Pillar {number}</div>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <p className="text-sm text-gray-400 mt-0.5">{tagline}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Current state</div>
          <ul className="space-y-1">
            {currentState.map((item, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-gray-400">
                <span className="text-green-600 mt-0.5 flex-shrink-0">✓</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Building toward</div>
          <ul className="space-y-1">
            {buildingToward.map((item, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-gray-400">
                <span className={`${color} mt-0.5 flex-shrink-0`}>→</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className={`text-xs text-gray-500 leading-relaxed border-t ${borderColor} pt-4 mb-4`}>
        <span className="text-gray-400 font-medium">Why this is a moat: </span>
        {strategicWhy}
      </div>

      {code && <CodeBlock code={code} language={codeLanguage || 'python'} />}
    </div>
  )
}

// ─── Benchmark detail section ─────────────────────────────────────────────────

function BenchmarkDetail() {
  const taskTypes = [
    { category: 'Documents', tasks: 'PDF extraction, table parsing, OCR, multi-page understanding', modality: 'text + images', count: '22' },
    { category: 'Monitoring', tasks: 'Threshold alerts, health checks, anomaly detection', modality: 'text + numeric', count: '14' },
    { category: 'Communication', tasks: 'Email triage, chat routing, notification assembly', modality: 'text', count: '18' },
    { category: 'Dev Tools', tasks: 'CI/CD triage, PR digest, dependency audit', modality: 'text + code', count: '12' },
    { category: 'Content', tasks: 'Newsletter, research reports, voice journals, video Q&A', modality: 'text + audio + video', count: '20' },
    { category: 'Multimodal', tasks: 'Mixed PDF+audio+screenshot pipelines', modality: 'all modalities', count: '15+' },
  ]

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mt-8">
      <h3 className="text-base font-semibold text-white mb-1">The Benchmark in Detail</h3>
      <p className="text-sm text-gray-400 mb-5">
        Each task in the suite has: a <strong className="text-gray-300">recorded input</strong> (no live APIs), a <strong className="text-gray-300">task spec</strong> (what the agent should do), and a <strong className="text-gray-300">scoring function</strong> (deterministic checks + LLM-as-judge for open-ended outputs). Fully reproducible. Any agent, same score.
      </p>

      <div className="overflow-x-auto mb-5">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2 pr-6">Category</th>
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2 pr-6">Task types</th>
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2 pr-6">Modalities</th>
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2">Tasks</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {taskTypes.map((row) => (
              <tr key={row.category} className="hover:bg-gray-800/30">
                <td className="py-2 pr-6 text-sm text-gray-300 font-medium">{row.category}</td>
                <td className="py-2 pr-6 text-xs text-gray-500">{row.tasks}</td>
                <td className="py-2 pr-6">
                  <span className="text-xs font-mono text-emerald-600">{row.modality}</span>
                </td>
                <td className="py-2 text-sm font-mono text-gray-400">{row.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* How it differs from existing benchmarks */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { name: 'GAIA', what: 'General reasoning + web browsing on one-off questions', gap: 'Not pipeline tasks. Not reproducible across trigger types.' },
          { name: 'DocVQA', what: 'Document visual question answering (isolated)', gap: 'Tests single-document VQA. Not mixed-modality pipelines.' },
          { name: 'CUGA++ Benchmark', what: 'Production pipeline reliability across 100+ real-world task types', gap: 'The first benchmark that tests end-to-end agent pipelines with mock channels.' },
        ].map((item) => (
          <div key={item.name} className={`rounded-lg p-3.5 ${item.name === 'CUGA++ Benchmark' ? 'bg-emerald-900/15 border border-emerald-800/30' : 'bg-gray-800/40 border border-gray-700/30'}`}>
            <div className={`text-xs font-semibold mb-1 ${item.name === 'CUGA++ Benchmark' ? 'text-emerald-400' : 'text-gray-400'}`}>{item.name}</div>
            <div className="text-xs text-gray-400 mb-2 leading-relaxed">{item.what}</div>
            <div className={`text-xs italic leading-relaxed ${item.name === 'CUGA++ Benchmark' ? 'text-emerald-600' : 'text-gray-600'}`}>{item.gap}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Multimodal gap analysis ──────────────────────────────────────────────────

function MultimodalGapAnalysis() {
  const rows = [
    { capability: 'Pass image URL to LLM', openclaw: '✅', langgraph: '✅', cuga: '✅', note: '' },
    { capability: 'PDF → clean markdown before agent', openclaw: '🔧 via tool call', langgraph: '❌', cuga: '✅ DoclingChannel', note: 'Pre-extraction = no tokens wasted on parsing' },
    { capability: 'Audio file → transcript before agent', openclaw: '✅ Whisper/Deepgram', langgraph: '❌', cuga: '✅ AudioChannel', note: '' },
    { capability: 'Video → frames + transcript', openclaw: '❌', langgraph: '❌', cuga: '🔧 Roadmap: VideoChannel', note: 'Sample frames at N fps + Whisper transcript' },
    { capability: 'Layout-aware table extraction (PDF)', openclaw: '❌', langgraph: '❌', cuga: '🔧 Roadmap: extended DoclingChannel', note: 'Tables → JSON, not flattened markdown' },
    { capability: 'Screenshot → structured description', openclaw: '✅ Chrome CDP', langgraph: '❌', cuga: '🔧 Roadmap: ScreenshotChannel', note: 'Vision-grounded tool use without browser' },
    { capability: 'Real-time audio streaming', openclaw: '✅', langgraph: '❌', cuga: '🔧 Roadmap: StreamAudioChannel', note: 'Streaming transcription for live meetings' },
    { capability: 'Chart / graph understanding (input)', openclaw: '❌', langgraph: '❌', cuga: '🔧 Roadmap: make_chart_understanding_tool()', note: 'Extract data from chart images' },
    { capability: 'Mixed-modality pipelines', openclaw: '🔧 manual routing', langgraph: '❌', cuga: '✅ → 🔧 deeper', note: 'Combine PDF + audio + image in one pipeline' },
    { capability: 'Image generation (output)', openclaw: '✅', langgraph: '❌', cuga: '✅ DALL-E 3', note: '' },
  ]

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2.5 pr-4">Capability</th>
            <th className="text-center text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2.5 px-3">OpenClaw</th>
            <th className="text-center text-xs font-semibold text-gray-500 uppercase tracking-wider pb-2.5 px-3">LangGraph</th>
            <th className="text-center text-xs font-semibold text-pink-600 uppercase tracking-wider pb-2.5 px-3">CUGA++</th>
            <th className="text-left text-xs font-semibold text-gray-600 uppercase tracking-wider pb-2.5 pl-4">Note</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/40">
          {rows.map((row) => (
            <tr key={row.capability} className="hover:bg-gray-800/20">
              <td className="py-2 pr-4 text-xs text-gray-300">{row.capability}</td>
              <td className="py-2 px-3 text-center text-xs">{row.openclaw}</td>
              <td className="py-2 px-3 text-center text-xs">{row.langgraph}</td>
              <td className="py-2 px-3 text-center text-xs font-medium">{row.cuga}</td>
              <td className="py-2 pl-4 text-xs text-gray-600 italic">{row.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Flywheel prose ───────────────────────────────────────────────────────────

function FlywheelProse() {
  const steps = [
    {
      from: 'I/O Runtime',
      to: 'Use Case Library',
      color: 'text-blue-400',
      border: 'border-blue-800/30',
      bg: 'bg-blue-900/10',
      desc: 'Every new channel and tool factory directly enables new use cases. Adding DoclingChannel unlocked 6 document intelligence use cases. Adding AudioChannel unlocked voice and video use cases.',
    },
    {
      from: 'Use Case Library',
      to: 'Eval Environment',
      color: 'text-indigo-400',
      border: 'border-indigo-800/30',
      bg: 'bg-indigo-900/10',
      desc: 'Each use case, when given a mock input and a scoring function, becomes a benchmark task. 100 use cases = 100 benchmark tasks. The library IS the benchmark — no separate content work.',
    },
    {
      from: 'Eval Environment',
      to: 'Multimodal Leadership',
      color: 'text-emerald-400',
      border: 'border-emerald-800/30',
      bg: 'bg-emerald-900/10',
      desc: 'Running 50+ agent frameworks against the benchmark reveals where they break. Mixed-modality tasks (PDF + audio + image) will expose the largest gaps. This is where CUGA++ differentiates: our extraction-before-reasoning architecture handles these natively.',
    },
    {
      from: 'Multimodal Leadership',
      to: 'I/O Runtime',
      color: 'text-pink-400',
      border: 'border-pink-800/30',
      bg: 'bg-pink-900/10',
      desc: 'Every new modality (video, screenshot, streaming audio, chart understanding) strengthens the I/O Runtime and creates new use cases to benchmark. The cycle compounds.',
    },
  ]

  return (
    <div className="space-y-3">
      {steps.map((step) => (
        <div key={step.from} className={`rounded-xl border ${step.border} ${step.bg} p-4`}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className={`text-xs font-semibold ${step.color}`}>{step.from}</span>
            <span className="text-gray-600 text-xs">→</span>
            <span className={`text-xs font-semibold ${step.color}`}>{step.to}</span>
          </div>
          <p className="text-xs text-gray-400 leading-relaxed">{step.desc}</p>
        </div>
      ))}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function VisionPage() {
  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">Strategic Vision</h2>
        <p className="text-indigo-300 text-sm font-medium max-w-2xl mb-2">
          A framework that connects event sources → agent reasoning → output destinations, with reusable skills and orchestration patterns baked in.
        </p>
        <p className="text-gray-400 text-sm max-w-2xl">
          Four bets that reinforce each other. Each pillar makes the others stronger.
          Together they define a position that no existing tool occupies.
        </p>
      </div>

      {/* Flywheel diagram */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-4">
        <FlywheelDiagram />
        <p className="text-center text-xs text-gray-600 mt-2">
          The reinforcing cycle — each pillar feeds the next
        </p>
      </div>

      {/* Flywheel explanation */}
      <div className="mb-10">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">How the cycle works</h3>
        <FlywheelProse />
      </div>

      {/* Four pillars */}
      <div className="space-y-6">

        {/* Pillar 1: I/O Runtime */}
        <Pillar
          number="1"
          icon="⚡"
          title="I/O Runtime"
          tagline="Event-driven infrastructure that connects any agent to the world"
          color="text-blue-400"
          borderColor="border-blue-800/30"
          bgColor="bg-blue-900/5"
          currentState={[
            'ConversationGateway: browser + Telegram + WhatsApp + Voice (phone) — one agent, four front-ends',
            '8 pipeline input channels (RSS, IMAP, Docling, Audio, Telegram, Discord, Slack, Webhook)',
            '8 pipeline output channels (Email, Slack, Telegram, Discord, SMS, WhatsApp, TTS, Log)',
            '7 tool factories (web search, calendar, GitHub, shell, market data, image gen, RAG)',
            'CugaRuntime + CugaHost production daemon',
            'cuga_checkpointer (persistent conversation state across restarts)',
          ]}
          buildingToward={[
            'add_slack_adapter() + add_discord_adapter() for ConversationGateway',
            'add_email_adapter() + add_sms_adapter() — full channel parity',
            'NotionChannel + DatabaseChannel + TwitterChannel',
            'Multi-agent pipelines (CugaPipeline)',
            'Human-in-the-loop approval (ApprovalChannel)',
            'ChannelPlanner → natural language → Python code',
          ]}
          strategicWhy="Two surfaces, one runtime. ConversationGateway makes the gateway surface composable — add a new front-end in one line, same agent, same memory. The pipeline surface compounds: every new channel unlocks new use cases and new benchmark tasks. The production hardening (async isolation, MIME handling, cron reliability, per-user thread history) is the kind of work big frameworks consistently underinvest in."
        />

        {/* Pillar 2: Use Case Library */}
        <Pillar
          number="2"
          icon="📦"
          title="Use Case Library"
          tagline="100+ production pipeline tasks — the asset that enables everything else"
          color="text-indigo-400"
          borderColor="border-indigo-800/30"
          bgColor="bg-indigo-900/5"
          currentState={[
            '53/82 OpenClaw use cases working today',
            '22 working demo apps with full documentation',
            'Categorised by domain: monitoring, devtools, content, documents, productivity',
            'Each demo: defined input → defined behavior → defined output',
          ]}
          buildingToward={[
            '100+ use cases across all domains',
            'Each use case formalized as a TaskSpec (input, criteria, scoring)',
            'Community contributions: external teams add their own use cases',
            'Use cases as the benchmark corpus — the library IS the test suite',
          ]}
          strategicWhy="The use case library is the most underappreciated asset. It's not just demos — it's a structured corpus of real-world agent tasks that no other framework has at this depth. OpenClaw has 82 use cases documented. No eval framework has them tested. CUGA++ bridges that gap."
        />

        {/* Pillar 3: Eval Environment */}
        <Pillar
          number="3"
          icon="🏆"
          title="Eval Environment"
          tagline="Bring your agent. Run it against 100+ production tasks. Get a score."
          color="text-emerald-400"
          borderColor="border-emerald-800/30"
          bgColor="bg-emerald-900/5"
          currentState={[
            'Agent-agnostic interface: any .ainvoke() agent works today',
            'Use cases exist as informal specs (README + demo code)',
            'MockAgent pattern established in integration tests',
          ]}
          buildingToward={[
            'MockChannelHarness — channels that replay recorded inputs (no live APIs)',
            'TaskRegistry — 100+ task specs with inputs, criteria, scoring functions',
            'ScoringEngine — deterministic checks + LLM-as-judge for open-ended outputs',
            'Pluggable agent adapters: LangGraph ReAct, AutoGen, CrewAI, raw API',
            'Public leaderboard — any team can submit their agent and get a score',
            'Benchmark categories: per-domain scores + multimodal score',
          ]}
          strategicWhy="Nobody has a production pipeline reliability benchmark for agents. GAIA tests general reasoning. DocVQA tests isolated document VQA. Neither tests: can your agent run a reliable newsletter pipeline? can it triage 500 contracts? can it handle a mixed PDF+audio+screenshot task? CUGA++ defines this benchmark — and whoever defines the benchmark becomes the reference point."
          code={MOCK_HARNESS_CODE}
          codeLanguage="python"
        />

        {/* Pillar 4: Multimodal */}
        <Pillar
          number="4"
          icon="🎨"
          title="Multimodal Leadership"
          tagline="Every input modality handled natively before the LLM sees a single token"
          color="text-pink-400"
          borderColor="border-pink-800/30"
          bgColor="bg-pink-900/5"
          currentState={[
            'DoclingChannel: PDF/Word/Excel/HTML/images → markdown (pre-extraction)',
            'AudioChannel: audio/video → Whisper transcript (pre-extraction)',
            'AgentState.input: Union[str, List[Any]] — multimodal messages natively',
            'make_image_generation_tool(): DALL-E 3 output',
            'image_chat demo: Telegram photo → vision analysis',
          ]}
          buildingToward={[
            'VideoChannel: frame sampling + transcript (not just audio strip)',
            'Extended DoclingChannel: layout-aware tables → structured JSON',
            'ScreenshotChannel: screenshot → structured description for tool use',
            'StreamAudioChannel: real-time streaming transcription for live meetings',
            'make_chart_understanding_tool(): extract data from chart images',
            'Mixed-modality benchmark tasks (unique — no other benchmark has these)',
          ]}
          strategicWhy="Most frameworks call 'multimodal' when they pass an image URL to the LLM. That's not multimodal infrastructure — that's a single tool call. CUGA++'s extraction-before-reasoning principle means every modality arrives as clean, structured text before the agent fires. No tokens wasted on parsing. No agent confusion about encoding. This architectural difference becomes the largest differentiator on the benchmark — mixed-modality pipeline tasks expose every framework that doesn't have native extraction."
          code={MULTIMODAL_CODE}
          codeLanguage="python"
        />
      </div>

      {/* Pluggable agents */}
      <div className="mt-10 bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <h3 className="text-base font-semibold text-white mb-1">Pluggable Agents — the contract is already there</h3>
        <p className="text-sm text-gray-400 mb-4">
          CUGA++ doesn't compete with LangGraph, AutoGen, or CrewAI at the reasoning layer. It provides the environment they run in. The only contract: <code className="text-gray-300 bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">agent.ainvoke(message)</code>. Any framework that implements this runs in CUGA++ today.
        </p>
        <CodeBlock code={LANG_GRAPH_CODE} language="python" />
        <p className="text-xs text-gray-600 mt-3">
          This is also the eval story: swap <code className="text-gray-500">langgraph_agent</code> for <code className="text-gray-500">autogen_agent</code> for <code className="text-gray-500">your_agent</code> — same pipeline, same benchmark, comparable scores.
        </p>
      </div>

      {/* Multimodal gap table */}
      <div className="mt-6 bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <h3 className="text-base font-semibold text-white mb-1">Multimodal coverage — where the gap is</h3>
        <p className="text-sm text-gray-400 mb-4">
          Most frameworks handle text-only pipelines well. Mixed-modality production tasks expose a large gap that CUGA++ is positioned to close.
        </p>
        <MultimodalGapAnalysis />
      </div>

      {/* Benchmark detail */}
      <BenchmarkDetail />

      {/* The positioning statement */}
      <div className="mt-8 bg-gradient-to-r from-indigo-900/20 via-emerald-900/10 to-pink-900/20 border border-indigo-800/20 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-white mb-3">The positioning in one paragraph</h3>
        <p className="text-sm text-gray-300 leading-relaxed">
          CUGA++ is not trying to build a better reasoning engine. The reasoning layer is a commodity. What nobody has built is <strong className="text-white">the production I/O runtime that sits between any agent and the world</strong> — across two distinct surfaces. The <strong className="text-indigo-300">Gateway surface</strong>: one agent, reachable via browser, Telegram, WhatsApp, and phone simultaneously — <code className="text-xs bg-gray-800 px-1 py-0.5 rounded text-indigo-300">gateway.add_telegram_adapter()</code>, <code className="text-xs bg-gray-800 px-1 py-0.5 rounded text-indigo-300">gateway.add_whatsapp_adapter()</code>, <code className="text-xs bg-gray-800 px-1 py-0.5 rounded text-indigo-300">gateway.add_voice_adapter()</code>. The <strong className="text-emerald-300">Pipeline surface</strong>: agents that run on schedules, react to webhooks, monitor folders, and triage inboxes — no human in the loop, no boilerplate. Both surfaces share <strong className="text-white">the strongest multimodal extraction pipeline in the Python ecosystem</strong> and <strong className="text-white">100+ real-world use cases as a benchmark corpus</strong>. The team that defines the runtime owns the reference point. The team that owns multimodal extraction owns the hardest tasks. These are the same team.
        </p>
      </div>
    </div>
  )
}
