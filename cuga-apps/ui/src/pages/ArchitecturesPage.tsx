import CodeBlock from '../components/CodeBlock'

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const CUSTOMIZED_DEMO_APPS = [
  { name: 'newsletter',      icon: '📰', desc: 'RSS feeds → curated email digest on a cron schedule' },
  { name: 'smart_todo',      icon: '✅', desc: 'Natural language todos + reminders + daily digest' },
  { name: 'server_monitor',  icon: '🖥️',  desc: 'CPU/disk alerts + morning briefing + interactive chat' },
  { name: 'voice_journal',   icon: '🎙️', desc: 'Upload voice/PDF → structured journal entries in SQLite' },
  { name: 'video_qa',        icon: '🎬', desc: 'Transcribe a video → ask questions with timestamps' },
  { name: 'doc_pipeline',    icon: '📄', desc: 'Watch a folder for docs → extract with docling → report' },
  { name: 'image_chat',      icon: '🖼️', desc: 'Multi-turn chat about uploaded images' },
]

const COMPARISON_ROWS = [
  {
    dimension: 'Who shapes the pipeline',
    customized: 'Developer — wired at build time',
    universal: 'User — described at chat time',
  },
  {
    dimension: 'Channels available',
    customized: 'Exactly the channels the developer picked',
    universal: 'Any channel in the registry',
  },
  {
    dimension: 'Agent tools',
    customized: 'Fixed set chosen by the developer',
    universal: 'Any tool in the registry, chosen at runtime',
  },
  {
    dimension: 'Configuration file',
    customized: 'cuga_pipelines.yaml  (developer artifact)',
    universal: 'None — pipeline spec is the chat message',
  },
  {
    dimension: 'Factory registration',
    customized: 'Static — host_factories.py loaded at startup',
    universal: 'Dynamic — host.register_factory() called per chat',
  },
  {
    dimension: 'Skill files',
    customized: 'Hand-written per app (e.g. newsletter_curation.md)',
    universal: 'Auto-generated from description at runtime',
  },
  {
    dimension: 'Best for',
    customized: 'Production apps with well-defined scope',
    universal: 'Exploration, rapid prototyping, power users',
  },
  {
    dimension: 'Reliability',
    customized: 'Higher — developer validates the exact flow',
    universal: 'Lower — depends on planner LLM accuracy',
  },
]

const CUSTOMIZED_CODE = `# host_factories.py  (developer writes once)
def register(host):
    host.register_factory("newsletter", RuntimeFactory.declare(
        agent_fn=lambda _: make_agent(),
        message="Curate and send the newsletter digest.",
        thread_id="newsletter-digest",
        trigger=CronChannel.from_config,
        data=[RssChannel.from_config],
        output=EmailChannel.from_config,
        require_buffer=True,
    ))

# User chat (the only thing the user controls)
"Watch arxiv and email me@co.com daily"
 → adjusts schedule + email in the pre-wired pipeline`

const UNIVERSAL_CODE = `# app.py  (developer ships a toolkit, not an app)
agent = make_planner_agent(host=host, client=client)
gateway = ConversationGateway(agent=agent)
await gateway.start()

# User chat (user controls everything)
"Monitor arxiv for AI papers, email me@co.com every morning"
 → planner calls create_pipeline(data_type="rss",
     rss_sources=[...], trigger_schedule="0 8 * * *",
     output_type="email", output_target="me@co.com")
 → host.register_factory("monitor-arxiv...", build_factory(spec))
 → client.start_runtime("monitor-arxiv...", ...)`

const CUSTOMIZED_ARCH = `Browser
    ↓
ConversationGateway
    ↓
CugaAgent  (app-specific tools + skills)
    ↓
CugaHostClient  ──►  CugaHost
                          └── CugaRuntime  (pre-wired)
                                ├── RssChannel  (fixed)
                                ├── CronChannel (schedule)
                                ├── CugaAgent   (fixed tools)
                                └── EmailChannel (fixed)`

