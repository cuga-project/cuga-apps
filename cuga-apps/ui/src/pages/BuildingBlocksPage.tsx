import { useState } from 'react'
import CodeBlock from '../components/CodeBlock'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Block {
  name: string
  badge?: string
  desc: string
  api?: string
  notes?: string[]
  envVars?: string[]
}

interface Layer {
  id: string
  title: string
  icon: string
  accent: keyof typeof ACCENT
  description: string
  groups: { label?: string; role?: string; blocks: Block[] }[]
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const ACCENT = {
  purple:  { border: 'border-purple-800/40',  bg: 'bg-purple-900/8',   text: 'text-purple-400',  badge: 'bg-purple-900/30 text-purple-300 border-purple-800/40',  dot: 'bg-purple-500',  header: 'text-purple-300' },
  indigo:  { border: 'border-indigo-800/40',  bg: 'bg-indigo-900/8',   text: 'text-indigo-400',  badge: 'bg-indigo-900/30 text-indigo-300 border-indigo-800/40',  dot: 'bg-indigo-500',  header: 'text-indigo-300' },
  sky:     { border: 'border-sky-800/40',     bg: 'bg-sky-900/8',      text: 'text-sky-400',     badge: 'bg-sky-900/30 text-sky-300 border-sky-800/40',          dot: 'bg-sky-500',     header: 'text-sky-300' },
  emerald: { border: 'border-emerald-800/40', bg: 'bg-emerald-900/8',  text: 'text-emerald-400', badge: 'bg-emerald-900/30 text-emerald-300 border-emerald-800/40', dot: 'bg-emerald-500', header: 'text-emerald-300' },
  amber:   { border: 'border-amber-800/40',   bg: 'bg-amber-900/8',    text: 'text-amber-400',   badge: 'bg-amber-900/30 text-amber-300 border-amber-800/40',    dot: 'bg-amber-500',   header: 'text-amber-300' },
  pink:    { border: 'border-pink-800/40',    bg: 'bg-pink-900/8',     text: 'text-pink-400',    badge: 'bg-pink-900/30 text-pink-300 border-pink-800/40',       dot: 'bg-pink-500',    header: 'text-pink-300' },
  cyan:    { border: 'border-cyan-800/40',    bg: 'bg-cyan-900/8',     text: 'text-cyan-400',    badge: 'bg-cyan-900/30 text-cyan-300 border-cyan-800/40',       dot: 'bg-cyan-500',    header: 'text-cyan-300' },
} as const

// ---------------------------------------------------------------------------
// Layer data
// ---------------------------------------------------------------------------

const LAYERS: Layer[] = [

  // ── 1. Reasoning ─────────────────────────────────────────────────────────
  {
    id: 'reasoning',
    title: 'Reasoning Engine',
    icon: '🧠',
    accent: 'purple',
    description: 'The LLM-backed agent that calls tools, follows skills, and produces output. Everything else in cuga++ exists to feed data into and deliver results from this layer.',
    groups: [{
      blocks: [
        {
          name: 'CugaAgent',
          desc: 'LangChain ReAct agent wired to any chat model. Accepts tools, plugins (skills), and a persistent checkpointer.',
          api: `from cuga import CugaAgent
agent = CugaAgent(
    model=create_llm(),
    tools=[web_search, ...],
    plugins=[CugaSkillsPlugin(skills_dir="./skills")],
    cuga_folder=".cuga",
)
result = await agent.invoke("summarise today's AI news")
print(result.answer)`,
          notes: [
            'Multi-turn memory via LangGraph checkpointer',
            'thread_id isolates conversations — each pipeline gets its own thread',
            'result.answer is the final plain-text or HTML response',
          ],
        },
        {
          name: 'CugaSkillsPlugin',
          desc: 'Loads .md files from a skills/ directory and injects them as the agent system prompt. The skill file IS the domain expertise.',
          api: `# skills/newsletter_curation.md
# ---
# Write a styled HTML newsletter.
# Lead with the 3 most impactful items...

plugins=[CugaSkillsPlugin(skills_dir="./skills")]`,
          notes: [
            'No code change needed to change agent behaviour — edit the .md',
            'Multiple skill files are concatenated in alphabetical order',
            'Works for both pipeline agents and planner agents',
          ],
        },
        {
          name: 'create_llm()',
          desc: 'Multi-provider LLM factory. Auto-detects provider from env vars. Returns a LangChain BaseChatModel.',
          api: `from _llm import create_llm

llm = create_llm()                          # auto-detect
llm = create_llm(provider="anthropic")
llm = create_llm(provider="rits", model="llama-3-3-70b-instruct")
llm = create_llm(provider="openai", model="gpt-4o")`,
          notes: [
            'Providers: openai · anthropic · rits · watsonx · litellm · ollama',
            'Provider selected by LLM_PROVIDER env var or first detected API key',
            'Model overridden by LLM_MODEL env var',
          ],
          envVars: ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'RITS_API_KEY', 'WATSONX_APIKEY'],
        },
      ],
    }],
  },

