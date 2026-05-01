import { useEffect, useState } from 'react';
import { listTools, refreshTools, toggleTool, ToolRecord } from '../api/client';

function prettySource(source: string): string {
  if (source.startsWith('mcp:')) return `MCP · ${source.slice(4)}`;
  if (source === 'generated') return 'Generated';
  return source;
}

interface Props {
  rev?: number;
}

export default function ToolsPanel({ rev = 0 }: Props) {
  const [tools, setTools] = useState<ToolRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setTools(await listTools());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function refresh() {
    setLoading(true);
    try {
      await refreshTools();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function onToggle(t: ToolRecord) {
    const next = !t.disabled;
    setBusy(t.name);
    setError(null);
    try {
      await toggleTool(t.name, next);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    load();
  }, [rev]);

  // Split into the two top-level buckets the user wants to see distinctly.
  const preloaded = tools.filter((t) => !t.acquired);
  const acquired = tools.filter((t) => !!t.acquired);

  function bySource(list: ToolRecord[]): Record<string, ToolRecord[]> {
    const out: Record<string, ToolRecord[]> = {};
    for (const t of list) (out[t.source] ??= []).push(t);
    return out;
  }

  const disabledCount = tools.filter((t) => t.disabled).length;

  return (
    <aside className="border-l w-72 flex flex-col bg-gray-50">
      <div className="px-3 py-2 border-b flex items-center justify-between">
        <h2 className="text-sm font-semibold">
          Tools ({tools.length}
          {disabledCount > 0 && <span className="text-amber-600"> · {disabledCount} off</span>})
        </h2>
        <button
          onClick={refresh}
          disabled={loading}
          className="text-xs text-blue-600 hover:underline disabled:opacity-50"
        >
          {loading ? '...' : 'refresh'}
        </button>
      </div>
      {error && <div className="px-3 py-2 text-xs text-red-600">error: {error}</div>}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-4 text-xs">
        {tools.length === 0 && !loading && (
          <div className="text-gray-500">
            No tools registered. Start the cuga adapter and click refresh.
          </div>
        )}

        <Bucket
          title="Pre-loaded"
          subtitle="from MCP_SERVERS env"
          accent="blue"
          tools={preloaded}
          bySource={bySource(preloaded)}
          busy={busy}
          onToggle={onToggle}
        />

        <Bucket
          title="Acquired by Toolsmith"
          subtitle="catalog mounts + generated"
          accent="emerald"
          tools={acquired}
          bySource={bySource(acquired)}
          busy={busy}
          onToggle={onToggle}
          emptyHint="Nothing acquired yet — disable a pre-loaded tool and ask a question that needs it."
        />
      </div>
    </aside>
  );
}

interface BucketProps {
  title: string;
  subtitle: string;
  accent: 'blue' | 'emerald';
  tools: ToolRecord[];
  bySource: Record<string, ToolRecord[]>;
  busy: string | null;
  onToggle: (t: ToolRecord) => void;
  emptyHint?: string;
}

function Bucket({ title, subtitle, accent, tools, bySource, busy, onToggle, emptyHint }: BucketProps) {
  const headerColor = accent === 'blue' ? 'text-blue-700' : 'text-emerald-700';
  const dotColor = accent === 'blue' ? 'bg-blue-500' : 'bg-emerald-500';
  return (
    <section>
      <div className="flex items-center gap-2 mb-1">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColor}`} />
        <span className={`text-[11px] font-semibold ${headerColor}`}>{title}</span>
        <span className="text-gray-400 text-[10px]">({tools.length})</span>
        <span className="text-gray-400 text-[10px] ml-auto">{subtitle}</span>
      </div>
      {tools.length === 0 ? (
        <div className="text-gray-400 text-[11px] italic px-1 py-1">
          {emptyHint ?? 'Nothing here.'}
        </div>
      ) : (
        Object.entries(bySource).map(([source, items]) => (
          <div key={source} className="mb-2">
            <div className="text-gray-400 uppercase tracking-wide text-[10px] mb-1">
              {prettySource(source)}{' '}
              <span className="text-gray-300 normal-case">({items.length})</span>
            </div>
            <ul className="space-y-1">
              {items.map((t) => (
                <li
                  key={t.id}
                  className={
                    'border rounded px-2 py-1 flex items-start gap-2 ' +
                    (t.disabled ? 'bg-amber-50 border-amber-200' : 'bg-white')
                  }
                >
                  <div className="flex-1 min-w-0">
                    <div
                      className={
                        'font-mono text-[11px] ' + (t.disabled ? 'line-through text-gray-500' : '')
                      }
                    >
                      {t.name}
                    </div>
                    {t.description && (
                      <div className="text-gray-500 text-[11px] line-clamp-2">{t.description}</div>
                    )}
                  </div>
                  <button
                    onClick={() => onToggle(t)}
                    disabled={busy === t.name}
                    title={t.disabled ? 'enable this tool' : 'disable this tool for the next chat'}
                    className={
                      'shrink-0 text-[10px] px-1.5 py-0.5 rounded border ' +
                      (t.disabled
                        ? 'border-amber-400 text-amber-800 hover:bg-amber-100'
                        : 'border-gray-300 text-gray-600 hover:bg-gray-100') +
                      ' disabled:opacity-50'
                    }
                  >
                    {busy === t.name ? '...' : t.disabled ? 'enable' : 'disable'}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
