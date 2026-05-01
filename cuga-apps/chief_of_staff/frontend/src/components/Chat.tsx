import { FormEvent, useState } from 'react';
import { AcquisitionResult, ChatResponse, sendChat, ToolCall } from '../api/client';
import CredentialPrompt from './CredentialPrompt';

type Turn = {
  role: 'user' | 'agent';
  text: string;
  gap?: ChatResponse['gap'];
  acquisition?: AcquisitionResult | null;
  toolsUsed?: ToolCall[];
};

interface Props {
  onToolsChanged?: () => void;
}

export default function Chat({ onToolsChanged }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || pending) return;
    setInput('');
    setTurns((t) => [...t, { role: 'user', text: msg }]);
    setPending(true);
    try {
      const r = await sendChat(msg);
      setTurns((t) => [
        ...t,
        {
          role: 'agent',
          text: r.error ? `error: ${r.error}` : r.response || '(no answer)',
          gap: r.gap,
          acquisition: r.acquisition,
          toolsUsed: r.tools_used ?? [],
        },
      ]);
      if (r.acquisition?.success) {
        onToolsChanged?.();
      }
    } catch (err) {
      setTurns((t) => [...t, { role: 'agent', text: `error: ${(err as Error).message}` }]);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto p-4">
      <div className="flex-1 overflow-y-auto space-y-3 pb-4">
        {turns.length === 0 && (
          <div className="text-gray-400 text-sm">
            Ask anything. If I'm missing a tool, Toolsmith will build one and tell you.
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === 'user' ? 'text-right' : 'text-left space-y-2'}>
            <div
              className={
                'inline-block rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ' +
                (t.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-900')
              }
            >
              {t.text}
            </div>
            {t.role === 'agent' && t.toolsUsed && t.toolsUsed.length > 0 && (
              <div className="text-[11px] text-gray-500 font-mono space-x-1">
                <span>via:</span>
                {t.toolsUsed.map((tc, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center bg-gray-100 rounded overflow-hidden"
                    title={tc.server ? `from ${tc.server} MCP server` : 'runtime-generated tool'}
                  >
                    <span className="px-1.5 py-0.5">{tc.name}</span>
                    <span
                      className={
                        'px-1.5 py-0.5 text-[10px] uppercase tracking-wide ' +
                        (tc.server
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-emerald-100 text-emerald-700')
                      }
                    >
                      {tc.server ? `mcp · ${tc.server}` : 'generated'}
                    </span>
                  </span>
                ))}
              </div>
            )}
            {t.role === 'agent' && t.toolsUsed && t.toolsUsed.length === 0 && !t.acquisition && (
              <div className="text-[11px] text-gray-400 italic">
                (no tools called — answered from the model directly)
              </div>
            )}
            {t.role === 'agent' && t.acquisition && (
              <>
                <AcquisitionNotice acquisition={t.acquisition} />
                {t.acquisition.needs_secrets && (
                  <CredentialPrompt
                    needs={t.acquisition.needs_secrets}
                    onSubmitted={() => onToolsChanged?.()}
                  />
                )}
              </>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={onSubmit} className="flex gap-2 border-t pt-3">
        <input
          className="flex-1 border rounded px-3 py-2 text-sm focus:outline-none focus:ring"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything..."
          disabled={pending}
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          className="bg-blue-600 text-white rounded px-4 py-2 text-sm disabled:opacity-50"
        >
          {pending ? '...' : 'Send'}
        </button>
      </form>
    </div>
  );
}

function AcquisitionNotice({ acquisition }: { acquisition: AcquisitionResult }) {
  const ok = acquisition.success;
  const alreadyExisted = !ok && !!acquisition.already_existed;

  // Three states: built (green), already-had-it (blue), failed (amber).
  const palette = ok
    ? { border: 'border-green-300', bg: 'bg-green-50', title: 'text-green-900', body: 'text-green-800' }
    : alreadyExisted
    ? { border: 'border-blue-300', bg: 'bg-blue-50', title: 'text-blue-900', body: 'text-blue-800' }
    : { border: 'border-amber-300', bg: 'bg-amber-50', title: 'text-amber-900', body: 'text-amber-800' };

  const title = ok
    ? 'Toolsmith built a tool'
    : alreadyExisted
    ? 'Tool already in your toolbox'
    : "Toolsmith couldn't build a tool";

  return (
    <div className={`border rounded-lg p-2 text-xs ${palette.border} ${palette.bg}`}>
      <div className={`font-semibold ${palette.title}`}>{title}</div>
      <div className={palette.body}>{acquisition.summary}</div>
      {acquisition.artifact_id && (
        <div className="text-gray-500 mt-0.5 font-mono">{acquisition.artifact_id}</div>
      )}
      {ok && (
        <div className="text-gray-600 mt-1">
          Try asking again — the new tool is now available.
        </div>
      )}
      {alreadyExisted && (
        <div className="text-gray-600 mt-1">
          Re-running your question against the existing tool — the answer above is from the retry.
        </div>
      )}
    </div>
  );
}
