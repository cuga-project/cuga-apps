import { COMPARISON_SECTIONS } from '../data/comparison'

const ICON: Record<string, string> = {
  yes: '✅',
  partial: '🔧',
  no: '❌',
}

const WHERE_CUGA_WINS = [
  {
    title: 'Python = AI ecosystem',
    desc: 'Every AI library is Python-first: LangChain, LangGraph, Hugging Face, FAISS, ChromaDB, Whisper, Ollama. OpenClaw is TypeScript — it always wraps Python tools via subprocess. CUGA++ composes with them directly via import.',
  },
  {
    title: 'Developer builds the app',
    desc: 'OpenClaw is a product you use. CUGA++ is a library you build with. If you\'re building for other people — a document intelligence service for a law firm, a monitoring agent for your infra team — CUGA++ is the right tool.',
  },
  {
    title: 'Multi-user, team, production',
    desc: 'OpenClaw explicitly says it\'s not for teams. CUGA++ is designed for exactly this: one pipeline, multiple users, deployed to a server, running 24/7. CugaHost, YAML-configured pipelines, and the deployment model are all production-oriented.',
  },
  {
    title: 'Extraction before reasoning (DoclingChannel)',
    desc: 'OpenClaw routes documents through the agent which then decides to call a PDF tool. CUGA++ pre-extracts documents to clean markdown before the agent fires. Cheaper (fewer tokens), more reliable, faster.',
  },
  {
    title: 'Composable pipelines as first-class objects',
    desc: 'A CUGA++ pipeline is a Python object you can inspect, test, reconfigure, and version-control. In OpenClaw, the pipeline emerges from configuration — it\'s not a single inspectable object.',
  },
  {
    title: 'MCP tool bridge',
    desc: 'CUGA++ is an MCP client. The entire growing ecosystem of MCP tool servers plugs in with one line. OpenClaw has no MCP support.',
  },
]

const WHERE_OPENCLAW_WINS = [
  {
    title: 'Consumer experience',
    desc: 'Install OpenClaw and talk to it in WhatsApp. No code. No server. No YAML. For someone who wants a personal AI assistant, OpenClaw is a much better experience than any Python library.',
  },
  {
    title: 'Multi-agent spawning',
    desc: 'OpenClaw agents can spawn subagents. Long-horizon tasks benefit from specialist subagents. CUGA++ treats this as future work.',
  },
  {
    title: 'Browser automation and device pairing',
    desc: 'Full Chrome CDP browser control and iOS/Android device nodes. CUGA++ has no equivalent.',
  },
  {
    title: 'More messaging channels',
    desc: 'OpenClaw supports 20+ messaging channels including Matrix, Signal, iMessage, Teams, IRC. CUGA++ supports 6.',
  },
  {
    title: 'Skill marketplace (ClawHub)',
    desc: '50+ bundled skills, a registry, versioning. CUGA++ has no marketplace — each team builds their own tool factories.',
  },
]

