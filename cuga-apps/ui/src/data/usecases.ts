export type Status = 'working' | 'partial' | 'not-working' | 'gap'
export type Category = 'personal' | 'enterprise'

export type Surface = 'gateway' | 'pipeline'

/**
 * event-driven          — triggered by time, RSS, file drops, or other events; runs in the background.
 * document-intelligence — extracts and reasons over documents (PDF, DOCX, slides, etc.) or images.
 * audio-video           — transcribes/processes audio or video.
 * other                 — on-demand conversational/interactive apps.
 */
export type UseCaseType = 'event-driven' | 'document-intelligence' | 'audio-video' | 'other'

/** MCP server usage — which tools an app consumes from each shared server. */
export interface McpServerUsage {
  /** mcp-server name (matches keys in apps/_ports.MCP_PORTS) */
  server: 'web' | 'knowledge' | 'geo' | 'finance' | 'code' | 'local' | 'text' | 'invocable_apis'
  /** tools from that server the app actually uses */
  tools: string[]
}

export interface UseCase {
  id: string
  name: string
  tagline: string
  description: string
  category: Category
  status: Status
  type: UseCaseType
  /**
   * 'gateway'  — a human talks to the agent in real-time (browser, Telegram, WhatsApp, phone).
   * 'pipeline' — the agent runs automatically on a schedule or system event (cron, webhook, folder).
   */
  surface: Surface
  /** Which channels power this demo */
  channels: string[]
  /** Which tool factories are used */
  tools: string[]
  /**
   * MCP servers + tools consumed by this app. Populated per the post-stage-3
   * wiring; `undefined` means "not yet wired or no MCP usage".
   */
  mcpUsage?: McpServerUsage[]
  /** Inline `@tool` defs kept local (app-state, vendor auth, etc.) */
  inlineTools?: string[]
  /** Path relative to repo root */
  demoPath: string | null
  /** Runnable command (copy-pasteable) */
  howToRun: {
    setup: string[]
    command: string
    envVars: string[]
  }
  /** High-level architecture description */
  architecture: string
  /** ASCII/text diagram of the pipeline */
  diagram: string
  /** What CUGA specifically contributes */
  cugaContribution: string[]
  /** Future: URL of the live app (empty until implemented) */
  appUrl: string | null
  /** If true, show "Coming soon" badge instead of a launch button */
  comingSoon?: boolean
  /** If true, hide from the umbrella UI entirely */
  hidden?: boolean
  /** Copy-pasteable examples — chat messages for web UI apps, commands for CLI apps */
  examples?: string[]
}

