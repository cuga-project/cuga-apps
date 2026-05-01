import { useState } from 'react';
import { NeedsSecrets, setSecret } from '../api/client';

interface Props {
  needs: NeedsSecrets;
  onSubmitted: () => void;
}

export default function CredentialPrompt({ needs, onSubmitted }: Props) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(needs.missing.map((k) => [k, ''])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      for (const key of needs.missing) {
        const v = (values[key] || '').trim();
        if (!v) throw new Error(`missing value for ${key}`);
        await setSecret(needs.tool_id, key, v);
      }
      setDone(true);
      onSubmitted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="border border-green-300 bg-green-50 rounded-lg p-3 text-xs">
        <div className="text-green-900 font-semibold">Secret saved</div>
        <div className="text-green-800">
          Re-ask your question and Toolsmith will build {needs.api_name}.
        </div>
      </div>
    );
  }

  return (
    <div className="border border-blue-300 bg-blue-50 rounded-lg p-3 text-xs">
      <div className="font-semibold text-blue-900 mb-1">
        {needs.api_name} needs credentials
      </div>
      <div className="text-blue-800 mb-2">
        Toolsmith found a candidate but it can't run without:
      </div>
      <ul className="space-y-2">
        {needs.missing.map((key) => (
          <li key={key}>
            <label className="block text-blue-900 mb-0.5 font-mono">{key}</label>
            <input
              type="password"
              value={values[key] || ''}
              onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              disabled={busy}
              placeholder="paste secret value"
              className="w-full border rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring"
            />
          </li>
        ))}
      </ul>
      {needs.help && (
        <div className="text-[11px] text-gray-600 mt-2 whitespace-pre-line">{needs.help}</div>
      )}
      <div className="flex gap-2 mt-2">
        <button
          onClick={submit}
          disabled={busy}
          className="text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded px-3 py-1"
        >
          {busy ? '...' : 'Save'}
        </button>
        <span className="text-[10px] text-gray-500 self-center">
          Stored locally in the vault — never logged.
        </span>
      </div>
      {error && <div className="text-xs text-red-700 mt-2">error: {error}</div>}
    </div>
  );
}
