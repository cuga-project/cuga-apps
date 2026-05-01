// The Moat — what is actually defensible about CUGA++ in an enterprise setting?
// Honest analysis: what can be copied in a weekend vs what compounds over time.

// ── Enterprise use cases that illustrate the moat ────────────────────────────

interface EnterpriseUC {
  id: string
  title: string
  tag: string
  tagColor: string
  surface: 'Event-Driven' | 'Multimodal' | 'Multi-Agent' | 'Gateway'
  surfaceColor: string
  problem: string
  howCuga: string
  channels: string[]
  whyHard: string  // what makes this hard to replicate without CUGA++
}

const ENTERPRISE_USE_CASES: EnterpriseUC[] = [
  {
    id: 'contract-review',
    title: 'Contract Review Pipeline',
    tag: 'Legal',
    tagColor: 'bg-purple-900/30 text-purple-300 border-purple-800/40',
    surface: 'Event-Driven',
    surfaceColor: 'text-emerald-400',
    problem:
      'A legal team receives 200+ vendor contracts per month via email. Each must be reviewed for non-standard clauses, liability caps, and IP ownership terms. Manual review takes 2–4 hours each.',
    howCuga:
      'IMAPChannel watches the contracts inbox. Each inbound email triggers CugaRuntime. DoclingChannel extracts structured text from PDF/DOCX. A skills-equipped CugaAgent (legal_review.md, ip_clauses.md, liability_flags.md) analyses each contract and routes to Slack with a risk summary. High-risk contracts trigger a human-in-the-loop approval step.',
    channels: ['IMAPChannel', 'DoclingChannel', 'SlackChannel', 'CugaSkillsPlugin'],
    whyHard:
      'Requires multimodal extraction (DoclingChannel handles scanned PDFs, tables, section headers), persistent conversation state per contract thread, and legal-domain skills encoded as .md files. Replicating this without the full I/O runtime means wiring 5 separate systems.',
  },
  {
    id: 'incident-response',
    title: 'Automated Incident Response',
    tag: 'SRE / Ops',
    tagColor: 'bg-red-900/30 text-red-300 border-red-800/40',
    surface: 'Event-Driven',
    surfaceColor: 'text-emerald-400',
    problem:
      'On-call engineers are paged for incidents at 3am. 60% are false positives or require only a standard runbook action. The cognitive load of triage at off-hours degrades both response quality and engineer wellbeing.',
    howCuga:
      'WebhookChannel receives PagerDuty/Alertmanager webhooks. CugaAgent (sre_runbook.md, incident_triage.md) classifies severity, checks related metrics via make_web_search_tool() + MCPToolBridge (Datadog MCP), and either auto-resolves (false positive) or drafts a pre-populated incident report and pages the on-call engineer with context. CronChannel runs post-incident retros weekly.',
    channels: ['WebhookChannel', 'CronChannel', 'MCPToolBridge', 'SlackChannel', 'CugaSkillsPlugin'],
    whyHard:
      'Event-driven + scheduled in the same runtime. The same agent that handles real-time webhook alerts also runs the weekly retro cron job. Skills encode org-specific runbooks — not generic LLM knowledge.',
  },
  {
    id: 'meeting-intelligence',
    title: 'Meeting Intelligence — Full Pipeline',
    tag: 'Productivity',
    tagColor: 'bg-blue-900/30 text-blue-300 border-blue-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'Executive meetings produce decisions that never get captured. Action items are discussed but not tracked. New team members have no institutional memory to query.',
    howCuga:
      'Video/audio ingested via AudioChannel → Whisper transcription + speaker diarization (pyannote). Slide decks parsed via DoclingChannel. Keyframes extracted and described via QWEN2-VL. All indexed into ChromaDB. ConversationGateway exposes a Q&A interface ("What did we decide about the API roadmap in Q1?"). CronChannel sends weekly action item digests to Slack/Jira.',
    channels: ['AudioChannel', 'DoclingChannel', 'QWEN2-VL', 'ChromaDB', 'ConversationGateway', 'CronChannel', 'SlackChannel'],
    whyHard:
      'True multimodal pipeline: audio + PDF + video keyframes all indexed together, queryable in a single semantic search. No other agent framework has first-class support for this combination. The ConversationGateway means employees can ask questions in natural language via browser or Slack — not a separate app.',
  },
  {
    id: 'financial-report-monitor',
    title: 'Earnings Report Monitor',
    tag: 'Finance',
    tagColor: 'bg-yellow-900/30 text-yellow-300 border-yellow-800/40',
    surface: 'Event-Driven',
    surfaceColor: 'text-emerald-400',
    problem:
      'Analyst teams need to process 50+ earnings reports per quarter. Each PDF is 80–120 pages. Key figures (revenue, guidance, risk factors) must be extracted and compared to prior quarters within minutes of release.',
    howCuga:
      'CugaWatcher monitors SEC EDGAR / IR pages for new filings. On detection, DoclingChannel parses the PDF (tables, footnotes, highlighted figures). CugaAgent (financial_analysis.md, risk_factors.md) extracts key metrics, diffs against prior quarter stored in memory, and pushes a structured summary to Slack and Google Sheets via MCPToolBridge.',
    channels: ['CugaWatcher', 'DoclingChannel', 'MCPToolBridge', 'SlackChannel', 'CugaSkillsPlugin'],
    whyHard:
      'DoclingChannel preserves table structure from complex financial PDFs — critical for earnings data where a misread row means a wrong number. Skills encode analyst-specific extraction heuristics that generic LLMs don\'t have.',
  },
  {
    id: 'multimodal-support',
    title: 'Multimodal Customer Support Gateway',
    tag: 'Support',
    tagColor: 'bg-cyan-900/30 text-cyan-300 border-cyan-800/40',
    surface: 'Gateway',
    surfaceColor: 'text-indigo-400',
    problem:
      'Enterprise support teams handle tickets that include screenshots, log files, error traces, and voice messages — in addition to text. Routing and initial triage is manual because most ticketing systems can\'t parse the attachments.',
    howCuga:
      'ConversationGateway exposes the support agent on browser (existing helpdesk embed) + WhatsApp (field teams) + Voice/phone (legacy users). Inbound messages with image attachments are processed by a vision-enabled CugaAgent (QWEN2-VL for screenshots, DoclingChannel for attached PDFs). Agent classifies, triages, and either auto-resolves or escalates with a structured context packet.',
    channels: ['ConversationGateway', 'WhatsApp adapter', 'Voice adapter', 'QWEN2-VL', 'DoclingChannel'],
    whyHard:
      'Same agent accessible on 3 surfaces simultaneously. A WhatsApp message with a screenshot gets the same analysis as a browser session. Multimodal understanding at the gateway layer — not a post-processing step.',
  },
  {
    id: 'code-review-agent',
    title: 'PR Review & Security Scan Agent',
    tag: 'Engineering',
    tagColor: 'bg-orange-900/30 text-orange-300 border-orange-800/40',
    surface: 'Event-Driven',
    surfaceColor: 'text-emerald-400',
    problem:
      'Engineering teams at scale have too many PRs for thorough human review. Security issues (hardcoded secrets, OWASP top 10 patterns, dependency vulnerabilities) slip through. Junior engineers lack context on architectural decisions.',
    howCuga:
      'WebhookChannel receives GitHub PR opened/updated events. CugaAgent (code_review.md, security_scan.md, architecture_patterns.md) analyses the diff via MCPToolBridge (GitHub MCP), checks for security patterns, comments inline on the PR, and posts a structured review to Slack. CugaSupervisor routes complex architectural questions to a senior-dev-skills agent.',
    channels: ['WebhookChannel', 'MCPToolBridge', 'SlackChannel', 'CugaSkillsPlugin', 'CugaSupervisor'],
    whyHard:
      'Multi-agent routing: simple PRs handled by base agent, complex ones escalated to supervisor with different skills. MCPToolBridge to GitHub MCP means no custom GitHub client code. Skills encode org-specific patterns (naming conventions, library choices, security policies).',
  },
  {
    id: 'supply-chain-monitor',
    title: 'Supply Chain Event Monitor',
    tag: 'Operations',
    tagColor: 'bg-teal-900/30 text-teal-300 border-teal-800/40',
    surface: 'Event-Driven',
    surfaceColor: 'text-emerald-400',
    problem:
      'Operations teams monitor dozens of supplier feeds, logistics APIs, and news sources for disruptions. A port strike in Rotterdam, a chip shortage announcement, a supplier financial filing — each requires different response playbooks.',
    howCuga:
      'CugaWatcher monitors supplier API feeds and news RSS. WebhookChannel receives logistics platform webhooks (FedEx, DHL). CronChannel runs daily digest. CugaAgent (supply_chain_risk.md, procurement_escalation.md) classifies each event by impact tier, cross-references with current open orders via MCPToolBridge (ERP MCP), and triggers the appropriate playbook (email procurement, update ETA in system, escalate to VP).',
    channels: ['CugaWatcher', 'WebhookChannel', 'CronChannel', 'MCPToolBridge', 'EmailChannel', 'CugaSkillsPlugin'],
    whyHard:
      'Three trigger types in one runtime: continuous watcher + webhook + scheduled digest. Most agent frameworks force you to choose one trigger pattern per deployment. The same agent handles all three with shared conversation memory and skills.',
  },
  {
    id: 'compliance-monitor',
    title: 'Regulatory Change Monitor',
    tag: 'Compliance',
    tagColor: 'bg-indigo-900/30 text-indigo-300 border-indigo-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'Compliance teams at financial institutions must track regulatory changes across 15+ regulators (SEC, FINRA, FCA, EBA…). New guidance documents, consultation papers, and rule amendments are published as PDFs. Manual monitoring is impossible at scale.',
    howCuga:
      'CugaWatcher monitors regulator RSS/ATOM feeds. New documents trigger DoclingChannel to extract structured text (headings, tables, effective dates). CugaAgent (regulatory_analysis.md, impact_assessment.md) assesses impact on current policies, cross-references against an internal policy library (ChromaDB RAG), and generates a change impact report routed to compliance officers via email and the ConversationGateway Q&A interface.',
    channels: ['CugaWatcher', 'DoclingChannel', 'ChromaDB RAG', 'ConversationGateway', 'EmailChannel', 'CugaSkillsPlugin'],
    whyHard:
      'DoclingChannel correctly handles regulatory PDFs with complex table structures, multi-column layouts, and footnotes — where generic text extraction loses structure. RAG against internal policies requires the full pipeline to be in one runtime so the agent can reason across both the new document and existing policies simultaneously.',
  },

  // ── Box + Slack multimodal use cases ──────────────────────────────────────
  {
    id: 'cross-meeting-deck',
    title: 'Cross-Meeting Deck Assembly',
    tag: 'Content',
    tagColor: 'bg-violet-900/30 text-violet-300 border-violet-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'You have 3 months of meeting recordings in Box and 20+ decks shared across Slack channels. Someone asks: "We\'re pitching to a new enterprise customer next week — build me a deck on our API platform story." The relevant content exists. Nobody can find it.',
    howCuga:
      'BoxChannel ingests all recordings + decks (MP4, PPTX, PDF). AudioChannel → Whisper transcribes, pyannote diarizes. DoclingChannel parses decks into per-slide chunks (title, body, tables). QWEN2-VL describes diagrams and keyframes. Everything lands in ChromaDB with metadata (source file, timestamp, speaker, slide number). User query triggers semantic search across all modalities. QWEN2-VL re-ranks by visual relevance (diagrams preferred for technical slides). CugaAgent (deck_assembly.md) synthesises retrieved content into a new PPTX via python-pptx.',
    channels: ['BoxChannel', 'SlackChannel', 'AudioChannel', 'DoclingChannel', 'QWEN2-VL', 'ChromaDB', 'ConversationGateway', 'CugaSkillsPlugin'],
    whyHard:
      'Cross-modal linking: a spoken decision ("we went REST-first") must be connected to its corresponding slide ("API Architecture — slide 14") from a different file. Generic RAG treats modalities as separate indexes. CUGA++ indexes them together, so retrieval crosses audio transcript + slide text + visual description in a single query.',
  },
  {
    id: 'institutional-memory-qa',
    title: 'Institutional Memory Q&A',
    tag: 'Knowledge',
    tagColor: 'bg-sky-900/30 text-sky-300 border-sky-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'A new engineer asks: "Why do we use event sourcing in the payments service?" The answer lives across a 6-month-old Slack thread, an architecture review recording, and a decision doc in Box. Without a unified index, they ask three people and get three partial answers.',
    howCuga:
      'SlackChannel ingests thread history + file attachments from #architecture, #decisions. BoxChannel ingests docs (PDF, DOCX, PPTX). AudioChannel processes linked meeting recordings. All indexed with author, date, channel, document type. ConversationGateway exposes a Q&A interface in Slack (#ask-anything) or browser. CugaAgent answers with citations: "In the Jan 15 architecture review [00:14:22], Alice said X. This is reflected in the decision doc linked in #architecture on Jan 17."',
    channels: ['SlackChannel', 'BoxChannel', 'AudioChannel', 'DoclingChannel', 'ChromaDB', 'ConversationGateway'],
    whyHard:
      'Cross-source citation — the answer must trace back to a Slack message, a doc page, and a recording timestamp simultaneously. Three separate search tools cannot do this. It requires a single retrieval layer over a unified multimodal index, with metadata preserved per chunk.',
  },
  {
    id: 'sales-call-briefing',
    title: 'Sales Call Intelligence — Pre-Meeting Briefing',
    tag: 'Sales',
    tagColor: 'bg-orange-900/30 text-orange-300 border-orange-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'A sales rep has a renewal call in 1 hour with Acme Corp. Six past calls are stored in Box over 18 months. The rep needs: top objections, feature requests, last pricing discussion, and sentiment trend — in 5 minutes, not 2 hours of re-listening.',
    howCuga:
      'All past call recordings in Box → AudioChannel → Whisper + speaker diarization (customer voice vs rep voice separated). Indexed with CRM metadata (account, deal stage, attendees, date). CronChannel pre-computes briefings nightly before calendar meetings pulled via MCPToolBridge (Google Calendar). CugaAgent (sales_briefing.md) generates: (a) sentiment over time, (b) top objections ranked by frequency, (c) feature requests, (d) last pricing discussion verbatim. Delivered proactively via Slack DM and on-demand via ConversationGateway.',
    channels: ['BoxChannel', 'AudioChannel', 'CronChannel', 'MCPToolBridge', 'SlackChannel', 'ConversationGateway', 'CugaSkillsPlugin'],
    whyHard:
      'Speaker diarization separates customer voice from rep voice — without this, every statement is misattributed. The CronChannel proactive delivery + ConversationGateway on-demand Q&A are two access patterns on the same indexed corpus from one runtime. Most frameworks make you build these as separate systems.',
  },
  {
    id: 'product-feedback-synthesis',
    title: 'Product Feedback Synthesis',
    tag: 'Product',
    tagColor: 'bg-rose-900/30 text-rose-300 border-rose-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'A PM asks: "What are users saying about the onboarding flow?" The answer is scattered: 8 user interview recordings in Box, 6 months of #customer-feedback Slack messages, and a Zendesk export CSV. Each source tells a partial story.',
    howCuga:
      'BoxChannel ingests interview recordings → AudioChannel transcribes. SlackChannel ingests #customer-feedback (text + image screenshots). QWEN2-VL describes UI screenshots users shared ("user was on billing page, step 3 of onboarding"). DoclingChannel parses Zendesk CSV export as structured document. CugaAgent (product_research.md, feedback_synthesis.md) clusters by theme, ranks by frequency, flags outliers. Output → structured report to Notion/Confluence via MCPToolBridge + summary to #product Slack.',
    channels: ['BoxChannel', 'SlackChannel', 'AudioChannel', 'QWEN2-VL', 'DoclingChannel', 'MCPToolBridge', 'CugaSkillsPlugin'],
    whyHard:
      'Screenshots are the critical signal: users share an image of where they got confused, not a description. QWEN2-VL on the screenshot gives "user was on billing page, third onboarding step" — signal the text alone does not have. Pure text RAG misses this entirely.',
  },
  {
    id: 'rfp-proposal-generator',
    title: 'RFP / Proposal Generator from Past Wins',
    tag: 'Sales',
    tagColor: 'bg-amber-900/30 text-amber-300 border-amber-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'A new RFP arrives from a healthcare company. The sales team has 30 past winning proposals in Box (PDF) and 5 discovery call recordings from similar deals. Drafting a first-pass response from scratch takes 2 days. Most of the content already exists.',
    howCuga:
      'IMAPChannel or WebhookChannel receives the RFP. DoclingChannel parses it into structured requirements (section headings, mandatory fields, evaluation criteria). BoxChannel searches past proposals → DoclingChannel extracts reusable sections by heading. AudioChannel processes discovery call recordings → extracts customer pain points and language. CugaAgent (proposal_writing.md, rfp_analysis.md) maps RFP sections to best-matching past content, drafts new sections where no match exists. Draft pushed to Google Docs via MCPToolBridge for human review.',
    channels: ['IMAPChannel', 'BoxChannel', 'AudioChannel', 'DoclingChannel', 'MCPToolBridge', 'CugaSkillsPlugin'],
    whyHard:
      'Requires understanding the structure of an RFP — DoclingChannel preserves section hierarchy from complex PDFs, so matching happens at section level ("security & compliance section" → past proposal section), not full-document similarity. Section-level matching is the difference between a useful draft and a hallucinated one.',
  },
  {
    id: 'talk-to-content',
    title: 'Conference Talk → Blog / Docs / Social',
    tag: 'Content',
    tagColor: 'bg-violet-900/30 text-violet-300 border-violet-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'A developer advocate gave a 40-minute conference talk with live demos and architecture diagrams. The recording and slides are in Box. The content should become a blog post, a docs page, and LinkedIn posts — but nobody has time to rewatch and rewrite.',
    howCuga:
      'AudioChannel transcribes the recording with timestamps. QWEN2-VL describes demo screens and diagram keyframes ("slide shows before/after API response time — 2400ms vs 180ms"). DoclingChannel parses the slide deck to get section structure. CugaAgent (content_writing.md, technical_writing.md) gets transcript + slide structure + visual descriptions and generates: long-form blog (diagrams described inline), structured docs page (headings mirror slide sections), 5 LinkedIn posts (key quotes rephrased for character limit). Pushed to CMS / docs repo via MCPToolBridge.',
    channels: ['BoxChannel', 'AudioChannel', 'QWEN2-VL', 'DoclingChannel', 'MCPToolBridge', 'CugaSkillsPlugin'],
    whyHard:
      'The visual descriptions are load-bearing: a live coding demo or a before/after diagram cannot be understood from the transcript alone. QWEN2-VL on the keyframe gives the agent what was on screen — without that, the blog post has a gap where the demo was.',
  },
  {
    id: 'competitive-intel',
    title: 'Competitive Intelligence Aggregator',
    tag: 'Strategy',
    tagColor: 'bg-red-900/30 text-red-300 border-red-800/40',
    surface: 'Multimodal',
    surfaceColor: 'text-pink-400',
    problem:
      'A product team has a Box folder of competitor recordings: earnings calls, product launches, conference talks, analyst briefings. Accumulated over 12 months. Nobody watches them all. Ask: "What has Competitor X said about enterprise pricing in the last 6 months?" currently requires manual scrubbing.',
    howCuga:
      'CugaWatcher monitors a shared Box folder for new additions. AudioChannel transcribes, QWEN2-VL describes slide keyframes. Indexed with metadata: competitor, event type, date, speaker role. Two access patterns on the same corpus: CronChannel sends a weekly digest ("here\'s what changed in the competitive landscape this week") and ConversationGateway answers on-demand queries with direct quotes + recording timestamps. CugaAgent (competitive_analysis.md) synthesises responses across sources.',
    channels: ['BoxChannel', 'CugaWatcher', 'AudioChannel', 'QWEN2-VL', 'CronChannel', 'ConversationGateway', 'SlackChannel', 'CugaSkillsPlugin'],
    whyHard:
      'Two access patterns — weekly proactive digest (CronChannel) and on-demand Q&A (ConversationGateway) — powered by the same indexed corpus and same agent. One runtime. Most teams build these as two entirely separate systems that drift apart.',
  },
]