  // ── 2. Channels ──────────────────────────────────────────────────────────
  {
    id: 'channels',
    title: 'Channels',
    icon: '📡',
    accent: 'sky',
    description: 'Channels are the I/O primitives of cuga++. They implement one of three protocols: DataChannel (feeds buffer), TriggerChannel (wakes agent), OutputChannel (delivers results). They are composable — any combination works.',
    groups: [
      {
        label: 'DataChannel',
        role: 'Continuously collects data into a buffer. Never calls the agent directly.',
        blocks: [
          {
            name: 'RssChannel',
            badge: 'data',
            desc: 'Polls RSS/Atom feeds on an interval, filters by keywords, pushes matched items to buffer.',
            api: `RssChannel(
    sources=["https://arxiv.org/rss/cs.AI"],
    keywords=["agent", "LLM"],
    poll_minutes=15,
)`,
            envVars: [],
          },
          {
            name: 'IMAPChannel',
            badge: 'data',
            desc: 'Watches an email inbox for UNSEEN messages. Extracts plain-text bodies.',
            api: `IMAPChannel(
    host="imap.gmail.com",
    username="you@gmail.com",
    password=os.getenv("IMAP_PASSWORD"),
    folder="INBOX",
    poll_minutes=5,
)`,
            envVars: ['IMAP_PASSWORD'],
          },
          {
            name: 'SlackDataChannel',
            badge: 'data',
            desc: 'Polls a Slack channel for new messages. Filters own bot messages.',
            api: `SlackDataChannel(
    token=os.getenv("SLACK_BOT_TOKEN"),
    channel="#general",
    poll_minutes=2,
)`,
            envVars: ['SLACK_BOT_TOKEN'],
          },
          {
            name: 'TelegramDataChannel',
            badge: 'data',
            desc: 'Receives Telegram messages via long-polling (getUpdates). Supports allowlist.',
            api: `TelegramDataChannel(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    allowed_user_ids=[123456],
)`,
            envVars: ['TELEGRAM_BOT_TOKEN'],
          },
          {
            name: 'DiscordDataChannel',
            badge: 'data',
            desc: 'Polls a Discord channel for new messages via REST API.',
            api: `DiscordDataChannel(
    token=os.getenv("DISCORD_BOT_TOKEN"),
    channel_id="1234567890",
    poll_seconds=10,
)`,
            envVars: ['DISCORD_BOT_TOKEN'],
          },
          {
            name: 'DoclingChannel',
            badge: 'data',
            desc: 'Watches a folder for PDF, images, and Office docs. Extracts content with docling into clean markdown before agent fires. Agent receives text — no extraction tool needed.',
            api: `DoclingChannel(
    watch_dir="./inbox",
    extensions={".pdf", ".docx", ".png"},
    poll_minutes=1,
    move_to_processed=True,
)`,
          },
          {
            name: 'AudioChannel',
            badge: 'data',
            desc: 'Watches a folder for audio files (.mp3, .m4a, .wav). Transcribes with Whisper (local or OpenAI API). Also used in voice_journal for browser upload.',
            api: `AudioChannel(
    watch_dir="./recordings",
    model="base",  # tiny | base | small | medium | large
)

# One-shot transcription (for file upload):
transcript = await AudioChannel.transcribe(
    audio_bytes, filename="memo.m4a"
)`,
            envVars: ['OPENAI_API_KEY (fallback if local Whisper not installed)'],
          },
        ],
      },
      {
        label: 'TriggerChannel',
        role: 'Wakes the pipeline agent on a schedule or external event.',
        blocks: [
          {
            name: 'CronChannel',
            badge: 'trigger',
            desc: 'Fires the agent on a 5-field cron schedule via APScheduler. The message param is injected as the agent\'s task prompt.',
            api: `CronChannel(
    schedule="0 8 * * 1-5",  # weekdays at 8am
    message="Send the daily digest.",
)`,
          },
          {
            name: 'WebhookChannel',
            badge: 'trigger',
            desc: 'Runs a FastAPI server. Fires the agent on HTTP POST. Supports Bearer token auth. Good for CI/CD triggers and external integrations.',
            api: `WebhookChannel(
    port=18791,
    path="/webhook",
    secret_token=os.getenv("WEBHOOK_SECRET"),
    message_template="New event: {payload}",
)

# Trigger:
# curl -X POST http://localhost:18791/webhook \\
#      -H "Authorization: Bearer $TOKEN" \\
#      -d '{"event": "build_failed"}'`,
          },
        ],
      },
      {
        label: 'OutputChannel',
        role: 'Delivers the agent\'s result. The agent never decides delivery — CugaRuntime routes to all configured output channels.',
        blocks: [
          {
            name: 'EmailChannel',
            badge: 'output',
            desc: 'Sends HTML content via SMTP. subject_prefix + timestamp = subject line.',
            api: `EmailChannel(
    to="you@co.com",
    smtp_username=os.getenv("SMTP_USERNAME"),
    smtp_password=os.getenv("SMTP_PASSWORD"),
    smtp_host="smtp.gmail.com",
    subject_prefix="CUGA Digest",
)`,
            envVars: ['SMTP_USERNAME', 'SMTP_PASSWORD'],
          },
          {
            name: 'SlackChannel',
            badge: 'output',
            desc: 'Posts to Slack via incoming webhook or bot token. Auto-splits at 3000 chars.',
            api: `# Via webhook (simpler):
SlackChannel(webhook_url=os.getenv("SLACK_WEBHOOK_URL"))

# Via bot token (more flexible):
SlackChannel(
    token=os.getenv("SLACK_BOT_TOKEN"),
    channel="#alerts",
)`,
            envVars: ['SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN'],
          },
          {
            name: 'TelegramChannel',
            badge: 'output',
            desc: 'Sends messages via Telegram Bot API. Supports Markdown. Auto-splits at 4096 chars.',
            api: `TelegramChannel(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    chat_id="@mychannel",   # or numeric chat ID
    parse_mode="Markdown",
)`,
            envVars: ['TELEGRAM_BOT_TOKEN'],
          },
          {
            name: 'DiscordChannel',
            badge: 'output',
            desc: 'Posts to Discord via webhook or bot token. Auto-splits at 2000 chars.',
            api: `DiscordChannel(webhook_url=os.getenv("DISCORD_WEBHOOK_URL"))`,
            envVars: ['DISCORD_WEBHOOK_URL or DISCORD_BOT_TOKEN'],
          },
          {
            name: 'SMSChannel',
            badge: 'output',
            desc: 'Sends SMS via Twilio. Auto-splits messages > max_chars (default 160).',
            api: `SMSChannel(
    to="+15551234567",
    from_=os.getenv("TWILIO_FROM"),
    account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
    auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
)`,
            envVars: ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM'],
          },
          {
            name: 'LogChannel',
            badge: 'output',
            desc: 'Prints to stdout and optionally appends to a file. Always added as a fallback alongside any real output channel. Zero config.',
            api: `LogChannel()              # stdout only
LogChannel(path="./out.log")   # + file`,
          },
          {
            name: 'TTSChannel',
            badge: 'output',
            desc: 'Text-to-speech output. Priority: ElevenLabs → macOS say → pyttsx3 → print fallback.',
            api: `TTSChannel(
    voice="auto",
    elevenlabs_voice_id="21m00Tcm4TlvDq8ikWAM",
)`,
            envVars: ['ELEVENLABS_API_KEY (optional)'],
          },
          {
            name: 'WhatsAppChannel',
            badge: 'output',
            desc: 'Sends messages via Meta WhatsApp Cloud API. Auto-splits at 4000 chars.',
            api: `WhatsAppChannel(
    to="+15551234567",
    phone_number_id=os.getenv("WHATSAPP_PHONE_ID"),
    access_token=os.getenv("WHATSAPP_TOKEN"),
)`,
            envVars: ['WHATSAPP_PHONE_ID', 'WHATSAPP_TOKEN'],
          },
        ],
      },
    ],
  },

