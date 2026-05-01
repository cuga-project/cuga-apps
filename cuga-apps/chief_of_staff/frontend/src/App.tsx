import { useEffect, useState, useCallback } from 'react';
import Chat from './components/Chat';
import ToolsPanel from './components/ToolsPanel';
import { health, HealthResponse } from './api/client';

export default function App() {
  const [status, setStatus] = useState<'unknown' | 'backend-up' | 'backend-down'>('unknown');
  const [info, setInfo] = useState<HealthResponse | null>(null);
  const [toolsRev, setToolsRev] = useState(0);

  const refreshHealth = useCallback(() => {
    health()
      .then((h) => {
        setStatus('backend-up');
        setInfo(h);
      })
      .catch(() => setStatus('backend-down'));
  }, []);

  useEffect(() => {
    refreshHealth();
    const i = setInterval(refreshHealth, 10_000);
    return () => clearInterval(i);
  }, [refreshHealth]);

  const onToolsChanged = useCallback(() => {
    setToolsRev((n) => n + 1);
    refreshHealth();
  }, [refreshHealth]);

  const ts = info?.toolsmith;
  const failedExtras = info?.failed_extras ?? [];
  return (
    <div className="h-full flex flex-col bg-white">
      <header className="border-b px-4 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Chief of Staff</h1>
        <div className="text-xs text-gray-500 space-x-2">
          <span>backend: {status}</span>
          <span>·</span>
          <span>planner: {info?.planner_reachable ? 'reachable' : 'stub'}</span>
          <span>·</span>
          <span>
            toolsmith: {ts?.status ?? 'unknown'}
            {ts?.coder ? ` (coder: ${ts.coder}` : ''}
            {ts?.coder ? `, llm: ${ts.orchestration_llm ? 'on' : 'off'})` : ''}
          </span>
          <span>·</span>
          <span>tools: {info?.tools_registered ?? 0}</span>
          {failedExtras.length > 0 && (
            <>
              <span>·</span>
              <span
                className="text-red-600 font-semibold"
                title={failedExtras
                  .map((f) => `${f.tool_name}: ${f.error_class ?? ''} ${f.error ?? ''}`)
                  .join('\n')}
              >
                {failedExtras.length} failed extra{failedExtras.length > 1 ? 's' : ''}
              </span>
            </>
          )}
        </div>
      </header>
      <main className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-hidden">
          <Chat onToolsChanged={onToolsChanged} />
        </div>
        <ToolsPanel rev={toolsRev} />
      </main>
    </div>
  );
}
