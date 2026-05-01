export interface ComparisonRow {
  capability: string
  openclaw: string
  openclaw_status: 'yes' | 'no' | 'partial'
  cuga: string
  cuga_status: 'yes' | 'no' | 'partial'
}

export interface ComparisonSection {
  title: string
  rows: ComparisonRow[]
}

export const COMPARISON_SECTIONS: ComparisonSection[] = [
  {
    title: 'Triggers',
    rows: [
      { capability: 'Cron scheduling', openclaw: 'Built-in, SQLite-persisted, 40+ test cases', openclaw_status: 'yes', cuga: 'CronChannel', cuga_status: 'yes' },
      { capability: 'Webhooks', openclaw: 'Webhook tool', openclaw_status: 'yes', cuga: 'WebhookChannel', cuga_status: 'yes' },
      { capability: 'Threshold watcher', openclaw: 'Dreaming mode (undocumented)', openclaw_status: 'partial', cuga: 'CugaWatcher (explicit, composable)', cuga_status: 'yes' },
      { capability: 'Incoming messages', openclaw: '20+ chat platforms', openclaw_status: 'yes', cuga: '6 platforms (Telegram, Discord, Slack, IMAP, RSS, Audio)', cuga_status: 'yes' },
      { capability: 'Voice wake word', openclaw: 'macOS, iOS, Android', openclaw_status: 'yes', cuga: 'Not yet', cuga_status: 'no' },
      { capability: 'File drop trigger', openclaw: 'Not supported', openclaw_status: 'no', cuga: 'DoclingChannel, AudioChannel', cuga_status: 'yes' },
    ],
  },
  {
    title: 'Data In',
    rows: [
      { capability: 'RSS/Atom feeds', openclaw: 'Web search, not feed parsing', openclaw_status: 'partial', cuga: 'RssChannel', cuga_status: 'yes' },
      { capability: 'Email (IMAP)', openclaw: 'Via Himalaya skill (CLI wrapper)', openclaw_status: 'partial', cuga: 'IMAPChannel (native)', cuga_status: 'yes' },
      { capability: 'Document extraction (PDF, OCR)', openclaw: 'Via PDF.js tool', openclaw_status: 'partial', cuga: 'DoclingChannel (pre-extracts before agent)', cuga_status: 'yes' },
      { capability: 'Audio transcription', openclaw: 'Whisper, Deepgram, Sherpa', openclaw_status: 'yes', cuga: 'AudioChannel (Whisper)', cuga_status: 'yes' },
      { capability: 'Browser content', openclaw: 'Full Chrome CDP', openclaw_status: 'yes', cuga: 'Not yet', cuga_status: 'no' },
      { capability: 'Database input', openclaw: 'Not supported', openclaw_status: 'no', cuga: 'On roadmap', cuga_status: 'no' },
    ],
  },
  {
    title: 'Agent & Reasoning',
    rows: [
      { capability: 'LLM providers', openclaw: '30+ (Anthropic, OpenAI, Ollama, etc.)', openclaw_status: 'yes', cuga: '6+ (same list, LangGraph-based)', cuga_status: 'yes' },
      { capability: 'Local / air-gapped (Ollama)', openclaw: 'Supported', openclaw_status: 'yes', cuga: 'Supported', cuga_status: 'yes' },
      { capability: 'Plugin system', openclaw: 'Skills (.md files + TypeScript modules)', openclaw_status: 'yes', cuga: 'CugaSkillsPlugin (.md skill files)', cuga_status: 'yes' },
      { capability: 'Tool calling', openclaw: '20+ built-in tools', openclaw_status: 'yes', cuga: 'Factory pattern (make_*_tools())', cuga_status: 'yes' },
      { capability: 'Multi-agent spawning', openclaw: 'Subagent spawning via session tool', openclaw_status: 'yes', cuga: 'Not yet (on roadmap)', cuga_status: 'no' },
      { capability: 'Eval / testing framework', openclaw: 'Not supported', openclaw_status: 'no', cuga: 'On roadmap (potential moat)', cuga_status: 'no' },
      { capability: 'MCP support', openclaw: 'Not supported', openclaw_status: 'no', cuga: 'MCPToolBridge', cuga_status: 'yes' },
    ],
  },
  {
    title: 'Output',
    rows: [
      { capability: 'Email', openclaw: 'Via Himalaya skill', openclaw_status: 'partial', cuga: 'EmailChannel', cuga_status: 'yes' },
      { capability: 'Slack', openclaw: 'Skill', openclaw_status: 'yes', cuga: 'SlackChannel', cuga_status: 'yes' },
      { capability: 'Telegram', openclaw: 'Channel', openclaw_status: 'yes', cuga: 'TelegramChannel', cuga_status: 'yes' },
      { capability: 'Discord', openclaw: 'Channel', openclaw_status: 'yes', cuga: 'DiscordChannel', cuga_status: 'yes' },
      { capability: 'SMS', openclaw: 'Not supported', openclaw_status: 'no', cuga: 'SMSChannel (Twilio)', cuga_status: 'yes' },
      { capability: 'WhatsApp', openclaw: 'Channel', openclaw_status: 'yes', cuga: 'WhatsAppChannel', cuga_status: 'yes' },
      { capability: 'Voice / TTS', openclaw: 'ElevenLabs, macOS say', openclaw_status: 'yes', cuga: 'TTSChannel (ElevenLabs → say → pyttsx3)', cuga_status: 'yes' },
      { capability: 'Image generation', openclaw: 'Tool', openclaw_status: 'yes', cuga: 'make_image_generation_tool()', cuga_status: 'yes' },
      { capability: 'Browser actions', openclaw: 'Chrome CDP', openclaw_status: 'yes', cuga: 'Not yet', cuga_status: 'no' },
    ],
  },
  {
    title: 'Developer Experience',
    rows: [
      { capability: 'Language', openclaw: 'TypeScript / Node.js', openclaw_status: 'partial', cuga: 'Python (AI ecosystem native)', cuga_status: 'yes' },
      { capability: 'LangChain/LangGraph composability', openclaw: 'Not supported', openclaw_status: 'no', cuga: 'Any LangGraph agent works', cuga_status: 'yes' },
      { capability: 'Multi-user / team deployment', openclaw: 'Explicitly single-user', openclaw_status: 'no', cuga: 'Designed for this', cuga_status: 'yes' },
      { capability: 'Docker / server deployment', openclaw: 'Possible but not primary', openclaw_status: 'partial', cuga: 'Primary use case', cuga_status: 'yes' },
      { capability: 'Pipeline-as-code', openclaw: 'Imperative, message-driven', openclaw_status: 'partial', cuga: 'Declarative pipeline objects', cuga_status: 'yes' },
      { capability: 'Skill marketplace', openclaw: 'ClawHub registry (50+ skills)', openclaw_status: 'yes', cuga: 'No marketplace yet', cuga_status: 'no' },
      { capability: 'Mobile device pairing', openclaw: 'iOS/Android (camera, mic, commands)', openclaw_status: 'yes', cuga: 'Not supported', cuga_status: 'no' },
    ],
  },
]