  // ── 3. Pipeline Orchestration ─────────────────────────────────────────────
  {
    id: 'orchestration',
    title: 'Pipeline Orchestration',
    icon: '⚙️',
    accent: 'indigo',
    description: 'The infrastructure layer that connects channels to agents, manages multiple pipelines, persists state across restarts, and exposes an HTTP control plane.',
    groups: [{
      blocks: [
        {
          name: 'CugaRuntime',
          desc: 'Orchestrates the full pipeline: DataChannels fill a buffer, TriggerChannel wakes the agent, agent produces output, OutputChannels deliver it. One runtime = one pipeline.',
          api: `runtime = CugaRuntime(
    agent=agent,
    input_channels=[
        RssChannel(sources=[...]),   # DataChannel
        CronChannel("0 8 * * *", message="Send digest."),  # TriggerChannel
    ],
    output_channels=[EmailChannel(...), LogChannel()],
    thread_id="my-pipeline",
    require_buffer=True,   # only fire when buffer has items
)
await runtime.start()   # blocks until SIGINT`,
          notes: [
            'require_buffer=False: trigger fires even when buffer is empty (agent fetches own data via tools)',
            'ChannelBuffer deduplicates items by "url" field (falls back to title+source)',
            'Multiple output channels all receive the same content',
          ],
        },
        {
          name: 'ChannelBuffer',
          desc: 'Thread-safe buffer between DataChannels and TriggerChannel. Deduplicates items, caps at max_items (default 40). Flushed after each agent invocation.',
          notes: [
            'Dedup key: item["url"] → fallback to hash of title+source',
            'Items from all DataChannels merged into one list for the agent',
            'Not user-facing — managed internally by CugaRuntime',
          ],
        },
        {
          name: 'CugaHost',
          desc: 'Daemon that manages multiple CugaRuntime instances. Exposes a REST API on port 18790. Persists runtime configs to runtimes.json and restores on restart.',
          api: `# Embedded (dev / single process):
host = CugaHost(state_dir=".cuga/host", port=18790)
host.register_factory("newsletter", my_factory)
await host.start_background()

# REST API:
# POST   /runtime          { id, factory, config }
# PUT    /runtime/{id}     update config + restart
# DELETE /runtime/{id}     stop
# GET    /runtime          list all
# POST   /runtime/{id}/invoke  one-shot agent call`,
          notes: [
            'Generic — knows nothing about RSS, newsletters, or todos',
            'Apps register RuntimeFactories; host calls them with config dict',
            'connect_or_embed() reuses an existing host process or embeds a new one',
          ],
        },
        {
          name: 'CugaHostClient',
          desc: 'HTTP client to CugaHost. Same API whether the host is embedded in-process or running as a daemon.',
          api: `host, client = await CugaHostClient.connect_or_embed(
    state_dir=".cuga/host",
    pipelines_config="cuga_pipelines.yaml",
)

await client.start_runtime("my-pipeline", "newsletter", config)
await client.update_runtime("my-pipeline", "newsletter", new_config)
await client.stop_runtime("my-pipeline")
runtimes = await client.list_runtimes()`,
        },
        {
          name: 'RuntimeFactory',
          desc: 'Declarative builder that converts a spec dict into a CugaRuntime factory callable. The factory is registered with CugaHost and called on every start/restart.',
          api: `RuntimeFactory.declare(
    agent_fn=lambda config: make_agent(),
    message="Good morning! Send the digest.",
    thread_id="my-digest",
    trigger=CronChannel.from_config,
    data=[RssChannel.from_config],
    output=EmailChannel.from_config,
    subject_prefix="My Digest",
    require_buffer=True,
)`,
          notes: [
            'trigger: (config, message) → TriggerChannel',
            'data: list of (config) → DataChannel callables',
            'output: (config, subject_prefix) → OutputChannel | None',
          ],
        },
      ],
    }],
  },

