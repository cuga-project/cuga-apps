export interface NeedsSecrets {
  tool_id: string;
  tool_name: string;
  api_name: string;
  required: string[];
  missing: string[];
  auth: { type: string; secret_key: string; help?: string } | null;
  help: string;
}

export interface AcquisitionResult {
  success: boolean;
  artifact_id: string | null;
  summary: string;
  transcript: { role: string; content: string }[];
  needs_secrets: NeedsSecrets | null;
  already_existed?: boolean;
}

export interface ToolCall {
  name: string;
  server: string | null;
}

export interface ChatResponse {
  response: string;
  thread_id: string;
  error: string | null;
  gap: { capability?: string; expected_output?: string; inputs?: string[] } | null;
  acquisition: AcquisitionResult | null;
  tools_used: ToolCall[];
}

export interface ToolRecord {
  id: string;
  name: string;
  source: string;
  description: string;
  health: string;
  disabled?: boolean;
  acquired?: boolean;
}

export interface ToolsmithHealth {
  status?: string;
  coder?: string | null;
  orchestration_llm?: boolean;
  artifact_count?: number;
}

export interface FailedExtra {
  tool_name: string;
  artifact_id?: string | null;
  error_class?: string;
  error?: string;
}

export interface HealthResponse {
  status: string;
  planner_reachable: boolean;
  toolsmith: ToolsmithHealth;
  tools_registered: number;
  failed_extras?: FailedExtra[];
}

export interface Artifact {
  id: string;
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  requires_secrets: string[];
  provenance: Record<string, unknown>;
  version: number;
  last_probe_ok: boolean | null;
  last_probe_at: string | null;
}

const BASE = '/api';

export async function sendChat(message: string, threadId = 'default'): Promise<ChatResponse> {
  const r = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!r.ok) throw new Error(`chat failed: ${r.status}`);
  return r.json();
}

export async function health(): Promise<HealthResponse> {
  const r = await fetch(`${BASE}/health`);
  if (!r.ok) throw new Error(`health failed: ${r.status}`);
  return r.json();
}

export async function listTools(): Promise<ToolRecord[]> {
  const r = await fetch(`${BASE}/tools`);
  if (!r.ok) throw new Error(`tools failed: ${r.status}`);
  return r.json();
}

export async function refreshTools(): Promise<{ synced: number }> {
  const r = await fetch(`${BASE}/tools/refresh`, { method: 'POST' });
  if (!r.ok) throw new Error(`refresh failed: ${r.status}`);
  return r.json();
}

export async function listArtifacts(): Promise<Artifact[]> {
  const r = await fetch(`${BASE}/toolsmith/artifacts`);
  if (!r.ok) throw new Error(`artifacts failed: ${r.status}`);
  return r.json();
}

export async function removeArtifact(artifactId: string): Promise<{ removed: boolean }> {
  const r = await fetch(`${BASE}/toolsmith/artifacts/${encodeURIComponent(artifactId)}`, {
    method: 'DELETE',
  });
  if (!r.ok) throw new Error(`remove failed: ${r.status}`);
  return r.json();
}

export async function setSecret(toolId: string, secretKey: string, value: string): Promise<{ stored: boolean }> {
  const r = await fetch(`${BASE}/vault/secret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_id: toolId, secret_key: secretKey, value }),
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => '');
    throw new Error(`secret set failed: ${r.status} ${detail}`);
  }
  return r.json();
}

export async function deleteSecret(toolId: string, secretKey?: string): Promise<{ deleted: boolean }> {
  const r = await fetch(`${BASE}/vault/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_id: toolId, secret_key: secretKey ?? null }),
  });
  if (!r.ok) throw new Error(`secret delete failed: ${r.status}`);
  return r.json();
}

export async function listVaultKeys(toolId: string): Promise<{ tool_id: string; keys: string[]; backend: string }> {
  const r = await fetch(`${BASE}/vault/keys/${encodeURIComponent(toolId)}`);
  if (!r.ok) throw new Error(`vault keys failed: ${r.status}`);
  return r.json();
}

export async function toggleTool(name: string, disabled: boolean): Promise<{ name: string; disabled: boolean; all_disabled: string[] }> {
  const r = await fetch(`${BASE}/tools/${encodeURIComponent(name)}/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disabled }),
  });
  if (!r.ok) throw new Error(`toggle failed: ${r.status}`);
  return r.json();
}