export default function ComparisonPage() {
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">CUGA++ vs OpenClaw</h2>
        <p className="text-gray-400 text-sm max-w-2xl">
          These are different products targeting different people. OpenClaw is a personal assistant you install and talk to. CUGA++ is infrastructure you build with.
        </p>
      </div>

      {/* TL;DR */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">OpenClaw</div>
          <div className="space-y-2 text-sm text-gray-300">
            <div><span className="text-gray-500">Who it's for:</span> A person who wants AI in their messaging apps</div>
            <div><span className="text-gray-500">Metaphor:</span> Personal assistant you talk to</div>
            <div><span className="text-gray-500">Language:</span> TypeScript / Node.js</div>
            <div><span className="text-gray-500">Architecture:</span> Hub-and-spoke WebSocket gateway</div>
            <div><span className="text-gray-500">Agent:</span> Embedded (Claude, managed by OpenClaw)</div>
            <div><span className="text-gray-500">Multi-user:</span> Explicitly single-user</div>
            <div><span className="text-gray-500">Setup:</span> Install app, pair devices, use it</div>
          </div>
        </div>
        <div className="bg-gray-900 border border-indigo-800/30 rounded-xl p-5">
          <div className="text-xs font-semibold text-indigo-500 uppercase tracking-wider mb-3">CUGA++</div>
          <div className="space-y-2 text-sm text-gray-300">
            <div><span className="text-gray-500">Who it's for:</span> A developer building an automated agent pipeline</div>
            <div><span className="text-gray-500">Metaphor:</span> Infrastructure library you code with</div>
            <div><span className="text-gray-500">Language:</span> Python (AI ecosystem native)</div>
            <div><span className="text-gray-500">Architecture:</span> Composable channel pipeline</div>
            <div><span className="text-gray-500">Agent:</span> Yours to provide (any .ainvoke() agent)</div>
            <div><span className="text-gray-500">Multi-user:</span> Designed for it</div>
            <div><span className="text-gray-500">Setup:</span> Write code, deploy it</div>
          </div>
        </div>
      </div>

      {/* Positioning quote */}
      <blockquote className="border-l-2 border-indigo-600 pl-4 mb-8">
        <p className="text-sm text-gray-300 italic">
          "This is the difference between <strong className="text-white">using software</strong> and <strong className="text-white">building software</strong>."
        </p>
      </blockquote>

      {/* Feature comparison tables */}
      {COMPARISON_SECTIONS.map((section) => (
        <div key={section.title} className="mb-6">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">{section.title}</h3>
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/80">
                  <th className="text-left text-xs font-semibold text-gray-600 px-4 py-2.5 w-1/3">Capability</th>
                  <th className="text-left text-xs font-semibold text-gray-600 px-4 py-2.5 w-1/3">OpenClaw</th>
                  <th className="text-left text-xs font-semibold text-indigo-600 px-4 py-2.5 w-1/3">CUGA++</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {section.rows.map((row) => (
                  <tr key={row.capability} className="hover:bg-gray-800/30">
                    <td className="px-4 py-2.5 text-sm text-gray-400">{row.capability}</td>
                    <td className="px-4 py-2.5 text-sm text-gray-400">
                      <span className="mr-1.5">{ICON[row.openclaw_status]}</span>
                      {row.openclaw}
                    </td>
                    <td className="px-4 py-2.5 text-sm text-gray-300">
                      <span className="mr-1.5">{ICON[row.cuga_status]}</span>
                      {row.cuga}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {/* Where each wins */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
        <div>
          <h3 className="text-sm font-semibold text-indigo-400 mb-3">Where CUGA++ wins — genuinely</h3>
          <div className="space-y-3">
            {WHERE_CUGA_WINS.map((item) => (
              <div key={item.title} className="bg-indigo-900/10 border border-indigo-800/20 rounded-lg p-3.5">
                <div className="text-sm font-medium text-gray-200 mb-1">{item.title}</div>
                <div className="text-xs text-gray-400 leading-relaxed">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Where OpenClaw wins — honestly</h3>
          <div className="space-y-3">
            {WHERE_OPENCLAW_WINS.map((item) => (
              <div key={item.title} className="bg-gray-800/30 border border-gray-700/30 rounded-lg p-3.5">
                <div className="text-sm font-medium text-gray-300 mb-1">{item.title}</div>
                <div className="text-xs text-gray-500 leading-relaxed">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Differentiation direction */}
      <div className="mt-8 bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3">Where CUGA++ should go to stay differentiated</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="text-left text-xs font-semibold text-gray-500 pb-2 pr-6">Direction</th>
                <th className="text-left text-xs font-semibold text-gray-500 pb-2">Why it differentiates</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {[
                ['Production multi-user deployment', "OpenClaw won't go here (single-user by design)"],
                ['Built-in eval / testing framework', "Neither has it — first mover wins"],
                ['Python-native ML pipeline integration', "OpenClaw will always need subprocesses"],
                ['Team workflow automation (approval flows, HITL)', "OpenClaw is personal, not team"],
                ['Data-heavy pipelines (batch DoclingChannel)', "OpenClaw routes through agent; CUGA++ pre-extracts"],
                ['Configurable / white-label SaaS', "Build a CUGA++ app, deploy it as a product"],
              ].map(([dir, why]) => (
                <tr key={dir} className="hover:bg-gray-800/30">
                  <td className="py-2 pr-6 text-sm text-gray-300">{dir}</td>
                  <td className="py-2 text-sm text-gray-500">{why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
