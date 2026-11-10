import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { MCP_SERVERS, mcpServerUrl, TOOL_EXPLORER_URL, type McpServer } from '../data/mcpServers'
import { CE_REGION } from '../data/deployment'
import CodeBlock from '../components/CodeBlock'

// Copy-pasteable snippet: connect to this server's /mcp endpoint over streamable
// HTTP with LangChain's own MCP adapter (what cuga >= 0.4.5 uses) and get tools
// for any LangChain / LangGraph / CUGA agent.
function usageSnippet(s: McpServer): string {
  const preview = s.tools.slice(0, 4).join(', ') + (s.tools.length > 4 ? ', …' : '')
  if (s.tokenEnv) {
    return `# pip install "langchain[mcp]" fastmcp
import os
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter

transport = StreamableHttpTransport(
    "${mcpServerUrl(s.id)}",
    headers={"Authorization": f"Bearer {os.environ['${s.tokenEnv}']}"},
)
tools = await MCPAdapter(Client(transport)).list_tools()
# → ${preview}`
  }
  return `# pip install "langchain[mcp]" fastmcp
from langchain.mcp import MCPAdapter

tools = await MCPAdapter("${mcpServerUrl(s.id)}").list_tools()
# → ${preview}`
}

const ACCENT: Record<McpServer['accent'], { dot: string; text: string; chip: string; glow: string }> = {
  blue:    { dot: 'bg-indigo-600',  text: 'text-indigo-600',  chip: 'bg-indigo-500/10 text-indigo-700 border-indigo-500/20',   glow: 'from-indigo-500/15' },
  emerald: { dot: 'bg-emerald-500', text: 'text-emerald-600', chip: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20', glow: 'from-emerald-500/15' },
  amber:   { dot: 'bg-amber-500',   text: 'text-amber-600',   chip: 'bg-amber-500/10 text-amber-700 border-amber-500/20',       glow: 'from-amber-500/15' },
  pink:    { dot: 'bg-pink-500',    text: 'text-pink-600',    chip: 'bg-pink-500/10 text-pink-700 border-pink-500/20',          glow: 'from-pink-500/15' },
  cyan:    { dot: 'bg-sky-600',     text: 'text-sky-700',     chip: 'bg-sky-500/10 text-sky-700 border-sky-500/20',             glow: 'from-sky-500/15' },
  violet:  { dot: 'bg-violet-500',  text: 'text-violet-600',  chip: 'bg-violet-500/10 text-violet-700 border-violet-500/20',    glow: 'from-violet-500/15' },
  rose:    { dot: 'bg-rose-500',    text: 'text-rose-600',    chip: 'bg-rose-500/10 text-rose-700 border-rose-500/20',          glow: 'from-rose-500/15' },
}

function ServerCard({ s }: { s: McpServer }) {
  const a = ACCENT[s.accent]
  const url = mcpServerUrl(s.id)
  return (
    <div id={`mcp-${s.id}`} className="scroll-mt-24 flex flex-col bg-tsurf border border-tborder rounded hover:border-indigo-600 transition-colors overflow-hidden">
      <div className={`px-6 pt-5 pb-4 bg-gradient-to-b ${a.glow} to-transparent`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${a.dot}`} />
              <h3 className="font-display text-xl font-medium text-t1">{s.name}</h3>
              <code className="text-xs font-mono text-t4">mcp-{s.id}</code>
            </div>
            <p className="text-sm text-t2 mt-1.5 leading-relaxed">{s.blurb}</p>
          </div>
          <span className={`shrink-0 text-xs font-semibold px-2 py-1 rounded-full border ${a.chip}`}>
            {s.tools.length} tools
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {s.hostedBy && (
            <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-t1 text-tsurf">
              Hosted by {s.hostedBy}
            </span>
          )}
          {s.sources.map((src) => (
            <span key={src} className="text-xs px-2 py-0.5 rounded-full bg-tsurf border border-tborder text-t3">{src}</span>
          ))}
        </div>
      </div>

      <div className="px-6 pb-5 flex flex-col gap-4">
        <div className="flex flex-wrap gap-1.5">
          {s.tools.map((t) => (
            <span key={t} className="text-xs font-mono px-2 py-0.5 rounded-md bg-tsurf2 text-t2 border border-tborder">{t}</span>
          ))}
        </div>

        {s.examples.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {s.examples.map((ex) => (
              <span key={ex} className="text-sm text-t2 pl-3 border-l-2 border-tborder italic">“{ex}”</span>
            ))}
          </div>
        )}

        <CodeBlock code={usageSnippet(s)} language="python" />
        {s.tokenEnv && (
          <p className="text-xs text-t3 -mt-2">
            Needs a <code className="font-mono">{s.tokenEnv}</code> sent as a bearer token. CUGA apps add it for you
            (<code className="font-mono">load_tools(["{s.id}"])</code>).
          </p>
        )}
      </div>

      <div className="mt-auto border-t border-tborder px-6 py-3 flex items-center justify-between gap-3 bg-tsurf2/50">
        <code className="text-xs text-t3 font-mono truncate" title={url}>{url.replace('https://', '')}</code>
        <div className="flex items-center gap-4 shrink-0">
          <a href={TOOL_EXPLORER_URL} target="_blank" rel="noopener noreferrer"
             title={`Browse & invoke mcp-${s.id} tools in the MCP Tool Explorer`}
             className="text-xs font-semibold text-t3 hover:text-t1 whitespace-nowrap">
            Try in Tool Explorer ↗
          </a>
          {!s.tokenEnv && (
            <a href={url} target="_blank" rel="noopener noreferrer"
               className={`text-xs font-semibold ${a.text} hover:underline whitespace-nowrap`}>
              Endpoint ↗
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

export default function McpServersPage() {
  const ours = MCP_SERVERS.filter((s) => !s.hostedBy)
  const hosted = MCP_SERVERS.filter((s) => s.hostedBy)
  const totalTools = MCP_SERVERS.reduce((n, s) => n + s.tools.length, 0)
  const location = useLocation()
  // Deep-link support: arriving with #mcp-<id> (from a server chip on the Apps
  // page) scrolls that server's card into view.
  useEffect(() => {
    if (!location.hash) return
    const el = document.getElementById(location.hash.slice(1))
    if (el) requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [location.hash])

  return (
    <div className="px-4 md:px-14 py-14">
      <div className="mb-8 max-w-3xl">
        <div className="eyebrow text-indigo-600 mb-5">
          MCP Servers · IBM Cloud Code Engine · {CE_REGION}
        </div>
        <h1 className="font-display font-medium tracking-[-0.02em] leading-[1.02] text-[40px] md:text-[56px] mb-5">The tools behind every app.<br /><span className="text-t3">One bridge to all of them.</span></h1>
        <p className="text-base text-t2 leading-relaxed">
          Every shared tool lives in an <strong className="text-t1">MCP server</strong>. Apps connect over
          streamable HTTP through one bridge, so a REST API, a custom server and a hosted service like Tavily
          all bind the same way — <strong className="text-t1">{MCP_SERVERS.length} servers, {totalTools} tools</strong>.
        </p>
      </div>

      <a href={TOOL_EXPLORER_URL} target="_blank" rel="noopener noreferrer"
         className="group flex items-center gap-4 mb-12 p-5 rounded bg-indigo-600 hover:bg-indigo-700 text-white transition-colors">
        <div className="w-11 h-11 rounded bg-white/15 flex items-center justify-center text-xl shrink-0">⛭</div>
        <div className="flex-1">
          <div className="text-base font-semibold">MCP Tool Explorer</div>
          <div className="text-sm text-white/80">Browse and call every tool on every server — including Tavily — from one page.</div>
        </div>
        <span className="text-sm font-semibold whitespace-nowrap group-hover:translate-x-0.5 transition-transform">Open ↗</span>
      </a>

      {hosted.length > 0 && (
        <>
          <h2 className="eyebrow text-t3 mb-4">01 · Hosted partners</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-10">
            {hosted.map((s) => <ServerCard key={s.id} s={s} />)}
          </div>
        </>
      )}

      <h2 className="eyebrow text-t3 mb-4">02 · Run by CUGA Apps</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {ours.map((s) => <ServerCard key={s.id} s={s} />)}
      </div>

      <p className="mt-8 text-sm text-t4">
        Ours are hosted at <code className="font-mono text-t3">cuga-apps-mcp-&lt;name&gt;.…codeengine.appdomain.cloud/mcp</code>{' '}
        and run locally on ports 29100–29106 — see <code className="font-mono text-t3">mcp_servers/README.md</code>.
      </p>
    </div>
  )
}
