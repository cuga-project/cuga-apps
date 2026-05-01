import { MANUS_USE_CASES } from '../data/comparison'

const STATUS_ICON: Record<string, string> = {
  working: '✅',
  partial: '🔧',
  gap: '❌',
}

const STATUS_LABEL: Record<string, string> = {
  working: 'Working',
  partial: 'Partial',
  gap: 'Gap',
}

const STATUS_COLOR: Record<string, string> = {
  working: 'text-green-400',
  partial: 'text-yellow-400',
  gap: 'text-gray-500',
}

export default function ManusPage() {
  const working = MANUS_USE_CASES.filter((u) => u.status === 'working').length
  const partial = MANUS_USE_CASES.filter((u) => u.status === 'partial').length
  const gap = MANUS_USE_CASES.filter((u) => u.status === 'gap').length

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">Manus Use Case Mapping</h2>
        <p className="text-gray-400 text-sm max-w-2xl">
          Manus AI is an agentic AI system that executes complex, multi-step tasks autonomously. This page maps Manus's publicly demonstrated use cases against what CUGA++ can do today.
        </p>
      </div>

      {/* What is Manus */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8">
        <h3 className="text-sm font-semibold text-white mb-3">What is Manus?</h3>
        <p className="text-sm text-gray-300 leading-relaxed mb-3">
          Manus is a general-purpose AI agent that can browse the web, write and execute code, create files, and interact with external services — all autonomously from a single natural language instruction. It's designed as a one-shot task executor: give it a goal, come back when it's done.
        </p>
        <p className="text-sm text-gray-300 leading-relaxed mb-3">
          <strong className="text-white">Where Manus runs a one-shot task for a person, CUGA++ turns the same task into a running pipeline for a team.</strong> Manus is optimised for "do this once, well." CUGA++ is optimised for "do this every Monday, for every customer, reliably."
        </p>
        <div className="grid grid-cols-3 gap-3 mt-4">
          <div className="text-center">
            <div className="text-lg font-bold text-green-400">{working}</div>
            <div className="text-xs text-gray-500">Working today</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-yellow-400">{partial}</div>
            <div className="text-xs text-gray-500">Partial / needs tool</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-gray-500">{gap}</div>
            <div className="text-xs text-gray-500">Gap</div>
          </div>
        </div>
      </div>

      {/* Use case table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-8">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-900/80">
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-4 py-2.5 w-8">#</th>
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2.5">Manus Use Case</th>
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2.5 hidden md:table-cell">CUGA++ approach</th>
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {MANUS_USE_CASES.map((uc) => (
              <tr key={uc.id} className="hover:bg-gray-800/30">
                <td className="px-4 py-3 text-gray-600 text-sm font-mono">{uc.id}</td>
                <td className="px-3 py-3 text-sm text-gray-300">{uc.name}</td>
                <td className="px-3 py-3 hidden md:table-cell">
                  <div className="text-xs text-gray-500">{uc.notes}</div>
                  {uc.channels.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {uc.channels.map((c) => (
                        <span key={c} className="text-xs font-mono bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded">
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-3 py-3">
                  <span className={`text-sm ${STATUS_COLOR[uc.status]}`}>
                    {STATUS_ICON[uc.status]} {STATUS_LABEL[uc.status]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* The 3 gaps */}
      <div className="mb-8">
        <h3 className="text-sm font-semibold text-white mb-3">The 3 gaps</h3>
        <div className="space-y-3">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="text-sm font-medium text-gray-200 mb-1">1. HTML / web app generation</div>
            <div className="text-xs text-gray-500">
              Manus can generate interactive HTML pages and deploy web apps. CUGA++ has no equivalent output channel. A <code className="text-gray-400">WebAppOutputChannel</code> or HTML file output would close use cases #2, #9, #10.
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="text-sm font-medium text-gray-200 mb-1">2. Data visualization / chart generation</div>
            <div className="text-xs text-gray-500">
              CUGA++ can produce data analysis in text, but has no chart generation. A <code className="text-gray-400">make_chart_tool()</code> using matplotlib or Plotly would close use case #12.
            </div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="text-sm font-medium text-gray-200 mb-1">3. Browser automation / Chrome CDP</div>
            <div className="text-xs text-gray-500">
              Manus can browse the web, fill forms, and take screenshots via a real browser. OpenClaw also has Chrome CDP. CUGA++ has no browser automation — only Tavily web search. A Playwright-based channel would be high-leverage.
            </div>
          </div>
        </div>
      </div>

      {/* Key insight */}
      <div className="bg-indigo-900/20 border border-indigo-800/40 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-indigo-300 mb-2">Key insight: task vs pipeline</h3>
        <p className="text-sm text-gray-300 leading-relaxed">
          Manus excels at one-shot, deep, autonomous tasks for a single user. CUGA++ excels at recurring, scheduled, multi-user pipelines. The overlap is strongest exactly where CUGA++ is positioned:{' '}
          <strong className="text-white">research, monitoring, content creation, and document processing</strong> — all tasks that are more valuable run repeatedly than run once.
        </p>
        <p className="text-sm text-gray-400 mt-3 leading-relaxed">
          Example: Manus can produce a competitor analysis report once. CUGA++ makes that same report run every Monday and land in your Slack before standup — for every member of the strategy team.
        </p>
      </div>
    </div>
  )
}