const UNIVERSAL_ARCH = `Browser
    ↓
ConversationGateway
    ↓
CugaAgent  (planner — create/stop/list tools)
    ↓  calls create_pipeline(spec)
    ├── build_factory(spec)        ← factory.py
    ├── host.register_factory(id, factory)
    └── client.start_runtime(id, ...)

CugaHost  (embedded)
    └── CugaRuntime  (dynamically assembled from spec)
          ├── DataChannel   (from spec.data_type)
          ├── CronChannel   (from spec.trigger_schedule)
          ├── CugaAgent     (tools from spec.tool_names)
          └── OutputChannel (from spec.output_type)`

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ArchitecturesPage() {
  return (
    <div className="p-6 max-w-6xl mx-auto">

      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">App Architectures</h2>
        <p className="text-gray-400 text-sm max-w-3xl leading-relaxed">
          cuga++ supports two distinct patterns for building agent-powered apps.
          Both use the same underlying infrastructure — CugaAgent, CugaRuntime, CugaHost,
          channels, and tools — but they differ in <em className="text-gray-300">who decides what the pipeline looks like</em>.
        </p>
      </div>

      {/* Side-by-side cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">

        {/* Customized App */}
        <div className="bg-indigo-900/10 border border-indigo-800/40 rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 flex items-center justify-center text-xl flex-shrink-0">
              🏗️
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Customized App</h3>
              <p className="text-xs text-indigo-400 mt-0.5">Developer owns the pipeline shape</p>
            </div>
          </div>

          <p className="text-sm text-gray-300 leading-relaxed mb-5">
            The developer pre-wires exactly which channels, tools, and agents the app uses.
            The user interacts via chat but can only configure <em>parameters</em> of the
            pipeline — not its structure.
          </p>

          {/* Flow */}
          <div className="bg-gray-950/60 border border-gray-800 rounded-xl p-4 mb-4">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Data flow</div>
            <CodeBlock code={CUSTOMIZED_ARCH} language="text" />
          </div>

          {/* What the developer writes */}
          <div className="space-y-2 mb-4">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Developer writes</div>
            {[
              { file: 'agent.py', desc: 'App-specific tools + skills' },
              { file: 'cuga_pipelines.yaml', desc: 'Pipeline shape + defaults' },
              { file: 'host_factories.py', desc: 'Wires channels into a runtime factory' },
              { file: 'skills/*.md', desc: 'Hand-crafted prompts for this domain' },
            ].map((f) => (
              <div key={f.file} className="flex items-start gap-2.5 bg-gray-900/60 rounded-lg px-3 py-2">
                <span className="font-mono text-xs text-indigo-300 flex-shrink-0 mt-0.5">{f.file}</span>
                <span className="text-xs text-gray-400">{f.desc}</span>
              </div>
            ))}
          </div>

          <CodeBlock code={CUSTOMIZED_CODE} language="python" />
        </div>

        {/* Universal App */}
        <div className="bg-emerald-900/10 border border-emerald-800/40 rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-600/20 flex items-center justify-center text-xl flex-shrink-0">
              🌐
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Universal App</h3>
              <p className="text-xs text-emerald-400 mt-0.5">User owns the pipeline shape</p>
            </div>
          </div>

          <p className="text-sm text-gray-300 leading-relaxed mb-5">
            The developer ships a toolkit — a registry of channels and tools, a
            factory builder, and a planner agent. The user's chat message IS the
            configuration. Any combination of channels and tools can be assembled
            at runtime.
          </p>

          {/* Flow */}
          <div className="bg-gray-950/60 border border-gray-800 rounded-xl p-4 mb-4">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Data flow</div>
            <CodeBlock code={UNIVERSAL_ARCH} language="text" />
          </div>

          {/* What the developer writes */}
          <div className="space-y-2 mb-4">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Developer writes</div>
            {[
              { file: 'registry.py', desc: 'Manifest of all channels + tools' },
              { file: 'factory.py', desc: 'build_factory(spec) → CugaRuntime' },
              { file: 'planner_tools.py', desc: 'create / update / stop / list pipeline tools' },
              { file: 'skills/planner.md', desc: 'How to read user intent and pick channels' },
            ].map((f) => (
              <div key={f.file} className="flex items-start gap-2.5 bg-gray-900/60 rounded-lg px-3 py-2">
                <span className="font-mono text-xs text-emerald-300 flex-shrink-0 mt-0.5">{f.file}</span>
                <span className="text-xs text-gray-400">{f.desc}</span>
              </div>
            ))}
          </div>

          <CodeBlock code={UNIVERSAL_CODE} language="python" />
        </div>
      </div>

      {/* Comparison table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-8">
        <div className="px-5 py-3.5 border-b border-gray-800 bg-gray-900/80">
          <h3 className="text-sm font-semibold text-white">Head-to-head comparison</h3>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-2.5 w-48">Dimension</th>
              <th className="text-left text-xs font-semibold text-indigo-400 uppercase tracking-wider px-4 py-2.5">🏗️ Customized App</th>
              <th className="text-left text-xs font-semibold text-emerald-400 uppercase tracking-wider px-4 py-2.5">🌐 Universal App</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {COMPARISON_ROWS.map((row) => (
              <tr key={row.dimension} className="hover:bg-gray-800/30 transition-colors">
                <td className="px-5 py-3 text-xs font-medium text-gray-400">{row.dimension}</td>
                <td className="px-4 py-3 text-xs text-gray-300">{row.customized}</td>
                <td className="px-4 py-3 text-xs text-gray-300">{row.universal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Demo apps */}
      <div className="mb-8">
        <h3 className="text-sm font-semibold text-white mb-4">Demo apps — Customized pattern</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {CUSTOMIZED_DEMO_APPS.map((app) => (
            <div key={app.name} className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3.5 flex items-start gap-3 hover:border-gray-700 transition-colors">
              <span className="text-lg flex-shrink-0 mt-0.5">{app.icon}</span>
              <div>
                <div className="font-mono text-xs text-indigo-300 mb-0.5">{app.name}</div>
                <div className="text-xs text-gray-400 leading-relaxed">{app.desc}</div>
              </div>
            </div>
          ))}
          <div className="bg-emerald-900/10 border border-emerald-800/30 rounded-xl px-4 py-3.5 flex items-start gap-3">
            <span className="text-lg flex-shrink-0 mt-0.5">🌐</span>
            <div>
              <div className="font-mono text-xs text-emerald-300 mb-0.5">universal_app</div>
              <div className="text-xs text-gray-400 leading-relaxed">
                Single chat — dynamically creates any pipeline from natural language
              </div>
              <div className="mt-1.5 inline-flex items-center gap-1 bg-emerald-900/30 border border-emerald-800/40 rounded px-2 py-0.5 text-xs text-emerald-400">
                Universal pattern
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* When to use each */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">
        <div className="bg-indigo-900/10 border border-indigo-800/30 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-indigo-300 mb-3">Use the Customized pattern when…</h3>
          <ul className="space-y-2">
            {[
              'You know exactly what the app does and who uses it',
              'The pipeline structure needs to be validated end-to-end',
              'You want hand-tuned prompts for a specific domain',
              'You\'re shipping a production product, not a prototype',
              'The user population is non-technical',
            ].map((item) => (
              <li key={item} className="flex items-start gap-2 text-xs text-gray-300">
                <span className="text-indigo-400 mt-0.5 flex-shrink-0">✓</span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-emerald-900/10 border border-emerald-800/30 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-emerald-300 mb-3">Use the Universal pattern when…</h3>
          <ul className="space-y-2">
            {[
              'You want users to define their own automation without code',
              'You\'re building a platform, not a single-purpose app',
              'Use cases are varied and hard to pre-enumerate',
              'Rapid prototyping — let users discover what works',
              'Power users who know what channels and tools exist',
            ].map((item) => (
              <li key={item} className="flex items-start gap-2 text-xs text-gray-300">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0">✓</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Key insight callout */}
      <div className="bg-amber-900/10 border border-amber-800/30 rounded-xl p-5">
        <div className="flex items-start gap-3">
          <span className="text-xl flex-shrink-0">💡</span>
          <div>
            <h3 className="text-sm font-semibold text-amber-300 mb-1.5">They share the same infrastructure</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              Both patterns use identical cuga++ primitives — <span className="font-mono text-xs text-gray-200">CugaAgent</span>,{' '}
              <span className="font-mono text-xs text-gray-200">CugaRuntime</span>,{' '}
              <span className="font-mono text-xs text-gray-200">CugaHost</span>, channels, and tool factories.
              The difference is purely in <em className="text-amber-200">who wires them together and when</em>.
              A Customized App wired today can evolve into a Universal App by adding a planner layer — no
              channel or runtime code needs to change.
            </p>
          </div>
        </div>
      </div>

    </div>
  )
}
