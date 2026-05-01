// Ideas & open questions — a scratchpad for strategic directions not yet on the formal roadmap.
// These are half-formed thoughts, not commitments. The goal is to capture them before they're lost.

import { useState } from 'react'

// ── Meeting intelligence use case gallery ─────────────────────────────────

interface UseCaseImage {
  src: string
  title: string
  caption: string
}

const MEETING_INTEL_IMAGES: UseCaseImage[] = [
  {
    src: '/usecases/5_Gemini_Generated_Image_94ouza94ouza94ou.png',
    title: 'CUGA Audior — The Foundation',
    caption: 'Transcription pipeline + visual intelligence + Scrum agent — the three core use cases on one canvas.',
  },
  {
    src: '/usecases/2_Gemini_Generated_Image_x2nckhx2nckhx2nc.png',
    title: 'Complete Meeting Intelligence Platform',
    caption: 'Ingestion → Whisper → diarization → ChromaDB. Per-meeting summaries, action items, cross-meeting synthesis, Jira/Slack output.',
  },
  {
    src: '/usecases/4_Gemini_Generated_Image_hmfo44hmfo44hmfo.png',
    title: 'Q&A Over a Video Recording',
    caption: 'Audio (Whisper) + slide deck (Docling) + keyframes (QWEN2-VL) → ChromaDB → cited answers.',
  },
  {
    src: '/usecases/3_Gemini_Generated_Image_upkg35upkg35upkg.png',
    title: 'Scrum Agent — Auto Notes + TODOs + Slack',
    caption: 'Speaker-diarized transcript → LLM extracts action items/owners/blockers → per-person todo lists → Slack → nightly cron standup.',
  },
  {
    src: '/usecases/1_Gemini_Generated_Image_1ofyee1ofyee1ofy.png',
    title: 'Topic-Filtered Slide Deck Assembly',
    caption: 'Ingest multiple decks, embed with ChromaDB, semantic search + QWEN2-VL re-rank, assemble a new topic-filtered deck.',
  },
]