  // ── 4. Agent Tools ───────────────────────────────────────────────────────
  {
    id: 'tools',
    title: 'Agent Tool Factories',
    icon: '🔧',
    accent: 'emerald',
    description: 'On-demand capabilities given to agents. Each factory returns one or more LangChain @tool functions. Tools are used when the agent needs to fetch its own data (no DataChannel) or act on something in the world.',
    groups: [{
      blocks: [
        {
          name: 'make_web_search_tool()',
          desc: 'Tavily web search. Real-time results, optional answer synthesis. Use for news monitoring, topic research, current events.',
          api: `tools = [make_web_search_tool(max_results=5)]
# → web_search(query: str) -> str`,
          envVars: ['TAVILY_API_KEY'],
        },
        {
          name: 'make_calendar_tools()',
          desc: 'Google Calendar read and write. Two tools: get upcoming events, create an event.',
          api: `tools = make_calendar_tools(calendar_id="primary")
# → get_upcoming_events(days: int) -> str
# → create_calendar_event(title, date, ...) -> str`,
          envVars: ['GOOGLE_CALENDAR_ACCESS_TOKEN'],
        },
        {
          name: 'make_github_tools()',
          desc: 'GitHub REST API wrapper. Five tools covering PRs, issues, workflow runs, and comments.',
          api: `tools = make_github_tools(
    token=os.getenv("GITHUB_TOKEN"),
    default_repo="anthropics/claude-code",
)
# → list_pull_requests, get_pull_request,
#   list_issues, get_workflow_runs,
#   create_issue_comment`,
          envVars: ['GITHUB_TOKEN'],
        },
        {
          name: 'make_market_data_tools()',
          desc: 'Crypto prices via CoinGecko (free, no key) and stock quotes via Alpha Vantage.',
          api: `tools = make_market_data_tools()
# → get_crypto_price(symbol="BTC", vs_currency="usd")
# → get_stock_quote(symbol="AAPL")`,
          envVars: ['ALPHA_VANTAGE_API_KEY (stocks only)'],
        },
        {
          name: 'make_image_generation_tool()',
          desc: 'DALL-E image generation. Returns a URL or base64 image.',
          api: `tools = make_image_generation_tool()
# → generate_image(prompt, size="1024x1024", quality="standard")`,
          envVars: ['OPENAI_API_KEY'],
        },
        {
          name: 'make_rag_tools()',
          desc: 'Local ChromaDB vector database. Two tools: ingest a document, search by semantic query.',
          api: `tools = make_rag_tools(
    collection_name="docs",
    persist_dir="./chroma_db",
)
# → ingest_document(text, source, metadata)
# → search_documents(query, n_results=5)`,
        },
        {
          name: 'make_shell_tools()',
          desc: 'Safe, allowlisted shell commands. Blocks pipes and metacharacters. Used in server_monitor and dev_tools.',
          api: `tools = make_shell_tools()
# → run_shell_command(command)   # df, du, ps, git, pip, npm...
# → check_python_dependencies()
# → run_test_coverage()`,
          notes: ['Allowlist: df, du, uptime, free, ps, netstat, pip, npm, git, cat, ls, iostat, vmstat, coverage, pytest'],
        },
      ],
    }],
  },