export const USE_CASES: UseCase[] = [
  // ── TRY IT NOW ────────────────────────────────────────────────────────────
  {
    id: 'stock-alert',
    name: 'Stock & Crypto Alert',
    tagline: 'Ask market questions or set a threshold alert — browser UI, browser-only notifications',
    description:
      'A browser UI with two panels. Market Query: type any symbol and ask a free-form question — the agent fetches live data and answers with prices and % changes highlighted. Price Watch: add a watch (symbol, threshold, above/below); the browser polls every 5 minutes and triggered alerts surface in the Recent Alerts panel at the bottom of the page (in-UI, no browser notifications, no email). Watches, alert history, and the Alpha Vantage API key all live entirely in the user\'s own browser (localStorage). The key is sent on each request and forwarded to mcp-finance as a tool argument, then scrubbed from the agent\'s reply before returning — never persisted on the server. Different browsers see only their own watches and use their own Alpha Vantage quotas. Crypto via CoinGecko (no key needed); stocks via Alpha Vantage (per-user key).',
    category: 'personal',
    type: 'event-driven',
    surface: 'pipeline',
    status: 'working',
    channels: [],
    tools: ['get_crypto_price()', 'get_stock_quote()'],
    demoPath: 'apps/stock_alert',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ALPHA_VANTAGE_API_KEY'],
      setup: [
        'cd apps/stock_alert',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. Server is stateless w.r.t. watches — only two endpoints touch the agent: POST /ask (free-form market query) and POST /check (one threshold check for a single symbol). Each request opens a fresh agent thread (uuid-suffixed) so concurrent users do not share conversation state. Watches, alert history, and notification permission live in browser localStorage; a setInterval loop in the page polls /check every 5 min for each watch and calls Notification API on triggers. Per-user isolation is automatic — every browser is its own world.',
    diagram: `python main.py  →  http://127.0.0.1:28801

Panel 1 — Market Query (on-demand):
User: "What is the current price and 24h change?"
Symbol: BTC  Type: Crypto
      │  POST /ask  (stateless — fresh agent thread per call)
      ▼
CugaAgent + finance MCP
      │  get_crypto_price("BTC")   ← CoinGecko public API
      ▼
"BTC is $84,230 (+2.3% in 24h)…"

Panel 2 — Price Watch (browser-driven, per-user):
Browser: addWatch(BTC, above, $90,000) → localStorage
      │  setInterval(5 min)
      │  POST /check { symbol, threshold, direction }
      ▼
CugaAgent + finance MCP
      │  agent.invoke("Check BTC price. Alert threshold: $90,000 (above).")
      ▼
{ triggered: true, message: "PRICE ALERT — BTC crossed $90,000" }
      │
      ▼
new Notification("Stock Alert — BTC", { body: ... })
      + appended to localStorage alerts log (capped at 50)`,
    cugaContribution: [
      'finance MCP wraps CoinGecko and Alpha Vantage — agent gets live prices, volume, and market cap without any HTTP code',
      'CugaAgent + inlined synthesis prompt defines the "PRICE ALERT" sentinel; the server parses one substring and the browser does the rest — no LLM-side delivery logic',
      'Stateless server: every /ask and /check opens a uuid-suffixed thread so concurrent users never share conversation history. No per-user backend identity needed',
      'Per-user isolation by construction — watches and alert history live in browser localStorage, so a second user on a second browser sees only their own watches without an account system',
      'Browser Notification API + 30-min cooldown per watch — matches the "alert me when crossed" semantics without spamming every poll cycle while a price stays past threshold',
    ],
    examples: [
      'What is the current price and 24h change?',
      'Is this a good entry point compared to recent range?',
      'Compare BTC and ETH — which is performing better today?',
      'Give me a quick bull or bear read on SOL right now.',
      'Add Watch: BTC above $90,000 — fires a browser notification when crossed',
      'Add Watch: AAPL below $180',
    ],
    appUrl: 'http://localhost:28801',
    mcpUsage: [
      { server: 'finance', tools: ['get_crypto_price', 'get_stock_quote'] },
    ],
    inlineTools: [],
  },
  {
    id: 'server-monitor',
    name: 'Server Monitor',
    tagline: 'Real-time server health gauges, chat diagnostics, and threshold alerts',
    type: 'event-driven',
    description:
      'A browser UI with four panels: Live Metrics (CPU/RAM/Disk/load gauges, colour-coded, auto-refreshed every 15s), Chat (ask the DevOps agent anything about system health), Alert Log (background asyncio monitor logs threshold breaches with full diagnoses), and Alert Settings (configure poll interval, cooldown, and thresholds — persisted to .store.json). No CugaHost, no channels — just CugaAgent + psutil + FastAPI.',
    category: 'enterprise',
    surface: 'pipeline',
    status: 'working',
    channels: [],
    tools: ['get_system_metrics()', 'list_top_processes()', 'check_disk_usage()', 'find_large_files()', 'get_service_status()', 'run_safe_command()'],
    demoPath: 'apps/server_monitor',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL'],
      setup: [
        'cd apps/server_monitor',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. Chat: POST /ask → CugaAgent.invoke(question) → psutil-based tools → diagnosis. Background monitor: asyncio loop polls metrics every N seconds; when a threshold is breached and cooldown has elapsed, the agent diagnoses and appends to the Alert Log. Thresholds, poll interval, and cooldown are configurable in the UI and persisted to .store.json.',
    diagram: `python main.py  →  http://127.0.0.1:8767

Live Metrics panel (auto-refresh every 15s):
  CPU 45% ██████░░░░  RAM 61% ████████░░  Disk 72% █████████░

Chat panel (on-demand):
User: "What's eating my disk?"
      │  POST /ask
      ▼
CugaAgent + check_disk_usage() + find_large_files()
      │  check_disk_usage("/")
      │  find_large_files("/", min_mb=500)
      ▼
"/var/log is 12 GB (47% of disk). Largest file: app.log 8.2 GB"

Alert Log (background asyncio loop):
asyncio loop (every 60s)
      │  get_system_metrics() → CPU 92% > critical threshold
      ▼
CugaAgent ("CPU critical: 92%. Diagnose and recommend action.")
      │  list_top_processes(sort_by="cpu")
      ▼
Alert entry: "python train.py consuming 88% CPU since 14:02"`,
    cugaContribution: [
      'CugaAgent + skills/server_health.md — the skill defines severity levels, report format, and safety rules (never rm, never kill PIDs)',
      'run_safe_command() enforces an allowlist (df, du, uptime, ps, netstat, …) — agent gets shell access without arbitrary execution risk',
      'Background asyncio monitor replaces a separate cron daemon — threshold polling and cooldown logic are self-contained in main.py',
      'All settings configurable from the UI without restart — thresholds, poll interval, and cooldown persist to .store.json',
    ],
    examples: [
      "What's the current server health?",
      "What's using the most CPU right now?",
      "What's eating my disk?",
      "Why is the server slow?",
      "Is nginx running?",
      "Find files larger than 500MB",
      "Give me a full health briefing",
    ],
    appUrl: 'http://localhost:28767',
    mcpUsage: [
      { server: 'local', tools: ['get_system_metrics_with_alerts'] },
    ],
    inlineTools: ['list_top_processes', 'check_disk_usage', 'find_large_files', 'get_service_status', 'run_safe_command'],
  },

  {
    id: 'newsletter',
    name: 'Newsletter Intelligence',
    tagline: 'Monitor RSS feeds, ask questions over live articles, set keyword alerts — in-UI panel, no email',
    type: 'event-driven',
    surface: 'pipeline',
    description:
      'A browser UI with two panels. Feed Query: ask any question over your configured RSS feeds — the agent fetches live articles and answers in plain language. Scheduled Alerts: configure keyword monitors that run hourly or daily; the agent searches your feeds and matches surface in the Recent Alerts panel at the bottom of the page (no email). Feed list and alert rules persist in .store.json across restarts; the alerts log is in-memory and refreshed every 30s by the browser.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['fetch_feed()', 'search_feeds()'],
    demoPath: 'apps/newsletter',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL'],
      setup: [
        'cd apps/newsletter',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI web server serves the single-page UI. Feed Query: POST /ask → CugaAgent.invoke(question) → make_feed_tools() fetches and parses RSS/Atom feeds → answer. Scheduled Alerts: asyncio background scheduler checks each alert on its cron interval → agent searches feeds for keyword matches → triggered alerts surface in the in-UI Recent Alerts panel. All state saved to .store.json.',
    diagram: `python main.py  →  http://127.0.0.1:18793

Panel 1 — Feed Query (on-demand):
User: "Find anything about agentic AI this week"
      │  POST /ask
      ▼
CugaAgent + make_feed_tools()
      │  fetch_feed("https://arxiv.org/rss/cs.AI")
      │  search_feeds(keywords="agentic AI")
      ▼
"Found 3 matching articles: …"

Panel 2 — Scheduled Alerts (background scheduler):
Alert: keywords="LLM release"  schedule=hourly
      │  asyncio scheduler fires
      ▼
agent.invoke("Check feeds for: LLM release …")
      │  "ALERT: Found 2 matches …"
      ▼
Recent Alerts panel (in-UI, refreshed every 30s)`,
    cugaContribution: [
      'make_feed_tools() wraps feedparser — agent gets structured article lists (title, URL, summary, published) without any HTTP or XML code',
      'CugaAgent + skills/newsletter.md — the skill file defines search format and alert rules; swap to change behaviour',
      'Persistent state — .store.json restores feeds and alert schedules on restart',
      'Alerts surface in-UI — no SMTP setup, no app passwords; the page polls and renders matches as they arrive',
    ],
    examples: [
      'Summarize the latest AI research papers from my feeds',
      'Find anything about agentic AI or multi-agent systems',
      'What new LLM releases happened this week?',
      'What are the key AI trends from my feeds today?',
      'Add alert: keywords="agent frameworks", schedule=daily',
    ],
    appUrl: 'http://localhost:28793',
    mcpUsage: [
      { server: 'web', tools: ['fetch_feed', 'search_feeds'] },
    ],
    inlineTools: [],
  },

  {
    id: 'video-qa',
    name: 'Video Q&A',
    tagline: 'Transcribe a video, then ask questions with exact timestamps',
    type: 'audio-video',
    surface: 'pipeline',
    description:
      'Load a video or audio file and ask questions about it in natural language. faster-whisper transcribes locally (cached on disk after the first run), sentence-transformers embeds each segment into ChromaDB, and CugaAgent answers with bold timestamps. Runs as a CLI REPL or a browser UI with a searchable transcript panel.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['transcribe_audio()', 'search_transcript()', 'get_segment_at_time()'],
    demoPath: 'apps/video_qa',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL'],
      setup: [
        'cd apps/video_qa',
        'pip install -r requirements.txt',
        'brew install ffmpeg',
      ],
      command: 'python run.py --web',
    },
    architecture:
      'Two phases: Phase 1 (Python only) — ffmpeg extracts audio, faster-whisper transcribes to timestamped segments, sentence-transformers embeds, ChromaDB stores on disk. Phase 2 (CugaAgent) — user question → search_transcript() cosine similarity → get_segment_at_time() timestamp lookup → answer with citations. The LLM only handles retrieval and reasoning.',
    diagram: `Phase 1 — Transcription (Python, no LLM, cached)
meeting.mp4
      │  ffmpeg extract audio
      ▼
faster-whisper → [{start, end, text}, ...]
      │  sentence-transformers embed
      ▼
ChromaDB (disk cache)

Phase 2 — Q&A (CugaAgent)
User: "Where was M3 discussed?"
      │
      ▼
CugaAgent (guided by skills/video_qa.md)
      ├─ search_transcript("M3")      ← ChromaDB cosine similarity
      └─ get_segment_at_time(600)     ← timestamp lookup
            │
            ▼
"M3 was introduced at **00:04** and benchmarks covered at **10:02–11:45**"`,
    cugaContribution: [
      'CugaAgent + skills/video_qa.md — the skill file defines tool usage, timestamp format, and citation rules; swap it to change behaviour without touching agent code',
      'Two-phase architecture — transcription is deterministic Python (zero LLM tokens); the LLM only reasons over search results',
      'Transcript cached on disk — re-running the app on the same file skips transcription entirely',
      'Browser UI (python run.py --web) adds a filterable transcript panel; clicking a segment pre-fills the question box',
    ],
    examples: [
      'python run.py meeting.mp4',
      'python run.py meeting.mp4 --ask "where was M3 discussed?"',
      'python run.py --web',
      'Where was the Q2 budget discussed?',
      'What decisions were made?',
      'What was said around the 30-minute mark?',
      'Summarise the key action items',
    ],
    appUrl: 'http://localhost:28766',
    mcpUsage: [],
    inlineTools: ['transcribe_audio', 'search_transcript', 'get_segment_at_time'],
  },

  {
    id: 'drop-summarizer',
    name: 'Drop Summarizer',
    tagline: 'Upload any file — get a plain-English summary instantly, in-UI feed only',
    type: 'document-intelligence',
    surface: 'gateway',
    description:
      'A browser UI with an upload panel and a summary feed. Upload any .txt, .md, .pdf, or image file via the browser — the app extracts text (docling in a subprocess for PDF/images; plain read for TXT/MD), passes it to the agent for summarisation, and the result appears in the feed within seconds. Click any file to ask follow-up questions over the stored content. No folder watcher, no email — every summary is the result of an active upload, and the feed itself is the alerts surface. Summaries stored in SQLite.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: [],
    demoPath: 'apps/drop_summarizer',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL'],
      setup: [
        'cd apps/drop_summarizer',
        'pip install -r requirements.txt',
        'pip install docling  # optional: for PDF and image support',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. Upload: user drops a file via the browser; the app extracts text (.txt/.md read directly; .pdf/images via docling running in a subprocess so OOM kills do not crash the server), then passes the content to the agent for summarisation. App stores content + summary in SQLite. Chat: POST /ask → for specific files, the stored content is injected into the prompt; for general queries, recent summaries are injected as context.',
    diagram: `python main.py  →  http://127.0.0.1:18794

User uploads ./inbox/report.pdf via the browser
      │
      ▼
App extracts text
      │  .txt/.md → read directly
      │  .pdf/image → docling subprocess
      ▼
CugaAgent (content injected): summarise → summary
      │
      ▼
SQLite: store { filename, summary, full_content }
      │
      ▼
UI: summary card appears in feed

Chat panel (click any file to focus):
User: "What were the key risks in this report?"
      │  POST /ask  (file content injected into prompt)
      ▼
CugaAgent → answer`,
    cugaContribution: [
      'Docling extraction runs in a subprocess — large/complex PDFs cannot OOM-kill the server',
      'Agent only sees clean extracted text — no token waste on tool plumbing or HTML noise',
      'Background asyncio watcher replaces inotify/polling boilerplate — file arrives, summary appears automatically',
      'Persistent SQLite store — summaries and full content survive restarts; click any past file to resume Q&A',
    ],
    examples: [
      'cp ~/Downloads/q1_report.pdf ./inbox/',
      'cp ~/Downloads/meeting_notes.md ./inbox/',
      'cp ~/Downloads/research_paper.pdf ./inbox/',
      'What were the key risks in this report?',
      'Summarise the action items from the meeting notes',
      'What is the main conclusion?',
    ],
    appUrl: 'http://localhost:28794',
    mcpUsage: [
      { server: 'text', tools: ['extract_text'] },
    ],
    inlineTools: [],
  },

  {
    id: 'web-researcher',
    name: 'Web Researcher',
    tagline: 'Schedule recurring web research — results land in the in-UI Research Log',
    type: 'event-driven',
    surface: 'pipeline',
    description:
      'A browser UI for scheduling recurring web research tasks. Add topics with hourly / daily / weekly cadences — the background scheduler runs overdue topics every 5 minutes using Tavily and appends results to the Research Log panel (no email). Also supports ad-hoc searches via the chat panel. Research history persists across restarts in SQLite; the UI auto-refreshes every 30s so scheduled completions surface without a manual reload.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['web_search()'],
    demoPath: 'apps/web_researcher',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/web_researcher',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. Chat: POST /ask → CugaAgent calls web_search (Tavily) → answer. Scheduled topics: asyncio background scheduler checks every 5 minutes for overdue topics; when due, runs the agent and appends results to the in-UI Research Log (no email). Topic schedule persisted in .store.json.',
    diagram: `python main.py  →  http://127.0.0.1:18798

Chat panel (ad-hoc):
User: "What's the latest news on quantum computing?"
      │  POST /ask
      ▼
CugaAgent + web_search()
      │  web_search("quantum computing news 2026")
      ▼
"IBM announced a 1000-qubit processor..."

Scheduled topics panel:
Topic: "AI agent frameworks"  Schedule: daily
      │  asyncio scheduler fires (every 5 min — checks overdue)
      ▼
CugaAgent + web_search()
      │  web_search("AI agent frameworks 2026")
      ▼
SQLite: log result in research.db
      │
      ▼
Research Log panel (in-UI, auto-refreshed every 30s)`,
    cugaContribution: [
      'CugaAgent synthesises multiple Tavily search results into a structured report — not just a list of links',
      'Background scheduler checks overdue topics every 5 minutes without a cron daemon or external task runner',
      'Persistent log in SQLite — all research results survive restarts and are viewable in the history panel',
      'Results surface in-UI — no SMTP setup, no app passwords; the Research Log auto-refreshes',
    ],
    examples: [
      "What's the latest news on quantum computing?",
      'Search for Python 3.13 release notes',
      'Find recent papers on RAG architectures',
      'What are the top stories about climate policy this week?',
      'Add topic: "AI agent frameworks" → daily',
    ],
    appUrl: 'http://localhost:28798',
    mcpUsage: [
      { server: 'web', tools: ['web_search'] },
    ],
    inlineTools: [],
  },
  {
    id: 'voice-journal',
    name: 'Voice Journal',
    tagline: 'Drop a voice memo — Whisper transcribes, agent structures, SQLite stores',
    type: 'audio-video',
    surface: 'pipeline',
    description:
      'A personal journal that accepts audio recordings (.m4a, .mp3, .wav) and text entries via a browser UI. OpenAI Whisper API transcribes audio automatically (local Whisper as fallback). The agent structures each entry and stores it in SQLite alongside a Markdown file. A background watcher monitors ./inbox for new files. A configurable email digest sends a summary of recent entries on schedule.',
    category: 'personal',
    status: 'working',
    channels: ['EmailChannel'],
    tools: ['transcribe_audio()', 'save_journal_entry()', 'list_entries()', 'list_dates()'],
    demoPath: 'apps/voice_journal',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'OPENAI_API_KEY', 'SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'DIGEST_TO'],
      setup: [
        'cd apps/voice_journal',
        'pip install -r requirements.txt',
        '# optional local whisper fallback:',
        'pip install openai-whisper',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. Inbox watcher: asyncio loop monitors ./inbox for new audio/text files; audio is transcribed via OpenAI Whisper API, then the agent structures the entry and stores it in SQLite + a Markdown file under ./entries/. Email digest: configurable schedule sends a summary of recent entries via SMTP.',
    diagram: `python main.py  →  http://127.0.0.1:18799

Inbox watcher (background, auto):
./inbox/memo_20260421.m4a  (new file detected)
      │
      ▼
OpenAI Whisper API → clean transcript text
      │
      ▼
CugaAgent ("Structure this journal entry: mood, topics, action items")
      │
      ▼
SQLite (journal.db) + ./entries/memo_20260421.md

Upload / quick-write panel:
User uploads audio or types an entry
      │  POST /entry or file upload
      ▼
Same transcribe → structure → store pipeline

Chat panel (on-demand):
User: "What themes came up this week?"
      │  POST /ask (recent entries injected as context)
      ▼
CugaAgent → "You mentioned deadlines and team collaboration…"`,
    cugaContribution: [
      'Agent structures raw transcripts into mood, topics, and action items — not just a plain text dump',
      'Whisper API handles transcription; agent only sees clean text — zero transcription tokens wasted',
      'Inbox watcher processes audio automatically on drop — no manual trigger needed',
      'Configurable email digest keeps you connected to your journal without opening the app',
    ],
    examples: [
      'Click 📎 and upload a .m4a or .mp3 voice note',
      'What did I write about last week?',
      'Summarize my entries from this month',
      'What themes keep coming up in my journal?',
      'Show me everything I recorded on Monday',
    ],
    appUrl: 'http://localhost:28799',
    mcpUsage: [
      { server: 'local', tools: ['transcribe_audio'] },
    ],
    inlineTools: ['save_journal_entry', 'list_entries', 'list_dates'],
  },
  {
    id: 'smart-todo',
    name: 'Smart Todo',
    type: 'event-driven',
    tagline: 'AI-powered task management with natural-language input — in-UI reminders, no email',
    surface: 'pipeline',
    description:
      'A conversational todo manager with a browser UI. Add tasks in natural language ("remind me to review the PR before EOD"), set due dates, and the background watcher polls SQLite every 60s for due reminders. When a reminder fires it surfaces in the Recent Alerts panel at the bottom of the page (no email, no per-user accounts). Tasks stored in SQLite survive restarts. The tabbed board shows Todos, Reminders, Notes, and Done.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['save_todo()', 'list_todos()', 'mark_done()'],
    demoPath: 'apps/smart_todo',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL'],
      setup: [
        'cd apps/smart_todo',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. Chat: POST /ask → CugaAgent parses natural language → adds todos to SQLite (todos.db) with due dates extracted from context. Background reminder watcher: asyncio loop checks every 60s for overdue items and surfaces them in the Recent Alerts panel. Todo board renders Todos / Reminders / Notes / Done tabs from SQLite on each load.',
    diagram: `python main.py  →  http://127.0.0.1:18800

Chat panel (on-demand):
User: "Remind me to review the PR before EOD"
      │  POST /ask
      ▼
CugaAgent → parses due date, category, priority
      │  inserts todo into todos.db
      ▼
"Got it! PR review added — due today at 17:00."

Todo board (tabbed, loaded from SQLite):
  Todos | Reminders | Notes | Done
  ─────────────────────────────────
  ● Review the PR            due today 17:00
  ● Deploy to production     due Friday 17:00

Background reminder watcher:
asyncio loop (every 60s)
      │  query todos.db for overdue items
      ▼
Recent Alerts panel (in-UI): "Reminder: Review the PR is due now"`,
    cugaContribution: [
      'Natural language due-date extraction — "by EOD", "Friday at 5pm", "tomorrow morning" all resolve to timestamps',
      'Categorises input automatically into Todos, Reminders, or Notes based on phrasing',
      'Persistent SQLite store — todos and notes survive restarts; no reconfiguration needed',
      'Background reminder watcher fires on due time and surfaces alerts in-UI — no SMTP, no app passwords',
    ],
    examples: [
      'Remind me to review the PR by EOD',
      'Add high priority: deploy to production by Friday at 5pm',
      "What are my open todos?",
      "What's due today?",
      'Mark the PR review as done',
      'Add a note: check with Alice about the project timeline',
    ],
    appUrl: 'http://localhost:28800',
    mcpUsage: [],
    inlineTools: ['save_todo', 'list_todos', 'mark_done'],
  },
  {
    id: 'travel-agent',
    name: 'Travel Planner',
    tagline: 'Plan a full trip in a conversation — live weather, attractions, and web search',
    type: 'other',
    surface: 'gateway',
    description:
      'A conversational travel planning agent with a browser UI. Describe your trip and the agent builds a day-by-day itinerary using live data: Wikipedia city overviews, real-time weather (wttr.in), geocoding (Nominatim/OSM), points of interest (OpenTripMap), and web search (Tavily). Also showcases CugaAgent vs LangGraph ReAct side-by-side on the same tools — same task, two architectures, one UI.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['get_city_overview()', 'get_weather()', 'get_coordinates()', 'search_attractions()', 'search_web()'],
    demoPath: 'apps/travel_planner',
    howToRun: {
      envVars: ['ANTHROPIC_API_KEY', 'TAVILY_API_KEY', 'OPENTRIPMAP_API_KEY'],
      setup: [
        'cd apps/travel_planner',
      ],
      command: 'uv run --project . main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /plan → CugaAgent calls get_city_overview(), get_weather(), search_attractions(), web_search() → full day-by-day itinerary with budget breakdown. POST /chat → multi-turn follow-up on the same plan. POST /configure injects API keys at runtime — no restart needed. The LangGraph ReAct backend is available as an alternative via the same UI toggle.',
    diagram: `uv run main.py  →  http://127.0.0.1:8090

User: "5 days in Kyoto in March, mid-range budget"
      │  POST /plan
      ▼
CugaAgent
      ├─ get_city_overview("Kyoto")    ← Wikipedia REST API
      ├─ get_weather("Kyoto", "March") ← wttr.in
      ├─ search_attractions("Kyoto")   ← OpenTripMap
      └─ web_search("Kyoto March tips")← Tavily
            │
            ▼
Day-by-day itinerary + budget breakdown

POST /chat — follow-up in the same session:
User: "Move the temple visit to Day 2 and add a tea ceremony"
      │
      ▼
CugaAgent (full plan in context) → updated itinerary`,
    cugaContribution: [
      'CugaAgent coordinates four live data sources in a single pass — no orchestration glue code required',
      'Side-by-side CugaAgent vs LangGraph ReAct on identical tools — same prompt, same task, toggle between architectures in the UI',
      'POST /configure injects API keys at runtime — demo audience can provide keys without restarting the server',
      'Multi-turn POST /chat preserves the full itinerary as conversation context — follow-up edits just work',
    ],
    examples: [
      '5 days in Kyoto in March, mid-range budget',
      'Weekend in Barcelona — focus on food and architecture',
      '10 days in Japan: Tokyo, Kyoto, and Osaka',
      'Family trip to Rome, 7 days, two kids under 10',
      'Move the temple visit to Day 2 and add a tea ceremony',
      'What\'s the weather like during my trip?',
    ],
    appUrl: 'http://localhost:28090',
    mcpUsage: [
      { server: 'web', tools: ['web_search'] },
      { server: 'knowledge', tools: ['get_wikipedia_article'] },
      { server: 'geo', tools: ['geocode', 'search_attractions', 'get_weather'] },
    ],
    inlineTools: [],
  },
  {
    id: 'deck-forge',
    name: 'Deck Forge',
    tagline: 'Point at a folder of docs, PDFs, and recordings — get a polished slide deck',
    type: 'document-intelligence',
    surface: 'pipeline',
    description:
      'An AI presentation architect powered by a LangGraph ReAct agent and a RAG knowledge base. Give it a local directory (PDFs, slides, markdown, recordings) and a topic — the agent discovers every file, extracts and indexes the content with ChromaDB + sentence-transformers, reasons about a narrative arc, and builds a coherent slide deck with speaker notes. Output: a .pptx file and a structured Markdown report. Progress streams live to the browser via SSE.',
    category: 'enterprise',
    status: 'working',
    channels: [],
    tools: ['list_directory()', 'extract_and_index()', 'search_knowledge_base()', 'add_slide()', 'finalize()'],
    demoPath: 'apps/deck_forge',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ANTHROPIC_API_KEY', 'RITS_API_KEY', 'OPENAI_API_KEY'],
      setup: [
        'cd apps/deck_forge',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18802',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /api/generate creates a session and launches an asyncio task that runs the LangGraph ReAct agent. The agent calls five async tools (closed over the session): list_directory discovers files; extract_and_index uses pdfplumber / python-pptx / faster-whisper to extract text and chunk-embed it into an ephemeral ChromaDB collection; search_knowledge_base retrieves relevant chunks by semantic similarity; add_slide accumulates slides; finalize writes deck.pptx and deck.md. Each tool pushes typed events to session.queue, which the SSE endpoint streams to the browser in real time.',
    diagram: `python main.py  →  http://127.0.0.1:18802

User: directory=/research/transformers  topic="Self-Attention in Transformers"
      │  POST /api/generate
      ▼
LangGraph ReAct Agent
      ├─ list_directory("/research/transformers")
      │    → 3 PDFs, 1 PPTX, 2 Markdown files
      │
      ├─ extract_and_index("attention_paper.pdf")
      │    → pdfplumber → 847 chunks → ChromaDB
      ├─ extract_and_index("overview.md") → 23 chunks
      ├─ extract_and_index("slides.pptx") → 41 chunks
      │
      ├─ search_knowledge_base("self-attention query key value")
      │    → top 5 chunks from 3 sources
      │
      ├─ [agent reasons: 9 slides needed, sections: intro, mechanism, BERT, scaling, takeaways]
      │
      ├─ add_slide("Introduction to Transformers", bullets=[...], notes="...")
      ├─ add_slide("The Self-Attention Mechanism", ...)
      ├─ ... (9 slides total)
      │
      └─ finalize("Transformer Architecture")
           → deck.pptx  (10 slides incl. title)
           → deck.md    (structured text report)

SSE stream → browser: live progress per tool call`,
    cugaContribution: [
      'Agent owns all content decisions — which files are relevant, narrative arc, section structure, slide count, deduplication across sources; the app is a thin shell',
      'Chunked RAG retrieval — each slide gets a targeted search query, pulling the most relevant content from the indexed corpus',
      'Five async tools push typed SSE events (directory_scanned, indexed, search, slide_added, done) — live progress without polling',
      'Works on any LLM provider via the shared _llm.py factory — RITS, Anthropic, OpenAI, WatsonX, or local Ollama',
      'LangGraph ReAct graph with CugaAgent placeholder — toggle between architectures in the UI once CugaAgent is wired',
    ],
    examples: [
      'directory=/Users/me/research/transformers, topic="Self-Attention and BERT"',
      'directory=/Users/me/project/design_docs, topic="Vakra Architecture Overview"',
      'directory=/Users/me/talks/ai_summit, topic="Enterprise AI Deployment Challenges"',
      'directory=/Users/me/papers/multimodal, topic="Vision Transformers and DALL-E"',
    ],
    appUrl: 'http://localhost:28802',
    mcpUsage: [],
    inlineTools: ['list_directory', 'extract_and_index', 'search_knowledge_base', 'add_slide', 'finalize'],
  },
  {
    id: 'youtube-research',
    name: 'YouTube Research',
    tagline: 'Research any topic via YouTube — find videos, fetch transcripts, synthesise with citations',
    type: 'audio-video',
    surface: 'gateway',
    description:
      'A browser UI for topic research powered by YouTube content. Topic mode: type a subject and the agent searches the web for relevant YouTube videos, fetches their transcripts, and synthesises findings organised by theme with citations and timestamps. URL mode: paste one or more YouTube links directly for instant summaries with key moments. Research history stored in SQLite.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['web_search()', 'get_video_info()', 'get_transcript()'],
    demoPath: 'apps/youtube_research',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/youtube_research',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent uses web_search (Tavily) to find YouTube videos, get_video_info (oEmbed) for metadata, get_transcript (youtube-transcript-api) for captions → synthesises across transcripts with citations and timestamps. Research log stored in SQLite.',
    diagram: `python main.py  →  http://127.0.0.1:18803

Topic mode:
User: "Latest developments in AI agents"
      │  POST /ask
      ▼
CugaAgent
      ├─ web_search("AI agents youtube 2026")
      ├─ web_search("AI agent frameworks site:youtube.com")
      │     → 5 YouTube URLs found
      │
      ├─ get_video_info(url1..url5) → titles, channels
      ├─ get_transcript(url1..url4) → timestamped captions
      │     (url5: no captions — skipped)
      ▼
Synthesis by theme with citations:
"Both Channel A ([12:30]) and Channel B ([08:15]) emphasise…"

URL mode:
User: "https://youtube.com/watch?v=abc — summarise this"
      │
      ▼
CugaAgent → get_video_info + get_transcript → summary with timestamps`,
    cugaContribution: [
      'CugaAgent decides search strategy — generates 2-3 varied queries to surface the best YouTube results',
      'Agent synthesises across multiple video transcripts by theme, not per-video — cross-referencing what different creators say',
      'Citation format with channel attribution and timestamps is enforced by the skill prompt',
      'Transcripts capped at ~5000 words per video to stay within context limits; agent handles truncation gracefully',
    ],
    examples: [
      'Latest developments in AI agents',
      'How does RLHF work?',
      'Best practices for RAG pipelines',
      'https://youtube.com/watch?v=VIDEO_ID — summarise this video',
      'Compare what these creators say about fine-tuning: [url1] [url2]',
      'What did they say about scaling laws around the 20-minute mark?',
    ],
    appUrl: 'http://localhost:28803',
    mcpUsage: [
      { server: 'web', tools: ['web_search', 'get_youtube_video_info', 'get_youtube_transcript'] },
    ],
    inlineTools: [],
  },
  {
    id: 'arch-diagram',
    name: 'Architecture Diagram Generator',
    tagline: 'Describe a system in plain English, get a rendered architecture diagram',
    type: 'document-intelligence',
    surface: 'gateway',
    description:
      'A browser UI that turns natural-language system descriptions into rendered architecture diagrams. The agent generates Mermaid.js code (flowcharts, sequence diagrams, ER diagrams, state diagrams) and the browser renders it as interactive SVG. Supports iterative refinement — ask the agent to add, remove, or change components and it updates the diagram. Optionally uses web search to research unfamiliar technologies before diagramming. Diagrams downloadable as SVG.',
    category: 'enterprise',
    status: 'working',
    channels: [],
    tools: ['web_search()'],
    demoPath: 'apps/arch_diagram',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/arch_diagram',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI with mermaid.js loaded from CDN. POST /ask → CugaAgent generates Mermaid code in a fenced code block → server extracts the code via regex → frontend renders SVG via mermaid.js. The system prompt includes full Mermaid syntax reference with examples for each diagram type to minimise invalid output. Iterative refinement works via the agent thread — the agent remembers the previous diagram and modifies it.',
    diagram: `python main.py  →  http://127.0.0.1:18804

User: "Design a microservices e-commerce platform"
      │  POST /ask
      ▼
CugaAgent (system prompt includes Mermaid syntax reference)
      │  (optional) web_search("microservices patterns")
      ▼
Response contains:
  \`\`\`mermaid
  graph TD
    Client["Browser"] -->|HTTPS| GW["API Gateway"]
    GW --> UserSvc["User Service"]
    GW --> OrderSvc["Order Service"]
    OrderSvc --> MQ["Message Queue"]
    MQ --> PaySvc["Payment Service"]
  \`\`\`
  + explanation of each component
      │
      ▼
Frontend: mermaid.js renders SVG → Download SVG / Copy code

User: "Add a Redis cache between services and the database"
      ▼
CugaAgent → updated diagram with cache node added`,
    cugaContribution: [
      'CugaAgent picks the best diagram type (flowchart, sequence, ER, state) based on what the user describes',
      'System prompt includes full Mermaid syntax reference with correct examples — minimises invalid diagram code',
      'Iterative refinement via conversation thread — "add a cache", "show as sequence diagram" modifies the existing diagram',
      'Optional web_search lets the agent research unfamiliar technologies before diagramming',
    ],
    examples: [
      'Microservices e-commerce platform with API gateway, user service, order service, and payment processing',
      'CI/CD pipeline from git push to production with testing, staging, and rollback',
      'Real-time chat system with WebSockets, load balancer, and Redis pub/sub',
      'OAuth2 login flow as a sequence diagram',
      'E-commerce database schema as an ER diagram',
      'Order lifecycle as a state diagram',
      'Add a Redis cache between the services and the database',
      'Show me the auth flow as a sequence diagram instead',
    ],
    appUrl: 'http://localhost:28804',
    mcpUsage: [
      { server: 'web', tools: ['web_search'] },
    ],
    inlineTools: [],
  },
  {
    id: 'hiking-research',
    name: 'Hiking Research',
    tagline: 'Discover and compare hiking trails near any location with AI-synthesised reviews',
    type: 'other',
    surface: 'gateway',
    description:
      'A browser UI for exploring hiking trails. Type any location and the agent geocodes it, queries OpenStreetMap via the Overpass API for named hiking route relations, and presents trails filtered by difficulty and kid-friendliness. Click any trail name to view it on OpenStreetMap. Tap "Get Reviews" on any trail to get an AI-synthesised summary of hiker reviews from the web via Tavily.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['geocode_location()', 'find_hikes()', 'get_review_summary()'],
    demoPath: 'apps/hiking_research',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/hiking_research',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls geocode_location (Nominatim/OpenStreetMap) to convert a place name to lat/lon, then find_hikes (Overpass API) to fetch named hiking route relations, filtered by difficulty and kid-friendliness. GET /hikes returns the cached results for the live trail-card panel. get_review_summary uses Tavily to search for and synthesise hiker reviews for a specific trail.',
    diagram: `python main.py  →  http://127.0.0.1:18805

User: "Easy hikes near Yosemite, CA"
      │  POST /ask
      ▼
CugaAgent
      ├─ geocode_location("Yosemite, CA")
      │     → lat=37.7489, lon=-119.5885
      │
      ├─ find_hikes(lat, lon, radius_km=25, difficulty="easy")
      │     → Overpass API: hiking route relations
      │     → filter by sac_scale / distance
      │     → _last_hikes updated (30 results)
      ▼
Summary: "Found 12 easy trails near Yosemite…"

GET /hikes → trail cards rendered in the right panel
  Each card: name (→ OSM link), difficulty, distance, kid-friendly badge

User: "Tell me about reviews for: Mist Trail"
      │
      ▼
CugaAgent → get_review_summary("Mist Trail", "Yosemite")
          → Tavily search → synthesised review summary`,
    cugaContribution: [
      'Agent chains geocode → find_hikes automatically — user just names any place, no coordinates needed',
      'Difficulty inferred from OSM sac_scale tag with a distance-based fallback for untagged routes',
      'Kid-friendly flag combines difficulty, distance, and an explicit OSM child= tag',
      'Review synthesis via Tavily search gives real hiker opinions without fabricating trail details',
    ],
    examples: [
      'Easy hikes near Yosemite, CA',
      'Kid-friendly trails near Boulder, CO',
      'Moderate hikes near Asheville, NC within 40 km',
      'Hard hikes near Denver, CO',
      'Family hikes near Lake Tahoe',
      'Tell me about user reviews for: Half Dome Trail',
    ],
    appUrl: 'http://localhost:28805',
    mcpUsage: [
      { server: 'geo', tools: ['geocode', 'find_hikes'] },
      { server: 'web', tools: ['web_search'] },
    ],
    inlineTools: [],
  },
  {
    id: 'movie-recommender',
    name: 'Movie Recommender',
    tagline: 'Tell the agent what you love — get a personalised watch-next list',
    type: 'other',
    surface: 'gateway',
    description:
      'A conversational movie recommendation agent with a browser UI. Tell it about films you enjoy, genres, favourite directors and actors, or your current mood — the agent builds a taste profile and recommends 5–8 films you will love. Movie details are verified via the Wikipedia REST API (no extra API key needed). Recommendations appear as cards in the right panel alongside a live view of your taste profile.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['lookup_movie()', 'save_preference()', 'get_preferences()', 'save_recommendations()'],
    demoPath: 'apps/movie_recommender',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ANTHROPIC_API_KEY'],
      setup: [
        'cd apps/movie_recommender',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18806',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent uses save_preference to record genres, liked/disliked films, actors, directors, and moods; get_preferences recalls the full profile; lookup_movie verifies details via Wikipedia; save_recommendations persists the structured card list. GET /session/{thread_id} returns the live profile and recommendation cards.',
    diagram: `python main.py  →  http://127.0.0.1:18806

User: "I love Inception and The Dark Knight"
      │  POST /ask
      ▼
CugaAgent
      ├─ save_preference(category="liked_movie", value="Inception")
      ├─ save_preference(category="liked_movie", value="The Dark Knight")
      │
User: "Recommend something similar"
      ├─ get_preferences()  → liked_movies, genres, moods …
      ├─ lookup_movie("Memento")   ← Wikipedia REST API
      ├─ lookup_movie("Prisoners")
      │
      ├─ save_recommendations([{title, year, genre, reason, rating}, ...])
      ▼
Recommendation cards rendered in the right panel`,
    cugaContribution: [
      'save_preference / get_preferences build a persistent taste profile within the session — the agent never forgets what you said earlier',
      'lookup_movie verifies film details via Wikipedia before suggesting — no hallucinated plot descriptions',
      'save_recommendations pushes structured JSON to the UI so cards render automatically without UI polling logic',
      'Warm, film-enthusiast persona defined in the skill prompt — swap the prompt to change tone or domain (books, games, etc.)',
    ],
    examples: [
      "I love Inception and The Dark Knight — what should I watch next?",
      "I enjoy sci-fi and psychological thrillers, suggest 5 films",
      "My favourite director is Denis Villeneuve",
      "I'm in the mood for something light and funny tonight",
      "I dislike jump-scare horror — what else is good?",
      "Recommend something with Tom Hanks I might have missed",
    ],
    appUrl: 'http://localhost:28806',
    mcpUsage: [
      { server: 'knowledge', tools: ['get_wikipedia_article'] },
    ],
    inlineTools: ['save_preference', 'get_preferences', 'save_recommendations'],
  },
  {
    id: 'webpage-summarizer',
    name: 'Webpage Summarizer',
    tagline: 'Paste any URL — get a structured plain-English summary instantly',
    type: 'other',
    surface: 'gateway',
    description:
      'A browser UI that fetches and summarises any webpage you provide. Paste a URL into the chat and the agent retrieves the page, strips HTML boilerplate (scripts, nav, footers), extracts readable text, and returns a structured summary: title, source URL, 2–3 sentence overview, key topics as bullet points, important facts, and a bottom-line takeaway. Also lists hyperlinks found on the page on request.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['fetch_webpage()', 'fetch_webpage_links()'],
    demoPath: 'apps/webpage_summarizer',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ANTHROPIC_API_KEY'],
      setup: [
        'cd apps/webpage_summarizer',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 8071',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls fetch_webpage (httpx + BeautifulSoup, truncated to 12 000 chars) → produces structured summary. fetch_webpage_links returns the list of external links for site exploration. No state is stored between requests.',
    diagram: `python main.py  →  http://127.0.0.1:8071

User: "Summarize https://en.wikipedia.org/wiki/Large_language_model"
      │  POST /ask
      ▼
CugaAgent
      └─ fetch_webpage("https://en.wikipedia.org/wiki/Large_language_model")
           │  httpx GET + BeautifulSoup strip
           │  title, meta description, body text (≤12 000 chars)
           ▼
Structured summary:
  Title: Large language model — Wikipedia
  Overview: A large language model (LLM) is …
  Key topics: • Architecture • Training • RLHF • Applications …
  Bottom line: LLMs are transformer-based models …

User: "List all links on https://news.ycombinator.com"
      └─ fetch_webpage_links(url) → up to 40 external links`,
    cugaContribution: [
      'fetch_webpage strips nav, header, footer, script, and style tags before sending text to the LLM — agent only sees signal, not boilerplate',
      'Content truncated to 12 000 chars to stay within context limits; the agent handles truncation gracefully',
      'Structured summary format (overview → bullets → bottom line) enforced by the system prompt — consistent output regardless of page type',
      'fetch_webpage_links enables lightweight site exploration without a separate crawling tool',
    ],
    examples: [
      "Summarize https://en.wikipedia.org/wiki/Large_language_model",
      "What is this page about? https://python.org",
      "Key takeaways from https://openai.com/blog",
      "List all links on https://news.ycombinator.com",
      "https://github.com/langchain-ai/langchain — give me a one-paragraph overview",
    ],
    appUrl: 'http://localhost:28071',
    mcpUsage: [
      { server: 'web', tools: ['fetch_webpage', 'fetch_webpage_links'] },
    ],
    inlineTools: [],
  },
  {
    id: 'code-reviewer',
    name: 'Code Reviewer',
    tagline: 'Paste or upload code — get structured bug, security, and style feedback',
    type: 'other',
    surface: 'gateway',
    description:
      'An AI-powered code review tool with a browser UI. Paste a snippet or upload a source file (.py, .js, .ts, .java, .go, .rs, .cpp, .sql, .sh, and more) and choose a focus mode: Full Review, Security, Performance, Style, Bugs, Architecture, or Testability. The agent detects the language, validates Python syntax via AST, extracts code metrics (LOC, complexity, top-level definitions), and returns a structured review with severity-rated issues, concrete suggestions, and deeper insights. Ask follow-up questions about the loaded code without re-submitting. Session review history is collapsible and copyable.',
    category: 'enterprise',
    status: 'working',
    channels: [],
    tools: ['check_python_syntax()', 'extract_code_metrics()', 'detect_language()'],
    demoPath: 'apps/code_reviewer',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ANTHROPIC_API_KEY'],
      setup: [
        'cd apps/code_reviewer',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18807',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /review → CugaAgent calls detect_language, check_python_syntax (Python only, AST-based), and extract_code_metrics → structured review with severity badges. POST /ask → free-form follow-up on any loaded code. POST /upload → reads a source file and returns its text so the UI can populate the code area. GET /history → in-memory list of last 50 reviews (session-scoped).',
    diagram: `python main.py  →  http://127.0.0.1:18807

User: pastes Python function, selects "Security" focus, clicks Review
      │  POST /review  {code, language:"python", focus:"security"}
      ▼
CugaAgent
      ├─ detect_language(code)          → {"language":"python","confidence":"high"}
      ├─ check_python_syntax(code)      → {"valid":true,"error":null}
      ├─ extract_code_metrics(code)     → {total_lines:42, branch_complexity:7, ...}
      ▼
Structured review:
  ### Summary  — Good overall, one injection risk
  ### Issues Found
    [HIGH] Unsanitised user input passed to subprocess.run() — line 14
  ### Suggestions
    1. Use shlex.quote() or subprocess list-form …
  ### Metrics  — Lines: 42 (non-blank: 36), Complexity: 7

User: "How would you refactor this using the strategy pattern?"
      │  POST /ask
      ▼
CugaAgent (code injected as context) → refactoring walkthrough`,
    cugaContribution: [
      'check_python_syntax runs AST.parse before the LLM sees the code — syntax errors reported instantly, no token waste',
      'extract_code_metrics gives the agent concrete numbers (LOC, branch count, top-level defs) to ground its review in facts',
      'Focus mode chips translate to a focus_hint injected into the prompt — same agent, different lens, no code duplication',
      'Session review history (last 50) is maintained in-memory and displayed as collapsible cards with copy-to-clipboard',
    ],
    examples: [
      "Paste a Python function and select Bugs focus",
      "Upload a JavaScript file and select Security focus",
      "Paste a SQL query and ask: How could I optimise this for 10M rows?",
      "Load a Go file and click Architecture",
      "How would you refactor this using the strategy pattern?",
      "Is there any XSS risk in the current code?",
    ],
    appUrl: 'http://localhost:28807',
    mcpUsage: [
      { server: 'code', tools: ['check_python_syntax', 'extract_code_metrics', 'detect_language'] },
    ],
    inlineTools: [],
  },
  {
    id: 'paper-scout',
    name: 'Paper Scout',
    tagline: 'Research academic papers via arXiv and Semantic Scholar — no API key needed',
    description:
      'A browser UI for academic research. Type a topic and the agent searches both arXiv (CS, ML, physics, math, biology) and Semantic Scholar (broader coverage with citation counts), then synthesises findings across papers with inline citations. Paste an arXiv ID or URL directly for an instant structured summary: contributions, method, results, limitations. Ask follow-up questions like "what does this build on?" to fetch reference lists.',
    category: 'personal',
    type: 'other',
    surface: 'gateway',
    status: 'working',
    channels: [],
    tools: ['search_arxiv', 'get_arxiv_paper', 'search_semantic_scholar', 'get_paper_references'],
    demoPath: 'apps/paper_scout',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG'],
      setup: [
        'cd apps/paper_scout',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18808',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls search_arxiv and search_semantic_scholar in parallel, deduplicates results, then synthesises a structured report grouped by theme with inline citations (title, URL, citation count, year). For direct arXiv IDs, get_arxiv_paper is called immediately. get_paper_references fetches the Semantic Scholar reference graph for any paper. No API keys required — arXiv and Semantic Scholar both offer free public APIs.',
    diagram: `python main.py  →  http://127.0.0.1:18808

Mode 1 — Topic research:
User: "LoRA and parameter-efficient fine-tuning"
      │  POST /ask
      ▼
CugaAgent
      ├─ search_arxiv("LoRA fine-tuning", category="cs.LG")
      │     → [2106.09685, 2305.14314, 2402.09353, …]
      ├─ search_semantic_scholar("parameter-efficient fine-tuning")
      │     → [papers with citation counts]
      ▼
Synthesised report:
  **Topic**: LoRA and Parameter-Efficient Fine-Tuning
  **Papers found**: 8 (5 arXiv, 3 Semantic Scholar)
  **Synthesis**: LoRA (Hu et al., 2021) introduces low-rank decomposition…
  **Key papers to read first**: …

Mode 2 — Direct arXiv ID:
User: "arxiv 2305.11206"
      │  POST /ask
      ▼
CugaAgent
      ├─ get_arxiv_paper("2305.11206")
      ▼
  **Paper**: [Title](url)
  **Summary** / **Method** / **Key results** / **Limitations**`,
    cugaContribution: [
      'Searches arXiv and Semantic Scholar independently then deduplicates — same paper cited once, never twice',
      'Category filter on arXiv (cs.AI, cs.LG, stat.ML, etc.) lets users narrow to a field without knowing exact terminology',
      'Citation counts from Semantic Scholar ground the synthesis in impact, not just recency',
      'get_paper_references follows the citation graph to surface the foundational papers a new work builds on',
    ],
    examples: [
      "LoRA and parameter-efficient fine-tuning methods",
      "Mixture of Experts in large language models",
      "Retrieval-Augmented Generation for knowledge-intensive NLP",
      "https://arxiv.org/abs/1706.03762",
      "2310.01445",
      "What papers does Attention Is All You Need build on?",
    ],
    appUrl: 'http://localhost:28808',
    mcpUsage: [
      { server: 'knowledge', tools: ['search_arxiv', 'get_arxiv_paper', 'search_semantic_scholar', 'get_paper_references'] },
    ],
    inlineTools: [],
  },
  {
    id: 'wiki-dive',
    name: 'Wiki Dive',
    tagline: 'Deep Wikipedia research — reads articles section by section, follows related links, synthesises with citations',
    description:
      'A browser UI for encyclopedic deep dives. Unlike a Wikipedia search that returns a snippet, Wiki Dive reads the full article section by section, follows "See Also" links to pull connected concepts, and synthesises a structured report with inline citations. Great for building mental models from first principles — complex topics, historical events, scientific concepts, philosophical ideas. No API keys required; uses Wikipedia\'s free public REST and action APIs.',
    category: 'personal',
    type: 'other',
    surface: 'gateway',
    status: 'working',
    channels: [],
    tools: ['search_wikipedia', 'get_article_summary', 'get_article_sections', 'get_related_articles'],
    demoPath: 'apps/wiki_dive',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG'],
      setup: [
        'cd apps/wiki_dive',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18809',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls search_wikipedia to identify relevant articles, get_article_summary for a quick relevance check, get_article_sections for deep section-by-section reading of the primary article, get_related_articles to discover connected concepts, then get_article_summary on 2-3 related articles for breadth. The agent synthesises across all content into a structured report. No API keys required — uses Wikipedia\'s free public REST API and MediaWiki action API.',
    diagram: `python main.py  →  http://127.0.0.1:18809

User: "How does transformer attention work?"
      │  POST /ask
      ▼
CugaAgent
      ├─ search_wikipedia("transformer attention mechanism")
      │     → ["Transformer (deep learning)", "Attention (machine learning)", …]
      ├─ get_article_summary("Transformer (deep learning)")
      │     → lead paragraph confirming relevance
      ├─ get_article_sections("Transformer (deep learning)")
      │     → Introduction / Architecture / Attention / Training / Applications / …
      ├─ get_related_articles("Transformer (deep learning)")
      │     → ["BERT", "GPT", "Self-attention", "Seq2seq", …]
      ├─ get_article_summary("Attention (machine learning)")
      │     → historical context: Bahdanau 2014, Vaswani 2017
      ▼
Synthesised report:
  **Overview**: Transformers use self-attention to…
  **Key concepts**: Query/Key/Value matrices, Multi-head attention, Positional encoding
  **History**: Bahdanau (2014) introduced attention for NMT…
  **Related topics**: BERT, GPT, Vision Transformer`,
    cugaContribution: [
      'get_article_sections reads every section of the article — not just the lead — giving the agent encyclopedic depth instead of snippet-level knowledge',
      'get_related_articles surfaces the Wikipedia editor-curated "See Also" graph, pulling in adjacent concepts the user may not have known to ask for',
      'Multi-article synthesis: agent reads 3-5 articles and synthesises across them, resolving overlaps and connecting ideas',
      'Output is structured (Overview → Key concepts → History → Applications → Related topics) rather than raw article text',
    ],
    examples: [
      "How does transformer attention work?",
      "The French Revolution — causes, events, and legacy",
      "Quantum entanglement explained from first principles",
      "CRISPR gene editing and its applications",
      "Game theory and Nash equilibrium",
      "The philosophy of consciousness and the hard problem",
    ],
    appUrl: 'http://localhost:28809',
    mcpUsage: [
      { server: 'knowledge', tools: ['search_wikipedia', 'get_article_summary', 'get_article_sections', 'get_related_articles'] },
    ],
    inlineTools: [],
  },
  {
    id: 'box-qa',
    name: 'Box Document Q&A',
    tagline: 'Ask questions across documents stored in your Box cloud storage',
    type: 'document-intelligence',
    surface: 'gateway',
    description:
      'A browser UI that connects to a Box folder and lets you ask natural-language questions across your documents. The agent lists files, fetches and extracts text from supported document types (PDF, DOCX, PPTX, XLSX, TXT, MD, CSV), and answers questions with citations to specific files and passages. Video/audio files are surfaced by name but noted as unsupported — a multimodal extension (Whisper transcription + keyframe vision) is planned for v2.',
    category: 'enterprise',
    status: 'not-working',
    channels: [],
    tools: ['list_box_folder()', 'get_file_content()', 'search_box()'],
    demoPath: 'apps/box_qa',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'BOX_CONFIG_PATH', 'BOX_FOLDER_ID'],
      setup: [
        'cd apps/box_qa',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent uses list_box_folder (Box SDK JWT auth) to enumerate files, search_box to find relevant candidates, get_file_content to download and extract text (plain read for TXT/CSV/MD; docling OCR for PDF/DOCX/PPTX/XLSX) → answers with file citations. Two-panel UI: left is conversational chat (thread-aware, multi-turn), right shows the latest agent response in full.',
    diagram: `python main.py  →  http://127.0.0.1:18810

User: "What does the Q4 report say about revenue?"
      │  POST /ask
      ▼
CugaAgent
      ├─ list_box_folder("0") → sees Q4_Report.pdf, budget.xlsx, intro.mp4
      ├─ get_file_content(id=Q4_Report.pdf)
      │     → docling extracts text
      │     → intro.mp4 skipped ("video/audio not supported")
      ▼
Answer with citation:
"[Q4_Report.pdf] — 'Revenue grew 18% YoY, driven by…'"`,
    cugaContribution: [
      'Agent decides which files are relevant before fetching — avoids downloading the entire folder',
      'Cross-document synthesis: "Both the Q4 report and the board brief mention X"',
      'Multi-turn thread memory: follow-up questions work without re-fetching already-read files',
      'Graceful handling of unsupported types: media files are surfaced but not silently skipped',
    ],
    examples: [
      'What files are in my Box folder?',
      'Summarize the most recent PDF',
      'Find any documents about contracts and list key terms',
      'What does the project brief say about timelines?',
      'Compare the two most recent reports',
      'List all files — which ones can you read?',
    ],
    appUrl: 'http://localhost:28810',
    mcpUsage: [
      { server: 'text', tools: ['extract_text_from_bytes'] },
    ],
    inlineTools: ['list_box_folder', 'get_file_content', 'search_box'],
  },
  {
    id: 'ibm-whats-new',
    name: "IBM What's New Monitor",
    tagline: 'Track IBM Cloud release notes across services — scheduled digest, email alerts, ad-hoc chat',
    description:
      "A browser UI that monitors IBM Cloud service release notes and What's New announcements. Add services to your watch list (Code Engine, watsonx.ai, Event Streams, etc.), set a daily or weekly schedule, and the agent searches ibm.com and cloud.ibm.com via Tavily for recent changes. Meaningful updates appear in the Digest Log and are emailed automatically. Chat panel for ad-hoc questions like 'what changed in Cloud Object Storage this month?'",
    category: 'enterprise',
    type: 'event-driven',
    surface: 'pipeline',
    status: 'working',
    channels: ['EmailChannel'],
    tools: ['search_ibm_updates()', 'fetch_release_notes()'],
    demoPath: 'apps/ibm_whats_new',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'TAVILY_API_KEY', 'SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'DIGEST_TO'],
      setup: [
        'cd apps/ibm_whats_new',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18814',
    },
    architecture:
      "FastAPI serves the single-page UI. Chat: POST /ask → CugaAgent calls search_ibm_updates (Tavily scoped to ibm.com/cloud.ibm.com) + fetch_release_notes (httpx + BeautifulSoup, IBM URLs only) → answer with sources. Background scheduler: asyncio task checks every 5 minutes whether a digest is due; when due, agent checks each tracked service in turn, collects UPDATE: responses, and sends an SMTP digest. State persisted in .store.json.",
    diagram: `python main.py  →  http://127.0.0.1:18814

Chat panel (on-demand):
User: "What changed in Code Engine this month?"
      │  POST /ask
      ▼
CugaAgent
      ├─ search_ibm_updates("IBM Code Engine release notes 2026")
      │     → Tavily → cloud.ibm.com/docs/code-engine release notes
      ├─ fetch_release_notes("https://cloud.ibm.com/docs/code-engine?topic=...")
      │     → httpx + BeautifulSoup → clean release notes text
      ▼
"[Apr 2026] Custom domain mapping added for private visibility apps..."

Background scheduler (daily):
asyncio task (every 5 min — checks if digest is due)
      │  services: ["Code Engine", "watsonx.ai", "Event Streams"]
      ▼
agent.invoke("Check what is new for IBM Cloud service: Code Engine")
      │  → "UPDATE: [Apr 2026] ..."
agent.invoke("Check what is new for IBM Cloud service: watsonx.ai")
      │  → "UPDATE: [Mar 2026] ..."
      ▼
SMTP digest → DIGEST_TO`,
    cugaContribution: [
      'search_ibm_updates uses Tavily scoped to ibm.com + cloud.ibm.com — only real IBM sources, no hallucinated features',
      'fetch_release_notes strips nav/header/footer before the LLM sees text — agent reads signal, not HTML noise',
      'UPDATE: protocol — agent decides if changes are meaningful; only real updates trigger email, not empty "no changes" noise',
      'Background asyncio scheduler fires digests without a cron daemon — daily or weekly, configurable from the UI',
      'Per-service agent invocations keep context clean — one service per call, no cross-contamination of release notes',
    ],
    examples: [
      "What is new in IBM Code Engine in 2026?",
      "Latest changes to IBM Cloud Object Storage",
      "What changed in watsonx.ai recently?",
      "Any IBM Cloud breaking changes in the last 30 days?",
      "Summarize IBM Event Streams release notes from this month",
    ],
    appUrl: 'http://localhost:28814',
    mcpUsage: [
      { server: 'web', tools: ['web_search', 'fetch_webpage'] },
    ],
    inlineTools: [],
  },
  {
    id: 'ibm-cloud-advisor',
    name: 'IBM Cloud Architecture Advisor',
    tagline: 'Describe what you want to build — get real IBM Cloud services, CLI commands, and cost hints',
    description:
      'A browser UI powered by the IBM Global Catalog public API (no IBM account required). Describe your use case in plain English and the agent searches the live IBM service catalog, recommends 3–7 IBM Cloud services with roles and integration points, and generates ibmcloud CLI commands to provision them. Supports iterative refinement: ask for HA, HIPAA compliance, Terraform output, or AWS-to-IBM mappings.',
    category: 'enterprise',
    type: 'other',
    surface: 'gateway',
    status: 'working',
    channels: [],
    tools: ['search_ibm_catalog()', 'search_ibm_docs()'],
    demoPath: 'apps/ibm_cloud_advisor',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/ibm_cloud_advisor',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18812',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls search_ibm_catalog (IBM Global Catalog public REST API — no key needed) with 2–3 keyword queries to find real services, optionally calls search_ibm_docs (Tavily restricted to ibm.com) for pricing and architecture patterns, then produces a structured recommendation with CLI commands. No state stored between sessions.',
    diagram: `python main.py  →  http://127.0.0.1:18812

User: "Event-driven microservices with a message queue and a managed database"
      │  POST /ask
      ▼
CugaAgent
      ├─ search_ibm_catalog("message queue event streaming")
      │     → IBM Event Streams, IBM MQ
      ├─ search_ibm_catalog("managed postgresql database")
      │     → Databases for PostgreSQL
      ├─ search_ibm_catalog("serverless container compute")
      │     → IBM Code Engine
      ├─ (optional) search_ibm_docs("IBM Event Streams pricing tiers")
      ▼
Architecture: Event-Driven Microservices on IBM Cloud

IBM Cloud Services:
- IBM Event Streams (event-streams): Kafka-compatible message bus
- Databases for PostgreSQL (databases-for-postgresql): Persistent store
- IBM Code Engine (codeengine): Serverless consumer microservices

ibmcloud CLI:
  ibmcloud resource service-instance-create my-kafka event-streams standard us-south`,
    cugaContribution: [
      'search_ibm_catalog hits the live IBM Global Catalog API — only real, current services are ever recommended',
      'Agent runs 2–3 focused queries per use case (one per capability) to maximise catalog hit rate',
      'search_ibm_docs uses Tavily restricted to ibm.com — pricing tiers, feature comparisons from official sources',
      'Iterative refinement via conversation thread — "make it HA" or "show Terraform" modifies the previous recommendation in context',
    ],
    examples: [
      'IoT sensor pipeline with real-time processing and dashboards',
      'Serverless web app with auth and a managed database',
      'Event-driven microservices with a message queue',
      'ML model training and serving platform on IBM Cloud',
      'AWS equivalent: S3 + Lambda + DynamoDB on IBM Cloud',
      'HIPAA-compliant data processing pipeline',
      'Show Terraform for a Kubernetes workload on IBM Cloud',
    ],
    appUrl: 'http://localhost:28812',
    mcpUsage: [
      { server: 'web', tools: ['web_search'] },
    ],
    inlineTools: ['search_ibm_catalog'],
  },
  {
    id: 'ibm-docs-qa',
    name: 'IBM Docs Q&A',
    tagline: 'Ask any IBM Cloud question — get a precise answer from real IBM documentation with source links',
    description:
      'A browser UI that answers IBM Cloud questions by searching and reading real IBM documentation. Ask anything: setup procedures, plan limits, service comparisons, config options, pricing. The agent searches ibm.com and cloud.ibm.com via Tavily, fetches the most relevant doc pages in full, and synthesises a precise answer with inline citations. Multi-turn: ask follow-up questions without re-submitting context.',
    category: 'enterprise',
    type: 'other',
    surface: 'gateway',
    status: 'working',
    channels: [],
    tools: ['search_ibm_docs()', 'fetch_doc_page()'],
    demoPath: 'apps/ibm_docs_qa',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/ibm_docs_qa',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18813',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls search_ibm_docs (Tavily restricted to ibm.com/cloud.ibm.com, search_depth=advanced) to find relevant pages, then optionally calls fetch_doc_page (httpx + BeautifulSoup, strips nav/header/footer, extracts main content up to 6000 chars) on the most relevant URL. Agent synthesises across sources and cites every claim with a page title and URL.',
    diagram: `python main.py  →  http://127.0.0.1:18813

User: "How do I set up a private endpoint for Cloud Object Storage?"
      │  POST /ask
      ▼
CugaAgent
      ├─ search_ibm_docs("IBM Cloud Object Storage private endpoint setup")
      │     → Tavily → 6 results from cloud.ibm.com/docs
      │
      ├─ fetch_doc_page("https://cloud.ibm.com/docs/cloud-object-storage?topic=…")
      │     → httpx GET → BeautifulSoup strip → 4800 chars of clean doc text
      ▼
Answer:
  1. Create a service credential with HMAC enabled
  2. Use private endpoint: s3.private.<region>.cloud-object-storage.appdomain.cloud
  3. Ensure your compute is in the same region VPC

  Sources:
  - [Cloud Object Storage Endpoints](https://cloud.ibm.com/docs/…)

User: "What's the difference between private and direct endpoints?"
      ▼
CugaAgent (previous context retained) → follow-up with comparison table`,
    cugaContribution: [
      'search_ibm_docs uses Tavily advanced mode with ibm.com domain restriction — results always from official IBM sources',
      'fetch_doc_page strips nav, header, footer, and scripts before the LLM sees text — agent reads clean content, not HTML noise',
      'URL safety check refuses non-IBM URLs — agent cannot be redirected off-domain',
      'Multi-turn conversation thread — follow-up questions work without re-submitting context',
    ],
    examples: [
      'How do I set up a private endpoint for Cloud Object Storage?',
      'What are the Lite plan limits for Watson Discovery?',
      'How does IBM Cloud IAM service ID authentication work?',
      'Code Engine: Dockerfile vs Buildpacks — which should I use?',
      'How do I connect IBM Databases for PostgreSQL to Code Engine?',
      'What is IBM watsonx.ai and how do I get started?',
    ],
    appUrl: 'http://localhost:28813',
    mcpUsage: [
      { server: 'web', tools: ['web_search', 'fetch_webpage'] },
    ],
    inlineTools: [],
  },
  {
    id: 'api-doc-gen',
    name: 'API Doc Generator',
    tagline: 'Upload an OpenAPI spec and get human-readable docs with realistic examples in seconds',
    type: 'document-intelligence',
    surface: 'gateway',
    description:
      'A browser UI that turns OpenAPI/Swagger specs into developer-friendly documentation. Upload a JSON or YAML spec, point to a URL, or pick from five built-in samples (Petstore, GitHub Issues, Stripe Payments, Slack Messaging, OpenWeather). The agent reads the spec endpoint by endpoint, resolves $ref schemas, and writes clear Markdown docs with realistic curl examples and example responses. Supports iterative refinement — ask for more examples, filter to specific endpoints, change tone, or generate a Postman collection structure.',
    category: 'enterprise',
    status: 'working',
    channels: [],
    tools: ['list_endpoints()', 'get_endpoint_details()', 'get_schema()'],
    demoPath: 'apps/api_doc_gen',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG'],
      setup: [
        'cd apps/api_doc_gen',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 18811',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls list_endpoints to survey the loaded spec, get_endpoint_details for each endpoint being documented, and get_schema to resolve $ref models — then writes structured Markdown with tables, curl examples, and example responses. POST /load-spec parses JSON/YAML and stores it server-side. POST /upload-spec handles file uploads. Five sample OpenAPI specs are embedded in the UI for one-click loading. No database — spec is in-memory, conversation is thread-aware.',
    diagram: `python main.py  →  http://127.0.0.1:18811

User loads Stripe Payments spec (sample), then:
User: "Document all endpoints"
      │  POST /ask
      ▼
CugaAgent
      ├─ list_endpoints()
      │     → 9 endpoints across Customers, Charges, Refunds, Subscriptions
      ├─ get_endpoint_details("/charges", "POST")
      │     → amount, currency, customer, source, description fields
      ├─ get_schema("Charge")
      │     → id, amount, currency, status, paid, receipt_url
      ▼
Generated docs:
### POST /charges — Create a charge

**Authentication:** Basic auth — Stripe secret key as username

**Request body:**
| Field    | Type    | Required | Description              |
|----------|---------|----------|--------------------------|
| amount   | integer | Yes      | Amount in cents (e.g. 4999) |
| currency | string  | Yes      | ISO 4217 code (e.g. "usd") |

\`\`\`bash
curl -X POST https://api.stripe.com/v1/charges \\
  -u sk_live_…: \\
  -d amount=4999 \\
  -d currency=usd \\
  -d customer=cus_Qk5fG2hJ8mPx3N
\`\`\``,
    cugaContribution: [
      'Agent decides how many tool calls to make — one endpoint at a time for large specs, or in bulk for small ones',
      'get_schema resolves $ref chains the LLM would otherwise hallucinate around',
      'Realistic example values are inferred by the LLM from field names — amount → 4999, email → alice@acme.com',
      'Multi-turn thread: "add more examples" or "document only POST endpoints" refines the previous output in context',
    ],
    examples: [
      'Document all endpoints',
      'Show me the authentication details and how to get started',
      'Generate a quick-start guide for a new developer',
      'Document only the POST endpoints with example request bodies',
      'List all endpoints with a one-line description of each',
      'Generate a Postman collection structure for these endpoints',
    ],
    appUrl: 'http://localhost:28811',
    mcpUsage: [],
    inlineTools: ['list_endpoints', 'get_endpoint_details', 'get_schema'],
  },
  {
    id: 'bird-invocable-api',
    name: 'Bird Invocable API Creator',
    tagline: 'Turn a Bird-SQL database into a validated invocable API + ground-truth tool-call dataset',
    type: 'document-intelligence',
    surface: 'gateway',
    description:
      'A browser UI that turns a Bird-SQL database (sqlite + NL questions + gold SQL) into three artifacts: a small set of reusable, parametric Python tools; per-question ground-truth tool-call sequences; and a runnable MCP server you can plug into any tool-calling agent for benchmarking. Pick a database, watch live progress as the agent walks every question — orient on the schema, reason about decomposition, register or reuse tools, smoke-test them on real sqlite, record a sequence, and validate it end-to-end against the gold result. The Question Inspector shows the NL, evidence, gold SQL, recorded sequence, and pass/fail with diff. The Tool Browser shows every registered tool with reuse counts, slot pills, and the qids that reference it.',
    category: 'enterprise',
    status: 'working',
    channels: [],
    tools: [
      'db_get_schema()', 'db_sample_rows()', 'db_run_sql()',
      'bird_list_databases()', 'bird_list_questions()', 'bird_get_question()', 'bird_run_gold()',
      'tool_register()', 'tool_list()', 'tool_get()', 'tool_call()', 'tool_delete()',
      'seq_record()', 'seq_execute()', 'seq_validate()',
      'ignore_set()', 'ignore_list()', 'dataset_emit()',
    ],
    demoPath: 'apps/bird_invocable_api_creator',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'BIRD_DEV_JSON', 'BIRD_DBS_DIR'],
      setup: [
        'cd apps/bird_invocable_api_creator',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 28815',
    },
    architecture:
      'FastAPI serves the single-page UI. CugaAgent is bound to the 15 invocable_apis MCP tools and a long synthesis-policy system prompt. POST /question/{db}/{qid} runs the loop on a single question; POST /synthesize/{db} kicks off a background job that walks every question (live progress at GET /jobs/{id}). The agent calls db_* to orient, bird_* for the question + oracle, tool_* to register/reuse/call generated tools, and seq_* to record + validate the chain against the gold SQL result on the actual sqlite. dataset_emit freezes the registry to disk under output/<db>/. Server-side guards block forbidden names (question_*, *_wrapper, *_solver, gold_*) and near-duplicate SQL skeletons / name-token overlap, so the LLM cannot bloat the registry. Generated tool code runs in an exec() sandbox with sqlite3/json/re only and a read-only sqlite connection.',
    diagram: `python main.py --port 28815  →  http://127.0.0.1:28815

User picks db='california_schools', clicks "▶ Run agent on this question" for qid=28
      │  POST /question/california_schools/28
      ▼
CugaAgent + 15 MCP tools (mcp-invocable_apis @ 29107)
      ├─ bird_get_question(qid=28)        → NL + evidence + gold SQL
      ├─ bird_run_gold(qid=28)            → 57-row canonical answer
      ├─ db_get_schema, db_sample_rows
      ├─ db_run_sql("SELECT DISTINCT FundingType FROM schools")
      │     → ['Directly funded', 'Locally funded', 'Not in CS funding model']
      ├─ tool_list                        → see what's already registered
      ├─ Reasoning: "subquery in gold SQL → 2-step decomposition"
      ├─ tool_register avg_enrollment_difference_by_funding_type
      ├─ tool_call(funding_type='Locally funded')  → {avg_difference: 16.7}
      ├─ tool_register schools_with_enrollment_difference_above
      ├─ tool_call(threshold=16.7, …)              → 57 schools
      ├─ seq_record([step1 bind="avg",
      │              step2 threshold="{{avg.avg_difference}}"])
      └─ seq_validate                      → passed=true (set-equal vs gold)

dataset_emit  →  output/california_schools/california_schools_{tools.py,
                                                              tools.json,
                                                              dataset.json,
                                                              mcp_server.py,
                                                              tool_usage.json,
                                                              validation_report.json}`,
    cugaContribution: [
      'Closed-loop synthesis — orient (db_get_schema + DISTINCT), design (decomposition reasoning), register, smoke-test (tool_call on real sqlite), record sequence, validate against gold; up to 2 retries on failure',
      'Server-side quality guards — forbidden-name patterns, SQL-skeleton equality, ≥85% name-token overlap → reject; the agent cannot bloat the registry with question_N wrappers or near-duplicates',
      'Cross-question accumulation — every tool registered for question N is visible when synthesizing N+1; reuse is mandatory whenever a tool with different args can answer the new question. The "tools reused across qs" tile is the meta-moat alarm',
      'Slot-value discovery without leaking the answer — examples come from SELECT DISTINCT but exclude the literal value used in this question\'s gold SQL, so the dataset still tests an agent\'s NL→args mapping',
      'Validation comparator handles dict-of-list-of-dicts vs SQL tuples, set-equality, casing — every emitted record carries proof its sequence reproduces the gold SQL result on the real sqlite',
      'Emitted artifacts include a runnable MCP server (output/<db>/<db>_mcp_server.py) so the synthesized API can be benchmarked by any tool-calling agent — not just CUGA',
    ],
    examples: [
      'Run agent on this question (single-question demo from the inspector)',
      '⚡ Batch synthesize — walk every question in the selected database',
      'Filter the question list to ✗ fail and re-run the inspector to debug failures',
      'Open the Tool Browser, sort by "most reused" — the small reusable core of the API',
      '⊘ Mark ignore on questions with broken gold SQL so they\'re excluded from the keep set',
      '📥 Re-emit to refresh output/<db>/ artifacts after manual edits',
    ],
    appUrl: 'http://localhost:28815',
    mcpUsage: [
      { server: 'invocable_apis', tools: [
        'db_get_schema', 'db_sample_rows', 'db_run_sql',
        'bird_list_databases', 'bird_list_questions', 'bird_get_question', 'bird_run_gold',
        'tool_register', 'tool_list', 'tool_get', 'tool_call', 'tool_delete',
        'seq_record', 'seq_execute', 'seq_validate',
        'ignore_set', 'ignore_list', 'dataset_emit',
      ] },
    ],
    inlineTools: [],
  },

  {
    id: 'brief-budget',
    name: 'Brief Budget',
    tagline: 'Research brief on a hard tool-call budget — planner-driven, light prompt',
    type: 'other',
    surface: 'gateway',
    description:
      'A research-brief generator with a hard tool-call budget. The system prompt is goal-shaped: no prescribed sub-topics, no prescribed tool order. The agent must decompose the question, allocate the budget across sub-topics, execute, replan if a sub-topic dries up, and synthesize a structured brief with citations. Designed specifically to exercise CUGA\'s planner — every other app in the lineup uses a procedural prompt that absorbs the planner\'s job. Plan + tool calls stream live to the UI over SSE.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['propose_plan()'],
    demoPath: 'apps/brief_budget',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'TAVILY_API_KEY'],
      setup: [
        'cd apps/brief_budget',
      ],
      command: 'python main.py --port 28816',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /api/run starts a session with a question + budget; the app spins up a per-session CugaAgent whose tools are budget-wrapped (each non-plan call decrements session.used and streams a tool_call event). A free propose_plan tool records the agent\'s decomposition. The system prompt is deliberately goal-shaped: it prescribes the meta-process (plan → execute → replan → synthesize) but NOT sub-topics or tool order. SSE event stream feeds the UI: init / plan / tool_call / tool_result / budget_exhausted / brief / done. When budget hits 0, every further tool call returns {ok:false, code:budget_exhausted} and the agent must synthesize from what it has.',
    diagram: `python main.py --port 28816  →  http://127.0.0.1:28816

User: question + budget=15  →  POST /api/run
      │
      ▼
BriefSession { id, budget=15, used=0, plan_history=[], queue }
      │  asyncio.create_task(_execute(session))
      ▼
CugaAgent + tools
  ├─ propose_plan(plan)       FREE       ──► SSE: plan
  ├─ search_arxiv             cost: 1    ──► SSE: tool_call (used=1)
  ├─ search_semantic_scholar  cost: 1    ──► SSE: tool_call (used=2)
  ├─ propose_plan(replan)     FREE       ──► SSE: plan v2
  ├─ web_search               cost: 1    ──► SSE: tool_call (used=3)
  ├─ ...                                                  (used=14, used=15)
  └─ tool_call → {ok:false, code:"budget_exhausted"}
      │
      ▼
agent synthesizes brief from observations  ──► SSE: brief
      │
      ▼
SSE: done { used=15, budget=15, plan_count=2 }`,
    cugaContribution: [
      'Goal-shaped system prompt — under 50 lines, prescribes meta-process only (plan → execute → replan → synthesize). No sub-topics, no tool order. The planner decomposes per question.',
      'First-class propose_plan tool — free; records the agent\'s decomposition + budget split + tool intentions; UI renders each plan version live so viewers see the planner work.',
      'Hard budget enforcement at the tool boundary — every non-plan tool call decrements; budget_exhausted returns force the agent to stop calling and synthesize.',
      'A/B-able demo — comparison between this (planner-driven, no procedural workflow) and procedural-prompt apps like paper_scout shows the difference in budget allocation across sub-topics.',
    ],
    examples: [
      "What's the state of MoE architectures in LLMs?",
      'Compare RAG benchmarks 2025–2026 (BEIR, BERGEN, etc.)',
      'Open problems in agent observability',
      'Recent advances in LoRA fine-tuning of code models',
      'How are AI agents being applied to bug triage?',
    ],
    appUrl: 'http://localhost:28816',
    mcpUsage: [
      { server: 'web', tools: ['web_search', 'fetch_webpage', 'fetch_webpage_links', 'fetch_feed', 'search_feeds', 'get_youtube_video_info', 'get_youtube_transcript'] },
      { server: 'knowledge', tools: ['search_arxiv', 'get_arxiv_paper', 'search_semantic_scholar', 'get_paper_references', 'search_wikipedia', 'get_wikipedia_article', 'get_article_summary', 'get_article_sections', 'get_related_articles'] },
    ],
    inlineTools: ['propose_plan'],
  },

  {
    id: 'trip-designer',
    name: 'Trip Designer',
    tagline: 'Travel itinerary planner with a light, goal-shaped prompt — CUGA decides the workflow',
    type: 'other',
    surface: 'gateway',
    description:
      'Same domain as travel_planner, but the system prompt is deliberately light (~25 lines, no prescribed workflow or tool order). The agent decides its own decomposition (days × themes? geographic zones? practicalities first?), the order of investigation, and the tool mix per sub-task. Plan + tool calls stream live so viewers can compare what this agent chose to do versus the prescribed-workflow travel_planner. Built to test whether CUGA can plan an itinerary when the prompt stops scripting it.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: ['propose_plan()'],
    demoPath: 'apps/trip_designer',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'TAVILY_API_KEY', 'OPENTRIPMAP_API_KEY'],
      setup: [
        'cd apps/trip_designer',
      ],
      command: 'python main.py --port 28817',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /api/run starts a per-session CugaAgent with tools loaded from mcp-web + mcp-knowledge + mcp-geo. Each MCP tool is wrapped with a thin shim that streams tool_call + tool_result events to the session queue (no budget enforcement — this app is about visibility). A free propose_plan tool records the agent\'s plan; the UI renders each plan version. The system prompt is ~25 lines and prescribes nothing about workflow — only "call propose_plan first, cite real sources." Replanning is first-class: the agent can call propose_plan again at any time.',
    diagram: `python main.py --port 28817  →  http://127.0.0.1:28817

User: destination=Berlin, days=5, month=March,
      interests=[history, street food],
      constraints="must end at airport by 3pm Friday"
      │
      ▼  POST /api/run
TripSession { id, request, plan_history=[], tool_calls=[], queue }
      │
      ▼  asyncio.create_task(_execute(session))
CugaAgent (system prompt: ~25 lines, no workflow prescribed)
  ├─ propose_plan(plan)    ──► SSE: plan v1
  ├─ <agent decides which tools to call, in what order>
  ├─ tool_call A           ──► SSE: tool_call + tool_result
  ├─ tool_call B           ──► SSE: tool_call + tool_result
  ├─ propose_plan(replan)  ──► SSE: plan v2  (if direction changes)
  ├─ tool_call C ...
  └─ synthesise itinerary  ──► SSE: itinerary
      │
      ▼
SSE: done { tool_call_count, plan_count }`,
    cugaContribution: [
      'Light goal-shaped prompt — exposes whether CUGA can plan an itinerary without a procedural script. The contrast with travel_planner (which has a 6-step prescribed workflow) is the demo.',
      'First-class propose_plan + replanning — agent can revise its decomposition mid-flight; the UI shows version history.',
      'Cross-server orchestration — agent picks freely across mcp-web + mcp-knowledge + mcp-geo with no prompt-level guidance about which server is for what.',
      'Live plan + tool-call visibility via SSE — viewers can see exactly what the agent chose to do, in what order, and why (replan rationales captured per version).',
    ],
    examples: [
      'Berlin · 5 days · March · history + street food',
      'Kyoto · 4 days · November · temples + gardens + food',
      'Lisbon · 3 days · May · azulejos + fado + viewpoints',
      'Reykjavik · 6 days · February · northern lights + hot springs',
      'Paris · 4 days · June · museums + boulangeries · constraint: vegetarian only',
    ],
    appUrl: 'http://localhost:28817',
    mcpUsage: [
      { server: 'web', tools: ['web_search', 'fetch_webpage', 'fetch_webpage_links'] },
      { server: 'knowledge', tools: ['search_wikipedia', 'get_wikipedia_article', 'get_article_summary', 'get_article_sections', 'get_related_articles'] },
      { server: 'geo', tools: ['geocode', 'find_hikes', 'search_attractions', 'get_weather'] },
    ],
    inlineTools: ['propose_plan'],
  },

  {
    id: 'code-engine-deployer',
    name: 'Code Engine Deployer',
    tagline: 'Triage a docker-compose stack and deploy it to IBM Cloud Code Engine, with the agent running every CLI call under your eye',
    type: 'other',
    surface: 'gateway',
    description:
      'Hand the agent a docker-compose.yml path. It parses every service and classifies it for Code Engine readiness — CE-ready (single port, no bind mounts, sane memory), needs-work (env-secret bind mount → translate to CE Secret; large RO data → bake into image or COS), or won\'t-fit (multi-port containers, writable bind mounts to host paths). Then you tell it which subset to deploy. It walks the one-time setup (ICR namespace, registry secret so CE can pull, env secret from your .env), then per service: docker_build (always linux/amd64) → docker_push → ibmcloud ce app create — each command shown to you BEFORE it runs, results streamed back. On failure it pulls `ibmcloud ce app events` + logs and proposes one specific fix instead of retrying blindly. All shell calls are validated against allowlist regexes; no shell=True, no string interpolation.',
    category: 'enterprise',
    status: 'working',
    channels: [],
    tools: ['classify_compose_services()', 'docker_build()', 'deploy_ce_app()'],
    demoPath: 'apps/code_engine_deployer',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG'],
      setup: [
        'cd apps/code_engine_deployer',
        '# Host requirements: ibmcloud CLI + code-engine + container-registry plugins; docker CLI + daemon',
        '# Auth: ibmcloud login --sso && ibmcloud target -r <region> -g <rg>',
      ],
      command: 'python main.py --port 28818',
    },
    architecture:
      'FastAPI serves the single-page UI. /classify is a non-LLM endpoint that returns a parse + verdict for the supplied compose path so the table renders without burning an LLM call. /ask is the conversational path through CugaAgent. All tools are inline — this is a new ops domain (Code Engine + ICR) that doesn\'t fit any existing shared MCP server, and the spec\'s ≥2-consumers bar for a new MCP server isn\'t met. ce_ops.py wraps every CLI call in a strict validator: lowercase DNS-label regex for names, tag regex for image refs, region regex for ICR. subprocess.run with list args, never shell=True. Every tool returns a structured envelope including the executed command, returncode, stdout, stderr — so the agent can read the actual error from CE and propose targeted fixes.',
    diagram: `python main.py --port 28818  →  http://127.0.0.1:28818

User: "Classify /path/to/docker-compose.yml"
      │
      ▼  POST /classify  (non-LLM, pure parse)
compose_parser.parse_compose(path) → services[]
compose_parser.classify_all(...)   → verdicts[]
      │
      ▼  rendered as table on the left panel

User: "Deploy the CE-ready services to project foo"
      │
      ▼  POST /ask  (CugaAgent thread)
agent.tools = [
  parse_compose_file, classify_compose_services,
  check_prereqs, list_ce_projects, target_ce_project,
  list_ce_apps, get_ce_app, get_ce_app_logs, get_ce_app_events,
  create_ce_secret_from_env_file, create_ce_registry_secret,
  cr_login, cr_region_set, cr_namespace_add,
  docker_build, docker_push,
  deploy_ce_app, update_ce_app, delete_ce_app
]
each tool → ce_ops.<fn> → subprocess.run(list_args)
                       → {ok, command, returncode, stdout, stderr}

On failure:
  agent reads stderr → calls get_ce_app_events / get_ce_app_logs
                    → matches known patterns (ImagePullBackOff, OOM, port mismatch)
                    → proposes ONE fix → asks user to confirm`,
    cugaContribution: [
      'Conversational triage — classify-and-explain phase reads any compose file (not just cuga-apps shaped) and tells the user WHY a service won\'t fit before they try, instead of failing mid-deploy.',
      'Diagnosis loop — on `ibmcloud ce app create` failure, the agent fetches events + logs, matches the error pattern, and proposes a specific fix; no blind retries.',
      'Hard validation under the LLM — every command is built from validated args (regex allowlist + structured kwargs), so the LLM cannot shell-inject through a malformed service name or tag.',
      'Confirmation gates by default — destructive tools (delete_ce_app) require force=True and the system prompt instructs the agent to confirm the exact name with the user first.',
    ],
    examples: [
      'Classify the compose file at /home/me/work/agent-apps/cuga-apps/docker-compose.yml',
      'Deploy just the 8 MCP servers to my cuga-apps Code Engine project',
      'My mcp-web deploy is stuck in ImagePullBackOff — what is wrong?',
      'Walk me through first-time setup: ICR namespace, registry secret, env secret',
      'Update mcp-knowledge to image us.icr.io/cuga-apps/mcp:v2 and roll',
    ],
    appUrl: 'http://localhost:28818',
    mcpUsage: [],
    inlineTools: [
      'parse_compose_file', 'classify_compose_services',
      'check_prereqs', 'list_ce_projects', 'target_ce_project',
      'list_ce_apps', 'get_ce_app', 'get_ce_app_logs', 'get_ce_app_events', 'delete_ce_app',
      'create_ce_secret_from_env_file', 'create_ce_registry_secret',
      'cr_login', 'cr_region_set', 'cr_namespace_add',
      'docker_build', 'docker_push',
      'deploy_ce_app', 'update_ce_app',
    ],
  },

  {
    id: 'chief-of-staff',
    name: 'Chief of Staff',
    tagline: 'One chat over every MCP server — and a Toolsmith that acquires new tools when it hits a gap',
    type: 'other',
    surface: 'gateway',
    description:
      'A single chat UI that aggregates every MCP server in mcp_servers/* through one cuga planner. When the agent hits a gap, a separate Toolsmith service (LangGraph ReAct) goes shopping: searches a curated OpenAPI catalog + APIs.guru, generates tool code with a swappable Coder (gpt-oss or Claude), probes it, and live-mounts it back into the cuga adapter. Auth-aware (api-key, bearer, oauth2 with auto-refresh on 401), vault-backed secrets, persistent ToolArtifacts that survive restarts, optional browser-driven tools for sites without APIs (Playwright + a YAML browser-task DSL).',
    category: 'enterprise',
    status: 'partial',
    channels: [],
    tools: ['cuga adapter', 'Toolsmith', 'browser-runner'],
    demoPath: 'chief_of_staff',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'AGENT_SETTING_CONFIG', 'TOOLSMITH_CODER'],
      setup: [
        'cd chief_of_staff',
        '# MCP servers must be running first: python apps/launch.py',
      ],
      command: './start.sh   # or: docker compose up',
    },
    architecture:
      'Five services: (1) cuga-adapter (port 8000) wraps cuga.sdk.CugaAgent and exec()s artifact code under an import allowlist; (2) Toolsmith (port 8001) is a LangGraph ReAct agent with its own tool belt — search_catalog, search_openapi_index, generate_tool_code, probe_generated_tool, register_tool_artifact; (3) browser-runner (port 8002) is a Playwright + Chromium service that executes a declarative YAML DSL (go_to / click_text / fill_field / extract_text / user_confirm) for sites without APIs; (4) backend (port 8765) is the FastAPI shell + MCP discovery + registry; (5) frontend (port 5174) is the chat surface plus a tools panel. ToolArtifacts persist on disk at data/tools/<id>/ and are reloaded on restart. Secrets live in a vault (OS keyring → SQLite + base64-XOR fallback) and are injected at call time, never logged.',
    diagram: `./start.sh   →   http://127.0.0.1:5174  (frontend)
                                │
                                ▼
                  backend  :8765   (FastAPI shell, registry, MCP discovery)
                  ├─►  cuga-adapter  :8000   (planner; exec()s tool code)
                  ├─►  Toolsmith      :8001   (LangGraph ReAct, the brain)
                  └─►  browser-runner :8002   (Playwright; YAML DSL)

User: "do X"
   │
   ▼
cuga planner → tool call            ──── existing MCP tool? ──► run it
                  │
                  └── [[TOOL_GAP]]  ──► Toolsmith.acquire(intent)
                                          ├─ search_catalog (curated)
                                          ├─ search_openapi_index / APIs.guru
                                          ├─ Coder.generate_tool_code (gpt-oss or Claude)
                                          ├─ probe (structural → exec → revise×3)
                                          └─ register ToolArtifact + reload cuga
                                                       │
                                                       ▼
                                            new tool live-mounted
                                                       │
                                                       ▼
                                            retry user's request`,
    cugaContribution: [
      'Cuga planner is the swappable front end; Toolsmith is the durable brain. The planner can be replaced without losing acquired tools.',
      'Adapter exec()s LLM-generated tool code under an import allowlist — disallowed imports register as error stubs that raise on call instead of crashing the adapter.',
      'Auth-aware Coder + auto-refresh on 401 — the OAuth2 access token is swapped, retried once, and the refreshed token persisted back to the vault.',
      'ToolArtifacts are the canonical disk format (manifest.yaml + tool.py + probe.json); LangChain / MCP / OpenAPI bindings are computed from one source of truth.',
    ],
    examples: [
      "What's the weather in Berlin?  (api_key_query — openweather, seeded)",
      'Show me trending Hacker News stories  (browser source — HN scrape template)',
      'Send an email to alice@x.com with subject Y  (oauth2 — Gmail Send, paste tokens)',
      'List my Google Calendar events for next week  (oauth2 — Calendar list-events)',
      'What is the GitHub repo about for anthropics/claude-code?  (browser source — GitHub About scrape)',
    ],
    appUrl: 'http://localhost:5174',
    mcpUsage: [],
    inlineTools: [],
  },
  {
    id: 'recipe-composer',
    name: 'Recipe Composer',
    tagline: 'Tell the agent what\'s in your pantry — get 3–5 cookable recipes for tonight',
    type: 'other',
    surface: 'gateway',
    description:
      'A pantry-first home-cooking assistant with a browser UI. Tell the agent what ingredients you have, your dietary preferences (vegetarian, vegan, pescatarian, gluten-free, dairy-free, keto), and any allergies — it tracks all of it per session. When you ask for ideas, it brainstorms 3–5 dishes that use what you have, validates each against your diet/allergies, looks up rough macros from a built-in lookup table, and proposes substitutions for items you\'re missing. Recipes appear as cards in the right panel with cook time, difficulty, calorie estimate, and collapsible step-by-step instructions. All tools are inline — no MCP servers, no API keys beyond the LLM provider.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: [
      'add_to_pantry()', 'remove_from_pantry()', 'list_pantry()',
      'set_diet()', 'add_allergy()',
      'estimate_macros()', 'suggest_substitution()', 'check_diet_compatibility()',
      'save_recipes()',
    ],
    demoPath: 'apps/recipe_composer',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ANTHROPIC_API_KEY'],
      setup: [
        'cd apps/recipe_composer',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 28820',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent calls add_to_pantry / set_diet / add_allergy eagerly as the user mentions ingredients and preferences. On a recipe request: list_pantry → brainstorm dishes → check_diet_compatibility per candidate → optional estimate_macros → save_recipes (structured cards). GET /session/{thread_id} returns live pantry + diet + allergies + recipes for the right-panel poll. All tools are inline @tool defs over a per-thread session dict; no MCP, no external APIs.',
    diagram: `python main.py  →  http://127.0.0.1:28820

User: "I have chicken breast, rice, broccoli, and soy sauce"
      │  POST /ask
      ▼
CugaAgent
      ├─ add_to_pantry(thread_id=…, ingredient="chicken breast")
      ├─ add_to_pantry(thread_id=…, ingredient="rice")
      ├─ add_to_pantry(thread_id=…, ingredient="broccoli")
      ├─ add_to_pantry(thread_id=…, ingredient="soy sauce")
      │
User: "I'm vegetarian and what can I cook tonight?"
      ├─ set_diet(thread_id=…, diet="vegetarian")
      ├─ list_pantry(thread_id=…)            → pantry, diet, allergies
      ├─ check_diet_compatibility(thread_id=…, ingredients_csv="chicken breast,…")
      │      → blocked_by_diet=["chicken breast"]
      ├─ suggest_substitution(ingredient="chicken breast")
      │      → tofu, chickpeas
      ├─ estimate_macros(ingredient="rice", grams=200)
      ├─ save_recipes([{title, time_minutes, difficulty, uses, missing,
      │                 calories_est, why, steps}, …])
      ▼
Right panel: pantry + diet pills + 3–5 recipe cards w/ collapsible steps`,
    cugaContribution: [
      'Eagerly mutates per-session pantry state as the user mentions ingredients — no "add to pantry" button needed in the UI',
      'check_diet_compatibility short-circuits dishes that violate diet/allergies before they reach the user — fewer apologetic retries',
      'estimate_macros uses a static lookup table baked into the tool body — no nutrition API key, no external network call',
      'save_recipes pushes structured JSON to the UI; the right panel renders cards (with collapsible cook steps) automatically',
    ],
    examples: [
      "I have chicken breast, rice, broccoli, and soy sauce",
      "Add eggs, spinach, and tomato to my pantry",
      "I'm vegetarian and allergic to peanut butter",
      "What can I cook tonight in under 25 minutes?",
      "Roughly how many calories in a 200 g portion of pasta?",
      "What can I substitute for butter in a sauté?",
      "Anything with high protein?",
    ],
    appUrl: 'http://localhost:28820',
    mcpUsage: [],
    inlineTools: [
      'add_to_pantry', 'remove_from_pantry', 'list_pantry',
      'set_diet', 'add_allergy',
      'estimate_macros', 'suggest_substitution', 'check_diet_compatibility',
      'save_recipes',
    ],
  },
  {
    id: 'city-beat',
    name: 'City Beat',
    tagline: 'Name a city — get a one-screen briefing of weather, news, background, and (optional) crypto',
    type: 'other',
    surface: 'gateway',
    description:
      'Type a city name. The agent assembles a one-screen briefing pulling from four MCP servers: geocode + current weather (mcp-geo), today\'s news (mcp-web), encyclopedia background (mcp-knowledge), and an optional crypto market spotlight (mcp-finance). Inline session tools track the active city, an editable focus-topic list (biases the news search), a clickable watchlist of cities you\'ve visited, and an optional crypto ticker. The briefing appears as a hero card on the right (city + tagline + lat/lon), followed by weather, news headlines (linked), Wikipedia background, optional nearby attractions, optional crypto sidebar.',
    category: 'personal',
    status: 'working',
    channels: [],
    tools: [
      'geocode()', 'get_weather()', 'search_attractions()',
      'web_search()', 'get_wikipedia_article()', 'get_crypto_price()',
      'set_current_city()', 'add_focus_topic()', 'save_briefing()',
    ],
    demoPath: 'apps/city_beat',
    howToRun: {
      envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'ANTHROPIC_API_KEY'],
      setup: [
        'cd apps/city_beat',
        'pip install -r requirements.txt',
      ],
      command: 'python main.py --port 28821',
    },
    architecture:
      'FastAPI serves the single-page UI. POST /ask → CugaAgent (1) calls set_current_city + get_session_state, (2) geocodes via mcp-geo.geocode, (3) fans out to mcp-geo.get_weather + mcp-web.web_search + mcp-knowledge.get_wikipedia_article in any order, (4) optionally calls mcp-geo.search_attractions and mcp-finance.get_crypto_price, (5) calls inline save_briefing with a structured JSON object. GET /session/{thread_id} returns the live state for the right-panel poll. _mcp_bridge.load_tools resolves URLs automatically: Code Engine when CE_APP is set, docker-compose DNS in containers, localhost otherwise.',
    diagram: `python main.py  →  http://127.0.0.1:28821

User: "Brief me on Lisbon — focus on tech startups"
      │  POST /ask
      ▼
CugaAgent
      ├─ set_current_city(thread_id=…, city="Lisbon")
      ├─ add_focus_topic(thread_id=…, topic="tech startups")
      ├─ get_session_state(thread_id=…)
      ├─ geocode(place="Lisbon")              [mcp-geo]
      │      → lat, lon, display_name
      ├─ get_weather(city="Lisbon")           [mcp-geo]
      ├─ web_search(query="Lisbon news today tech startups", max_results=5) [mcp-web]
      ├─ get_wikipedia_article(title="Lisbon") [mcp-knowledge]
      ├─ (optional) search_attractions(lat, lon, category="cultural") [mcp-geo]
      ├─ (optional) get_crypto_price(symbol="eth") [mcp-finance]
      ├─ save_briefing({city, lat, lon, weather, wiki, news, attractions?, crypto?, tagline})
      ▼
Right panel: hero card + weather + news (linked) + Wikipedia + (optional)
            attractions + (optional) crypto + clickable watchlist`,
    cugaContribution: [
      'Composes tools from four MCP servers (geo, web, knowledge, finance) with six inline session-state tools — neither half stands alone',
      '_mcp_bridge auto-resolves URLs across local / docker / Code Engine — same app code, three deployment targets',
      'Inline focus_topics bias the web_search query string at composition time — no need to retrain or fork mcp-web',
      'save_briefing\'s docstring is the contract: structured JSON the right panel renders without UI-side schema knowledge',
      'Watchlist accumulates cities the user asks about — the UI re-asks on click, turning the right panel into a navigable history',
    ],
    examples: [
      "Brief me on Lisbon",
      "What's happening in Tokyo today?",
      "Brief me on Mexico City — focus on live music",
      "Spotlight ETH on the briefing",
      "What can I do in Berlin tonight?",
      "Brief me on Bangalore — focus on weather and transit",
      "Clear the focus and give me a fresh take on Paris",
    ],
    appUrl: 'http://localhost:28821',
    mcpUsage: [
      { server: 'geo',       tools: ['geocode', 'get_weather', 'search_attractions'] },
      { server: 'web',       tools: ['web_search'] },
      { server: 'knowledge', tools: ['get_wikipedia_article', 'search_wikipedia'] },
      { server: 'finance',   tools: ['get_crypto_price'] },
    ],
    inlineTools: [
      'set_current_city', 'add_focus_topic', 'clear_focus_topics',
      'set_crypto_spotlight', 'get_session_state', 'save_briefing',
    ],
  },
]

export const CATEGORIES: Record<Category, { label: string; color: string }> = {
  personal:   { label: 'Personal Productivity', color: 'green' },
  enterprise: { label: 'Enterprise',            color: 'indigo' },
}

export const STATUS_LABELS: Record<Status, { label: string; color: string }> = {
  working:       { label: 'Working',     color: 'green' },
  partial:       { label: 'Partial',     color: 'yellow' },
  'not-working': { label: 'Not working', color: 'orange' },
  gap:           { label: 'Gap',         color: 'red' },
}

export const SURFACES: Record<Surface, { label: string; tagline: string; color: string; icon: string }> = {
  gateway: {
    label: 'Conversation Gateways',
    tagline: 'A human talks to the agent in real-time — browser, Telegram, WhatsApp, or phone. One agent, any channel.',
    color: 'indigo',
    icon: '💬',
  },
  pipeline: {
    label: 'Automated Pipelines',
    tagline: 'The agent runs on a schedule or reacts to system events — cron, webhooks, folder drops, IMAP, audio/video files. No human in the loop.',
    color: 'emerald',
    icon: '⚡',
  },
}
