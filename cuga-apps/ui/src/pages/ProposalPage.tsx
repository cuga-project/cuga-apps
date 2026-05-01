// Strategic Proposal — where to take CUGA++ next.
// Eight bets: the original six + skills/multi-agent + use case library as asset.
// Target user and "why us/why now" are explicit up front, not implicit.

interface Bet {
  number: number
  tag: string
  tagColor: string
  headline: string
  why: string
  implies: string[]
  synthesis: string
}

const BETS: Bet[] = [
  {
    number: 1,
    tag: 'Multimodal',
    tagColor: 'bg-pink-900/30 text-pink-300 border-pink-800/40',
    headline: 'Focus heavily on multimodal enterprise use cases',
    why: `Enterprise work is not text-only. Contracts come as PDFs. Meetings are audio + slides.
Dashboards are screenshots. Reports are PPTX decks. The agents that win in enterprise
will be the ones that can handle all of these natively — not just plain text.

CUGA++ already has DoclingChannel, AudioChannel, and a path to vision-ready LLMs.
The bet is to lean into this hard and build a suite of multimodal enterprise use cases
that no other framework offers out of the box.`,
    implies: [
      'Build specialized agents tuned for document-heavy workflows (legal, finance, HR)',
      'Develop purpose-built tools: DoclingChannel, AudioChannel, VideoChannel, BoxChannel',
      'QWEN2-VL or similar for keyframe + diagram understanding',
      'ChromaDB as the default multimodal index — unified search across text, audio, visuals',
      'First targets: meeting intelligence, contract review, financial report monitoring',
    ],
    synthesis: 'This is the clearest product bet. Multimodal enterprise is a real gap — LangGraph has no opinion on it, n8n has no LLM-native extraction. The 15 enterprise use cases on the Positioning page are the roadmap.',
  },
  {
    number: 2,
    tag: 'Event-Driven',
    tagColor: 'bg-emerald-900/30 text-emerald-300 border-emerald-800/40',
    headline: 'Event-driven use cases require a long-running daemon',
    why: `The "event-driven" framing only holds if CUGA++ can actually run continuously —
watching inboxes, listening to webhooks, firing on cron schedules — without a human
keeping it alive. Today CugaHost is a server you run manually. The next step is a
proper daemon: something that starts on boot, survives crashes, and processes events
without babysitting.`,
    implies: [
      'cuga-watcher: a process that monitors channels (IMAP, Slack, webhooks) and emits trigger events',
      'cuga-trigger: lightweight dispatcher that routes trigger events to the right runtime',
      'CugaHost as a supervised daemon (systemd / Docker Compose / launchctl)',
      'Dead-letter queue for failed pipeline runs — retry with backoff, alert on repeated failure',
      'Health endpoint + restart policy — the daemon must self-heal',
    ],
    synthesis: 'cuga-watcher and cuga-trigger are the two concrete primitives to build. Without them, "event-driven" is a marketing claim, not a runtime property.',
  },
  {
    number: 3,
    tag: 'Tools',
    tagColor: 'bg-blue-900/30 text-blue-300 border-blue-800/40',
    headline: 'Tool integrations come for free — by design',
    why: `Because CUGA++ is channel/tool-agnostic, MCP tools, LangChain tools, and shell
tools all slot in without framework changes. The architecture deliberately doesn't
prescribe which tools an agent uses — only how events flow in and results flow out.

This means every MCP server, every LangChain community tool, every shell script
is a potential CUGA++ tool with near-zero integration work. This is a real advantage
over opinionated frameworks that require rewriting tools to fit their interface.`,
    implies: [
      'MCPToolBridge — connects any MCP server to any CUGA++ runtime',
      'LangChain tool adapter — one-line wrapper to use any LangChain tool in CUGA++',
      'Tool registry / discovery — list available tools per runtime, document their schemas',
      'Investment goes into discoverability and examples, not building the integrations themselves',
    ],
    synthesis: '"For free" means no framework changes needed — but documentation and examples are not free. The work is making it easy to discover and wire up tools, not building integrations.',
  },
  {
    number: 4,
    tag: 'Channels',
    tagColor: 'bg-indigo-900/30 text-indigo-300 border-indigo-800/40',
    headline: 'Continue enhancing channels as the core abstraction',
    why: `Channels are what makes CUGA++ composable. A new input channel means every
existing pipeline can now be triggered by a new event source. A new output channel
means every agent result can now be delivered somewhere new.

The current channel library (IMAP, Slack, Cron, Telegram, Docling, Audio) is a good
start. There are obvious gaps, especially on the enterprise input side (Box, S3, webhooks)
and the enterprise output side (Jira, Notion, Google Docs).`,
    implies: [
      'BoxChannel — ingest from Box folders (documents, recordings, decks)',
      'WebhookChannel — generic inbound HTTP trigger for any system that can POST',
      'S3Channel / GCSChannel — watch cloud storage buckets for new files',
      'Output channels: GoogleDocsOutput, NotionOutput, JiraOutput, ConfluenceOutput',
      'Channel composition — chain channels (S3 → Docling → Slack) as a pipeline primitive',
    ],
    synthesis: 'The channel library is the moat. Each new channel makes every existing use case more powerful. Prioritise input channels that unlock multimodal enterprise (Box, S3) and output channels that complete the enterprise loop (Jira, Notion, Google Docs).',
  },
  {
    number: 5,
    tag: 'Skills & Agents',
    tagColor: 'bg-violet-900/30 text-violet-300 border-violet-800/40',
    headline: 'Skills and multi-agent patterns are first-class, not add-ons',
    why: `CugaSkillsPlugin, CugaSupervisor, and CollabOrchestrator are key differentiators
that no other framework ships with. Skills are how org knowledge gets encoded into
agents — a legal_review.md or incident_response.md skill is reusable across every
pipeline that needs it. This compounds: the skill library grows with the use case library.

Multi-agent patterns (supervisor delegation, dynamic handoffs) are what make complex
enterprise tasks tractable. A single agent reviewing a 200-page contract is worse than
a supervisor routing to a specialist per section.`,
    implies: [
      'Skills authoring workflow — a standard format and tooling for writing .md persona files',
      'Skill registry — discover, share, and version skills across pipelines',
      'CugaSupervisor: one boss / many specialists — built-in, not custom code per use case',
      'CollabOrchestrator: dynamic multi-round handoffs between agents with handoff_to routing',
      'Treat skills as first-class artifacts alongside channels and tools — they appear in docs, examples, benchmarks',
    ],
    synthesis: 'Skills are how CUGA++ encodes institutional knowledge. A team that has built 20 .md skills files has made those skills reusable, versionable, and shareable — that is a moat no API call can replicate.',
  },
  {
    number: 6,
    tag: 'Use Case Library',
    tagColor: 'bg-teal-900/30 text-teal-300 border-teal-800/40',
    headline: 'The use case library is a compounding strategic asset',
    why: `53 working use cases are not just demos. They are benchmark seeds, training data for
a ChannelPlanner model, an adoption funnel for developers, and evidence that the
"enterprise I/O layer" claim is real and not marketing.

Most frameworks have zero working examples at this level of depth. CUGA++ already has
53. Each new use case compounds — it adds to the benchmark, enriches the training data,
and gives the next developer something to build on instead of starting from scratch.`,
    implies: [
      'cuga.usecases package — 50+ use cases as a browsable, installable library',
      'Each use case: config.yaml + runnable demo + README + skills/ + expected outputs',
      'Two required checkboxes per use case: event-driven trigger + multimodal input',
      'Organized by category (devtools, finance, legal, ops, comms, productivity)',
      'Public index — developers browse and fork, not copy-paste from a GitHub search',
      'Use cases double as fine-tuning data for a future ChannelPlanner (describe in English → get working pipeline)',
    ],
    synthesis: 'Keep the use case library public, well-documented, and growing. It is the single asset that makes every other bet more credible — the benchmark, the skills library, the channel coverage, all of it is validated here.',
  },
  {
    number: 7,
    tag: 'Benchmark',
    tagColor: 'bg-yellow-900/30 text-yellow-300 border-yellow-800/40',
    headline: 'Benchmark CUGA++ against popular multimodal benchmarks — publish a leaderboard',
    why: `Claims without numbers are marketing. To establish CUGA++ as a credible
infrastructure layer, it needs to perform measurably well on benchmarks that the
community already trusts. The targets: FinanceBench, TAT-QA, DocVQA, ChartQA, GAIA L3.

This also validates that the multimodal bet (bet 1) actually produces agents
that are better, not just differently packaged. The comparison vs. LangGraph is
important for positioning — not to "beat" it, but to show that the channel/skills
abstraction produces measurably different outcomes on real tasks.`,
    implies: [
      'Pick 2–3 benchmarks first — FinanceBench + DocVQA are most relevant to enterprise multimodal',
      'Run three baselines: CUGA++ pipeline, LangGraph baseline, vanilla Claude API',
      'Publish results openly — the benchmark run itself is the credibility signal',
      'Public leaderboard: any team can submit their agent scores against the same tasks',
      'cuga.benchmark package — reproducible harness, not a one-off script',
    ],
    synthesis: 'The goal is not to win every benchmark. It is to show that running the same task through a CUGA++ pipeline (channels + skills + multimodal extraction) produces measurably better outcomes than a raw API call or a generic LangGraph chain.',
  },
  {
    number: 8,
    tag: 'New Benchmark',
    tagColor: 'bg-purple-900/30 text-purple-300 border-purple-800/40',
    headline: 'Create a new benchmark environment from the CUGA++ use case library',
    why: `Once the use case library reaches 50+ entries, there is enough raw material
to define a new benchmark: one that the community doesn't have yet.

What makes it different from GAIA/DocVQA:
• Tasks drawn from real enterprise workflows, not academic datasets
• Multimodal by default — every task involves at least one non-text input
• Event-driven by design — tasks are triggered by channel events, not prompted directly
• End-to-end evaluation — does the right output reach the right destination (Slack, Jira, email)`,
    implies: [
      '30–50 tasks selected from the use case library with clear, evaluable outputs',
      'Metric per task — action item recall for meeting intel, clause F1 for contract review',
      'Open-source harness; CUGA++ ships as the reference implementation',
      'Any agent framework can be evaluated against the same tasks',
      'Partner with IBM Research or academic group for institutional credibility',
    ],
    synthesis: 'Owning the benchmark means owning the definition of "good" for enterprise agent I/O. The framework that sets the standard is the one people build on. This is the highest-leverage long-term bet.',
  },
]