function ImageGallery() {
  const [lightbox, setLightbox] = useState<UseCaseImage | null>(null)

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {MEETING_INTEL_IMAGES.map((img) => (
          <button
            key={img.src}
            onClick={() => setLightbox(img)}
            className="group text-left bg-gray-900 border border-gray-800 rounded-xl overflow-hidden hover:border-indigo-700/50 transition-colors"
          >
            <div className="overflow-hidden bg-gray-950">
              <img
                src={img.src}
                alt={img.title}
                className="w-full object-cover group-hover:scale-105 transition-transform duration-300"
              />
            </div>
            <div className="px-4 py-3">
              <div className="text-sm font-semibold text-gray-200 group-hover:text-indigo-300 transition-colors leading-tight">
                {img.title}
              </div>
              <div className="text-xs text-gray-500 mt-1 leading-relaxed">{img.caption}</div>
            </div>
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <div
            className="max-w-5xl w-full bg-gray-900 rounded-2xl overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <img src={lightbox.src} alt={lightbox.title} className="w-full" />
            <div className="px-6 py-4 border-t border-gray-800 flex items-start justify-between gap-4">
              <div>
                <div className="font-semibold text-white text-base">{lightbox.title}</div>
                <div className="text-sm text-gray-400 mt-0.5">{lightbox.caption}</div>
              </div>
              <button
                onClick={() => setLightbox(null)}
                className="text-gray-600 hover:text-gray-300 transition-colors text-xl flex-shrink-0"
              >
                ✕
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

interface Idea {
  title: string
  tldr: string
  why: string
  what: string[]
  questions: string[]
  horizon: 'near' | 'medium' | 'far'
  tag: string
}

const IDEAS: Idea[] = [
  {
    tag: 'Security',
    title: 'Security-first agent pipelines',
    tldr: 'The only agent I/O runtime with a security model baked in — not bolted on.',
    horizon: 'near',
    why: `Most agent frameworks treat security as an afterthought. A prompt injection attack on
an agent with shell access is catastrophic. An IMAP agent that processes malicious emails
and forwards them without sanitisation is a supply-chain attack vector. These aren't
hypothetical — they're already happening in production deployments.

CUGA++ has a head start: make_shell_tools() already has an allowlist model. The HITL
approval channel (roadmap) adds a human gate before sensitive actions. The question is
whether to formalise this into a first-class security layer.`,
    what: [
      'Prompt injection detection at the channel layer — flag adversarial content before it reaches the agent',
      'Input sanitisation in IMAPChannel / DoclingChannel — strip known injection patterns from extracted text',
      'Tool call auditing — every tool invocation logged with agent reasoning, caller, timestamp',
      'Allowlist-by-default for shell tools (already done) extended to all tool factories',
      'Secret scanning in make_shell_tools() output — redact API keys / credentials before delivery',
      'Rate limiting per channel — prevent runaway agents from hammering external APIs',
      'Sandboxed execution mode — run tool calls in Docker/subprocess isolation',
    ],
    questions: [
      'Is a "security profile" a selling point, or table stakes that all enterprise tools will have soon?',
      'Should the allowlist model be extended to ALL tool factories (not just shell)?',
      'Can prompt injection detection be accurate enough to not cause false positives on legitimate content?',
    ],
  },
  {
    tag: 'Scale',
    title: 'Horizontal scale and multi-tenant architecture',
    tldr: 'One CugaHost instance per team today. What does 10,000 tenants look like?',
    horizon: 'medium',
    why: `CugaHost runs one FastAPI/uvicorn process managing N runtimes. This scales vertically
(more RAM, more CPUs) but not horizontally. If CUGA++ becomes the infrastructure layer
for a SaaS platform — a document intelligence service, a newsletter platform, a monitoring
product — you need horizontal scaling, tenant isolation, and a proper job queue.

The current architecture is great for a single team's internal tooling. It's not designed
for running 10,000 independent agent pipelines for 10,000 customers.`,
    what: [
      'Replace asyncio.gather with a proper job queue (Celery + Redis, or the Kafka option below)',
      'Tenant isolation — each runtime runs in its own process/container with resource limits',
      'Stateless runtime workers — jobs pulled from queue, results pushed to output channels',
      'CugaHost becomes the control plane (submit, list, cancel jobs) not the execution plane',
      'Autoscaling worker pool — Kubernetes HPA or ECS based on queue depth',
      'Per-tenant rate limiting and billing hooks',
      'Shared-nothing architecture — no global state between tenants',
    ],
    questions: [
      'What is the smallest self-contained unit of work? (One runtime tick? One channel trigger?)',
      'Should the queue be pluggable (Redis, SQS, Kafka) or opinionated?',
      'At what scale does asyncio.gather actually become a bottleneck? (Probably not before 1000 concurrent runtimes)',
    ],
  },
  {
    tag: 'Kafka',
    title: 'Kafka as a first-class trigger and output channel',
    tldr: 'Replace polling with streaming — real-time event ingestion at enterprise scale.',
    horizon: 'medium',
    why: `CugaWatcher polls at an interval. CronChannel fires on a timer. Neither is designed
for high-throughput real-time event streams. Enterprise systems (Kafka, Kinesis, Pub/Sub)
produce millions of events per second. If CUGA++ is the "event-driven I/O layer for
intelligent agents," it should be able to consume from real event buses natively.

The gap: Kafka → CUGA++ requires writing a custom KafkaChannel today. There's no
first-class integration. For enterprises already running Kafka for their data pipelines,
this is a significant friction point.`,
    what: [
      'KafkaChannel (input) — consume from a Kafka topic, route each message to the agent',
      'KafkaOutputChannel — publish agent results to a Kafka topic for downstream consumers',
      'KinesisChannel / PubSubChannel — same pattern for AWS and GCP',
      'Message deduplication at the channel layer — Kafka at-least-once semantics handled by CUGA++',
      'Backpressure handling — if agent is slow, buffer or sample messages rather than crash',
      'Schema registry integration — auto-parse Avro/Protobuf messages to clean text',
      'Offset tracking persistence — resume from last processed offset on restart',
    ],
    questions: [
      'Is Kafka a real enterprise requirement or a nice-to-have? (What do the first 3 enterprise customers actually use?)',
      'Should this be a separate package (cugaio-kafka) or in the core channel library?',
      'Kafka + LLM is expensive — every Kafka event triggers an agent invocation. Need a filter/sampling layer.',
    ],
  },
  {
    tag: 'Privacy',
    title: 'Privacy and data residency as a product feature',
    tldr: 'Air-gapped, on-prem, local-model deployment — the enterprise privacy moat.',
    horizon: 'medium',
    why: `Enterprise AI adoption is blocked by one question more than any other: "where does
our data go?" Document intelligence pipelines process contracts, financial statements,
HR files, medical records. Running these through a cloud LLM API is a non-starter for
healthcare, legal, financial services, and government.

CUGA++ already supports Ollama (local models). This is the seed of a privacy story.
The question is whether to lean in and make "air-gapped deployment" a first-class product
feature, not just a configuration option.`,
    what: [
      'Local-first deployment guide — full CUGA++ stack running on a single machine with Ollama',
      'Data-at-rest encryption for cuga_checkpointer (conversation state stored encrypted)',
      'PII detection and redaction before external API calls — flag when data would leave the boundary',
      'Audit log per pipeline — every data movement logged with source, destination, timestamp',
      'GDPR-friendly deletion — "forget this user" removes all checkpointer state and RAG entries',
      'Model routing policy — route sensitive content to local model, non-sensitive to cloud',
      '"Privacy profile" per runtime — declare what data is in-scope, CUGA++ enforces the boundary',
    ],
    questions: [
      'Is the target customer regulated industry (healthcare, finance, legal) or general enterprise?',
      'Does "local-first" mean no cloud APIs at all, or just no cloud LLM? (Email, Slack, Telegram all touch cloud)',
      'Privacy certification (SOC 2, HIPAA BAA) — is this something to pursue, or just document the architecture?',
    ],
  },
  {
    tag: 'Enterprise',
    title: 'Enterprise-ready CUGA++ — the full picture',
    tldr: 'What it takes to go from "team tool" to "enterprise infrastructure."',
    horizon: 'medium',
    why: `"Enterprise-ready" is not a feature — it's a checklist of things enterprises require
before they'll put production workloads on your infrastructure. These requirements are
predictable. Most open-source tools that cross into enterprise have to rebuild the same
things. Better to design for them early.

The four pillars of enterprise readiness are: security (who can do what), observability
(what is happening), reliability (what happens when things fail), and compliance (audit
trail, data handling, certifications).`,
    what: [
      'SSO / SAML integration for CugaHost — enterprise auth, not API keys',
      'Role-based access control (RBAC) — who can create/modify/delete which runtimes',
      'Structured audit log — every agent invocation, tool call, and output delivery logged to append-only store',
      'OpenTelemetry integration — traces and metrics exported to Datadog, Grafana, Honeycomb',
      'SLA-aware retry logic — exponential backoff, dead-letter queues for failed pipeline runs',
      'Multi-region deployment support — run runtimes in eu-west-1 and us-east-1 with data residency controls',
      'Webhook signature verification — validate that incoming webhooks are from trusted sources',
      'Secret management integration — pull API keys from Vault / AWS Secrets Manager, not env vars',
      'Pipeline versioning — deploy pipeline v1 alongside v2, A/B test, rollback on failure',
    ],
    questions: [
      'Which of these are "must-have before first enterprise contract" vs "nice-to-have in year 2"?',
      'OpenTelemetry is the clear choice for observability — is the OpenLit integration already sufficient?',
      'Is CugaHost the right boundary for RBAC, or should this live at the pipeline/runtime level?',
    ],
  },
  {
    tag: 'Moat',
    title: 'Where the defensible moat actually is',
    tldr: 'Channels are commodity. These four things are not.',
    horizon: 'near',
    why: `Anyone can write a CronChannel in an afternoon. The moat is not the individual
components — it's what you can only build by having all of them together, in production,
across real use cases, over time. This is worth being explicit about.`,
    what: [
      'The benchmark environment — own the evaluation standard, own the reference point (see Vision page)',
      'Multimodal extraction pipeline — DoclingChannel + AudioChannel + VideoChannel before the agent fires (see Vision)',
      'Production hardening corpus — the bugs you\'ve already hit: MIME edge cases, cron isolation, async memory leaks, Pydantic v1/v2 conflicts. Nobody wants to rediscover these.',
      'Use case library as training data — 100+ real-world pipeline specs are valuable beyond benchmarking; they\'re fine-tuning data for an agent that can build pipelines from natural language',
      'Multi-user / multi-tenant by design — OpenClaw explicitly won\'t go here; LangGraph has no opinion on it',
      'The ChannelPlanner (roadmap) — describe a pipeline in English, get working code. If this works, cuga++ becomes the interface for non-engineers to deploy agent pipelines',
    ],
    questions: [
      'Is the benchmark actually defensible, or will someone fork the task list? (Answer: the execution environment + scoring is the moat, not the task list itself)',
      'Should the use case library be open-sourced aggressively to build the community, or kept proprietary?',
      'The ChannelPlanner could be the "killer app" that makes cuga++ accessible to non-engineers — is this Sprint 5 priority or a distraction?',
    ],
  },
]

const HORIZON_COLOR: Record<string, string> = {
  near: 'text-green-400 bg-green-900/20 border-green-800/30',
  medium: 'text-yellow-400 bg-yellow-900/20 border-yellow-800/30',
  far: 'text-purple-400 bg-purple-900/20 border-purple-800/30',
}

const HORIZON_LABEL: Record<string, string> = {
  near: 'Near-term',
  medium: 'Medium-term',
  far: 'Longer-term',
}

const TAG_COLOR: Record<string, string> = {
  Security: 'bg-red-900/30 text-red-300 border-red-800/40',
  Scale: 'bg-blue-900/30 text-blue-300 border-blue-800/40',
  Kafka: 'bg-orange-900/30 text-orange-300 border-orange-800/40',
  Privacy: 'bg-teal-900/30 text-teal-300 border-teal-800/40',
  Enterprise: 'bg-indigo-900/30 text-indigo-300 border-indigo-800/40',
  Moat: 'bg-purple-900/30 text-purple-300 border-purple-800/40',
}

export default function IdeasPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-white mb-2">Ideas & Open Questions</h2>
        <p className="text-gray-400 text-sm max-w-2xl">
          Half-formed thoughts on where CUGA++ could go. Not commitments. Captured here so they're not lost.
          Each idea has a <em>why</em>, a <em>what</em>, and the honest <em>questions</em> that need answering before it makes sense to build.
        </p>
      </div>

      {/* ── Use Case Gallery ── */}
      <div className="mb-12">
        <div className="flex items-center gap-3 mb-1">
          <h3 className="text-base font-semibold text-white">Meeting Intelligence — Use Cases</h3>
          <span className="text-xs px-2 py-0.5 rounded border bg-indigo-900/30 text-indigo-300 border-indigo-800/40">Near-term</span>
        </div>
        <p className="text-sm text-gray-500 mb-5 max-w-2xl">
          A suite of CUGA++ pipelines for meeting audio and video — transcription, Q&A, action items, slide assembly.
          Each diagram below is a standalone use case. Click to expand.
        </p>
        <ImageGallery />
      </div>

      {/* ── CUGA as Generalist ── */}
      <div className="mb-12">
        <div className="flex items-center gap-3 mb-1">
          <h3 className="text-base font-semibold text-white">CUGA as a Generalist Agent</h3>
          <span className="text-xs px-2 py-0.5 rounded border bg-yellow-900/20 text-yellow-400 border-yellow-800/30">Open question</span>
        </div>
        <p className="text-sm text-gray-500 mb-5 max-w-2xl">
          Capability gaps where CUGA++ could expand beyond event-driven pipelines — and benchmarks that would validate each.
          The open question: do we go broad (generalist agent) or deep in one domain?
        </p>

        {/* Gap table */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden mb-6">
          <div className="grid grid-cols-[1fr_2fr_1fr] text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-3 border-b border-gray-800 bg-gray-950/50">
            <div>Gap</div>
            <div>Capability / Use Case</div>
            <div>Benchmark</div>
          </div>
          {[
            {
              gap: 'Doc Intelligence',
              priority: 'easy',
              capabilities: ['Docling parsing — structured extraction from PDF, PPTX, DOCX'],
              benchmarks: ['FinanceBench', 'TAT-QA'],
            },
            {
              gap: 'Desktop Automation',
              priority: null,
              capabilities: [
                'Computer-use: screen reading + native controls',
                'Clean and organize the file system',
              ],
              benchmarks: ['OSWorld'],
            },
            {
              gap: 'Vision / MultiModal',
              priority: null,
              capabilities: [
                'Vision-ready LLMs (keyframe + diagram understanding)',
                'IBM Core Training creation',
                'Hunting for copyright violations',
              ],
              benchmarks: ['VisualWebArena', 'DocVQA', 'ChartQA'],
            },
            {
              gap: 'Long Planning',
              priority: null,
              capabilities: [
                'Mid-task recovery',
                'Create IBM Cloud account + resources + onboard team',
                'Migrate corporate workload (HR → SAP, multi-stage)',
              ],
              benchmarks: ['GAIA L3'],
            },
            {
              gap: 'Code Understanding',
              priority: 'nice-to-have',
              capabilities: ['Repo mapping + AST tools'],
              benchmarks: ['SWE-bench'],
            },
            {
              gap: 'Database Operations',
              priority: 'nice-to-have',
              capabilities: ['Schema introspection'],
              benchmarks: ['BIRD', 'Spider', 'M3'],
            },
          ].map((row, i) => (
            <div
              key={row.gap}
              className={`grid grid-cols-[1fr_2fr_1fr] px-5 py-3.5 text-sm gap-4 ${
                i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950/30'
              } border-b border-gray-800/50 last:border-0`}
            >
              <div>
                <div className="text-gray-200 font-medium leading-snug">{row.gap}</div>
                {row.priority && (
                  <span className={`text-xs mt-1 inline-block px-1.5 py-0.5 rounded border ${
                    row.priority === 'easy'
                      ? 'bg-green-900/20 text-green-400 border-green-800/30'
                      : 'bg-gray-800/60 text-gray-500 border-gray-700/40'
                  }`}>
                    {row.priority}
                  </span>
                )}
              </div>
              <ul className="space-y-1">
                {row.capabilities.map((c) => (
                  <li key={c} className="text-xs text-gray-400 leading-relaxed">
                    • {c}
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap gap-1 content-start">
                {row.benchmarks.map((b) => (
                  <span key={b} className="text-xs px-2 py-0.5 rounded bg-indigo-900/20 text-indigo-400 border border-indigo-800/30 font-mono">
                    {b}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Open question card */}
        <div className="bg-yellow-950/20 border border-yellow-800/30 rounded-xl px-5 py-4">
          <div className="text-xs font-semibold text-yellow-500 uppercase tracking-wider mb-2">The strategic question</div>
          <p className="text-sm text-gray-300 leading-relaxed mb-3">
            <strong className="text-white">Breadth vs. depth.</strong> The table above shows CUGA++ could expand in many directions.
            But spreading thin across all of them risks building nothing that's best-in-class.
          </p>
          <ul className="space-y-2">
            {[
              'Go generalist: cover all gaps, position as the agent I/O layer for any workload — competes with LangGraph, n8n',
              'Go deep on one domain: e.g., meeting intelligence (audio + video + deck + Q&A) as a complete, shippable product',
              'Go deep on enterprise multimodal (Box + Slack + email corpus) — a niche nobody owns yet',
              'Pick one benchmark and own it: highest GAIA L3 score, or best DocVQA pipeline — credibility as evaluation vehicle',
            ].map((q) => (
              <li key={q} className="flex gap-2 text-xs text-gray-400 leading-relaxed">
                <span className="text-yellow-600 mt-0.5 flex-shrink-0">→</span>
                {q}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Strategic Ideas ── */}
      <div className="mb-6">
        <h3 className="text-base font-semibold text-white mb-1">Strategic directions</h3>
        <p className="text-sm text-gray-500 mb-5">Half-formed thoughts on platform direction. Not commitments.</p>
      </div>

      <div className="space-y-5">
        {IDEAS.map((idea) => (
          <div key={idea.tag} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            {/* Header */}
            <div className="px-6 pt-5 pb-4 border-b border-gray-800">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-2.5">
                  <span className={`text-xs font-mono px-2 py-0.5 rounded border ${TAG_COLOR[idea.tag]}`}>
                    {idea.tag}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded border ${HORIZON_COLOR[idea.horizon]}`}>
                    {HORIZON_LABEL[idea.horizon]}
                  </span>
                </div>
              </div>
              <h3 className="text-base font-semibold text-white mt-2">{idea.title}</h3>
              <p className="text-sm text-gray-400 mt-0.5">{idea.tldr}</p>
            </div>

            {/* Body */}
            <div className="px-6 py-4 grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Why */}
              <div className="md:col-span-2">
                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Why this matters</div>
                <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-line">{idea.why.trim()}</p>
              </div>

              {/* What to build */}
              <div>
                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">What to build</div>
                <ul className="space-y-1.5">
                  {idea.what.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-400">
                      <span className="text-indigo-600 mt-0.5 flex-shrink-0">▸</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Open questions */}
              <div>
                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Open questions</div>
                <ul className="space-y-2">
                  {idea.questions.map((q, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-500 leading-relaxed">
                      <span className="text-gray-700 mt-0.5 flex-shrink-0">?</span>
                      {q}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 bg-gray-900/50 border border-gray-800 rounded-xl p-4 text-xs text-gray-600 leading-relaxed">
        These ideas were captured based on the question: "how do we make CUGA++ enterprise-friendly?" The framing is: security (prompt injection, tool allowlists, audit logs), scale (Kafka, horizontal workers, multi-tenant), privacy (local models, data residency, GDPR), and the defensible moat (benchmark + multimodal + production hardening). Not buzz words — these are the actual requirements that appear in every enterprise AI evaluation.
      </div>
    </div>
  )
}
