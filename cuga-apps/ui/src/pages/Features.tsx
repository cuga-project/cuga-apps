import CodeBlock from '../components/CodeBlock'

// ── Ecosystem map — the "everything at a glance" visual ──────────────────────

function EcosystemMap() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-10 overflow-x-auto">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-5">
        The CUGA++ ecosystem — one agent, every surface, every modality
      </h3>

      {/* Three-column layout: Gateway | Agent Core | Pipelines */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-4 min-w-[720px]">

        {/* ── Left: Gateway Surface ─────────────────────────────── */}
        <div className="flex flex-col gap-2">
          <div className="text-xs font-semibold text-indigo-400 mb-1 flex items-center gap-1.5">
            <span>💬</span> Conversation Gateways
            <span className="text-gray-600 font-normal text-[10px] ml-1">humans talk in real-time</span>
          </div>
          {[
            { icon: '🌐', label: 'Browser',   method: 'add_browser_adapter()',   status: 'bg-green-900/30 border-green-800/40 text-green-400' },
            { icon: '✈️', label: 'Telegram',  method: 'add_telegram_adapter()',  status: 'bg-green-900/30 border-green-800/40 text-green-400' },
            { icon: '💬', label: 'WhatsApp',  method: 'add_whatsapp_adapter()',  status: 'bg-green-900/30 border-green-800/40 text-green-400' },
            { icon: '📞', label: 'Phone',     method: 'add_voice_adapter()',     status: 'bg-green-900/30 border-green-800/40 text-green-400' },
            { icon: '🎮', label: 'Discord',   method: 'add_discord_adapter()',   status: 'bg-yellow-900/20 border-yellow-800/30 text-yellow-600' },
            { icon: '💼', label: 'Slack',     method: 'add_slack_adapter()',     status: 'bg-yellow-900/20 border-yellow-800/30 text-yellow-600' },
          ].map((a) => (
            <div key={a.label} className={`rounded-lg border px-3 py-2 ${a.status}`}>
              <div className="flex items-center gap-1.5">
                <span className="text-sm">{a.icon}</span>
                <span className="text-xs font-semibold text-gray-200">{a.label}</span>
              </div>
              <div className="text-[10px] font-mono text-gray-600 mt-0.5">{a.method}</div>
            </div>
          ))}
          <div className="mt-1 text-[10px] text-gray-700 italic">
            Per-user thread_id · voice/image/doc handling · asyncio.gather()
          </div>
        </div>

        {/* ── Center: Agent Core ────────────────────────────────── */}
        <div className="flex flex-col items-center justify-center gap-3 px-2">
          {/* Arrow left */}
          <div className="text-gray-700 text-lg">←</div>

          {/* Core box */}
          <div className="rounded-2xl border-2 border-indigo-600/60 bg-indigo-950/40 p-4 w-44 flex flex-col gap-3">
            <div className="text-center">
              <div className="text-xs font-bold text-indigo-300 mb-0.5">CUGA++ Runtime</div>
              <div className="text-[10px] text-gray-600">ConversationGateway / CugaRuntime</div>
            </div>

            <div className="border-t border-indigo-800/40 pt-2 space-y-1.5">
              <CorePill color="text-purple-400" label="Your Agent" sub="any .ainvoke()" />
              <CorePill color="text-pink-400"   label="Multimodal"  sub="text·image·audio·PDF" />
              <CorePill color="text-sky-400"    label="Skills"      sub=".md persona files" />
              <CorePill color="text-amber-400"  label="MCP Bridge"  sub="any MCP server" />
              <CorePill color="text-green-400"  label="Memory"      sub="per-thread history" />
              <CorePill color="text-rose-400"   label="Benchmark"   sub="100+ task corpus" />
            </div>
          </div>

          {/* Arrow right */}
          <div className="text-gray-700 text-lg">→</div>
        </div>

        {/* ── Right: Pipeline Surface ───────────────────────────── */}
        <div className="flex flex-col gap-2">
          <div className="text-xs font-semibold text-emerald-400 mb-1 flex items-center gap-1.5">
            <span>⚡</span> Automated Pipelines
            <span className="text-gray-600 font-normal text-[10px] ml-1">no human in the loop</span>
          </div>

          {/* Triggers */}
          <div className="text-[10px] text-gray-600 font-semibold uppercase tracking-wider">Triggers</div>
          {[
            { icon: '⏰', label: 'CronChannel',     sub: 'schedule expression' },
            { icon: '🔔', label: 'WebhookChannel',  sub: 'GitHub · Stripe · any' },
            { icon: '📁', label: 'CugaWatcher',     sub: 'folder · threshold · API' },
            { icon: '📧', label: 'IMAPChannel',     sub: 'inbox events' },
          ].map((c) => (
            <div key={c.label} className="rounded-lg border border-emerald-800/30 bg-emerald-900/10 px-3 py-2">
              <div className="flex items-center gap-1.5">
                <span className="text-sm">{c.icon}</span>
                <span className="text-xs font-semibold text-gray-200">{c.label}</span>
              </div>
              <div className="text-[10px] text-gray-600 mt-0.5">{c.sub}</div>
            </div>
          ))}

          {/* Outputs */}
          <div className="text-[10px] text-gray-600 font-semibold uppercase tracking-wider mt-1">Outputs</div>
          <div className="flex flex-wrap gap-1.5">
            {['Email', 'Slack', 'Telegram', 'Discord', 'SMS', 'WhatsApp', 'TTS', 'Log'].map((o) => (
              <span key={o} className="text-[10px] font-mono bg-gray-800 border border-gray-700 text-gray-400 px-1.5 py-0.5 rounded">
                {o}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom buzzword strip */}
      <div className="mt-6 pt-4 border-t border-gray-800 flex flex-wrap gap-2">
        {[
          'bring your own agent',
          'multimodal extraction',
          'per-user conversation memory',
          'voice → transcript',
          'PDF → markdown',
          'long-running agents',
          'cron · webhooks · watchers',
          'MCP ecosystem',
          'skills via .md files',
          '100+ use case benchmark',
          'asyncio isolated tasks',
          'production daemon',
          'any LLM provider',
          'one agent · four front-ends',
        ].map((tag) => (
          <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full border border-gray-700 text-gray-500 bg-gray-800/60">
            {tag}
          </span>
        ))}
      </div>
    </div>
  )
}

function CorePill({ color, label, sub }: { color: string; label: string; sub: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className={`text-xs font-medium ${color}`}>{label}</span>
      <span className="text-[9px] text-gray-700">{sub}</span>
    </div>
  )
}

// ── Feature sections ──────────────────────────────────────────────────────────

const GATEWAY_CODE = `from cuga import CugaAgent
from cuga_channels import ConversationGateway

agent = CugaAgent(model=llm, tools=tools, plugins=[skills])

gateway = ConversationGateway(agent=agent)
gateway.add_browser_adapter(port=8765, title="My Assistant")
gateway.add_telegram_adapter()    # reads TELEGRAM_BOT_TOKEN
gateway.add_whatsapp_adapter()    # reads WHATSAPP_* env vars
gateway.add_voice_adapter()       # Twilio TwiML on port 8777

# All four run concurrently on the same agent
# Each user gets their own thread_id + conversation history
asyncio.run(gateway.start())`

const PIPELINE_CODE = `from cuga import CugaAgent
from cuga_channels import (
    CugaRuntime, CronChannel, SlackChannel,
    make_github_tools, CugaSkillsPlugin
)

agent = CugaAgent(
    model=llm,
    tools=make_github_tools(default_repo="myorg/myrepo"),
    plugins=[CugaSkillsPlugin(skills_dir="./skills")],
)

runtime = CugaRuntime(
    agent=agent,
    input_channels=[
        CronChannel(
            schedule="0 9 * * 1-5",   # weekdays at 9am
            message="Produce the daily PR digest. Flag anything open 3+ days."
        )
    ],
    output_channels=[SlackChannel(webhook_url=os.getenv("SLACK_WEBHOOK_URL"))],
)

asyncio.run(runtime.start())`

const MULTIMODAL_CODE = `# All extraction happens BEFORE the agent fires — zero tokens on parsing
runtime = CugaRuntime(
    agent=agent,
    input_channels=[
        DoclingChannel(watch_dir="./contracts"),  # PDF/Word/Excel → clean markdown
        AudioChannel(watch_dir="./voice_notes"),  # .mp3/.m4a → Whisper transcript
        IMAPChannel(...),                         # email + attachments → clean text
    ],
)
# Agent receives: structured text. Never: raw bytes, MIME, base64, page layout.`

const SKILLS_CODE = `# skills/analyst.md — drop this file, change the agent's persona
# No retraining. No fine-tuning. No prompts in Python code.

# Senior Financial Analyst

You are a senior financial analyst. When given documents, extract:
- Revenue, EBITDA, and cash flow figures
- Key risks flagged by auditors
- YoY changes, highlighted in bold

Format output as structured JSON followed by a plain-English summary.`

const MCP_CODE = `# MCPToolBridge — the entire MCP ecosystem as cuga++ tools
from cuga_channels import MCPToolBridge

agent = CugaAgent(
    model=llm,
    tools=[
        *MCPToolBridge.from_server("npx -y @modelcontextprotocol/server-filesystem /docs"),
        *MCPToolBridge.from_server("npx -y @modelcontextprotocol/server-github"),
        *MCPToolBridge.from_server("npx -y @notionhq/notion-mcp-server"),
    ]
)
# Agent now has: file ops + GitHub + Notion — no custom tool code written`

const FEATURES = [
  {
    icon: '💬',
    title: 'Conversation Gateway',
    subtitle: 'One agent, every front-end — add_*_adapter() in one line each',
    accent: 'indigo',
    items: [
      { name: 'add_browser_adapter()', desc: 'Built-in dark-theme web chat UI. Per-session thread_id in localStorage. File upload (📎) with PDF/audio/image extraction. No frontend code needed.' },
      { name: 'add_telegram_adapter()', desc: 'Telegram bot via long-poll. Handles text, voice memos (→ Whisper transcript), photos (→ temp file), documents (→ extracted text). Per-chat thread history.' },
      { name: 'add_whatsapp_adapter()', desc: 'Meta Cloud API webhook. Verify + receive + reply. Audio/image/document inbound, auto-split at 4000 chars. Per-user phone number is thread_id.' },
      { name: 'add_voice_adapter()', desc: 'Twilio TwiML phone gateway. Caller speaks → Twilio transcribes → agent replies via <Say>. Multi-turn: each CallSid is a conversation thread.' },
      { name: 'add_discord_adapter() [partial]', desc: 'Discord bot adapter. Supports DMs and guild channels. Same agent — different skill file = different bot persona.' },
      { name: 'add_slack_adapter() [roadmap]', desc: 'Slack bot via Events API. Per-channel or per-DM thread_id. Rich message formatting.' },
    ],
    code: GATEWAY_CODE,
  },
  {
    icon: '⚡',
    title: 'Automated Pipelines',
    subtitle: 'Agents that run on schedule or react to system events — no human in the loop',
    accent: 'emerald',
    items: [
      { name: 'CronChannel', desc: 'Standard cron expressions. No cron daemon, no systemd, no crontab. Fires the agent on schedule with a configurable message.' },
      { name: 'WebhookChannel', desc: 'Built-in HTTP server. Receive webhooks from GitHub, Slack, Stripe, or any service. No Flask/FastAPI boilerplate.' },
      { name: 'CugaWatcher', desc: 'Poll any condition — file drop, price threshold, API response. Fires only when a condition is met. Compound conditions supported.' },
      { name: 'IMAPChannel', desc: 'Poll IMAP inbox. MIME decoded, boilerplate stripped. Agent receives clean email text + extracted attachments.' },
      { name: 'RssChannel', desc: 'Fetch RSS/Atom feeds. New items deduplicated by URL. Agent fires on fresh content.' },
      { name: 'SlackDataChannel', desc: 'Read messages from a Slack channel. Normalises threading and attachments.' },
    ],
    code: PIPELINE_CODE,
  },
  {
    icon: '🎨',
    title: 'Multimodal — Extraction Before Reasoning',
    subtitle: 'Every input modality arrives as clean text before the agent fires. Zero tokens on parsing.',
    accent: 'pink',
    items: [
      { name: 'DoclingChannel', desc: 'PDF, Word, Excel, HTML, images → clean markdown. Layout-aware table extraction. No LLM tokens spent on file parsing.' },
      { name: 'AudioChannel', desc: 'Audio and video files → Whisper transcript. Runs locally — no API key, no data leaves the machine.' },
      { name: '_extract_file_text()', desc: 'Called automatically by ConversationGateway on every upload: text decoded, PDFs extracted, images saved to temp file, audio transcribed.' },
      { name: 'Image handling', desc: 'Uploaded or received images saved to temp files. Agent receives the path and can call analyze_image() — no base64 encoding, no multimodal API complexity.' },
      { name: 'Voice in gateways', desc: 'Telegram and WhatsApp voice messages auto-transcribed before routing to the agent. Agent always sees text, never audio bytes.' },
      { name: 'VideoChannel [roadmap]', desc: 'Frame sampling at configurable fps + Whisper transcript. Mixed video+audio+text pipelines in one input channel.' },
    ],
    code: MULTIMODAL_CODE,
  },
  {
    icon: '🧠',
    title: 'Agent Layer — Bring Your Own',
    subtitle: 'CUGA++ wraps any agent. The only contract: agent.ainvoke(message)',
    accent: 'purple',
    items: [
      { name: 'CugaAgent (recommended)', desc: 'LangGraph ReAct agent. Multimodal input (Union[str, List[Any]]). Persistent memory via cuga_checkpointer. All CUGA++ integrations work out of the box.' },
      { name: 'PluginRuntime (cuga-runtime)', desc: 'Standalone equivalent — does not require the main cuga package. Use when building from cuga++ alone.' },
      { name: 'Any .ainvoke() agent', desc: 'LangGraph, AutoGen, CrewAI, raw API wrapper. If it has .ainvoke(), it runs in CUGA++. This is also the eval contract — swap agents, same benchmark.' },
      { name: 'cuga_checkpointer', desc: 'Replaces MemorySaver. Conversation threads survive process restarts. Works across browser sessions, Telegram users, WhatsApp contacts, and phone calls.' },
      { name: 'LLM providers', desc: 'OpenAI, Anthropic, RITS (IBM), WatsonX, LiteLLM, Ollama. create_llm(provider, model) returns a LangChain-compatible chat model. One line to switch.' },
      { name: 'Long-running agents', desc: 'CugaHost production daemon manages multiple runtimes, persists configs, and restores on restart. cuga_pipelines.yaml deploys a pipeline like a service.' },
    ],
  },
  {
    icon: '📖',
    title: 'Skills — Persona via .md Files',
    subtitle: 'Change the agent\'s behaviour by swapping a markdown file. No retraining.',
    accent: 'sky',
    items: [
      { name: 'CugaSkillsPlugin', desc: 'Loads .md files from a skills/ directory as the agent\'s system prompt. One plugin, any number of skill files.' },
      { name: 'Domain expertise', desc: 'A file named analyst.md makes it a financial analyst. legal.md makes it a contract reviewer. same_agent.md, different persona.' },
      { name: 'Multi-skill composition', desc: 'Multiple .md files are concatenated into one system prompt. Layer base_persona.md + domain.md + tone.md.' },
      { name: 'Runtime swapping', desc: 'Change the skills directory and restart — no code change. Different environments (prod vs staging) can run different personas.' },
      { name: 'CugaSkillsPlugin in gateways', desc: 'Skills work identically in ConversationGateway. The same agent behaves differently on browser vs Telegram just by pointing to different skill dirs.' },
    ],
    code: SKILLS_CODE,
    codeLanguage: 'markdown',
  },
  {
    icon: '🔌',
    title: 'MCP Tool Bridge — The Ecosystem',
    subtitle: 'Every MCP-compatible server becomes CUGA++ tools with one import',
    accent: 'amber',
    items: [
      { name: 'MCPToolBridge', desc: 'Connects to any running MCP server and exposes its tools to the agent as a typed tool list. No custom tool writing.' },
      { name: 'Filesystem MCP', desc: 'Search, read, create, and update local files via natural language. Safe — the MCP server scopes access.' },
      { name: 'GitHub MCP', desc: 'Full GitHub API as tools: list PRs, create issues, get file contents, post reviews.' },
      { name: 'Notion MCP', desc: 'Read and write Notion databases, pages, and blocks. Personal knowledge base becomes agent-queryable.' },
      { name: 'Hundreds of servers', desc: 'Anthropic, Zapier, Linear, HubSpot, Stripe, and the growing community ecosystem — all work through the same bridge.' },
      { name: 'Compose with channels', desc: 'MCPToolBridge + TelegramChannel = agent that manages your files from your phone. MCPToolBridge + CronChannel = weekly Notion digest.' },
    ],
    code: MCP_CODE,
  },
  {
    icon: '🔧',
    title: 'Tool Factories',
    subtitle: 'Composable capabilities — one factory call, typed tools for the agent',
    accent: 'orange',
    items: [
      { name: 'make_web_search_tool()', desc: 'Real-time web search via Tavily. Structured results with titles, URLs, and excerpts. Requires TAVILY_API_KEY.' },
      { name: 'make_calendar_tools()', desc: 'Read and write Google Calendar. OAuth2 token refresh handled internally.' },
      { name: 'make_github_tools()', desc: 'List PRs, issues, CI runs. Create comments. Get file contents. Requires GITHUB_TOKEN.' },
      { name: 'make_shell_tools()', desc: 'Safe shell access with an allowlist. Path traversal blocked. Ideal for audit and dev tool agents.' },
      { name: 'make_market_data_tools()', desc: 'Crypto prices (CoinGecko) and stock quotes (Alpha Vantage) with graceful degradation.' },
      { name: 'make_image_generation_tool()', desc: 'DALL-E 3 image generation with URL return. Works in both gateway and pipeline contexts.' },
      { name: 'make_rag_tools()', desc: 'Semantic search and ingestion via ChromaDB. ingest_document() + search_documents(). Works without chromadb installed (graceful degradation).' },
    ],
  },
  {
    icon: '📤',
    title: 'Output Channels',
    subtitle: 'Every destination, one import',
    accent: 'cyan',
    items: [
      { name: 'EmailChannel', desc: 'SMTP delivery with MIME formatting, HTML/plain-text, and retry logic.' },
      { name: 'SlackChannel', desc: 'Slack webhook delivery. Markdown formatted.' },
      { name: 'TelegramChannel', desc: 'Send text, photos, and documents to any Telegram chat. Auto-splits at 4096 chars.' },
      { name: 'DiscordChannel', desc: 'Post to Discord channels or DMs.' },
      { name: 'SMSChannel', desc: 'Twilio SMS delivery. International numbers supported.' },
      { name: 'WhatsAppChannel', desc: 'Meta Cloud API delivery. Auto-splits at 4000 chars.' },
      { name: 'TTSChannel', desc: 'Text-to-speech: ElevenLabs → macOS say → pyttsx3. Fallback chain always works.' },
      { name: 'LogChannel', desc: 'Structured JSON logging to file or stdout. For pipelines without a human recipient.' },
    ],
  },
  {
    icon: '🏆',
    title: 'Benchmark — 100+ Production Tasks',
    subtitle: 'The first eval framework built around real-world agent pipeline reliability',
    accent: 'rose',
    items: [
      { name: 'TaskRegistry (roadmap)', desc: '100+ task specs built from the use case library. Each task: recorded input, criteria, scoring function. No live APIs needed.' },
      { name: 'MockChannelHarness (roadmap)', desc: 'Replay recorded channel inputs for reproducible evals. Same task, any agent, comparable scores.' },
      { name: 'Pluggable agents', desc: 'Swap CugaAgent for LangGraph, AutoGen, or CrewAI. Same benchmark, different scores. This is how you find your weak spots.' },
      { name: 'Multimodal benchmark tasks', desc: 'Mixed PDF + audio + image pipelines. No other benchmark tests these. The hardest tasks expose framework gaps that text-only evals miss.' },
      { name: 'Use case library = test corpus', desc: 'The 26 demo apps are not just demos — they are the benchmark. Adding a use case adds a benchmark task. The library compounds.' },
      { name: 'Public leaderboard (roadmap)', desc: 'Any team submits their agent, gets a per-category score. CUGA++ defines the reference point.' },
    ],
  },
]

const ACCENT_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  indigo:  { border: 'border-indigo-800/30',  bg: 'bg-indigo-900/5',  text: 'text-indigo-400'  },
  emerald: { border: 'border-emerald-800/30', bg: 'bg-emerald-900/5', text: 'text-emerald-400' },
  pink:    { border: 'border-pink-800/30',    bg: 'bg-pink-900/5',    text: 'text-pink-400'    },
  purple:  { border: 'border-purple-800/30',  bg: 'bg-purple-900/5',  text: 'text-purple-400'  },
  sky:     { border: 'border-sky-800/30',     bg: 'bg-sky-900/5',     text: 'text-sky-400'     },
  amber:   { border: 'border-amber-800/30',   bg: 'bg-amber-900/5',   text: 'text-amber-400'   },
  orange:  { border: 'border-orange-800/30',  bg: 'bg-orange-900/5',  text: 'text-orange-400'  },
  cyan:    { border: 'border-cyan-800/30',    bg: 'bg-cyan-900/5',    text: 'text-cyan-400'    },
  rose:    { border: 'border-rose-800/30',    bg: 'bg-rose-900/5',    text: 'text-rose-400'    },
}

