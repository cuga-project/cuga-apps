export type CoverageStatus = 'yes' | 'partial' | 'no'

/**
 * event-driven   — triggered by time (CronChannel) or external events
 *                  (WebhookChannel, IMAPChannel, RssChannel, CugaWatcher).
 *                  Text-only I/O.
 * multimodal     — involves non-text data: audio/voice (AudioChannel,
 *                  TTSChannel, Whisper), images (vision, DALL-E), or rich
 *                  documents (DoclingChannel / PDF).
 * both           — event-driven trigger AND multimodal data processing.
 * conversational — real-time, human-in-loop, text-based, on-demand.
 */
export type UseCaseType = 'event-driven' | 'multimodal' | 'both' | 'conversational'

export interface OpenClawUseCase {
  id: number
  name: string
  category: string
  type: UseCaseType
  /** Can cuga (agent-only, on-demand) handle this via conversation? */
  cuga: CoverageStatus
  /** Can cuga++ (full automated pipeline) handle this? */
  cugaPlusPlus: CoverageStatus
  /** What makes it work or what's missing */
  note: string
}

export const OPENCLAW_CATEGORIES = [
  'Scheduling & Briefings',
  'Email & Messaging',
  'Research & Knowledge',
  'Finance & Trading',
  'Developer Tools',
  'Document Intelligence',
  'Content Creation',
  'Productivity',
  'Monitoring & Alerts',
  'CRM & Business',
] as const