  // ── 5. Front Doors ───────────────────────────────────────────────────────
  {
    id: 'frontdoors',
    title: 'Front Doors',
    icon: '🚪',
    accent: 'amber',
    description: 'How agents are exposed to users and external systems. Each front door is a different triggering model: interactive, reactive, or scheduled.',
    groups: [{
      blocks: [
        {
          name: 'ConversationGateway',
          desc: 'Browser chat UI over WebSocket. The user-facing front door for interactive apps. Supports file upload (audio → Whisper, PDF → pypdf, text → decode).',
          api: `gateway = ConversationGateway(agent=agent)
gateway.add_browser_adapter(host="127.0.0.1", port=8765, title="My App")
await gateway.start()   # serves at http://127.0.0.1:8765`,
          notes: [
            'File upload: audio transcribed with Whisper, PDF extracted with pypdf',
            'File content prepended to the next chat message',
            'Shares the same agent instance as background pipelines',
          ],
        },
        {
          name: 'CugaWatcher',
          desc: 'Reactive polling loop. @source decorator collects data on a schedule. @on decorator fires handlers with optional predicates and cooldowns.',
          api: `watcher = CugaWatcher(agent=agent)

@watcher.source(every_minutes=1)
async def collect_metrics():
    m = get_system_metrics()
    return None if m["severity"] == "ok" else m

@watcher.on(collect_metrics, when=lambda m: m["severity"] == "warning",
            cooldown_seconds=900)
async def handle_warning(metrics):
    await agent.invoke(f"CPU at {metrics['cpu']}%...")

await watcher.start()`,
          notes: [
            'Sources returning None are silently dropped — no agent call, no cost',
            'Multiple @on handlers can watch the same source with different predicates',
            'Cooldown prevents alert spam during sustained high-CPU periods',
          ],
        },
        {
          name: 'CugaMonitorApp',
          desc: 'Convenience wrapper that combines CugaWatcher + CugaHost + ConversationGateway into a single object. Used in server_monitor.',
          api: `app = CugaMonitorApp(
    agent=agent,
    watcher_factory=make_watcher,
    pipelines_config="cuga_pipelines.yaml",
    state_dir=".cuga/host",
    chat_port=8767,
    title="Server Monitor",
)
await app.run(
    enable_chat=True,
    enable_briefing=True,
)`,
        },
        {
          name: 'ChannelPlanner',
          desc: 'NL → structured config bridge. Builds a CugaAgent from PlannerTool specs, invokes it with the user\'s message, and returns a PlannerResult with captured config.',
          api: `planner = ChannelPlanner.from_schema(
    llm=create_llm(),
    tools=[
        PlannerTool("configure_monitor", "Start monitoring", params={
            "digest_minutes": (int, 240, "How often to digest"),
            "email":          (str, None, "Delivery email"),
        }),
        PlannerTool("stop_monitor", "Stop the monitor"),
    ],
)

pr = await planner.invoke("watch arxiv hourly, email me@co.com")
# pr.config == {"digest_minutes": 60, "email": "me@co.com"}
# pr.answer == "Monitor started — digesting every hour..."`,
          notes: [
            'Auto-generates system prompt from PlannerTool specs — no manual prompt writing',
            'First configure_* tool call wins → pr.config',
            'Non-configure tools set pr.action (e.g. "stop_monitor", "get_status")',
          ],
        },
      ],
    }],
  },