export default function Features() {
  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">Feature Overview</h2>
        <p className="text-gray-400 text-sm max-w-2xl">
          Two surfaces, one runtime. Conversation Gateways for agents humans talk to.
          Automated Pipelines for agents that run themselves. Every modality handled.
          Any agent. Any LLM. Production-ready.
        </p>
      </div>

      {/* Design principle */}
      <div className="bg-indigo-900/20 border border-indigo-800/40 rounded-xl p-5 mb-8">
        <h3 className="text-sm font-semibold text-indigo-300 mb-2">The Design Principle</h3>
        <p className="text-sm text-gray-300 leading-relaxed">
          <strong className="text-white">I/O is deterministic. Reasoning is not.</strong>{' '}
          Infrastructure should never cost LLM tokens. CUGA++ enforces this architecturally —
          channels handle I/O deterministically before the agent fires. Audio arrives as transcript.
          PDFs arrive as markdown. Images arrive as file paths. The agent handles only reasoning.
        </p>
      </div>

      {/* Ecosystem map */}
      <EcosystemMap />

      {/* Feature sections */}
      <div className="space-y-10">
        {FEATURES.map((section) => {
          const ac = ACCENT_COLORS[section.accent] ?? ACCENT_COLORS.indigo
          return (
            <div key={section.title} className={`rounded-2xl border ${ac.border} ${ac.bg} p-6`}>
              <div className="flex items-start gap-3 mb-5">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xl flex-shrink-0 bg-gray-950/60">
                  {section.icon}
                </div>
                <div>
                  <h3 className={`text-base font-semibold text-white`}>{section.title}</h3>
                  <p className="text-xs text-gray-500 mt-0.5">{section.subtitle}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
                {section.items.map((item) => (
                  <div key={item.name} className="bg-gray-900/60 border border-gray-800 rounded-lg p-3.5">
                    <div className={`font-mono text-xs ${ac.text} mb-1`}>{item.name}</div>
                    <div className="text-xs text-gray-400 leading-relaxed">{item.desc}</div>
                  </div>
                ))}
              </div>

              {'code' in section && section.code && (
                <CodeBlock code={section.code} language={(section as any).codeLanguage || 'python'} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
