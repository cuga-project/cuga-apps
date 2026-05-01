// Concrete Deliverables — what CUGA++ ships, not what it aspires to.

interface DeliverableItem {
  number: number
  tag: string
  tagColor: string
  headline: string
  description: string
  items: { label: string; detail: string }[] | string[]
  note?: string
  status: 'in-progress' | 'planned' | 'done'
}

const DELIVERABLES: DeliverableItem[] = [
  {
    number: 1,
    tag: 'Codebase',
    tagColor: 'bg-indigo-900/30 text-indigo-300 border-indigo-800/40',
    status: 'in-progress',
    headline: 'CUGA++ codebase — composable packages with clear goals',
    description: 'The codebase ships as a set of composable packages, each with a single defined responsibility. Developers install only what they need.',
    items: [
      { label: 'cuga', detail: 'Core agent graph, state management, LangGraph-based checkpointing' },
      { label: 'cuga.channels', detail: 'Input/output channel library — IMAP, Slack, Telegram, Cron, Webhook, Box, S3' },
      { label: 'cuga.multimodal', detail: 'DoclingChannel, AudioChannel (Whisper + pyannote), VideoChannel (QWEN2-VL), ChromaDB index' },
      { label: 'cuga.skills', detail: 'CugaSkillsPlugin — load .md persona files as reusable agent skills; skill registry' },
      { label: 'cuga.agents', detail: 'CugaSupervisor (one boss / many specialists), CollabOrchestrator (dynamic handoffs)' },
      { label: 'cuga.runtime', detail: 'CugaHost daemon, CugaRuntime per-pipeline execution, health endpoints' },
      { label: 'cuga-watcher', detail: 'Long-running process that monitors channels and emits trigger events' },
      { label: 'cuga-trigger', detail: 'Lightweight dispatcher that routes trigger events to the right runtime' },
      { label: 'cuga.tools', detail: 'Tool factories — make_shell_tools, MCPToolBridge, LangChain adapter' },
      { label: 'cuga.benchmark', detail: 'Benchmark harness, scoring, leaderboard runner' },
      { label: 'cuga.usecases', detail: '50+ pluggable, documented, runnable use cases as an installable library' },
    ],
    note: 'cuga-watcher, cuga-trigger, cuga.benchmark, and cuga.usecases are new packages. The rest extend what already exists.',
  },
  {
    number: 2,
    tag: 'Multimodal',
    tagColor: 'bg-pink-900/30 text-pink-300 border-pink-800/40',
    status: 'in-progress',
    headline: 'Tools, agents, and capabilities for multimodality',
    description: 'Multimodality is a pipeline of capabilities that fires before the agent sees anything. These are the building blocks.',
    items: [
      { label: 'DoclingChannel', detail: 'Structured extraction from PDF, PPTX, DOCX — section hierarchy, tables, headings preserved' },
      { label: 'AudioChannel', detail: 'Whisper transcription + pyannote speaker diarization → speaker-attributed transcript' },
      { label: 'VideoChannel', detail: 'Keyframe extraction + QWEN2-VL description per frame; slide OCR' },
      { label: 'BoxChannel', detail: 'Ingest from Box folders, trigger on new file uploads, route by MIME type' },
      { label: 'ChromaDB integration', detail: 'Unified multimodal index across text, audio transcripts, keyframe descriptions' },
      { label: 'QWEN2-VL tool', detail: 'Vision model callable as an agent tool for diagram/chart/screenshot understanding' },
      { label: 'MeetingIntelAgent', detail: 'Transcript + slides → summary, action items, per-person TODOs' },
      { label: 'ContractReviewAgent', detail: 'PDF extraction → clause analysis → risk summary → Slack' },
      { label: 'FinancialReportAgent', detail: 'Earnings PDF → structured metrics → comparison → alert' },
      { label: 'DeckAssemblyAgent', detail: 'Semantic search across past decks → assemble new topic-filtered deck' },
    ],
    note: 'These specialized agents are built on top of the channel + tool primitives. They are use cases, not framework code.',
  },
  {
    number: 3,
    tag: 'Use Case Library',
    tagColor: 'bg-teal-900/30 text-teal-300 border-teal-800/40',
    status: 'in-progress',
    headline: '50+ working use cases — pluggable, reusable, enhanceable',
    description: 'A library of production-ready use cases that developers can clone, modify, and extend. Each is self-contained and runnable.',
    items: [
      { label: 'config.yaml', detail: 'Channel bindings, model, skills, tools — declarative pipeline spec' },
      { label: 'agent.py / app.py', detail: 'Runnable demo (Streamlit or FastAPI) — works out of the box' },
      { label: 'README.md', detail: 'What it does, how to run it, expected outputs, customization guide' },
      { label: 'skills/', detail: 'Any .md persona files the use case uses — reusable across pipelines' },
      { label: 'Event-driven checkbox', detail: 'Every use case is triggered by a channel event, not manually invoked' },
      { label: 'Multimodal checkbox', detail: 'Every use case handles at least one non-text input (PDF, audio, image, PPTX)' },
    ],
    note: 'Currently 53/82 working across: devtools, finance, media/comms, ops/SRE, legal, HR, productivity. Target: 50+ that fully satisfy both checkboxes, organized into cuga.usecases with a browsable index.',
  },
  {
    number: 4,
    tag: 'Benchmark',
    tagColor: 'bg-yellow-900/30 text-yellow-300 border-yellow-800/40',
    status: 'planned',
    headline: 'CUGA++ vs LangGraph vs vanilla Claude — on popular benchmarks',
    description: 'Run CUGA++ against benchmarks the community already trusts. Compare against a LangGraph baseline and vanilla Claude API calls. Publish everything.',
    items: [
      { label: 'DocVQA', detail: 'Document visual Q&A — directly validates the multimodal extraction pipeline' },
      { label: 'ChartQA', detail: 'Chart understanding — validates QWEN2-VL + Docling combination' },
      { label: 'FinanceBench', detail: 'Financial document Q&A — validates enterprise document use case' },
      { label: 'GAIA L1/L2', detail: 'General agent capability — validates event-driven + tool use' },
      { label: 'TAT-QA', detail: 'Table + text Q&A — validates Docling structured extraction' },
      { label: 'Public leaderboard', detail: 'Any team can submit their agent scores against the same tasks and same harness' },
    ],
    note: 'The goal is not to win every benchmark. It is to show that the channel + skills + multimodal pipeline produces measurably better outcomes than a raw API call on real document tasks.',
  },
  {
    number: 5,
    tag: 'New Benchmark',
    tagColor: 'bg-purple-900/30 text-purple-300 border-purple-800/40',
    status: 'planned',
    headline: 'EnterpriseBench — a new benchmark built from the use case library',
    description: 'A benchmark that does not exist yet. Built from real enterprise workflows, not academic datasets. Multimodal and event-driven by design.',
    items: [
      { label: '30–50 tasks', detail: 'Selected from the use case library for clear, evaluable outputs (not open-ended generation)' },
      { label: 'Metric per task', detail: 'e.g. action item recall for meeting intel, clause detection F1 for contract review' },
      { label: 'End-to-end evaluation', detail: 'Does the right output reach the right destination (Slack, Jira, email) — not just LLM output correctness' },
      { label: 'Open-source harness', detail: 'Any agent framework can be evaluated; CUGA++ ships as the reference implementation' },
      { label: 'Institutional backing', detail: 'Partner with IBM Research or academic group for credibility and longevity' },
    ],
    note: 'Owning the benchmark means owning the definition of "good" for enterprise agent I/O. This is the highest-leverage long-term deliverable.',
  },
  {
    number: 6,
    tag: 'Productivity',
    tagColor: 'bg-green-900/30 text-green-300 border-green-800/40',
    status: 'done',
    headline: 'Productivity use cases',
    description: 'A suite of productivity use cases demonstrating CUGA++ across everyday workflows. These are running today and serve as entry points into the library.',
    items: [
      { label: 'Newsletter generator', detail: 'Fetches content, summarizes, formats, delivers on schedule' },
      { label: 'Smart todo', detail: 'Parses tasks from conversation, prioritizes, tracks progress' },
      { label: 'Engineering team assistant (eng_team)', detail: 'Persona-driven team simulation via CugaSkillsPlugin + CugaSupervisor — runs on localhost:8501' },
      { label: 'Engineering team collab (eng_team_collab)', detail: 'Dynamic multi-agent collaboration via CollabOrchestrator — runs on localhost:8502' },
      { label: 'Voice gateway', detail: 'Speech-to-agent-to-speech pipeline' },
      { label: 'Calendar agent, Discord agent, GitHub agent', detail: 'Event-driven, channel-triggered, working demos' },
      { label: 'Server monitor, stock alert', detail: 'Cron-triggered monitoring pipelines with alerting output' },
    ],
    note: 'These use cases are documented, runnable, and are the primary entry point for developers. They cover the full range from single-agent productivity tasks to complex multi-agent workflows.',
  },
]