export const OPENCLAW_USE_CASES: OpenClawUseCase[] = [
  // ── Scheduling & Briefings ────────────────────────────────────────────────
  { id: 1,  name: 'Morning daily briefing',             category: 'Scheduling & Briefings', type: 'both',          cuga: 'partial', cugaPlusPlus: 'yes',     note: 'cuga++: CronChannel + TTSChannel + calendar/web tools (smart_alarm demo)' },
  { id: 2,  name: 'Evening recap / end-of-day summary', category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'CronChannel + EmailChannel' },
  { id: 3,  name: 'Weekly digest delivery',             category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'newsletter demo — CronChannel + web search + EmailChannel' },
  { id: 4,  name: 'Meeting prep briefing',              category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'cuga: ask agent directly; cuga++: CronChannel fires 30 min before each event' },
  { id: 5,  name: 'Deadline / reminder system',         category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'partial', note: 'CugaWatcher + calendar_tools; needs calendar write for creation' },
  { id: 6,  name: 'Event countdown alerts',             category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'partial', note: 'CugaWatcher polls calendar; works today with make_calendar_tools()' },
  { id: 7,  name: 'Birthday / anniversary reminders',   category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'partial', note: 'CronChannel + calendar_tools; needs contacts integration' },
  { id: 8,  name: 'Auto-schedule meeting from email',   category: 'Scheduling & Briefings', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'partial', note: 'IMAPChannel + calendar_tools; calendar write path needs testing' },

  // ── Email & Messaging ─────────────────────────────────────────────────────
  { id: 9,  name: 'Email triage & prioritisation',     category: 'Email & Messaging', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'IMAPChannel decodes MIME; agent classifies and routes (email_mcp demo)' },
  { id: 10, name: 'Email drafting assistant',           category: 'Email & Messaging', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'cuga: conversational drafting; cuga++: IMAPChannel trigger → auto-draft' },
  { id: 11, name: 'Auto-reply to common emails',        category: 'Email & Messaging', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'yes',     note: 'IMAPChannel → agent classifies → EmailChannel sends reply' },
  { id: 12, name: 'Inbox zero automation',              category: 'Email & Messaging', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'partial', note: 'IMAPChannel works; needs multi-action routing (archive, label, forward)' },
  { id: 13, name: 'Newsletter creation & delivery',     category: 'Email & Messaging', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'newsletter demo — CronChannel + web search + EmailChannel' },
  { id: 14, name: 'SMS assistant',                      category: 'Email & Messaging', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'yes',     note: 'SMSChannel (Twilio) — send; inbound SMS via WebhookChannel' },
  { id: 15, name: 'WhatsApp message handling',          category: 'Email & Messaging', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'partial', note: 'WhatsAppChannel (Twilio bridge) exists; inbound via webhook' },
  { id: 16, name: 'Telegram conversational bot',        category: 'Email & Messaging', type: 'conversational', cuga: 'partial', cugaPlusPlus: 'yes',    note: 'telegram_agent demo — TelegramChannel bidirectional' },
  { id: 17, name: 'Discord community bot',              category: 'Email & Messaging', type: 'conversational', cuga: 'partial', cugaPlusPlus: 'yes',    note: 'discord_agent demo — DiscordChannel bidirectional' },
  { id: 18, name: 'Slack team notifications',           category: 'Email & Messaging', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'yes',     note: 'SlackChannel (webhook out); SlackDataChannel for inbound' },

  // ── Research & Knowledge ──────────────────────────────────────────────────
  { id: 19, name: 'On-demand web research',             category: 'Research & Knowledge', type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',   note: 'make_web_search_tool() — Tavily; web_researcher demo' },
  { id: 20, name: 'News aggregation briefing',          category: 'Research & Knowledge', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'CronChannel + web_search + EmailChannel/TelegramChannel' },
  { id: 21, name: 'Academic paper summarisation',       category: 'Research & Knowledge', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'RssChannel (arXiv) + make_rag_tools() for indexing' },
  { id: 22, name: 'Competitor monitoring (weekly)',     category: 'Research & Knowledge', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'CronChannel + web_search + SlackChannel — killer use case' },
  { id: 23, name: 'Market research report',             category: 'Research & Knowledge', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'CronChannel + web_search + EmailChannel' },
  { id: 24, name: 'Quick Q&A / factual lookup',        category: 'Research & Knowledge', type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',    note: 'Any channel → web_search → reply' },
  { id: 25, name: 'Social media content monitoring',    category: 'Research & Knowledge', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'partial', note: 'Needs make_twitter_tool() (Sprint 4 roadmap)' },
  { id: 26, name: 'RSS feed summarisation',             category: 'Research & Knowledge', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'RssChannel → agent summarises → EmailChannel/SlackChannel' },
  { id: 27, name: 'Podcast / article digest',           category: 'Research & Knowledge', type: 'both',          cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'AudioChannel (podcast) or RssChannel + web_search' },
  { id: 28, name: 'Personal knowledge base Q&A',        category: 'Research & Knowledge', type: 'conversational', cuga: 'partial', cugaPlusPlus: 'yes',   note: 'make_rag_tools() + TelegramChannel — mcp_second_brain demo' },

  // ── Finance & Trading ─────────────────────────────────────────────────────
  { id: 29, name: 'Stock price alerts',                 category: 'Finance & Trading', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'stock_alert demo — CugaWatcher + make_market_data_tools()' },
  { id: 30, name: 'Crypto price monitoring',            category: 'Finance & Trading', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'stock_alert demo — CoinGecko via market_data_tools' },
  { id: 31, name: 'Portfolio performance tracker',      category: 'Finance & Trading', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'partial', note: 'CronChannel + market_data_tools; needs make_pandas_tool() for analysis' },
  { id: 32, name: 'Invoice data extraction',            category: 'Finance & Trading', type: 'multimodal',    cuga: 'partial', cugaPlusPlus: 'yes',     note: 'DoclingChannel (PDF) → agent extracts → EmailChannel/LogChannel' },
  { id: 33, name: 'Expense report generation',          category: 'Finance & Trading', type: 'multimodal',    cuga: 'partial', cugaPlusPlus: 'partial', note: 'DoclingChannel extracts; make_pandas_tool() for aggregation (roadmap)' },
  { id: 34, name: 'Budget analysis',                    category: 'Finance & Trading', type: 'multimodal',    cuga: 'partial', cugaPlusPlus: 'partial', note: 'DoclingChannel + make_pandas_tool() (roadmap Sprint 4)' },
  { id: 35, name: 'Price drop / deal alert',            category: 'Finance & Trading', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'partial', note: 'CugaWatcher + web_search; no native e-commerce API tool yet' },

  // ── Developer Tools ───────────────────────────────────────────────────────
  { id: 36, name: 'Code review assistant',              category: 'Developer Tools', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'github_agent demo — make_github_tools() + CronChannel or WebhookChannel' },
  { id: 37, name: 'GitHub PR digest',                   category: 'Developer Tools', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'github_agent demo — daily CronChannel + list_pull_requests' },
  { id: 38, name: 'CI/CD failure alert & triage',      category: 'Developer Tools', type: 'event-driven',  cuga: 'no',      cugaPlusPlus: 'yes',     note: 'cicd_alerter demo — WebhookChannel + SlackChannel, zero polling' },
  { id: 39, name: 'Dependency vulnerability audit',     category: 'Developer Tools', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'dev_tools demo — make_shell_tools() + pip-audit' },
  { id: 40, name: 'Test coverage reporting',            category: 'Developer Tools', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'yes',     note: 'dev_tools demo — make_shell_tools() + pytest --cov' },
  { id: 41, name: 'Git activity summary',               category: 'Developer Tools', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'make_shell_tools() + make_github_tools(); CronChannel for weekly summary' },
  { id: 42, name: 'Documentation generator',           category: 'Developer Tools', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'make_shell_tools() reads source; agent writes docs; EmailChannel delivers' },
  { id: 43, name: 'Bug / issue triage',                category: 'Developer Tools', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'partial', note: 'make_github_tools() list_issues; WebhookChannel for realtime (partial)' },

  // ── Document Intelligence ─────────────────────────────────────────────────
  { id: 44, name: 'PDF summarisation',                  category: 'Document Intelligence', type: 'both',       cuga: 'partial', cugaPlusPlus: 'yes',     note: 'drop_summarizer demo — CugaWatcher + DoclingChannel' },
  { id: 45, name: 'Contract clause extraction',         category: 'Document Intelligence', type: 'multimodal', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'doc_intel demo — DoclingChannel pre-extracts → agent classifies' },
  { id: 46, name: 'Invoice / receipt processing',       category: 'Document Intelligence', type: 'multimodal', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'DoclingChannel (PDF) → structured extraction → LogChannel' },
  { id: 47, name: 'Resume / CV screening',              category: 'Document Intelligence', type: 'multimodal', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'DoclingChannel batch + make_rag_tools() for ranking' },
  { id: 48, name: 'Report generation from data',        category: 'Document Intelligence', type: 'event-driven', cuga: 'yes',   cugaPlusPlus: 'yes',     note: 'Any channel triggers; agent synthesises; EmailChannel delivers' },
  { id: 49, name: 'Form auto-fill from document',       category: 'Document Intelligence', type: 'multimodal', cuga: 'partial', cugaPlusPlus: 'no',      note: 'Gap: no browser automation to fill web forms' },
  { id: 50, name: 'Multi-document comparison',          category: 'Document Intelligence', type: 'multimodal', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'DoclingChannel (batch) + make_rag_tools() for cross-doc search' },
  { id: 51, name: 'Batch document ingestion & index',  category: 'Document Intelligence', type: 'multimodal', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'doc_pipeline demo — DoclingChannel + make_rag_tools() + ChromaDB' },

  // ── Content Creation ──────────────────────────────────────────────────────
  { id: 52, name: 'Blog post drafting',                 category: 'Content Creation', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'WebhookChannel triggers; agent drafts; EmailChannel delivers' },
  { id: 53, name: 'Social media post scheduling',       category: 'Content Creation', type: 'event-driven',  cuga: 'partial', cugaPlusPlus: 'partial', note: 'CronChannel ready; needs make_twitter_tool() for posting (Sprint 4)' },
  { id: 54, name: 'Image generation',                   category: 'Content Creation', type: 'multimodal',    cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'make_image_generation_tool() (DALL-E 3) — image_chat demo' },
  { id: 55, name: 'Video script writing',               category: 'Content Creation', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'CronChannel + web_search → script → EmailChannel' },
  { id: 56, name: 'SEO content assistant',              category: 'Content Creation', type: 'conversational', cuga: 'yes',    cugaPlusPlus: 'yes',     note: 'make_web_search_tool() for keyword research; agent writes copy' },
  { id: 57, name: 'Podcast show notes',                 category: 'Content Creation', type: 'multimodal',    cuga: 'partial', cugaPlusPlus: 'yes',     note: 'AudioChannel transcribes → agent writes show notes → EmailChannel' },
  { id: 58, name: 'Interactive HTML / web app gen',     category: 'Content Creation', type: 'conversational', cuga: 'partial', cugaPlusPlus: 'no',     note: 'Gap: agent can write HTML but no WebAppOutputChannel to deploy it' },

  // ── Productivity ──────────────────────────────────────────────────────────
  { id: 59, name: 'Task management assistant',          category: 'Productivity', type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'smart_todo demo — make_rag_tools() + TelegramChannel' },
  { id: 60, name: 'Calendar scheduling assistant',      category: 'Productivity', type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'calendar_agent demo — make_calendar_tools() + TelegramChannel' },
  { id: 61, name: 'Smart alarm (voice morning brief)',  category: 'Productivity', type: 'both',           cuga: 'no',      cugaPlusPlus: 'yes',     note: 'smart_alarm demo — CronChannel + TTSChannel (ElevenLabs / say)' },
  { id: 62, name: 'Note-taking & organisation',         category: 'Productivity', type: 'both',           cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'make_rag_tools() + TelegramChannel; voice via AudioChannel' },
  { id: 63, name: 'Meeting summarisation',              category: 'Productivity', type: 'multimodal',    cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'AudioChannel (recording) + agent summarises + EmailChannel' },
  { id: 64, name: 'Action items from meeting',          category: 'Productivity', type: 'multimodal',    cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'AudioChannel + agent extracts actions + EmailChannel/SlackChannel' },
  { id: 65, name: 'Daily standup preparation',          category: 'Productivity', type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'CronChannel + make_github_tools() + make_calendar_tools() + SlackChannel' },
  { id: 66, name: 'Focus session / Pomodoro manager',  category: 'Productivity', type: 'multimodal',    cuga: 'partial', cugaPlusPlus: 'partial', note: 'TTSChannel can announce; CronChannel can time; no real-time interaction yet' },

  // ── Monitoring & Alerts ───────────────────────────────────────────────────
  { id: 67, name: 'Server health monitoring',           category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'yes',     note: 'server_monitor demo — CugaWatcher + make_shell_tools() + SlackChannel' },
  { id: 68, name: 'Website uptime monitoring',          category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'partial', note: 'CugaWatcher + make_shell_tools() (curl check); no dedicated channel yet' },
  { id: 69, name: 'Brand mention alerts',               category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'partial', note: 'Needs make_twitter_tool() for social monitoring (Sprint 4 roadmap)' },
  { id: 70, name: 'Job posting monitor',                category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'partial', note: 'CugaWatcher + web_search; no structured job board API yet' },
  { id: 71, name: 'Domain / SSL expiry alerts',         category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'partial', note: 'CugaWatcher + make_shell_tools() (openssl check); works today' },
  { id: 72, name: 'GitHub issues / PRs monitor',        category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'github_agent + CronChannel; WebhookChannel for realtime events' },
  { id: 73, name: 'Threshold / anomaly alerting',       category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'yes',     note: 'CugaWatcher (compound conditions) + any output channel' },
  { id: 74, name: 'RSS / news keyword alert',           category: 'Monitoring & Alerts', type: 'event-driven', cuga: 'no',      cugaPlusPlus: 'yes',     note: 'RssChannel + agent filters by keyword + TelegramChannel/EmailChannel' },

  // ── CRM & Business ────────────────────────────────────────────────────────
  { id: 75, name: 'Lead scoring from CRM webhook',      category: 'CRM & Business', type: 'event-driven', cuga: 'yes',     cugaPlusPlus: 'partial', note: 'WebhookChannel works; needs make_hubspot_tool() for write-back (Sprint 4)' },
  { id: 76, name: 'CRM contact enrichment',             category: 'CRM & Business', type: 'event-driven', cuga: 'yes',     cugaPlusPlus: 'partial', note: 'crm demo — web_search + MCPToolBridge; HubSpot MCP server needed' },
  { id: 77, name: 'Customer support ticket triage',     category: 'CRM & Business', type: 'event-driven', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'IMAPChannel / WebhookChannel → classify → EmailChannel response' },
  { id: 78, name: 'Sales pipeline monitoring',          category: 'CRM & Business', type: 'event-driven', cuga: 'partial', cugaPlusPlus: 'partial', note: 'WebhookChannel + MCPToolBridge (HubSpot); make_hubspot_tool() on roadmap' },
  { id: 79, name: 'Meeting follow-up automation',       category: 'CRM & Business', type: 'both',         cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'AudioChannel + agent extracts action items + EmailChannel sends follow-ups' },
  { id: 80, name: 'Contract renewal reminders',         category: 'CRM & Business', type: 'both',         cuga: 'partial', cugaPlusPlus: 'partial', note: 'DoclingChannel extracts dates + CronChannel reminder; contacts integration partial' },
  { id: 81, name: 'Travel itinerary planning',          category: 'CRM & Business', type: 'event-driven', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'WebhookChannel + web_search + calendar_tools + EmailChannel' },
  { id: 82, name: 'Health & fitness tracking',          category: 'CRM & Business', type: 'event-driven', cuga: 'partial', cugaPlusPlus: 'yes',     note: 'health demo — TelegramChannel + make_rag_tools() (CronChannel daily summary)' },
]

// Manus use cases with cuga column added
export interface ManusUseCase2 {
  id: number
  name: string
  type: UseCaseType
  cuga: CoverageStatus
  cugaPlusPlus: CoverageStatus
  note: string
}

export const MANUS_USE_CASES_COVERAGE: ManusUseCase2[] = [
  { id: 1,  name: 'Company biography / research report',  type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'web_researcher demo; cuga++: CronChannel → weekly competitive report' },
  { id: 2,  name: 'Interactive educational website',       type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'no',      note: 'Agent can write content; gap: no HTML/WebApp output channel' },
  { id: 3,  name: 'Interview scheduling automation',       type: 'event-driven',   cuga: 'partial', cugaPlusPlus: 'partial', note: 'make_calendar_tools() + IMAPChannel; write-back to calendar partial' },
  { id: 4,  name: 'B2B supplier research',                 type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'web_search + structured output → EmailChannel' },
  { id: 5,  name: 'Travel planning / itinerary',           type: 'event-driven',   cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'WebhookChannel → agent → EmailChannel; web_search for flights/hotels' },
  { id: 6,  name: 'E-commerce analytics dashboard',        type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'partial', note: 'Agent can analyse data; gap: no dashboard/chart output channel' },
  { id: 7,  name: 'Financial analysis (stock reports)',    type: 'event-driven',   cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'make_market_data_tools() + make_rag_tools(); CronChannel weekly report' },
  { id: 8,  name: 'Data list / database compilation',      type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'web_search + make_rag_tools() for ingestion + EmailChannel delivery' },
  { id: 9,  name: 'Interactive web applications',          type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'no',      note: 'Gap: no web app generation or deployment channel' },
  { id: 10, name: 'Scientific research website',           type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'no',      note: 'Gap: same as #9 — no static site generation output' },
  { id: 11, name: 'Study materials / flashcard decks',     type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'web_search + agent generates flashcards + TelegramChannel delivery' },
  { id: 12, name: 'Climate / data visualisation',          type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'partial', note: 'Agent writes text report; gap: no chart generation tool yet' },
  { id: 13, name: 'Market research / competitive analysis',type: 'event-driven',   cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'Killer use case — CronChannel weekly + web_search + SlackChannel' },
  { id: 14, name: 'Business plan / pitch deck content',    type: 'conversational', cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'WebhookChannel + web_search + EmailChannel; agent writes structured content' },
  { id: 15, name: 'CRM auto-update / workflow automation', type: 'event-driven',   cuga: 'partial', cugaPlusPlus: 'partial', note: 'MCPToolBridge + CRM MCP server; make_hubspot_tool() on Sprint 4 roadmap' },
  { id: 16, name: 'HR — resume analysis',                  type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'yes',     note: 'DoclingChannel (PDF batch) → agent scores → structured output' },
  { id: 17, name: 'Invoice data extraction',               type: 'multimodal',     cuga: 'partial', cugaPlusPlus: 'yes',     note: 'DoclingChannel (PDF) → agent extracts → EmailChannel / LogChannel' },
  { id: 18, name: 'Customer support ticket triage',        type: 'event-driven',   cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'IMAPChannel / WebhookChannel → agent classifies → EmailChannel reply' },
  { id: 19, name: 'Content creation (scripts, storyboards)',type: 'event-driven',  cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'CronChannel or WebhookChannel → agent writes → EmailChannel / SlackChannel' },
  { id: 20, name: 'Academic research summaries',           type: 'event-driven',   cuga: 'yes',     cugaPlusPlus: 'yes',     note: 'web_search + DoclingChannel + make_rag_tools(); RssChannel for arXiv' },
]