  // ── 6. Universal Planner ─────────────────────────────────────────────────
  {
    id: 'universal',
    title: 'Universal Planner Pattern',
    icon: '🌐',
    accent: 'cyan',
    description: 'A higher-order pattern that composes the building blocks above into a single entry point. The developer ships a registry and factory builder; the user\'s chat message assembles the pipeline.',
    groups: [{
      blocks: [
        {
          name: 'registry.py',
          desc: 'Static manifest of every channel type and tool available. Describes params, env vars, and use cases. The planner reads this to know what\'s available.',
          api: `CHANNEL_REGISTRY = {
    "rss": ChannelSpec(role="data",
        description="Poll RSS feeds, filter by keywords",
        params={"rss_sources": (list, None, "Feed URLs"), ...}),
    "email": ChannelSpec(role="output",
        description="Send via SMTP",
        params={"output_target": (str, "", "Recipient")}),
    ...
}
TOOL_REGISTRY = {
    "web_search": ToolSpec(env_vars=["TAVILY_API_KEY"]),
    ...
}`,
        },
        {
          name: 'build_factory(spec)',
          desc: 'Takes a pipeline spec dict and returns a factory callable. Wires any combination of DataChannel + CronChannel + OutputChannel from the spec.',
          api: `spec = {
    "pipeline_id": "arxiv-monitor",
    "data_type": "rss",
    "rss_sources": ["https://arxiv.org/rss/cs.AI"],
    "trigger_schedule": "0 8 * * *",
    "output_type": "email",
    "output_target": "me@co.com",
    "tool_names": [],
}
factory = build_factory(spec)
host.register_factory("arxiv-monitor", factory)
await client.start_runtime("arxiv-monitor", "arxiv-monitor", spec)`,
        },
        {
          name: 'create_pipeline (tool)',
          desc: 'LangChain @tool that the planner agent calls. Closes over host and client. Builds the spec, registers the factory, starts the runtime in one step.',
          api: `# User: "Monitor arxiv for AI papers, email me@co.com every morning"
#
# Planner calls:
create_pipeline(
    description="Monitor arxiv for AI papers",
    data_type="rss",
    rss_sources=["https://arxiv.org/rss/cs.AI"],
    trigger_schedule="0 8 * * *",
    output_type="email",
    output_target="me@co.com",
)
# → host.register_factory("monitor-arxiv...", build_factory(spec))
# → client.start_runtime("monitor-arxiv...", ...)`,
        },
      ],
    }],
  },
]