const SURFACE_COLOR: Record<string, string> = {
  'Event-Driven': 'bg-emerald-900/20 text-emerald-400 border-emerald-800/30',
  'Multimodal': 'bg-pink-900/20 text-pink-400 border-pink-800/30',
  'Multi-Agent': 'bg-purple-900/20 text-purple-400 border-purple-800/30',
  'Gateway': 'bg-indigo-900/20 text-indigo-400 border-indigo-800/30',
}

interface MoatItem {
  rank: number
  title: string
  defensibility: 'high' | 'medium' | 'low'
  tldr: string
  why: string
  compoundsHow: string
  antiThesis: string
}

interface AntiMoat {
  thing: string
  whyNot: string
}

const ANTI_MOATS: AntiMoat[] = [
  {
    thing: 'Individual channel implementations (Telegram, WhatsApp, Voice)',
    whyNot:
      'Anyone can clone a Twilio webhook handler in an afternoon. The channel code itself is not defensible — what matters is what sits on top of it.',
  },
  {
    thing: 'LLM provider integrations (OpenAI, Anthropic, Ollama…)',
    whyNot:
      'Every framework does this. LiteLLM already abstracts all of them. Multi-provider support is table stakes for enterprise procurement, not a moat.',
  },
  {
    thing: '"Event-driven agent I/O" as a concept',
    whyNot:
      'A positioning phrase is not a moat. LangGraph, Temporal, and Prefect all have event-driven semantics. The concept is not proprietary.',
  },
  {
    thing: 'The Streamlit demos',
    whyNot:
      'Table stakes. Every framework has polished demos. Enterprises don\'t buy demos — they buy things that survive production.',
  },
  {
    thing: 'Being first to market',
    whyNot:
      'LangChain was first. It is not winning. First-mover advantage in developer tooling is weak — switching costs are low until organizations build deep on a platform.',
  },
]