const STATUS_STYLE: Record<string, string> = {
  done: 'bg-green-900/20 text-green-400 border-green-800/30',
  'in-progress': 'bg-yellow-900/20 text-yellow-400 border-yellow-800/30',
  planned: 'bg-gray-800/60 text-gray-400 border-gray-700/40',
}

const STATUS_LABEL: Record<string, string> = {
  done: 'Done',
  'in-progress': 'In progress',
  planned: 'Planned',
}

export default function DeliverablesPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto">

      {/* Header */}
      <div className="mb-10">
        <h2 className="text-2xl font-semibold text-white mb-2">Deliverables</h2>
        <p className="text-indigo-300 text-sm font-medium max-w-2xl mb-2">
          What CUGA++ ships — concrete, specific, checkable.
        </p>
        <p className="text-gray-400 text-sm max-w-2xl leading-relaxed">
          Six deliverables that translate the strategic bets into tangible outputs.
          Each one is either already working, in progress, or has a clear plan.
        </p>
      </div>

      {/* Status summary */}
      <div className="grid grid-cols-3 gap-3 mb-10">
        {[
          { label: 'Done', count: 1, style: 'bg-green-900/10 border-green-800/30 text-green-400' },
          { label: 'In progress', count: 3, style: 'bg-yellow-900/10 border-yellow-800/30 text-yellow-400' },
          { label: 'Planned', count: 2, style: 'bg-gray-800/30 border-gray-700/40 text-gray-400' },
        ].map((s) => (
          <div key={s.label} className={`border rounded-xl px-4 py-3 text-center ${s.style}`}>
            <div className="text-2xl font-bold">{s.count}</div>
            <div className="text-xs mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Deliverables */}
      <div className="space-y-5">
        {DELIVERABLES.map((d) => (
          <div key={d.number} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            {/* Header */}
            <div className="px-6 pt-5 pb-4 border-b border-gray-800">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-mono text-gray-600 bg-gray-800 px-2 py-0.5 rounded border border-gray-700">
                  {String(d.number).padStart(2, '0')}
                </span>
                <span className={`text-xs font-mono px-2 py-0.5 rounded border ${d.tagColor}`}>
                  {d.tag}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded border ${STATUS_STYLE[d.status]}`}>
                  {STATUS_LABEL[d.status]}
                </span>
              </div>
              <h3 className="text-base font-semibold text-white">{d.headline}</h3>
              <p className="text-sm text-gray-400 mt-1 leading-relaxed">{d.description}</p>
            </div>

            {/* Items */}
            <div className="px-6 py-5">
              <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">What ships</div>
              <div className="space-y-2">
                {(d.items as { label: string; detail: string }[]).map((item) => (
                  <div key={item.label} className="flex gap-3">
                    <span className="text-xs font-mono text-indigo-400 flex-shrink-0 mt-0.5 min-w-[160px]">
                      {item.label}
                    </span>
                    <span className="text-xs text-gray-400 leading-relaxed">{item.detail}</span>
                  </div>
                ))}
              </div>

              {d.note && (
                <div className="mt-4 bg-gray-800/50 border border-gray-700/50 rounded-lg px-4 py-3">
                  <p className="text-xs text-gray-500 leading-relaxed italic">{d.note}</p>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

    </div>
  )
}
