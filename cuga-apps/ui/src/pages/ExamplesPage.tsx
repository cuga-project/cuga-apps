import { useState } from 'react'
import CodeBlock from '../components/CodeBlock'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FileRef = { label: string; path: string }

type FlowStep = {
  component: string
  badge: 'cuga' | 'cuga++' | 'infra'
  what: string
  io?: { in: string; out: string }
  file?: FileRef
}

type Channel = {
  name: string
  type: 'data' | 'trigger' | 'output'
  detail: string
}

type Example = {
  utterance: string
  description: string
  plannerConfig: Record<string, unknown>
  channels: Channel[]
  steps: FlowStep[]
  files: FileRef[]
  notes?: string
}

type Category = {
  id: string
  label: string
  icon: string
  description: string
  examples: Example[]
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const CATEGORIES: Category[] = [
  {
    id: 'monitor',
    label: 'Start monitoring',
    icon: '📡',
    description: 'Utterances that start the RSS + podcast pipeline. ChannelPlanner extracts sources, keywords, schedule, and email, then CugaHost builds the runtime.',
    examples: [
      {
        utterance: 'watch arxiv cs.AI and the Practical AI podcast for AI agents, email me@co.com every 4 hours',
        description: 'Full pipeline — RSS + podcast, digest every 4 hours, delivered by email.',
        plannerConfig: {
          intent: 'monitor',
          sources: ['https://arxiv.org/rss/cs.AI'],
          podcast_sources: ['https://changelog.com/practicalai/feed'],
          keywords: ['AI agents', 'agent', 'agentic'],
          digest_minutes: 240,
          email: 'me@co.com',
        },
        channels: [
          { name: 'RssChannel', type: 'data', detail: 'Polls arxiv cs.AI every 15 min, keyword-filters, pushes text items to buffer' },
          { name: 'PodcastChannel', type: 'data', detail: 'Polls Practical AI RSS every 60 min — keyword match → download mp3 → Whisper → ChromaDB → buffer' },
          { name: 'CronChannel', type: 'trigger', detail: 'Fires every 4 hours (0 */4 * * *)' },
          { name: 'EmailChannel', type: 'output', detail: 'Delivers HTML digest to me@co.com' },
          { name: 'LogChannel', type: 'output', detail: 'Always-on console fallback' },
        ],
        steps: [
          {
            component: 'ChannelPlanner',
            badge: 'cuga',
            what: 'Parses the NL utterance into a structured config dict. Runs once at setup.',
            io: { in: 'raw utterance string', out: 'config dict with sources, keywords, digest_minutes, email' },
            file: { label: 'chat.py — _build_planner()', path: 'docs/examples/demo_apps/newsletter/chat.py' },
          },
          {
            component: 'CugaHostClient.start_runtime()',
            badge: 'cuga++',
            what: 'Sends the config to CugaHost over HTTP (or embedded). Host looks up the "newsletter" factory.',
            io: { in: 'runtime_id, factory="newsletter", config dict', out: 'running CugaRuntime entry' },
            file: { label: 'host_client.py', path: 'packages/cuga-channels/src/cuga_channels/host_client.py' },
          },
          {
            component: 'CugaHost — newsletter factory',
            badge: 'cuga++',
            what: 'Factory (registered from cuga_pipelines.yaml) builds the CugaRuntime with all channels.',
            io: { in: 'config dict + yaml defaults', out: 'CugaRuntime(RssChannel, PodcastChannel, CronChannel, EmailChannel)' },
            file: { label: 'cuga_pipelines.yaml', path: 'docs/examples/demo_apps/newsletter/cuga_pipelines.yaml' },
          },
          {
            component: 'RssChannel (every 15 min)',
            badge: 'cuga++',
            what: 'Polls arxiv cs.AI. Keyword-filters items. Pushes matched dicts to ChannelBuffer. Deduplicates by URL.',
            io: { in: 'HTTP RSS XML from arxiv', out: 'list[dict] → ChannelBuffer.add()' },
            file: { label: 'rss.py', path: 'packages/cuga-channels/src/cuga_channels/rss.py' },
          },
          {
            component: 'PodcastChannel (every 60 min)',
            badge: 'cuga++',
            what: 'Fetches Practical AI RSS. Checks title + description against keywords (free). If match and under duration limit → downloads mp3 → Whisper transcribes → indexes full transcript into ChromaDB → pushes item with transcript_excerpt to buffer.',
            io: { in: 'RSS XML → keyword hit → mp3 bytes → Whisper', out: '{title, url, transcript_excerpt, source:"podcast:…"} → ChannelBuffer' },
            file: { label: 'podcast.py', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
          },
          {
            component: 'CronChannel (every 4 hours)',
            badge: 'cuga++',
            what: 'Fires trigger message. CugaRuntime checks buffer — if items present, serialises them into the agent message.',
            io: { in: 'cron tick', out: 'trigger_message + JSON-serialised buffer items → agent.invoke()' },
            file: { label: 'runtime.py — _on_trigger()', path: 'packages/cuga-channels/src/cuga_channels/runtime.py' },
          },
          {
            component: 'CugaAgent (newsletter writer)',
            badge: 'cuga',
            what: 'Receives trigger message with all buffered items. Applies newsletter_curation skill. Can call search_documents() to retrieve deeper transcript passages from ChromaDB. Produces complete HTML digest.',
            io: { in: 'trigger msg + N buffer items (RSS + podcast)', out: 'styled HTML newsletter string' },
            file: { label: 'agent.py', path: 'docs/examples/demo_apps/newsletter/agent.py' },
          },
          {
            component: 'EmailChannel',
            badge: 'cuga++',
            what: 'Receives HTML from runtime. Sends via SMTP. Buffer is cleared. Cycle repeats in 4 hours.',
            io: { in: 'HTML string + metadata', out: 'email delivered to me@co.com' },
            file: { label: 'email.py', path: 'packages/cuga-channels/src/cuga_channels/email.py' },
          },
        ],
        files: [
          { label: 'cuga_pipelines.yaml', path: 'docs/examples/demo_apps/newsletter/cuga_pipelines.yaml' },
          { label: 'chat.py', path: 'docs/examples/demo_apps/newsletter/chat.py' },
          { label: 'agent.py', path: 'docs/examples/demo_apps/newsletter/agent.py' },
          { label: 'podcast.py', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
          { label: 'runtime.py', path: 'packages/cuga-channels/src/cuga_channels/runtime.py' },
        ],
      },
      {
        utterance: 'monitor huggingface and Latent Space podcast for LLM research every 2 hours',
        description: 'Same pipeline, different sources and schedule. No email → logs to console.',
        plannerConfig: {
          intent: 'monitor',
          sources: ['https://huggingface.co/blog/feed.xml'],
          podcast_sources: ['https://www.latent.space/feed/podcast'],
          keywords: ['LLM', 'large language model', 'research'],
          digest_minutes: 120,
          email: null,
        },
        channels: [
          { name: 'RssChannel', type: 'data', detail: 'Polls HuggingFace blog every 15 min' },
          { name: 'PodcastChannel', type: 'data', detail: 'Polls Latent Space podcast every 60 min' },
          { name: 'CronChannel', type: 'trigger', detail: 'Every 2 hours (0 */2 * * *)' },
          { name: 'LogChannel', type: 'output', detail: 'email=null → console output only' },
        ],
        steps: [
          {
            component: 'ChannelPlanner',
            badge: 'cuga',
            what: 'Extracts sources, podcast_sources, keywords, digest_minutes=120. email stays null → LogChannel only.',
            io: { in: 'utterance', out: 'config with digest_minutes=120, email=null' },
            file: { label: 'chat.py', path: 'docs/examples/demo_apps/newsletter/chat.py' },
          },
          {
            component: 'CugaHost factory',
            badge: 'cuga++',
            what: 'EmailChannel.from_config() returns None (no SMTP_USERNAME set or email=null). Runtime uses LogChannel only.',
            io: { in: 'config', out: 'CugaRuntime(RssChannel, PodcastChannel, CronChannel, LogChannel)' },
            file: { label: 'email.py — from_config()', path: 'packages/cuga-channels/src/cuga_channels/email.py' },
          },
          {
            component: 'Pipeline runs identically',
            badge: 'cuga++',
            what: 'RSS + podcast polling, Whisper transcription, ChromaDB indexing all happen the same. Output goes to stdout instead of email.',
            file: { label: 'runtime.py', path: 'packages/cuga-channels/src/cuga_channels/runtime.py' },
          },
        ],
        files: [
          { label: 'chat.py', path: 'docs/examples/demo_apps/newsletter/chat.py' },
          { label: 'email.py', path: 'packages/cuga-channels/src/cuga_channels/email.py' },
        ],
      },
    ],
  },
  {
    id: 'podcast',
    label: 'Podcast-focused',
    icon: '🎙️',
    description: 'Utterances that emphasise the podcast + audio transcription path. Shows the multimodal pipeline — RSS XML → keyword filter → mp3 download → Whisper → ChromaDB.',
    examples: [
      {
        utterance: 'watch the Practical AI podcast for anything about tool use, skip episodes over 30 minutes',
        description: 'Podcast-only intent with an explicit duration gate.',
        plannerConfig: {
          intent: 'monitor',
          podcast_sources: ['https://changelog.com/practicalai/feed'],
          keywords: ['tool use', 'function calling', 'tools'],
          digest_minutes: 240,
          max_duration_minutes: 30,
          email: null,
        },
        channels: [
          { name: 'RssChannel', type: 'data', detail: 'Still runs (default sources) — can\'t disable via NL yet' },
          { name: 'PodcastChannel', type: 'data', detail: 'Polls Practical AI. Duration gate: skip if episode > 30 min before any download' },
          { name: 'CronChannel', type: 'trigger', detail: 'Every 4 hours (default)' },
          { name: 'LogChannel', type: 'output', detail: 'Console output' },
        ],
        steps: [
          {
            component: 'PodcastChannel — duration gate',
            badge: 'cuga++',
            what: 'Fetches RSS XML (free). Parses <itunes:duration> — handles HH:MM:SS, MM:SS, raw seconds. Episode > 30 min → skipped before any download. No audio bytes transferred.',
            io: { in: '<itunes:duration>45:30</itunes:duration>', out: '45 min > 30 min limit → skip' },
            file: { label: 'podcast.py — _parse_duration()', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
          },
          {
            component: 'PodcastChannel — keyword filter',
            badge: 'cuga++',
            what: 'For episodes under 30 min, checks title + description for "tool use", "function calling", "tools". Match required before download.',
            io: { in: 'episode title + summary text', out: 'keyword hit → proceed to download' },
            file: { label: 'podcast.py — _process_episode()', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
          },
          {
            component: 'AudioChannel.transcribe()',
            badge: 'cuga++',
            what: 'Downloads matched episode mp3. Calls Whisper (local → OpenAI API → RITS fallback chain). Returns full transcript text.',
            io: { in: 'mp3 bytes + filename', out: 'transcript string (full episode text)' },
            file: { label: 'audio.py — transcribe()', path: 'packages/cuga-channels/src/cuga_channels/audio.py' },
          },
          {
            component: 'ChromaDB ingestion',
            badge: 'infra',
            what: 'Full transcript chunked into ~500-char overlapping pieces. Each chunk embedded and upserted into ChromaDB at .cuga/chroma. Persists across restarts.',
            io: { in: 'full transcript string', out: 'N chunks → ChromaDB collection "podcasts"' },
            file: { label: 'podcast.py — _ingest_transcript()', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
          },
          {
            component: 'ChannelBuffer',
            badge: 'cuga++',
            what: 'Only the excerpt (first 2000 chars) goes into the buffer. Full transcript lives in ChromaDB. Buffer deduplicates by URL.',
            io: { in: 'episode dict + transcript_excerpt', out: 'item added to in-memory buffer' },
            file: { label: 'buffer.py', path: 'packages/cuga-channels/src/cuga_channels/buffer.py' },
          },
        ],
        files: [
          { label: 'podcast.py', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
          { label: 'audio.py', path: 'packages/cuga-channels/src/cuga_channels/audio.py' },
          { label: 'buffer.py', path: 'packages/cuga-channels/src/cuga_channels/buffer.py' },
        ],
        notes: 'Duration gate happens before keyword filter — no unnecessary text processing on long episodes.',
      },
      {
        utterance: 'fetch the latest from the Practical AI podcast right now',
        description: 'One-shot run — no ongoing monitor. Fetches, transcribes, delivers once.',
        plannerConfig: {
          intent: 'run_once',
          podcast_sources: ['https://changelog.com/practicalai/feed'],
          keywords: ['agent', 'LLM', 'AI'],
          email: null,
        },
        channels: [
          { name: 'RssChannel.fetch_once()', type: 'data', detail: 'One-time fetch, no polling loop' },
          { name: 'PodcastChannel (ad-hoc)', type: 'data', detail: 'Fetches latest matching episode, transcribes, returns' },
          { name: 'LogChannel', type: 'output', detail: 'Output printed to console / chat' },
        ],
        steps: [
          {
            component: 'ChannelPlanner',
            badge: 'cuga',
            what: 'Detects intent="run_once" from "right now". No CugaHost runtime is created.',
            io: { in: 'utterance', out: 'PlannerResult(intent="run_once")' },
          },
          {
            component: 'run_once() in chat.py',
            badge: 'cuga',
            what: 'Fetches RSS + podcast ad-hoc. Passes items directly to CugaAgent.invoke(). No CronChannel or buffer.',
            file: { label: 'chat.py — run_once()', path: 'docs/examples/demo_apps/newsletter/chat.py' },
          },
        ],
        files: [
          { label: 'chat.py', path: 'docs/examples/demo_apps/newsletter/chat.py' },
        ],
      },
    ],
  },
  {
    id: 'qa',
    label: 'Q&A over podcasts',
    icon: '🔍',
    description: 'Asking questions about indexed podcast content. Works via app.py (browser chat) — the conversational agent has search_documents wired to the same ChromaDB that PodcastChannel writes to.',
    examples: [
      {
        utterance: 'what has Practical AI said about tool use?',
        description: 'Semantic search over indexed podcast transcripts. Only works after at least one episode has been transcribed and indexed.',
        plannerConfig: {},
        channels: [],
        steps: [
          {
            component: 'CugaAgent (conversational, app.py)',
            badge: 'cuga',
            what: 'Receives question. Recognises it\'s a knowledge query, not a pipeline command. Calls search_documents("tool use").',
            io: { in: 'user question', out: 'search_documents("tool use", n_results=5)' },
            file: { label: 'app.py — make_agent()', path: 'docs/examples/demo_apps/newsletter/app.py' },
          },
          {
            component: 'search_documents tool',
            badge: 'cuga++',
            what: 'Performs semantic (embedding) search over ChromaDB collection "podcasts". Returns top-5 chunks with source metadata and similarity scores.',
            io: { in: 'query string', out: 'top-5 transcript chunks from any indexed episode' },
            file: { label: 'rag_tools.py — search_documents()', path: 'packages/cuga-channels/src/cuga_channels/rag_tools.py' },
          },
          {
            component: 'CugaAgent synthesises answer',
            badge: 'cuga',
            what: 'Reads the returned chunks. Synthesises a natural-language answer citing the episode title, quote, and approximate time context.',
            io: { in: 'top-5 transcript chunks + source metadata', out: 'conversational answer with attribution' },
          },
        ],
        files: [
          { label: 'app.py', path: 'docs/examples/demo_apps/newsletter/app.py' },
          { label: 'rag_tools.py', path: 'packages/cuga-channels/src/cuga_channels/rag_tools.py' },
          { label: 'podcast.py — _ingest_transcript()', path: 'packages/cuga-channels/src/cuga_channels/podcast.py' },
        ],
        notes: 'Requires app.py (browser at localhost:8769), not chat.py. The terminal REPL only has ChannelPlanner which is config-only.',
      },
      {
        utterance: 'find me quotes about autonomous agents from the podcasts',
        description: 'Retrieves specific passages. The agent extracts direct quotes from the returned chunks.',
        plannerConfig: {},
        channels: [],
        steps: [
          {
            component: 'CugaAgent',
            badge: 'cuga',
            what: 'Calls search_documents("autonomous agents"). Receives chunks. Scans for direct quotable sentences. Returns formatted quotes with episode attribution.',
            io: { in: 'search query', out: 'formatted quotes with source + episode metadata' },
            file: { label: 'app.py', path: 'docs/examples/demo_apps/newsletter/app.py' },
          },
        ],
        files: [
          { label: 'app.py', path: 'docs/examples/demo_apps/newsletter/app.py' },
          { label: 'rag_tools.py', path: 'packages/cuga-channels/src/cuga_channels/rag_tools.py' },
        ],
      },
    ],
  },
  {
    id: 'control',
    label: 'Control',
    icon: '🎛️',
    description: 'Status, stop, and reconfigure utterances. These go through ChannelPlanner → CugaHostClient and never touch the pipeline agent.',
    examples: [
      {
        utterance: 'status',
        description: 'Reports whether a monitor is running and its current configuration.',
        plannerConfig: { action: 'status' },
        channels: [],
        steps: [
          {
            component: 'ChannelPlanner',
            badge: 'cuga',
            what: 'Detects intent="status". Returns PlannerResult(action="status", config=None).',
            io: { in: '"status"', out: 'PlannerResult(action="status")' },
          },
          {
            component: 'CugaHostClient.get_runtime()',
            badge: 'cuga++',
            what: 'GET /runtime/newsletter-monitor → returns runtime entry with config, started_at, running state.',
            io: { in: 'runtime_id', out: '{sources, podcast_sources, digest_minutes, email, running: true}' },
            file: { label: 'host_client.py', path: 'packages/cuga-channels/src/cuga_channels/host_client.py' },
          },
        ],
        files: [
          { label: 'chat.py — interactive_loop()', path: 'docs/examples/demo_apps/newsletter/chat.py' },
          { label: 'host_client.py', path: 'packages/cuga-channels/src/cuga_channels/host_client.py' },
        ],
      },
      {
        utterance: 'stop',
        description: 'Stops all channels cleanly. CronChannel, RssChannel, PodcastChannel all shut down. Config is removed from runtimes.json.',
        plannerConfig: { action: 'stop' },
        channels: [],
        steps: [
          {
            component: 'ChannelPlanner',
            badge: 'cuga',
            what: 'Detects action="stop".',
            io: { in: '"stop"', out: 'PlannerResult(action="stop")' },
          },
          {
            component: 'CugaHostClient.stop_runtime()',
            badge: 'cuga++',
            what: 'DELETE /runtime/newsletter-monitor → CugaHost calls runtime.stop() on all channels. Config removed from runtimes.json (won\'t restore on restart).',
            io: { in: 'runtime_id', out: 'all channels stopped, runtimes.json updated' },
            file: { label: 'host.py — stop_runtime()', path: 'packages/cuga-channels/src/cuga_channels/host.py' },
          },
        ],
        files: [
          { label: 'host.py', path: 'packages/cuga-channels/src/cuga_channels/host.py' },
          { label: 'runtime.py — stop()', path: 'packages/cuga-channels/src/cuga_channels/runtime.py' },
        ],
      },
    ],
  },
]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const BADGE_STYLES: Record<string, string> = {
  'cuga':   'bg-indigo-900/60 text-indigo-300 border border-indigo-700/50',
  'cuga++': 'bg-emerald-900/60 text-emerald-300 border border-emerald-700/50',
  'infra':  'bg-gray-800 text-gray-400 border border-gray-700',
}

const CHANNEL_TYPE_STYLES: Record<string, string> = {
  data:    'bg-sky-900/40 text-sky-300 border border-sky-800/50',
  trigger: 'bg-amber-900/40 text-amber-300 border border-amber-800/50',
  output:  'bg-purple-900/40 text-purple-300 border border-purple-800/50',
}

function FilePill({ file }: { file: FileRef }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-gray-800 border border-gray-700 text-xs font-mono text-gray-400">
      <span className="text-gray-600">→</span>
      {file.label}
    </span>
  )
}

function StepRow({ step, index }: { step: FlowStep; index: number }) {
  return (
    <div className="flex gap-4">
      {/* Number + connector */}
      <div className="flex flex-col items-center flex-shrink-0">
        <div className="w-6 h-6 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center text-xs text-gray-500 font-mono">
          {index + 1}
        </div>
        <div className="w-px flex-1 bg-gray-800 mt-1" />
      </div>

      {/* Content */}
      <div className="pb-5 flex-1 min-w-0">
        <div className="flex items-start gap-2 flex-wrap mb-1.5">
          <span className="text-sm font-medium text-gray-200">{step.component}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${BADGE_STYLES[step.badge]}`}>
            {step.badge}
          </span>
        </div>
        <p className="text-sm text-gray-400 leading-relaxed mb-2">{step.what}</p>
        {step.io && (
          <div className="grid grid-cols-2 gap-2 mb-2 text-xs">
            <div className="bg-gray-900 rounded p-2 border border-gray-800">
              <div className="text-gray-600 mb-1">in</div>
              <div className="text-gray-400 font-mono">{step.io.in}</div>
            </div>
            <div className="bg-gray-900 rounded p-2 border border-gray-800">
              <div className="text-gray-600 mb-1">out</div>
              <div className="text-gray-400 font-mono">{step.io.out}</div>
            </div>
          </div>
        )}
        {step.file && <FilePill file={step.file} />}
      </div>
    </div>
  )
}

function ExampleCard({ example }: { example: Example }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full text-left px-5 py-4 bg-gray-900 hover:bg-gray-800/70 transition-colors flex items-start justify-between gap-4"
      >
        <div className="flex-1 min-w-0">
          {/* Chat bubble */}
          <div className="inline-flex items-start gap-2 mb-2">
            <span className="text-gray-600 text-sm mt-0.5">You:</span>
            <span className="text-indigo-300 text-sm font-medium leading-snug">"{example.utterance}"</span>
          </div>
          <p className="text-xs text-gray-500">{example.description}</p>
        </div>
        <span className="text-gray-600 text-sm flex-shrink-0 mt-0.5">{open ? '▲' : '▼'}</span>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="bg-gray-950 border-t border-gray-800 p-5 space-y-6">

          {/* Planner output */}
          {Object.keys(example.plannerConfig).length > 0 && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-2">ChannelPlanner extracts</div>
              <CodeBlock
                language="json"
                code={JSON.stringify(example.plannerConfig, null, 2)}
              />
            </div>
          )}

          {/* Channels */}
          {example.channels.length > 0 && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-2">Channels in play</div>
              <div className="space-y-2">
                {example.channels.map(ch => (
                  <div key={ch.name} className="flex items-start gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded font-mono flex-shrink-0 mt-0.5 ${CHANNEL_TYPE_STYLES[ch.type]}`}>
                      {ch.type}
                    </span>
                    <div>
                      <span className="text-sm font-medium text-gray-300">{ch.name}</span>
                      <span className="text-xs text-gray-500 ml-2">{ch.detail}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Steps */}
          <div>
            <div className="text-xs text-gray-600 uppercase tracking-wider mb-3">Step by step</div>
            <div>
              {example.steps.map((step, i) => (
                <StepRow key={i} step={step} index={i} />
              ))}
            </div>
          </div>

          {/* Notes */}
          {example.notes && (
            <div className="bg-amber-950/30 border border-amber-900/40 rounded-lg px-4 py-3 text-sm text-amber-300/80">
              ⚠ {example.notes}
            </div>
          )}

          {/* File references */}
          {example.files.length > 0 && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-2">Files</div>
              <div className="flex flex-wrap gap-2">
                {example.files.map(f => <FilePill key={f.path} file={f} />)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Architecture diagram (text-based)
// ---------------------------------------------------------------------------

const ARCH_CODE = `You (NL utterance)
  └─► ChannelPlanner          [cuga — planning agent, runs once]
        └─► CugaHostClient.start_runtime()
              └─► CugaHost    [cuga++ — daemon, port 18790]
                    └─► CugaRuntime
                          ├── RssChannel         [DataChannel]  → ChannelBuffer
                          ├── PodcastChannel     [DataChannel]  → Whisper → ChromaDB → ChannelBuffer
                          ├── CronChannel        [TriggerChannel]
                          │     └─► on tick: buffer → CugaAgent.invoke()
                          │                           [cuga — newsletter writer]
                          │                            └─► search_documents()  [optional RAG]
                          └── EmailChannel       [OutputChannel] ← agent HTML output`

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ExamplesPage() {
  const [activeTab, setActiveTab] = useState('monitor')
  const category = CATEGORIES.find(c => c.id === activeTab)!

  return (
    <div className="p-6 max-w-5xl mx-auto">

      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">Newsletter + Podcast Pipeline</h2>
        <p className="text-gray-400 text-sm leading-relaxed max-w-2xl">
          End-to-end walkthrough of the RSS + podcast newsletter use case. Each utterance below
          shows exactly which components activate, what goes in, and what comes out at every step.
        </p>
      </div>

      {/* Architecture overview */}
      <div className="mb-8 bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-300">Architecture</span>
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-indigo-500" /> cuga (agent)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500" /> cuga++ (infra)
            </span>
          </div>
        </div>
        <CodeBlock language="text" code={ARCH_CODE} />
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 mb-6 bg-gray-900 p-1 rounded-xl border border-gray-800">
        {CATEGORIES.map(cat => (
          <button
            key={cat.id}
            onClick={() => setActiveTab(cat.id)}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
              activeTab === cat.id
                ? 'bg-indigo-600/20 text-indigo-300 font-medium'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
            }`}
          >
            <span>{cat.icon}</span>
            <span className="hidden sm:inline">{cat.label}</span>
          </button>
        ))}
      </div>

      {/* Category description */}
      <p className="text-sm text-gray-500 mb-5 leading-relaxed">{category.description}</p>

      {/* Examples */}
      <div className="space-y-3">
        {category.examples.map((ex, i) => (
          <ExampleCard key={i} example={ex} />
        ))}
      </div>

      {/* Legend */}
      <div className="mt-10 pt-6 border-t border-gray-800">
        <div className="text-xs text-gray-600 uppercase tracking-wider mb-3">Channel types</div>
        <div className="flex flex-wrap gap-3 text-xs">
          {(['data', 'trigger', 'output'] as const).map(t => (
            <span key={t} className={`px-2 py-1 rounded font-mono ${CHANNEL_TYPE_STYLES[t]}`}>
              {t}
            </span>
          ))}
          <span className="text-gray-600 self-center">
            data → buffer → trigger wakes agent → output delivers
          </span>
        </div>
      </div>
    </div>
  )
}
