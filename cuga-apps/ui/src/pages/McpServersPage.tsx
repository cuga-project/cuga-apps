import { MCP_SERVERS, mcpServerUrl, TOOL_EXPLORER_URL, type McpServer } from '../data/mcpServers'

const ACCENT: Record<McpServer['accent'], { bar: string; text: string; chip: string }> = {
  blue:    { bar: 'bg-indigo-600', text: 'text-indigo-600', chip: 'bg-indigo-500/10 text-indigo-600 border-indigo-500/25' },
  emerald: { bar: 'bg-emerald-500', text: 'text-emerald-600', chip: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/25' },
  amber:   { bar: 'bg-amber-500', text: 'text-amber-600', chip: 'bg-amber-500/10 text-amber-600 border-amber-500/25' },
  pink:    { bar: 'bg-pink-500', text: 'text-pink-600', chip: 'bg-pink-500/10 text-pink-600 border-pink-500/25' },
  cyan:    { bar: 'bg-cyan-500', text: 'text-cyan-600', chip: 'bg-cyan-500/10 text-cyan-600 border-cyan-500/25' },
  violet:  { bar: 'bg-violet-500', text: 'text-violet-600', chip: 'bg-violet-500/10 text-violet-600 border-violet-500/25' },
  rose:    { bar: 'bg-rose-500', text: 'text-rose-600', chip: 'bg-rose-500/10 text-rose-600 border-rose-500/25' },
}

function ServerCard({ s }: { s: McpServer }) {
  const a = ACCENT[s.accent]
  const url = mcpServerUrl(s.id)
  return (
    <div className="bg-tsurf border border-tborder flex flex-col overflow-hidden">
      <div className="flex items-stretch">
        <div className={`w-1 ${a.bar}`} />
        <div className="flex-1 p-5">
          <div className="flex items-center gap-2.5 mb-1">
            <h3 className="text-lg font-semibold text-t1">{s.name}</h3>
            <span className="font-mono text-xs text-t4">mcp-{s.id}</span>
            <span className="ml-auto font-mono text-xs text-t4">:{s.port}</span>
          </div>
          <p className="text-sm text-t2 leading-relaxed mb-4">{s.blurb}</p>

          <div className="text-[11px] font-semibold uppercase tracking-wider text-t4 mb-1.5">Sources</div>
          <div className="flex flex-wrap gap-1.5 mb-4">
            {s.sources.map((src) => (
              <span key={src} className={`text-xs px-2 py-0.5 border ${a.chip}`}>{src}</span>
            ))}
          </div>

          <div className="text-[11px] font-semibold uppercase tracking-wider text-t4 mb-1.5">
            {s.tools.length} tools
          </div>
          <div className="flex flex-wrap gap-1.5">
            {s.tools.map((t) => (
              <span key={t} className="text-xs font-mono px-2 py-0.5 bg-tsurf2 text-t3 border border-tborder">{t}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-auto border-t border-tborder px-5 py-3 bg-tsurf2/40 flex items-center justify-between gap-3">
        <code className="text-xs text-t3 font-mono truncate" title={url}>{url.replace('https://', '')}</code>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className={`shrink-0 text-xs font-semibold ${a.text} hover:underline whitespace-nowrap`}
        >
          Open endpoint ↗
        </a>
      </div>
    </div>
  )
}

export default function McpServersPage() {
  const totalTools = MCP_SERVERS.reduce((n, s) => n + s.tools.length, 0)
  return (
    <div className="p-6 md:p-8 max-w-screen-2xl mx-auto">
      {/* Hero */}
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 mb-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600 bg-indigo-500/10 border border-indigo-500/25 px-2 py-0.5">
            Code Engine
          </span>
          <span className="text-xs text-t4">IBM Cloud · us-east</span>
        </div>
        <h2 className="text-3xl md:text-4xl font-semibold text-t1 mb-2 tracking-tight">MCP Servers</h2>
        <p className="text-base text-t2 max-w-3xl leading-relaxed">
          Every shared tool primitive lives in its own <strong className="text-t1">MCP server</strong> —
          apps connect over streamable HTTP through a LangChain↔MCP bridge, so a REST API, a custom
          server, and a Python function all bind the same way. Seven servers are hosted on
          IBM Cloud Code Engine, exposing <strong className="text-t1">{totalTools} tools</strong> across
          web, knowledge, geo, finance, code, host and text domains.
        </p>
      </div>

      {/* Tool explorer callout */}
      <a
        href={TOOL_EXPLORER_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="group flex items-center gap-4 mb-8 p-4 bg-tsurf border border-tborder hover:border-indigo-500 transition-colors"
      >
        <div className="w-10 h-10 bg-indigo-600 text-white flex items-center justify-center text-lg shrink-0">⛭</div>
        <div className="flex-1">
          <div className="text-sm font-semibold text-t1">MCP Tool Explorer</div>
          <div className="text-sm text-t3">Browse and invoke every tool across all seven servers from one UI.</div>
        </div>
        <span className="text-sm font-semibold text-indigo-600 group-hover:underline whitespace-nowrap">Open ↗</span>
      </a>

      {/* Server grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {MCP_SERVERS.map((s) => (
          <ServerCard key={s.id} s={s} />
        ))}
      </div>

      <p className="mt-6 text-sm text-t4">
        Hosted at <code className="font-mono text-t3">cuga-apps-mcp-&lt;name&gt;.…codeengine.appdomain.cloud/mcp</code>.
        Run locally on ports 29100–29106 — see <code className="font-mono text-t3">mcp_servers/README.md</code>.
      </p>
    </div>
  )
}