export default function ProposalPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto">

      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">Proposal</h2>
        <p className="text-indigo-300 text-sm font-medium max-w-2xl mb-2">
          A framework that connects event sources → agent reasoning → output destinations,
          with reusable skills and orchestration patterns baked in.
        </p>
        <p className="text-gray-400 text-sm max-w-2xl leading-relaxed">
          Eight strategic bets for where CUGA++ goes next. This is a proposal, not a roadmap.
          The goal is alignment on direction.
        </p>
      </div>

      {/* Who is this for + Why now — explicit, not implicit */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10">
        <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Who this is for</div>
          <div className="space-y-3">
            {[
              {
                user: 'Enterprise team adopting AI',
                color: 'text-emerald-400',
                needs: 'Deployment guides, security model, Jira/Slack/Notion output channels, HITL approval flows. This is the primary target.',
              },
              {
                user: 'Developer building agent apps',
                color: 'text-indigo-400',
                needs: 'Clean SDK, good docs, channel library, working use cases to fork. Secondary — they follow enterprise adoption.',
              },
              {
                user: 'AI researcher / evaluator',
                color: 'text-yellow-400',
                needs: 'The benchmark harness, open-source code, reproducible results. Tertiary — they validate the claims.',
              },
            ].map((item) => (
              <div key={item.user} className="flex gap-3">
                <span className={`text-xs font-semibold ${item.color} mt-0.5 flex-shrink-0 w-40`}>{item.user}</span>
                <p className="text-xs text-gray-400 leading-relaxed">{item.needs}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Why us / why now</div>
          <ul className="space-y-2">
            {[
              '53 working use cases across 6 categories — no other framework has this depth',
              'Channel library: IMAP, Slack, Telegram, Cron, Docling, Audio, Video — already built',
              'Multi-agent patterns (CugaSupervisor, CollabOrchestrator) — working today',
              'OpenClaw comparison: 53/82 use cases covered, closing fast',
              'No existing framework owns enterprise multimodal + event-driven together',
            ].map((item) => (
              <li key={item} className="flex gap-2 text-xs text-gray-400 leading-relaxed">
                <span className="text-indigo-500 flex-shrink-0 mt-0.5">→</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Eight bets */}
      <div className="space-y-5 mb-10">
        {BETS.map((bet) => (
          <div key={bet.number} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            <div className="px-6 pt-5 pb-4 border-b border-gray-800">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-mono text-gray-600 bg-gray-800 px-2 py-0.5 rounded border border-gray-700">
                  {String(bet.number).padStart(2, '0')}
                </span>
                <span className={`text-xs font-mono px-2 py-0.5 rounded border ${bet.tagColor}`}>
                  {bet.tag}
                </span>
              </div>
              <h3 className="text-base font-semibold text-white">{bet.headline}</h3>
            </div>

            <div className="px-6 py-5 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="md:col-span-2">
                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Why</div>
                <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-line">{bet.why.trim()}</p>
              </div>

              <div>
                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">What this implies</div>
                <ul className="space-y-1.5">
                  {bet.implies.map((item) => (
                    <li key={item} className="flex gap-2 text-xs text-gray-400 leading-relaxed">
                      <span className="text-indigo-500 flex-shrink-0 mt-0.5">→</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="bg-indigo-950/30 border border-indigo-800/30 rounded-xl px-4 py-3 self-start">
                <div className="text-xs font-semibold text-indigo-500 uppercase tracking-wider mb-1.5">Synthesis</div>
                <p className="text-xs text-gray-400 leading-relaxed">{bet.synthesis}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* TL;DR */}
      <div className="bg-indigo-950/20 border border-indigo-800/30 rounded-2xl px-6 py-5">
        <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-3">TL;DR</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {
              label: 'The bet',
              text: 'Multimodal enterprise + event-driven runtime. These are not two bets — they are one product.',
            },
            {
              label: 'The differentiator',
              text: 'Channels + skills + multi-agent patterns, all working together, with 53 real use cases as proof.',
            },
            {
              label: 'The validation',
              text: 'Benchmark on FinanceBench + DocVQA. Then build the enterprise agent benchmark from the use case library.',
            },
          ].map((item) => (
            <div key={item.label}>
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">{item.label}</div>
              <p className="text-sm text-gray-300 leading-relaxed">{item.text}</p>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