// ---------------------------------------------------------------------------
// Role badge helper
// ---------------------------------------------------------------------------

const ROLE_COLORS: Record<string, string> = {
  data:    'bg-sky-900/40 text-sky-300 border border-sky-800/40',
  trigger: 'bg-amber-900/40 text-amber-300 border border-amber-800/40',
  output:  'bg-emerald-900/40 text-emerald-300 border border-emerald-800/40',
}

// ---------------------------------------------------------------------------
// Stack overview
// ---------------------------------------------------------------------------

const STACK_LAYERS = [
  { label: 'Front Doors',           items: ['ConversationGateway', 'CugaWatcher', 'WebhookChannel', 'ChannelPlanner'],   color: 'text-amber-400',   bg: 'bg-amber-900/10 border-amber-800/30' },
  { label: 'Pipeline Orchestration', items: ['CugaHost', 'CugaHostClient', 'CugaRuntime', 'RuntimeFactory'],              color: 'text-indigo-400',  bg: 'bg-indigo-900/10 border-indigo-800/30' },
  { label: 'Channels',              items: ['RssChannel', 'CronChannel', 'EmailChannel', 'SlackChannel', '+ 10 more'],    color: 'text-sky-400',     bg: 'bg-sky-900/10 border-sky-800/30' },
  { label: 'Agent Tool Factories',  items: ['web_search', 'github', 'calendar', 'market_data', 'rag', 'shell'],           color: 'text-emerald-400', bg: 'bg-emerald-900/10 border-emerald-800/30' },
  { label: 'Reasoning Engine',      items: ['CugaAgent', 'CugaSkillsPlugin', 'create_llm()'],                             color: 'text-purple-400',  bg: 'bg-purple-900/10 border-purple-800/30' },
]

// ---------------------------------------------------------------------------
// Block card
// ---------------------------------------------------------------------------