export interface ManusUseCase {
  id: number
  name: string
  status: 'working' | 'partial' | 'gap'
  notes: string
  channels: string[]
}

export const MANUS_USE_CASES: ManusUseCase[] = [
  { id: 1, name: 'Company biography / research report', status: 'working', notes: 'make_web_search_tool() + Email/Slack output', channels: ['CronChannel', 'EmailChannel'] },
  { id: 2, name: 'Interactive educational website', status: 'gap', notes: 'No HTML generation output channel', channels: [] },
  { id: 3, name: 'Interview scheduling automation', status: 'partial', notes: 'make_calendar_tools() + IMAPChannel', channels: ['IMAPChannel', 'EmailChannel'] },
  { id: 4, name: 'B2B supplier research', status: 'working', notes: 'Web search + structured output', channels: ['CronChannel', 'EmailChannel'] },
  { id: 5, name: 'Travel planning / itinerary', status: 'working', notes: 'WebhookChannel → agent → Email/Telegram', channels: ['WebhookChannel', 'TelegramChannel'] },
  { id: 6, name: 'E-commerce analytics dashboard', status: 'partial', notes: 'Agent can analyse, no HTML dashboard output', channels: [] },
  { id: 7, name: 'Financial analysis (stock reports)', status: 'working', notes: 'make_market_data_tools() + make_rag_tools()', channels: ['CronChannel', 'SlackChannel'] },
  { id: 8, name: 'Data list / database compilation', status: 'working', notes: 'Web search + RAG ingestion', channels: ['CronChannel', 'EmailChannel'] },
  { id: 9, name: 'Interactive web applications', status: 'gap', notes: 'No web app generation', channels: [] },
  { id: 10, name: 'Scientific research website', status: 'gap', notes: 'No web page generation', channels: [] },
  { id: 11, name: 'Study materials / flashcard decks', status: 'working', notes: 'Web search + Email/Telegram output', channels: ['CronChannel', 'TelegramChannel'] },
  { id: 12, name: 'Climate / data visualization', status: 'partial', notes: 'Agent writes report; no chart generation yet', channels: [] },
  { id: 13, name: 'Market research / competitive analysis', status: 'working', notes: 'Killer use case — CronChannel weekly → Slack', channels: ['CronChannel', 'SlackChannel'] },
  { id: 14, name: 'Business plan / pitch deck content', status: 'working', notes: 'WebhookChannel + web search → Email', channels: ['WebhookChannel', 'EmailChannel'] },
  { id: 15, name: 'CRM auto-update / workflow automation', status: 'partial', notes: 'MCPToolBridge + CRM MCP server', channels: ['WebhookChannel'] },
  { id: 16, name: 'HR — resume analysis', status: 'working', notes: 'DoclingChannel (PDF) → structured output', channels: ['DoclingChannel', 'EmailChannel'] },
  { id: 17, name: 'Invoice data extraction', status: 'working', notes: 'DoclingChannel (PDF) → Email/Log', channels: ['DoclingChannel', 'LogChannel'] },
  { id: 18, name: 'Customer support ticket triage', status: 'working', notes: 'IMAPChannel / WebhookChannel → Email', channels: ['IMAPChannel', 'EmailChannel'] },
  { id: 19, name: 'Content creation (scripts, storyboards)', status: 'working', notes: 'CronChannel or WebhookChannel → Email/Slack', channels: ['CronChannel', 'EmailChannel'] },
  { id: 20, name: 'Academic research summaries', status: 'working', notes: 'Web search + DoclingChannel + RAG', channels: ['CronChannel', 'EmailChannel'] },
]
