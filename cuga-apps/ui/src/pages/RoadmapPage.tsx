const SPRINT_4 = [
  { item: 'make_twitter_tool()', impact: '+3 use cases', effort: 'Medium', desc: 'Twitter/X API v2. Unlocks social media scheduler, brand monitoring, cross-posting.' },
  { item: 'NotionChannel + make_notion_tools()', impact: '+2 use cases', effort: 'Medium', desc: 'Read/write Notion databases. Living document assistants, meeting notes auto-population.' },
  { item: 'make_hubspot_tool()', impact: '+2 use cases', effort: 'Medium', desc: 'HubSpot CRM integration. Lead scoring, CRM data enrichment.' },
  { item: 'make_pandas_tool()', impact: '+1 use case', effort: 'Low', desc: 'Spreadsheet analyst. CSV/Excel upload → agent answers questions with pandas/DuckDB.' },
  { item: 'DatabaseChannel', impact: '+2 use cases', effort: 'Medium', desc: 'Poll Postgres/MySQL/SQLite. KPI snapshots, automated database reports.' },
]

const SPRINT_5_ARCH = [
  {
    item: 'Persistent agent memory (PersistentRuntime)',
    effort: 'Medium',
    desc: 'Agents that remember what they worked on last week, follow up on pending tasks, build context over time. Wraps CugaRuntime with a long-horizon memory store (SQLite/Chroma/Redis).',
    code: `runtime = PersistentRuntime(
    agent=agent,
    input_channels=[CronChannel("0 9 * * *", "What needs my attention today?")],
    memory_backend="sqlite",
    context_window_days=7,
)`,
  },
  {
    item: 'Multi-agent pipelines (CugaPipeline)',
    effort: 'High',
    desc: 'Chain multiple CugaRuntime instances — output of one becomes input to the next. Enables research → write → publish flows, approval workflows.',
    code: `pipeline = CugaPipeline([
    CugaRuntime(agent=researcher, input_channels=[CronChannel(...)]),
    CugaRuntime(agent=editor),       # receives step 1 output
    CugaRuntime(agent=publisher, output_channels=[EmailChannel(...)]),
])`,
  },
  {
    item: 'Human-in-the-loop approval (ApprovalChannel)',
    effort: 'Medium',
    desc: 'Pauses execution and waits for human confirmation via Telegram, Slack, or web before taking sensitive actions (sending email, creating calendar event).',
    code: `output_channels=[
    ApprovalChannel(via=TelegramChannel(...), timeout=300),
    EmailChannel(to="team@example.com"),
]`,
  },
  {
    item: 'ChannelPlanner → generates Python code',
    effort: 'Medium',
    desc: 'Non-engineers describe a pipeline in plain English, ChannelPlanner returns working Python code. The "product" play for CUGA++.',
    code: `planner = ChannelPlanner(model=llm)
code = planner.generate_python(
    "Monitor arxiv RSS for new ML papers, summarize daily, email me"
)
# Returns: runnable Python using RssChannel + CronChannel + EmailChannel`,
  },
  {
    item: 'MCP tool bridge (MCPToolBridge)',
    effort: 'Medium',
    desc: 'Any MCP-compatible tool server plugs into CUGA++ as a tool list. Notion, Linear, Figma, databases — one line each.',
    code: `tools = MCPToolBridge.from_server("notion://workspace")
tools = MCPToolBridge.from_server("linear://team")`,
  },
  {
    item: 'CugaHost dashboard + health API',
    effort: 'Medium',
    desc: 'Web dashboard (port 8080) showing all running pipelines, last run, last output, error state. Health endpoint for monitoring.',
    code: `host = CugaHost(
    runtimes=[runtime1, runtime2],
    dashboard_port=8080,
    health_port=8081,
)`,
  },
]

const SPRINT_6 = [
  {
    item: 'LongRunningAgent',
    effort: 'High',
    desc: 'Agents that work for hours with task checkpointing and background execution. "Research all 50 competitors" → runs overnight, emails you the report.',
    code: `agent = LongRunningAgent(
    base_agent=CugaAgent(model=llm, tools=[...]),
    max_steps=200,
    checkpoint_every=10,
    on_complete=EmailChannel(to="me@example.com"),
)`,
  },
  {
    item: 'Eval / testing framework',
    effort: 'High',
    desc: 'Neither CUGA++ nor OpenClaw has a built-in eval framework. First mover wins. Record agent runs, compare outputs, regression-test pipelines.',
  },
  {
    item: 'Browser automation (Playwright channel)',
    effort: 'High',
    desc: 'Fill forms, take screenshots, scrape JS-heavy pages. Would close the last major gap vs OpenClaw and Manus.',
  },
]

const WONT_BUILD = [
  { item: 'Native iOS/Android app', reason: 'Hardware/App Store distribution — out of scope for infrastructure' },
  { item: 'IoT firmware / edge sensors', reason: 'Use make_shell_tools() + MQTT broker instead' },
  { item: 'Plaid / bank API', reason: 'OAuth + compliance requirements make this an app-layer concern, not platform' },
  { item: 'Fine-tuning pipeline', reason: 'Separate concern from inference infrastructure' },
]

interface CodeProps { code: string }
function InlineCode({ code }: CodeProps) {
  return (
    <pre className="mt-2 p-3 bg-gray-950 border border-gray-800 rounded text-xs text-gray-400 font-mono whitespace-pre overflow-x-auto">
      {code}
    </pre>
  )
}