function BlockCard({ block, accentText, accentBg, accentBorder }: {
  block: Block
  accentText: string
  accentBg: string
  accentBorder: string
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className={`rounded-xl border ${accentBorder} ${accentBg} overflow-hidden`}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full text-left px-4 py-3.5 flex items-start gap-3 hover:bg-white/5 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-mono text-sm font-semibold ${accentText}`}>{block.name}</span>
            {block.badge && (
              <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${ROLE_COLORS[block.badge] || ''}`}>
                {block.badge}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-1 leading-relaxed">{block.desc}</p>
        </div>
        <span className="text-gray-500 text-xs mt-1 flex-shrink-0">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-gray-800/60 px-4 py-4 space-y-3">
          {block.api && <CodeBlock code={block.api} language="python" />}
          {block.notes && block.notes.length > 0 && (
            <ul className="space-y-1">
              {block.notes.map((n) => (
                <li key={n} className="flex items-start gap-2 text-xs text-gray-400">
                  <span className="text-gray-600 mt-0.5 flex-shrink-0">—</span>
                  {n}
                </li>
              ))}
            </ul>
          )}
          {block.envVars && block.envVars.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {block.envVars.map((v) => (
                <span key={v} className="font-mono text-xs bg-gray-900 border border-gray-700 text-gray-400 px-2 py-0.5 rounded">
                  {v}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BuildingBlocksPage() {
  const [activeLayer, setActiveLayer] = useState<string | null>(null)

  const visibleLayers = activeLayer
    ? LAYERS.filter((l) => l.id === activeLayer)
    : LAYERS

  return (
    <div className="p-6 max-w-5xl mx-auto">

      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">Building Blocks</h2>
        <p className="text-gray-400 text-sm max-w-3xl leading-relaxed">
          Every piece of the cuga++ framework, organised by layer. Click any block to see its
          API, key notes, and required env vars. Each block is independently usable — compose
          only what your app needs.
        </p>
      </div>

      {/* Stack overview */}
      <div className="mb-8">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Stack overview</div>
        <div className="space-y-1.5">
          {STACK_LAYERS.map((sl) => (
            <div
              key={sl.label}
              className={`rounded-lg border px-4 py-2.5 flex items-center gap-4 ${sl.bg}`}
            >
              <span className={`text-xs font-semibold w-44 flex-shrink-0 ${sl.color}`}>{sl.label}</span>
              <div className="flex flex-wrap gap-1.5">
                {sl.items.map((item) => (
                  <span key={item} className="font-mono text-xs text-gray-400 bg-gray-900/60 border border-gray-800 rounded px-2 py-0.5">
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Layer filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={() => setActiveLayer(null)}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
            activeLayer === null
              ? 'bg-gray-700 border-gray-600 text-white'
              : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-700'
          }`}
        >
          All layers
        </button>
        {LAYERS.map((layer) => {
          const ac = ACCENT[layer.accent]
          const isActive = activeLayer === layer.id
          return (
            <button
              key={layer.id}
              onClick={() => setActiveLayer(isActive ? null : layer.id)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
                isActive
                  ? `${ac.badge}`
                  : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-700'
              }`}
            >
              <span>{layer.icon}</span>
              {layer.title}
            </button>
          )
        })}
      </div>

      {/* Layers */}
      <div className="space-y-10">
        {visibleLayers.map((layer) => {
          const ac = ACCENT[layer.accent]
          return (
            <div key={layer.id}>
              {/* Layer header */}
              <div className={`flex items-center gap-3 mb-4 pb-3 border-b ${ac.border}`}>
                <span className="text-2xl">{layer.icon}</span>
                <div>
                  <h3 className={`text-base font-semibold ${ac.header}`}>{layer.title}</h3>
                  <p className="text-xs text-gray-500 mt-0.5 max-w-2xl leading-relaxed">{layer.description}</p>
                </div>
              </div>

              {/* Groups */}
              <div className="space-y-6">
                {layer.groups.map((group, gi) => (
                  <div key={gi}>
                    {group.label && (
                      <div className="flex items-center gap-3 mb-3">
                        <span className={`text-xs font-semibold uppercase tracking-wider ${ac.text}`}>{group.label}</span>
                        {group.role && (
                          <span className="text-xs text-gray-500">{group.role}</span>
                        )}
                      </div>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {group.blocks.map((block) => (
                        <BlockCard
                          key={block.name}
                          block={block}
                          accentText={ac.text}
                          accentBg={ac.bg}
                          accentBorder={ac.border}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

    </div>
  )
}