const MOATS: MoatItem[] = [
  {
    rank: 1,
    title: 'The benchmark as the evaluation standard',
    defensibility: 'high',
    tldr: 'Own how enterprises measure agent quality — own the conversation.',
    why: `Every enterprise AI evaluation eventually asks: "does this agent actually work in production?"
Right now, nobody has a good answer. Internal teams build ad-hoc evals. Consultants run
bespoke tests. Procurement teams compare vibes.

If CUGA++ becomes the standard for "here are 100 real-world agent tasks, here is the scoring
rubric, here is the reproduction environment" — that's a network-effect moat. Benchmarks are
sticky because: reports reference them, teams build muscle memory around them, new tools are
compared against them, and the organisation that runs the benchmark sets the terms of the debate.

The task list itself is not the moat. The execution environment, the scoring methodology, and the
corpus of real failure modes that informed the test design — that is the moat.`,
    compoundsHow:
      'Each new use case added to the benchmark makes it more comprehensive, which makes it harder to replicate credibly. The longer it runs, the more performance history it accumulates.',
    antiThesis:
      'Someone could fork the task list. But forking a list is not the same as owning the evaluation infrastructure or the community trust that benchmarks require to become standards.',
  },
  {
    rank: 2,
    title: 'Skills as organisational knowledge — the switching cost',
    defensibility: 'high',
    tldr: '.md skill files are institutional knowledge encoded as agent persona. That data compounds.',
    why: `The CugaSkillsPlugin loads Markdown files as agent skills — a PM's way of writing user
stories, a QA engineer's edge case heuristics, an SRE's deployment checklist, a legal team's
contract review rubric.

An enterprise that builds 50–100 skill files is encoding its institutional knowledge into agent
form. This is the "data moat" analog for the agent era. Switching away from CUGA++ means
re-encoding all of that knowledge into a different format — or throwing it away.

Compare: if your agent's "skills" live in a LangChain prompt template, they're easy to move.
If they live in a structured library of .md files with a specific skill-loading convention,
they're an asset that compounds with every new agent role you define.`,
    compoundsHow:
      'Each new role an enterprise defines (procurement agent, compliance agent, customer success agent) adds to the skill library. The library becomes part of onboarding new team members, not just agents.',
    antiThesis:
      'Skills are just Markdown files. A determined team could migrate them. The moat is organisational inertia and the fact that the skill format is tied to the agent runtime — not the files themselves.',
  },
  {
    rank: 3,
    title: 'Multi-surface runtime — one agent, every front-end',
    defensibility: 'medium',
    tldr: 'No other framework lets the same agent run on browser + Telegram + WhatsApp + phone simultaneously.',
    why: `Enterprises today maintain separate deployments for each channel: a Slack bot built by
one team, a web chat widget built by another, a phone IVR contracted out to a vendor. Each
has its own codebase, its own prompt, its own conversation state. They diverge over time.

CUGA++ collapses this to: one CugaAgent, N add_*_adapter() calls, one deployment. Every
channel gets the same agent intelligence, the same memory, the same tools.

This matters in enterprise settings because: (a) IT governance prefers fewer deployments,
(b) compliance teams want one audit trail not five, (c) product teams want consistent behaviour
across surfaces, (d) cost optimization happens at the agent level, not per-channel.`,
    compoundsHow:
      'Each new adapter (Slack, Discord, SMS, email) works immediately for every existing agent without code changes. The runtime abstraction pays off multiplicatively.',
    antiThesis:
      'A skilled team could wire multiple frameworks together. The moat is the integrated runtime, not the individual adapters.',
  },
  {
    rank: 4,
    title: 'Production hardening corpus — the bugs already solved',
    defensibility: 'medium',
    tldr: 'The invisible value: every production failure mode already discovered and fixed.',
    why: `The things that break agents in production are not in any tutorial:
MIME encoding edge cases in IMAP. Cron job isolation failures when two ticks overlap.
Async event loop memory leaks under sustained load. Pydantic v1/v2 conflicts in LangGraph
subgraph serialisation. Twilio TwiML multi-turn state loss when the POST timeout exceeds 5s.
Meta Cloud API media download race conditions on slow networks.

None of these are documented. They're discovered by running production workloads.
CUGA++ has already hit most of them. That corpus of failure modes — and the test suite
that prevents regressions — is real value that doesn't show up in a feature comparison.

This is why "built on top of" positions don't capture it: a wrapper around CUGA++ still
inherits the hardening. A rewrite does not.`,
    compoundsHow:
      'Every new production deployment surfaces new edge cases, which get fixed and tested, which makes the runtime more reliable, which attracts more production deployments.',
    antiThesis:
      'This moat erodes as the ecosystem matures. In 2 years, the obvious bugs will be documented everywhere. The window to own "production hardening" is narrow.',
  },
  {
    rank: 5,
    title: 'Meeting intelligence as the vertical wedge',
    defensibility: 'medium',
    tldr: 'Deep vertical ownership creates a wedge into enterprise accounts that generic frameworks cannot replicate.',
    why: `Generic frameworks lose to vertical solutions in enterprise sales. "We can build anything"
loses to "we built the exact thing you need, and we've already solved the hard parts."

Meeting intelligence is a universal enterprise pain point with clear ROI:
Every company has too many meetings and too little capture of what was decided.
The pipeline is well-defined: audio → transcription → diarization → action items → delivery.

CUGA++ can own this vertically: the Whisper ingestion channel, the Docling slide parser,
the QWEN2-VL keyframe extractor, the ChromaDB indexing, the Q&A interface, the Slack/Jira
output. A complete, tested, enterprise-deployable meeting intelligence stack on one runtime.

This is a wedge: you sell meeting intelligence, you land in the enterprise, you expand to
other pipelines once you're trusted infrastructure.`,
    compoundsHow:
      'Each enterprise deployment of meeting intelligence generates more skill files, more benchmark tasks, and more production edge cases — feeding the three higher-ranked moats.',
    antiThesis:
      'Fireflies, Otter.ai, and Notion AI all compete here. The wedge works only if CUGA++ is deployed by engineering teams who then build on top of it — not sold as an end-user SaaS.',
  },
]