export default function RoadmapPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-mono bg-gray-800 text-gray-500 border border-gray-700 px-2 py-0.5 rounded">
            Early thinking — Apr 2026
          </span>
          <span className="text-xs text-gray-600">
            See <a href="/vision" className="text-indigo-500 hover:text-indigo-400 underline">Vision</a> for the current strategic direction
          </span>
        </div>
        <h2 className="text-2xl font-semibold text-white mb-2">Early Thoughts</h2>
        <p className="text-gray-400 text-sm max-w-2xl">
          Original sprint-based roadmap from the start of the project. CUGA++ at 53/82 OpenClaw use cases after Sprint 3. Kept here as a record of where the thinking started.
        </p>
      </div>

      {/* Progress bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-400">OpenClaw coverage</span>
          <span className="text-sm font-mono text-gray-300">53 / 82 use cases</span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2">
          <div className="bg-indigo-600 h-2 rounded-full" style={{ width: '64.6%' }} />
        </div>
        <div className="flex justify-between text-xs text-gray-600 mt-1">
          <span>Sprint 3 (current)</span>
          <span>64.6%</span>
        </div>
      </div>

      {/* Sprint 4 */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <span className="bg-green-900/40 text-green-300 text-xs px-2 py-0.5 rounded font-mono border border-green-800/40">Sprint 4</span>
          <span className="text-xs text-gray-500">~+10 use cases → 63/82</span>
        </div>
        <p className="text-xs text-gray-500 mb-3">Highest leverage: each requires one new tool factory, channels already in place.</p>
        <div className="space-y-2">
          {SPRINT_4.map((item) => (
            <div key={item.item} className="bg-gray-900 border border-gray-800 rounded-lg p-3.5 flex items-start gap-3">
              <div className="flex-1">
                <div className="font-mono text-sm text-indigo-300">{item.item}</div>
                <div className="text-xs text-gray-400 mt-0.5">{item.desc}</div>
              </div>
              <div className="flex-shrink-0 text-right">
                <div className="text-xs text-green-400 font-mono">{item.impact}</div>
                <div className="text-xs text-gray-600 mt-0.5">{item.effort}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Sprint 5 */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <span className="bg-blue-900/40 text-blue-300 text-xs px-2 py-0.5 rounded font-mono border border-blue-800/40">Sprint 5</span>
          <span className="text-xs text-gray-500">Architectural investments — qualitative platform shift</span>
        </div>
        <div className="space-y-4">
          {SPRINT_5_ARCH.map((item) => (
            <div key={item.item} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="font-mono text-sm text-blue-300">{item.item}</div>
                <span className="text-xs text-gray-600 flex-shrink-0">{item.effort}</span>
              </div>
              <div className="text-xs text-gray-400 leading-relaxed mb-2">{item.desc}</div>
              {item.code && <InlineCode code={item.code} />}
            </div>
          ))}
        </div>
      </section>

      {/* Sprint 6 */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <span className="bg-purple-900/40 text-purple-300 text-xs px-2 py-0.5 rounded font-mono border border-purple-800/40">Sprint 6</span>
          <span className="text-xs text-gray-500">Long-horizon agents and moat-building capabilities</span>
        </div>
        <div className="space-y-4">
          {SPRINT_6.map((item) => (
            <div key={item.item} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="font-mono text-sm text-purple-300">{item.item}</div>
                <span className="text-xs text-gray-600 flex-shrink-0">{item.effort}</span>
              </div>
              <div className="text-xs text-gray-400 leading-relaxed mb-2">{item.desc}</div>
              {item.code && <InlineCode code={item.code} />}
            </div>
          ))}
        </div>
      </section>

      {/* Target state */}
      <div className="bg-indigo-900/20 border border-indigo-800/40 rounded-xl p-5 mb-8">
        <h3 className="text-sm font-semibold text-indigo-300 mb-3">Target state: what CUGA++ looks like when it's done</h3>
        <ul className="space-y-1.5">
          {[
            'Any trigger (cron, webhook, message, file drop, threshold) fires the right pipeline automatically',
            'Any data source (RSS, email, Slack, files, databases, APIs) flows to the agent as clean text',
            'Any action (web search, calendar, GitHub, shell, market data, RAG, CRM, image) is available as a @tool',
            'Any output (email, Slack, Telegram, Discord, SMS, WhatsApp, speech, log) is one import away',
            'Any LLM (Claude, GPT-4, Llama, Watson) works without changing pipeline code',
            'Non-engineers can describe a pipeline in natural language and get working code',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
              <span className="text-indigo-500 flex-shrink-0 mt-0.5">▸</span>
              {point}
            </li>
          ))}
        </ul>
        <p className="text-xs text-gray-500 mt-3">
          At that point, building an LLM-powered automation is a 30-line configuration exercise, not a 500-line engineering project.
        </p>
      </div>

      {/* Won't build */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 mb-3">What we won't build (and why)</h3>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left text-xs font-semibold text-gray-600 px-4 py-2.5">Capability</th>
                <th className="text-left text-xs font-semibold text-gray-600 px-4 py-2.5">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {WONT_BUILD.map((row) => (
                <tr key={row.item}>
                  <td className="px-4 py-2.5 text-sm text-gray-400">{row.item}</td>
                  <td className="px-4 py-2.5 text-xs text-gray-500">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-600 mt-2">
          The principle: CUGA++ is infrastructure for calling LLMs and routing their results. If a capability requires legal agreements, hardware, or OAuth approval workflows that vary by user, it belongs in the app layer as a @tool, not in the platform.
        </p>
      </div>
    </div>
  )
}
