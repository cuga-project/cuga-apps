import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { USE_CASES, CATEGORIES, STATUS_LABELS, type UseCaseType } from '../data/usecases'
import { resolveAppUrl } from '../data/deployment'
import Badge from '../components/Badge'
import CodeBlock from '../components/CodeBlock'

const TYPE_CONFIG: Record<UseCaseType, { label: string; cls: string }> = {
  'event-driven':          { label: 'Event-driven',          cls: 'bg-amber-900/40 text-amber-300 border border-amber-700/50' },
  'document-intelligence': { label: 'Document Intelligence', cls: 'bg-cyan-900/40 text-cyan-300 border border-cyan-700/50' },
  'audio-video':           { label: 'Audio / Video',         cls: 'bg-violet-900/40 text-violet-300 border border-violet-700/50' },
  'other':                 { label: 'Other',                 cls: 'bg-gray-800/40 text-gray-300 border border-gray-600/50' },
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }
  return (
    <button
      onClick={copy}
      title="Copy to clipboard"
      className="flex-shrink-0 px-2 py-0.5 text-xs rounded transition-colors border border-gray-700 hover:border-indigo-500 text-gray-500 hover:text-indigo-400"
    >
      {copied ? '✓ copied' : 'copy'}
    </button>
  )
}

export default function UseCaseDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const uc = USE_CASES.find((u) => u.id === id)

  if (!uc) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-500">Use case not found.</p>
        <button onClick={() => navigate('/')} className="mt-4 text-indigo-400 hover:text-indigo-300 text-sm">
          ← Back to use cases
        </button>
      </div>
    )
  }

  const cat = CATEGORIES[uc.category]
  const statusInfo = STATUS_LABELS[uc.status]

  const setupCode = [
    ...uc.howToRun.setup,
    '',
    '# Environment variables',
    ...uc.howToRun.envVars.map((v) => `export ${v}=<your-value>`),
  ].join('\n')

  const runCode = uc.howToRun.command

  const envFileContent = uc.howToRun.envVars.map((v) => `${v}=`).join('\n')

  // Effective URL based on deployment target. null on Hugging Face when
  // this app isn't deployed to CE (tier 3); null locally when uc.appUrl
  // itself is null.
  const launchUrl = resolveAppUrl(uc)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Back */}
      <button
        onClick={() => navigate('/')}
        className="text-gray-500 hover:text-gray-300 text-sm mb-5 flex items-center gap-1.5 transition-colors"
      >
        ← All use cases
      </button>

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-2xl font-semibold text-white">{uc.name}</h2>
            <p className="text-gray-400 mt-1">{uc.tagline}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 flex-wrap">
            <Badge label={cat.label} color={cat.color as any} />
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${TYPE_CONFIG[uc.type].cls}`}>
              {TYPE_CONFIG[uc.type].label}
            </span>
            <Badge label={statusInfo.label} color={statusInfo.color as any} />
            {/* Future: Launch App button */}
            {launchUrl ? (
              <a
                href={launchUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Launch App →
              </a>
            ) : (
              <button
                disabled
                className="px-4 py-1.5 bg-gray-800 text-gray-500 text-sm font-medium rounded-lg cursor-not-allowed border border-gray-700"
                title="Interactive app coming soon"
              >
                Launch App (soon)
              </button>
            )}
          </div>
        </div>

        <p className="text-gray-300 text-sm mt-4 leading-relaxed">{uc.description}</p>
      </div>

      {/* Channels + Tools */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Channels</h3>
          <div className="flex flex-wrap gap-1.5">
            {uc.channels.map((c) => (
              <span key={c} className="text-xs font-mono px-2 py-1 bg-indigo-900/30 text-indigo-300 border border-indigo-800/40 rounded">
                {c}
              </span>
            ))}
            {uc.channels.length === 0 && <span className="text-xs text-gray-600">—</span>}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Tool Factories</h3>
          <div className="flex flex-wrap gap-1.5">
            {uc.tools.map((t) => (
              <span key={t} className="text-xs font-mono px-2 py-1 bg-purple-900/30 text-purple-300 border border-purple-800/40 rounded">
                {t}
              </span>
            ))}
            {uc.tools.length === 0 && <span className="text-xs text-gray-600">No additional tools</span>}
          </div>
        </div>
      </div>

      {/* MCP servers + tools consumed */}
      {(uc.mcpUsage?.length || uc.inlineTools?.length) ? (
        <section className="mb-8 bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">MCP Servers &amp; Tools</h3>
          <div className="flex flex-col gap-3">
            {uc.mcpUsage?.map((u) => (
              <div key={u.server} className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider px-2 py-1 rounded bg-emerald-900/30 text-emerald-300 border border-emerald-800/40">
                  mcp-{u.server}
                </span>
                <span className="text-gray-600">→</span>
                {u.tools.map((t) => (
                  <span key={t} className="text-xs font-mono px-2 py-1 bg-emerald-950/30 text-emerald-200 border border-emerald-900/40 rounded">
                    {t}
                  </span>
                ))}
              </div>
            ))}
            {(uc.inlineTools?.length ?? 0) > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider px-2 py-1 rounded bg-amber-900/30 text-amber-300 border border-amber-800/40">
                  inline
                </span>
                <span className="text-gray-600">→</span>
                {uc.inlineTools!.map((t) => (
                  <span key={t} className="text-xs font-mono px-2 py-1 bg-amber-950/30 text-amber-200 border border-amber-900/40 rounded">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-3">
            <span className="text-emerald-400">mcp-*</span> tools are served by shared MCP servers (browse them at <a className="underline" href="http://localhost:28900" target="_blank" rel="noreferrer">/tool-explorer</a>).
            <span className="text-amber-400"> inline</span> tools live in the app process — they touch app-state (DB, sessions, vendor auth) that can't be shared.
          </p>
        </section>
      ) : null}

      {/* Architecture */}
      <section className="mb-8">
        <h3 className="text-base font-semibold text-white mb-3">Architecture</h3>
        <p className="text-gray-300 text-sm leading-relaxed mb-4">{uc.architecture}</p>
        <div className="bg-gray-950 border border-gray-800 rounded-xl p-4">
          <pre className="text-xs text-gray-400 font-mono leading-relaxed whitespace-pre">{uc.diagram}</pre>
        </div>
      </section>

      {/* What CUGA contributes */}
      <section className="mb-8">
        <h3 className="text-base font-semibold text-white mb-3">What CUGA enables</h3>
        <ul className="space-y-2">
          {uc.cugaContribution.map((point, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-gray-300">
              <span className="text-indigo-400 mt-0.5 flex-shrink-0">▸</span>
              {point}
            </li>
          ))}
        </ul>
      </section>

      {/* Try these examples */}
      {uc.examples && uc.examples.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <h3 className="text-base font-semibold text-white">Try these</h3>
            {launchUrl && (
              <span className="text-xs text-gray-500">
                — type into the app at{' '}
                <a href={launchUrl} target="_blank" rel="noopener noreferrer"
                  className="text-indigo-400 hover:text-indigo-300 font-mono"
                >
                  {launchUrl}
                </a>
              </span>
            )}
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden divide-y divide-gray-800/60">
            {uc.examples.map((ex, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-2.5 group hover:bg-gray-800/30 transition-colors">
                <span className="text-gray-600 text-xs font-mono mt-0.5 w-4 flex-shrink-0">{i + 1}</span>
                <pre className="flex-1 text-sm text-gray-300 font-mono whitespace-pre-wrap leading-relaxed min-w-0">{ex}</pre>
                <div className="opacity-0 group-hover:opacity-100 transition-opacity mt-0.5">
                  <CopyButton text={ex} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* How to run */}
      <section className="mb-8">
        <h3 className="text-base font-semibold text-white mb-4">How to run</h3>

        <div className="space-y-4">
          {/* Step 1: Setup */}
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              1 — Setup &amp; environment variables
            </h4>
            <CodeBlock code={setupCode} language="bash" />
          </div>

          {/* Step 2: .env */}
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              2 — Create a .env file
            </h4>
            <CodeBlock code={envFileContent} language=".env" />
          </div>

          {/* Step 3: Run */}
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              3 — Run
            </h4>
            <CodeBlock code={runCode} language="bash" />
          </div>
        </div>
      </section>

      {/* Demo path */}
      {uc.demoPath && (
        <section className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-sm text-gray-400">
          <span className="text-gray-600 text-xs font-semibold uppercase tracking-wider">Source path</span>
          <div className="font-mono text-xs text-gray-400 mt-1">{uc.demoPath}</div>
        </section>
      )}
    </div>
  )
}