const DEFENSIBILITY_STYLES: Record<string, string> = {
  high: 'bg-green-900/20 border-green-700/40 text-green-400',
  medium: 'bg-yellow-900/20 border-yellow-700/40 text-yellow-400',
  low: 'bg-gray-800/40 border-gray-700/30 text-gray-500',
}

const DEFENSIBILITY_LABEL: Record<string, string> = {
  high: 'High defensibility',
  medium: 'Medium defensibility',
  low: 'Low',
}

export default function MoatPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto">

      {/* ── Header ── */}
      <div className="mb-10">
        <h2 className="text-2xl font-semibold text-white mb-2">Positioning</h2>
        <p className="text-indigo-300 text-sm font-medium max-w-2xl mb-2">
          A framework that connects event sources → agent reasoning → output destinations, with reusable skills and orchestration patterns baked in.
        </p>
        <p className="text-gray-400 text-sm max-w-2xl leading-relaxed">
          What is actually defensible about CUGA++ in an enterprise setting?
          This is an honest analysis — not marketing. Most things people think are moats are not.
          A few things actually are.
        </p>
      </div>

      {/* ── The core tension ── */}
      <div className="mb-10 bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">The core tension</div>
        <p className="text-sm text-gray-300 leading-relaxed mb-4">
          CUGA++ is an <span className="text-indigo-300 font-medium">infrastructure layer</span>, not an application.
          Infrastructure moats are different from product moats. You cannot defend infrastructure
          with UX, brand, or a clever feature — those are copied in weeks. Infrastructure moats
          come from three things:
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {
              label: 'Switching costs',
              desc: 'The deeper an organisation builds on the platform, the more expensive it is to leave. Skills libraries, benchmark baselines, and production deployments all create this.',
              color: 'text-indigo-400',
            },
            {
              label: 'Network effects',
              desc: 'The benchmark becomes more valuable as more teams use it. Each new enterprise use case makes the task library more comprehensive. These are weak network effects, but real.',
              color: 'text-emerald-400',
            },
            {
              label: 'Production corpus',
              desc: 'The invisible bugs already solved. You cannot replicate this without running production workloads for 12–18 months. This moat has a time window — it erodes as the ecosystem matures.',
              color: 'text-amber-400',
            },
          ].map((item) => (
            <div key={item.label} className="bg-gray-800/50 rounded-xl p-4">
              <div className={`text-sm font-semibold mb-1.5 ${item.color}`}>{item.label}</div>
              <p className="text-xs text-gray-400 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── What is NOT a moat ── */}
      <div className="mb-10">
        <h3 className="text-base font-semibold text-white mb-1">What is NOT a moat</h3>
        <p className="text-xs text-gray-500 mb-4">Things that feel like moats but get copied in a weekend.</p>
        <div className="space-y-2">
          {ANTI_MOATS.map((item) => (
            <div key={item.thing} className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-3.5 flex items-start gap-4">
              <span className="text-red-500 text-sm mt-0.5 flex-shrink-0">✕</span>
              <div>
                <div className="text-sm font-medium text-gray-300">{item.thing}</div>
                <div className="text-xs text-gray-500 mt-0.5 leading-relaxed">{item.whyNot}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Real moats ── */}
      <div className="mb-8">
        <h3 className="text-base font-semibold text-white mb-1">Where the real moat is</h3>
        <p className="text-xs text-gray-500 mb-5">Ranked by defensibility. Each section includes an honest anti-thesis.</p>

        <div className="space-y-5">
          {MOATS.map((moat) => (
            <div key={moat.rank} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              {/* Card header */}
              <div className="px-6 pt-5 pb-4 border-b border-gray-800">
                <div className="flex items-center gap-3 mb-2 flex-wrap">
                  <span className="text-xs font-mono text-gray-600 bg-gray-800 px-2 py-0.5 rounded">
                    #{moat.rank}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded border ${DEFENSIBILITY_STYLES[moat.defensibility]}`}>
                    {DEFENSIBILITY_LABEL[moat.defensibility]}
                  </span>
                </div>
                <h4 className="text-base font-semibold text-white">{moat.title}</h4>
                <p className="text-sm text-gray-400 mt-0.5">{moat.tldr}</p>
              </div>

              {/* Body */}
              <div className="px-6 py-5 space-y-5">
                {/* Why */}
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Why this is defensible</div>
                  <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-line">{moat.why.trim()}</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Compounds */}
                  <div className="bg-green-900/10 border border-green-800/20 rounded-xl p-4">
                    <div className="text-xs font-semibold text-green-600 uppercase tracking-wider mb-2">How it compounds</div>
                    <p className="text-xs text-gray-400 leading-relaxed">{moat.compoundsHow}</p>
                  </div>

                  {/* Anti-thesis */}
                  <div className="bg-red-900/10 border border-red-800/20 rounded-xl p-4">
                    <div className="text-xs font-semibold text-red-700 uppercase tracking-wider mb-2">Honest anti-thesis</div>
                    <p className="text-xs text-gray-400 leading-relaxed">{moat.antiThesis}</p>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Enterprise use cases ── */}
      <div className="mb-10">
        <h3 className="text-base font-semibold text-white mb-1">Enterprise use cases that illustrate the moat</h3>
        <p className="text-xs text-gray-500 mb-5">
          These are the kinds of deployments that create switching costs, generate skill libraries, and feed the benchmark.
          Each one requires the full CUGA++ stack — channels + multimodal + skills + multi-agent.
          None of them work with a single-pattern framework.
        </p>

        {/* Event-driven subsection */}
        <div className="mb-3 flex items-center gap-2">
          <span className="text-xs font-semibold text-emerald-500 uppercase tracking-wider">Event-Driven Pipelines</span>
          <div className="flex-1 h-px bg-emerald-900/40" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          {ENTERPRISE_USE_CASES.filter(uc => uc.surface === 'Event-Driven').map((uc) => (
            <div key={uc.id} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              <div className="px-5 pt-4 pb-3 border-b border-gray-800">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className={`text-xs font-mono px-2 py-0.5 rounded border ${uc.tagColor}`}>
                    {uc.tag}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded border ${SURFACE_COLOR[uc.surface]}`}>
                    {uc.surface}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white">{uc.title}</h4>
              </div>

              <div className="px-5 py-4 space-y-3">
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1">Problem</div>
                  <p className="text-xs text-gray-400 leading-relaxed">{uc.problem}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1">How CUGA++ solves it</div>
                  <p className="text-xs text-gray-400 leading-relaxed">{uc.howCuga}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1">Why it's hard to replicate</div>
                  <p className="text-xs text-gray-500 leading-relaxed italic">{uc.whyHard}</p>
                </div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {uc.channels.map((c) => (
                    <span key={c} className="text-xs font-mono text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Multimodal subsection */}
        <div className="mb-3 flex items-center gap-2">
          <span className="text-xs font-semibold text-pink-500 uppercase tracking-wider">Box + Slack Multimodal</span>
          <div className="flex-1 h-px bg-pink-900/40" />
          <span className="text-xs text-gray-600">recordings · decks · screenshots · all queryable together</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {ENTERPRISE_USE_CASES.filter(uc => uc.surface === 'Multimodal').map((uc) => (
            <div key={uc.id} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              <div className="px-5 pt-4 pb-3 border-b border-gray-800">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className={`text-xs font-mono px-2 py-0.5 rounded border ${uc.tagColor}`}>
                    {uc.tag}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded border ${SURFACE_COLOR[uc.surface]}`}>
                    {uc.surface}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white">{uc.title}</h4>
              </div>
              <div className="px-5 py-4 space-y-3">
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1">Problem</div>
                  <p className="text-xs text-gray-400 leading-relaxed">{uc.problem}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1">How CUGA++ solves it</div>
                  <p className="text-xs text-gray-400 leading-relaxed">{uc.howCuga}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1">Why it's hard to replicate</div>
                  <p className="text-xs text-gray-500 leading-relaxed italic">{uc.whyHard}</p>
                </div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {uc.channels.map((c) => (
                    <span key={c} className="text-xs font-mono text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── The honest summary ── */}
      <div className="bg-gray-900/60 border border-indigo-900/40 rounded-2xl p-6">
        <div className="text-xs font-semibold text-indigo-600 uppercase tracking-wider mb-3">The honest summary</div>
        <p className="text-sm text-gray-300 leading-relaxed mb-4">
          No single thing above is an unassailable moat. The real moat is the{' '}
          <span className="text-indigo-300 font-medium">combination</span>: a production-hardened runtime
          that becomes the benchmark standard, that gets deeper as organisations encode their knowledge into skills,
          that lands in enterprises via a compelling vertical (meeting intelligence), and that expands
          because switching costs make it easier to build the next pipeline on CUGA++ than to start over.
        </p>
        <p className="text-sm text-gray-500 leading-relaxed">
          The most dangerous competitor is not LangChain or CrewAI — it's an enterprise deciding to build
          their own internal I/O runtime with 3 engineers and 6 months. That happens when CUGA++ is too generic
          ("a framework") and not specific enough ("the meeting intelligence platform that also powers your other pipelines").
          The wedge use case is therefore not just a go-to-market tactic — it's moat protection.
        </p>
      </div>

    </div>
  )
}
