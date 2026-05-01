# Chief of Staff

A single chat UI that aggregates every MCP server in `mcp_servers/*` through
one cuga planner — and (in later phases) autonomously acquires new tools when
it hits a gap. Self-contained: nothing outside this directory is modified.

## What's shipped

**Phase 1 — registry + adapter + discovery**
- Out-of-process cuga adapter wrapping `cuga.sdk.CugaAgent`
- MCP discovery → SQLite registry, with retry on cold start
- Stub fallback when adapter is unreachable

**Phase 2 — catalog acquisition**
- Structured `[[TOOL_GAP]]` signal; orchestrator parses it
- Curated YAML catalog with token-overlap matcher
- Consent prompt; live agent reload; per-acquisition activations

**Phase 3 — OpenAPI generation + autoresearch probe**
- Source plugin pattern with `CatalogSource` + `OpenAPISource`
- Probe harness (structural + optional LLM judge) — the autoresearch keep/discard gate
- Live tool mounting via the cuga adapter's `extra_tools`

**Phase 4 — browser-driven tools**
- New service [browser_runner/](browser_runner/) on port 8002 — Playwright + Chromium running in its own container, with persistent Chrome user-data profiles per provider. Falls back to a `MockExecutor` when Playwright isn't installed (tests).
- **Browser task DSL** ([browser_runner/dsl.py](browser_runner/dsl.py)) — declarative YAML: `go_to`, `click_text`, `click_selector`, `fill_field`, `wait_for_text`, `wait_for_selector`, `extract_text`, `screenshot`, `ensure_logged_in`, `user_confirm`, `sleep`. Variables interpolate from inputs (`${var}`) or secrets.
- **BrowserSource** plugin ([backend/acquisition/sources/browser_source.py](backend/acquisition/sources/browser_source.py)) — curated `browser_tasks.yaml` with seeded templates: HN scraping, Wikipedia website search, GitHub repo About scraping, plus auth-required templates for school portals, utility billing, and confirmable form submission.
- **Adapter dispatch**: artifacts now carry `kind` ("code" or "browser_task"). When `kind=browser_task`, the cuga adapter forwards the call to `browser-runner /execute` with the steps + interpolated inputs + injected secrets.
- **`user_confirm` step** webhooks the backend so the UI can pause for human approval (phase 4.1 will surface the UI prompt; v1 default-denies without a confirm callback).
- Toolsmith routes gaps to BrowserSource as a fallback when API sources don't match.

**Phase 3.7 — OAuth2 + spec discovery**
- New auth scheme `oauth2_token` ([sources/openapi_source.py](backend/acquisition/sources/openapi_source.py)) — bearer token + refresh token + token URL + client creds, all stored in the vault.
- **Auto-refresh on 401** in the cuga adapter — when a tool call returns 401, the adapter posts to the OAuth2 `token_url`, swaps in the new access token, retries once, and persists the refreshed token back to the vault.
- **Bring-your-own-token UX** — user pastes access + refresh tokens (typically obtained via the Google OAuth playground or equivalent). No redirect flow yet; that's deferred. Existing `CredentialPrompt` already handles multi-field input.
- Gmail Send + Google Calendar list-events seeded in [spec_index.yaml](backend/acquisition/sources/spec_index.yaml) as reference implementations.
- **`search_apis_guru_directory`** internal tool ([toolsmith/tools/build.py](toolsmith/tools/build.py)) — Toolsmith's ReAct loop can now hit the public APIs.guru index (~2,500 OpenAPI specs) when the curated index misses.

**Phase 3.8 — code-revise loop**
- New `probe_executed_code` ([backend/acquisition/probe.py](backend/acquisition/probe.py)) — exec()s the Coder's output, calls the entry point with sample input + secrets, validates the response. The structural probe still runs *first* against the upstream URL (cheap); this exec-probe runs *after* code generation.
- **Failed exec-probe → `Coder.revise_tool(prior, feedback)`** with the failure reason, status code, and response excerpt. Up to 3 revisions before giving up. Revision history is persisted in artifact provenance for diagnostics.

**Phase 3.6 — real code exec + auth UX + vault**
- **Adapter exec()s artifact code** with an import allowlist (httpx, json, re, datetime, urllib, asyncio, math, base64, hashlib, hmac, uuid, time, plus pydantic/typing). Disallowed imports register as error stubs that raise on call instead of crashing the adapter. ([adapters/cuga/server.py](adapters/cuga/server.py))
- **Auth-aware Coder** — the LLM/Claude Coder prompt knows the auth scheme and emits the secret as the last kwarg of the function signature, hidden from cuga's args_schema.
- **Auth-aware spec index** — `github_search` (bearer token) and `openweather` (api_key_query) added to [spec_index.yaml](backend/acquisition/sources/spec_index.yaml).
- **Vault** with optional OS keyring backend ([backend/acquisition/vault.py](backend/acquisition/vault.py)). Falls back to SQLite + base64-XOR when keyring isn't available. Toggle with `VAULT_BACKEND=keyring`.
- **Credential prompt UX** — when Toolsmith needs auth and the vault doesn't have it, `acquire` returns `needs_secrets` instead of failing silently. The UI renders a credential modal; user enters; backend stores in vault; user re-asks; Toolsmith retries.
- **Secrets injected at call time** — backend pulls per-tool secrets from Toolsmith's vault via `/effective_state`, hands them to the cuga adapter on `/agent/reload`. Adapter resolves them when the tool is invoked. Never logged.

**Phase 3.5 — Toolsmith service + Coder abstraction + persistent ToolArtifacts**
- **[Toolsmith service](toolsmith/)** — own FastAPI app on port 8001, LangGraph ReAct agent with its own tool belt. The cuga adapter is the swappable planner; Toolsmith is the durable, swap-resistant brain.
- **Internal tool belt** — search_catalog, search_openapi_index, generate_tool_code, probe_generated_tool, register_tool_artifact, etc. NOT MCP tools — agent tools the Toolsmith calls. ([toolsmith/tools/build.py](toolsmith/tools/build.py))
- **Coder abstraction** — pluggable code-generation specialist. `TOOLSMITH_CODER=gpt_oss` (RITS gpt-oss-120b) or `TOOLSMITH_CODER=claude` (Sonnet 4.6 via Anthropic SDK). One-line A/B switch.
- **ToolArtifact** — canonical disk-persisted tool format at `data/tools/<id>/{manifest.yaml, tool.py, probe.json}`. Multiple bindings (LangChain, MCP, OpenAPI doc) computed from one source of truth.
- **Reusability** — tools survive restarts; backend startup pulls Toolsmith's `/effective_state` and reloads cuga with the union.
- **Dumb UI** — chat surface plus tools panel. No consent modal. Toolsmith decides; UI shows what happened.

Not yet (phases 4+): web search for arbitrary specs, browser source for no-API sites, health checks + auto-quarantine, cross-domain mining.

## Run with Docker

The cleanest way to take a look. **Five** containers come up now (browser-runner joined in phase 4):

| Container | Port | What it does |
|---|---|---|
| `cuga-apps-cos-adapter` | 8000 | Wraps cuga.sdk — the swappable planner |
| `cuga-apps-cos-toolsmith` | 8001 | LangGraph ReAct acquisition agent — the durable brain |
| `cuga-apps-cos-browser` | 8002 | Playwright runner for browser-driven tools (phase 4) |
| `cuga-apps-cos-backend` | 8765 | Thin orchestrator + SQLite registry |
| `cuga-apps-cos-frontend` | 5174 | Dumb React UI |

### Prereqs

1. **The parent cuga-apps stack must be running** so the MCP servers are
   reachable on the `cuga-apps_default` network:

   ```bash
   cd cuga-apps
   docker compose up -d            # brings up mcp-web, mcp-knowledge, …
   ```

2. **An LLM API key** in `cuga-apps/apps/.env` (the same file the rest of
   cuga-apps reads). Without one, the adapter still loads tools — but
   `/chat` will return errors when it tries to plan. You can verify the
   shell + tool discovery without one; you need a key to see real planning.

### Up

```bash
cd cuga-apps/chief_of_staff
docker compose up --build
```

First build of the adapter image takes 5–10 minutes (cuga + LangChain).
Backend and frontend builds are seconds. Subsequent rebuilds are fast.

### Down

```bash
docker compose down
```

This only tears down chief_of_staff containers — the parent cuga-apps
stack is untouched.

## What to look at / test

The phase-2 demo flow: start with a small toolbox, ask something it can't
answer, watch it offer to install the missing tool, approve, and ask again.

### Setup

```bash
# Pull the latest changes, then force-rebuild (the adapter and frontend both
# changed; the backend changed too).
cd cuga-apps/chief_of_staff
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps   # all 3 should be Up
```

Open **http://localhost:5174**.

### ✅ Initial state — small toolbox by design

1. **Header** reads `backend: backend-up · agent: reachable · tools: 10–15`.
   That's intentionally a subset — the adapter's `MCP_SERVERS` defaults to
   `web,local,code` so phase 2 has real gaps to fill.
2. **Tools panel** shows entries from those three servers only. No `geo`,
   `knowledge`, `finance`, etc. yet.

### ✅ The acquisition flow

3. **Type:** *"What's the weather in Tokyo right now?"*
   - The agent should reply that it can't help with weather, and the
     orchestrator should attach **proposal cards** under the agent's reply.
   - Top proposal should be **"Geo MCP"** with a high match score.
4. **Click "Install"** on the Geo MCP card.
   - The button shows `...` for ~30 s while the adapter rebuilds with
     `web,local,code,geo`.
   - When done, the proposal disappears and the right-hand Tools panel
     refreshes — you should now see a `geo` group with `get_weather`,
     `geocode`, etc.
5. **Re-type:** *"What's the weather in Tokyo right now?"*
   - This time the agent should call `get_weather` and return a real answer.

### ✅ More variations to try

| Ask | Expected proposal | Expected tools after install |
|---|---|---|
| *"Look up the Eiffel Tower on Wikipedia"* | Knowledge MCP | `get_wikipedia_article`, `search_wikipedia` |
| *"What's NVIDIA's stock price?"* | Finance MCP | `get_quote`, market data tools |
| *"Extract the text from this PDF"* | Text MCP | document parsing tools |

### ✅ Decline path

6. Trigger another gap (e.g. *"find me a hike near Boulder"*) → click
   **"Skip"** on the Geo proposal (if you had reverted) → the proposal
   disappears, the agent stays as-is, and the activation is recorded as
   denied (won't be auto-mounted on next restart).

### ✅ API-level checks (skip if UI works)

```bash
# Catalog with current activation state
curl -s http://localhost:8765/catalog | jq

# What the agent currently has
curl -s http://localhost:8000/tools | jq 'length'   # tool count
curl -s http://localhost:8765/tools | jq 'length'   # registry count — should match

# Approve programmatically
curl -s -X POST http://localhost:8765/tools/approve \
  -H 'Content-Type: application/json' \
  -d '{"catalog_id":"geo"}'

# Check the agent now has more tools
curl -s http://localhost:8000/health | jq '.tool_count'
```

### What "passing" means at this stage

Phase 2's bar is: **the agent visibly grows its toolbox in response to
your questions, with explicit consent, no container restarts.**

Phase 3 adds the OpenAPI-generated source and the probe loop — the
catalog and OpenAPI sources both surface in the same proposal cards now
(look for the purple "Generated from OpenAPI" tag).

## Phase 3 test plan

### Setup (one-time per build)

```bash
cd cuga-apps/chief_of_staff

# Optional: configure Toolsmith's LLM. If unset, ranking falls back to
# pure score order — the loop still works, just less smart about ties.
export TOOLSMITH_LLM_PROVIDER=rits          # default
export TOOLSMITH_LLM_MODEL=gpt-oss-120b     # default
export RITS_API_KEY=...                     # required for the LLM path

docker compose down
docker compose build --no-cache
docker compose up -d
sleep 30
docker compose ps                           # all 3 Up
curl -s http://localhost:8765/health | jq   # toolsmith_llm should be true
```

### Demo 1 — catalog still works (regression)

Same as phase-2 demo: ask *"What's the weather in Tokyo?"* → install the
**Geo MCP** card → ask again → real answer. Phase 3 must not break this.

### Demo 2 — OpenAPI source (the headline)

Ask: *"Give me information about France: capital, population, currency."*

✅ **Pass:**
1. Agent emits a gap (no countries tool in default load).
2. Proposal cards appear. **Country Info API** has a purple `Generated
   from OpenAPI` tag and shows a preview endpoint (`get_country_by_name`)
   plus the base URL `https://restcountries.com/v3.1`.
3. Click **Generate + probe**. Button shows `...`.
4. Behind the scenes:
   - Toolsmith calls `OpenAPISource.realize()` → emits a `RealizedTool`
     with `invoke_url=https://restcountries.com/v3.1/name/{name}` and
     `sample_input={"name": "France"}`
   - Probe harness substitutes the path param, calls `GET .../name/France`,
     verifies 200 + JSON + non-empty payload (and, if RITS is configured,
     LLM-judges that the response looks like real country data)
   - On pass, the tool spec is sent to the adapter via `/agent/reload`
     under `extra_tools`; cuga rebuilds with `get_country_by_name` mounted
5. Tools panel shows `get_country_by_name` (kind: `generated`).
6. Re-ask the same question → cuga calls `get_country_by_name(name="France")`
   → real answer (capital: Paris, population: ~67M, currency: EUR).

### Demo 3 — Probe rejects a broken tool (autoresearch in action)

You can force this by editing [spec_index.yaml](backend/acquisition/sources/spec_index.yaml)
to point one entry at a URL that 404s, then triggering its acquisition.
The proposal card will display `error: probe failed: http 404` and the
tool will **not** be registered. That's the keep/discard gate doing its
job — phase 3 ships *no* unverified tools.

### Demo 4 — Toolsmith ranking

When both catalog and OpenAPI propose for the same gap, the Toolsmith
LLM (if configured) re-ranks them. Check the order of cards — the more
fitting source should be first. With `TOOLSMITH_LLM_PROVIDER` unset the
ordering falls back to pure score (catalog usually wins for narrow
gaps; OpenAPI for niche/long-tail).

### API-level checks

```bash
# Both sources are loaded by the Toolsmith
curl -s http://localhost:8765/health | jq '.toolsmith_llm'

# Adapter exposes generated-tool count separately
curl -s http://localhost:8000/health | jq '{tool_count, extra_tool_count}'

# Approve programmatically (skip the UI)
curl -s -X POST http://localhost:8765/tools/approve \
  -H 'Content-Type: application/json' \
  -d '{"proposal":{"id":"openapi:countries","name":"Country Info","description":"x","capabilities":[],"source":"openapi","score":0.5,"auth":[],"spec":{"spec_id":"countries","base_url":"https://restcountries.com/v3.1"}}}' \
  | jq '{success, reason, "probe_ok": .probe.ok}'
```

### Troubleshooting (phase 3)

| Symptom | Likely cause |
|---|---|
| No proposal card for OpenAPI gaps | Cuga isn't emitting `[[TOOL_GAP]]`. |
| `toolsmith_llm: false` after rebuild | RITS keys not propagated. `docker exec cuga-apps-cos-backend env \| grep RITS` |
| OpenAPI install fails with `probe failed: network error` | Public API down or container has no internet. |
| OpenAPI install fails with `judge: ...` | LLM judge thought the response looked fake. Disable judge by unsetting `TOOLSMITH_LLM_PROVIDER`. |

## Phase 3.5 test plan — the new architecture

### What changed since phase 3

- **The consent modal is gone.** The dumb UI doesn't gate Toolsmith — Toolsmith decides what to build and just builds it. The chat shows a green "Toolsmith built X" notice underneath the planner's reply.
- **Toolsmith runs as its own service** (`cuga-apps-cos-toolsmith` on port 8001). The backend talks to it via HTTP, mirroring the cuga adapter pattern.
- **Tool artifacts are persistent.** Every tool Toolsmith builds gets written to `data/tools/<id>/`. Backend restart re-mounts everything.
- **Coder is swappable.** `TOOLSMITH_CODER=gpt_oss` (default, free if you have RITS) or `TOOLSMITH_CODER=claude` (better code, costs Anthropic credits).

### Setup

```bash
cd cuga-apps/chief_of_staff

# Toolsmith orchestration LLM (drives the ReAct loop)
export TOOLSMITH_LLM_PROVIDER=rits
export TOOLSMITH_LLM_MODEL=gpt-oss-120b

# Coder selection — the A/B switch
export TOOLSMITH_CODER=gpt_oss        # or "claude" — both work, Claude is better at code

# Required keys (whichever provider you use)
# RITS_API_KEY, ANTHROPIC_API_KEY in apps/.env

docker compose down
docker compose build --no-cache       # mandatory — toolsmith image is new
docker compose up -d
sleep 30
docker compose ps                     # all 4 Up

# Toolsmith service health
curl -s http://localhost:8001/health | jq
# {"status":"ok","coder":"gpt_oss","orchestration_llm":true,"artifact_count":0}

# Backend should see toolsmith reachable
curl -s http://localhost:8765/health | jq
```

### Test 1 — Autonomous acquisition (the headline)

Open http://localhost:5174 in incognito.

**Type:** *"Tell me a random joke."*

✅ Pass criteria:
- Backend posts the gap to `http://chief-of-staff-toolsmith:8001/acquire`.
- Toolsmith ReAct loop runs: searches catalog (no match) → searches OpenAPI index (matches Joke API) → generates code via Coder → probes the URL → registers as a `data/tools/openapi__get_random_joke/` artifact.
- Chat shows a **green "Toolsmith built a tool" notice** with the artifact id.
- Tools panel shows `get_random_joke` (kind: `generated`).
- **Re-ask** the question → real joke.

### Test 2 — Coder A/B comparison

```bash
# Try gpt-oss
docker compose exec chief-of-staff-toolsmith env | grep TOOLSMITH_CODER
# → gpt_oss

# Switch to Claude (re-up only the toolsmith)
TOOLSMITH_CODER=claude docker compose up -d chief-of-staff-toolsmith
docker compose exec chief-of-staff-toolsmith env | grep TOOLSMITH_CODER
# → claude

# Trigger the same gap again ("Country information for Japan").
# Inspect both artifacts' tool.py — Claude's typically uses cleaner
# error handling and pagination logic. Both should pass the probe.
ls cuga-apps/chief_of_staff/data/tools/
cat cuga-apps/chief_of_staff/data/tools/openapi__get_country_by_name/tool.py
```

### Test 3 — Persistence (reusability)

Build a tool, then restart the backend:

```bash
docker compose restart chief-of-staff-backend
sleep 15
curl -s http://localhost:8000/health | jq '.tool_count, .extra_tool_count'
# extra_tool_count > 0 — the tool survived the restart and was re-mounted.
```

### Test 4 — Removing tools

```bash
# List artifacts
curl -s http://localhost:8765/toolsmith/artifacts | jq '.[].id'

# Remove one
curl -s -X DELETE http://localhost:8765/toolsmith/artifacts/openapi__get_random_joke

# Verify it's gone from the agent
curl -s http://localhost:8000/health | jq '.extra_tool_count'
```

### Test 5 — Probe still gates registration

Edit `chief_of_staff/toolsmith/Dockerfile` to bake in a `spec_index.yaml`
override that points at a 404 URL (or just trigger a gap with no OpenAPI
match), and confirm Toolsmith returns `success: false` with a clear
reason. The autoresearch keep/discard gate doesn't change.

### What "phase 3.5 passing" means

You've proven:
1. The brain (Toolsmith) is process-isolated from the planner (cuga adapter).
2. Tools persist as named artifacts and survive restarts.
3. The Coder is swappable mid-run via env var.
4. The probe still rejects unverified tools.
5. The UI is dumb — it shows what Toolsmith did, doesn't drive the decision.

## Phase 3.6 test plan — auth + real code execution

Same four containers, no compose changes. Force-rebuild because the adapter
and toolsmith images both changed.

```bash
cd cuga-apps/chief_of_staff
docker compose down
docker compose build --no-cache
docker compose up -d
sleep 30
curl -s http://localhost:8001/health | jq                  # toolsmith ok
```

### Test 1 — A no-auth API still works (regression)

UI: *"Tell me a random joke."*
Same flow as 3.5. Confirms the new exec path didn't break the simple case.

```bash
# Inspect the generated tool — under 3.6 the adapter actually exec()s it,
# rather than wrapping its URL with parameter substitution.
docker exec cuga-apps-cos-toolsmith \
  cat /app/chief_of_staff/data/tools/openapi__get_random_joke/tool.py
```

### Test 2 — The headline: an auth-required tool surfaces a credential prompt

UI: *"Search GitHub for popular Python repositories."*

✅ Pass criteria:
- Toolsmith matches the gap to `openapi:github_search`.
- Vault has no `github_token` for it.
- Toolsmith returns `success: false` with `needs_secrets`.
- Chat shows a **blue credential prompt card** below the agent's reply:
  > **GitHub Search API needs credentials**
  > github_token: [paste secret value] [Save]
  > (helpful instructions about generating a personal access token)
- Click into the field, paste a GitHub PAT, click **Save**.
- Card flips to green: *"Secret saved — re-ask your question."*

### Test 3 — Re-ask after providing the credential

UI: *"Search GitHub for popular Python repositories."* (again, same chat).

✅ Pass criteria:
- This time Toolsmith finds the secret, runs the probe (real GitHub API call),
  generates the tool via the Coder, registers it.
- Chat shows the green "Toolsmith built a tool" notice.
- Right-hand panel grows with `github_search_repos` (kind: generated).
- Re-asking gives a real list of repos.

### Test 4 — Direct vault interaction

```bash
# What's stored for a tool? (keys only, values never returned)
curl -s http://localhost:8765/vault/keys/openapi__github_search_repos | jq

# Set a secret directly
curl -s -X POST http://localhost:8765/vault/secret \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"openapi__openweather_current","secret_key":"openweather_api_key","value":"YOUR_KEY"}'

# Now ask "What's the current weather in Tokyo via OpenWeather?"
# Toolsmith should pick openweather (it's in the spec index now), find the
# key, build + probe + register the tool.
```

### Test 5 — Code execution sandbox

```bash
# Try to manually inject a hostile artifact and confirm the import allowlist blocks it.
docker exec cuga-apps-cos-toolsmith mkdir -p /app/chief_of_staff/data/tools/manual__danger
docker exec cuga-apps-cos-toolsmith bash -c 'cat > /app/chief_of_staff/data/tools/manual__danger/manifest.yaml << EOF
id: manual__danger
name: danger
description: hostile import
parameters_schema: {}
entry_point: tool.py
requires_secrets: []
provenance: {source: openapi}
version: 1
EOF'
docker exec cuga-apps-cos-toolsmith bash -c 'cat > /app/chief_of_staff/data/tools/manual__danger/tool.py << EOF
import subprocess
async def danger():
    return subprocess.check_output(["id"]).decode()
EOF'
# Force a backend resync. Adapter reload should NOT crash; instead the
# tool should be registered as an error stub that raises on call.
curl -s -X POST http://localhost:8765/internal/artifacts_changed | jq
docker logs cuga-apps-cos-adapter --tail 20 | grep "rejected"
# → "Artifact 'manual__danger' rejected: disallowed import: 'subprocess'"

# Confirm the tool exists in the agent but errors when invoked.
# Asking the chat to use 'danger' will surface the "disabled" error.
```

### Test 6 — Vault keyring backend (optional)

By default the vault uses SQLite + base64-XOR (clearly documented as
not-real-encryption). To switch to OS keyring:

```bash
# Linux containers usually don't have a working keyring backend; this is
# more meaningful when running the toolsmith service outside Docker.
TOOLSMITH_CMD="VAULT_BACKEND=keyring uvicorn chief_of_staff.toolsmith.server:app --port 8001"
# Then: curl -s http://localhost:8001/health | jq '.coder, .artifact_count'
# Backend reports the active backend in /vault/keys/<id> response.
```

### What "phase 3.6 passing" means

You've proven:
1. **Real code exec.** Coder-generated Python actually runs in the adapter.
2. **Auth UX.** Tools that need credentials surface a prompt; user provides; tool gets built.
3. **Sandboxing.** Hostile imports are caught before they execute.
4. **Vault separation.** Secrets travel from vault → adapter → tool, never to the UI or logs.
5. **Persistence still works.** Auth-aware artifacts survive restart; their secrets stay in the vault.

## Phase 3.7 / 3.8 test plan — OAuth2 + revise loop + spec search

```bash
cd cuga-apps/chief_of_staff
docker compose down
docker compose build --no-cache
docker compose up -d
sleep 30
```

### Test 1 — Gmail (OAuth2 reach)

UI: *"Send an email through Gmail."*

✅ Pass criteria:
- Toolsmith matches `openapi:gmail_send`. The auth scheme is `oauth2_token`,
  so the credential prompt asks for **four fields**: `gmail_access_token`,
  `gmail_refresh_token`, `google_oauth_client_id`, `google_oauth_client_secret`.
- Help text walks you through obtaining them via Google OAuth playground.
- After you paste all four, re-asking the question runs the build:
  - Toolsmith probes the URL (auth-aware probe injects access token).
  - Coder generates code that takes all four secrets as kwargs and uses
    them in the `Authorization` header.
  - Tool registers as `openapi__gmail_send_message`.
- Asking the agent to send a real test email actually sends one.

### Test 2 — OAuth2 token refresh on 401

```bash
# Expire the access token by replacing it with a known-bad value.
curl -s -X POST http://localhost:8765/vault/secret \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"openapi__gmail_send_message","secret_key":"gmail_access_token","value":"obviously_expired"}'

# Trigger a tool call. The first call to Gmail returns 401. The adapter
# should auto-refresh using the refresh_token + client creds, retry, succeed.
docker logs cuga-apps-cos-adapter -f | grep -i "OAuth2"
# → "OAuth2 refresh succeeded for 'openapi__gmail_send_message'"
```

### Test 3 — Code-revise loop (3.8)

You can force this by editing the spec_index entry for an existing API to
point at a *slightly wrong* path (e.g. `/random_jokes` instead of
`/random_joke`). The structural URL probe will still pass because the
domain is reachable, but the exec-probe will fail (404 from the actual
function). Toolsmith asks the Coder to revise based on the failure.

Look for these in the adapter logs / artifact provenance:
```bash
docker exec cuga-apps-cos-toolsmith \
  cat /app/chief_of_staff/data/tools/<artifact>/manifest.yaml | grep revisions
# revisions:
#   - {attempt: 0, ok: false, reason: 'upstream http 404'}
#   - {attempt: 1, ok: true, reason: 'executed code passed'}
```

### Test 4 — APIs.guru spec discovery (3.7e)

UI: *"Convert 100 USD to JPY."* (no currency conversion in our curated index)

With Toolsmith's orchestration LLM enabled, the ReAct loop:
1. Calls `search_catalog` → no match.
2. Calls `search_openapi_index` → no match.
3. **Calls `search_apis_guru_directory`** → finds e.g. `frankfurter.app` or
   `exchangerate.host`.
4. Manually fetches the spec, picks an endpoint, generates code, probes,
   registers.

```bash
docker logs cuga-apps-cos-toolsmith -f | grep -i "apis_guru"
```

Note: this only fires on the LLM path. Without `TOOLSMITH_LLM_PROVIDER`
configured, deterministic mode falls back to "no match" (same as 3.6).

### Test 5 — Sandbox + persistence still hold

All phase 3.6 tests still pass (regression). Sandbox catches hostile imports;
artifacts survive restart; vault-backed secrets are preserved.

### What "phase 3.7 + 3.8 passing" means

You've proven:
1. **OAuth2 reach.** Gmail/GCal-class APIs work end-to-end with token refresh.
2. **Spec discovery.** Toolsmith can find APIs not in the curated index.
3. **Self-correcting codegen.** Bad code gets rewritten with feedback; only working tools register.

## Phase 4 test plan — browser-driven tools

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
sleep 60                                  # browser-runner pulls Playwright base image (~500MB first time)
curl -s http://localhost:8002/health | jq
# {"status":"ok","executor":"playwright","profiles_dir":"/data/profiles"}
```

### The headline demo

UI: *"What are the top 5 stories on Hacker News right now?"*

✅ Pass:
- Catalog miss; OpenAPI miss; **BrowserSource matches `hn_top_stories`**
- Toolsmith probes the runner; runner opens news.ycombinator.com; extracts titles; passes
- Artifact persisted at `data/tools/browser__hn_top_stories/` with `kind: browser_task` and `steps.yaml`
- Tools panel shows `hn_top_stories` (kind: browser)
- Re-ask returns the actual top stories

### Auth-required browser flow

UI: *"Check my kid's grades on the school portal."*

✅ Pass:
- Credential prompt asks for `school_portal_username` + `school_portal_password`
- Note: the bundled template uses fictional URLs — adapt for your real portal by editing the YAML before the demo. Auth + dispatch flow works regardless.

### Extensive coverage

The full **70-test benchmark suite** is at [benchmark.md](benchmark.md). It covers all phases (skeleton → browser) with concrete prompts, expected outcomes, and what each test proves architecturally.

## What's still NOT done — the honest "are we done?" answer

Even with 3.7 + 3.8, these are real, useful features that don't exist yet:

| What | Phase | Why it matters |
|---|---|---|
| **OAuth2 redirect flow** (no token-pasting) | 3.7+ stretch | The bring-your-own-token UX works but is fiddly. Real consumer apps need a one-click OAuth flow. |
| **Browser-driven tools** | **4** | DoorDash, most consumer apps. Anything without a documented API. This is a huge slice of the real world. |
| **Tool composition** (Toolsmith builds a single tool that internally calls multiple atomic tools) | 4.5 | Today cuga composes at runtime. For reusable workflows ("daily Stripe digest"), composing once is much cheaper. |
| **Health checks & decay** | 5 | APIs change. Toolsmith generates against today's API; 6 months later, half your tools silently break. |
| **Multi-user / per-user state** | infra | Currently single-user. Vault, registry, artifacts are global. |
| **Cost meters / budget caps** | infra | An off-by-one in the revise loop could cost real money. There's no enforcement. |
| **Subprocess sandboxing** | 4 | Import allowlist is a tripwire, not a sandbox. Trustworthy generated code is one thing; arbitrary code from a hostile spec_index entry is another. |
| **Cross-domain insights over the user's data** | 6 | The genuinely novel demo. Nothing siloed-app can ship. |

So no, **we're not "truly done."** What we are after 3.8 is **architecturally complete for documented APIs.** Every phase from 4 onward is about *which kinds of capabilities* the system reaches, or about making it production-grade. The bones are right.

## Roadmap (phases 4.1+)

Phase 4 is shipped. What's left to round out the system:

| Phase | Adds | Why |
|---|---|---|
| **4.1** | BrowserScriptCoder — LLM generates browser DSL scripts on the fly (vs. curated templates only) | Removes the manual template ceiling for browser tools |
| **4.2** | UI surface for `user_confirm` browser steps — when the runner pauses, the chat shows an "Approve / Deny" prompt | Closes the human-in-the-loop UX gap |
| **4.5** | Tool composition — single tool internally chains atomic tools (e.g. `weekly_finance_digest` = stripe + plaid + email) | Power-user workflows |
| **5** | Health checks + auto-quarantine + auto-regenerate from provenance | Self-maintaining toolbox at month 3+ |
| **6** | Cross-domain mining over the unified data layer | Genuinely novel demos siloed apps can't ship |

See [benchmark.md](benchmark.md) for the comprehensive 70-test suite.

## Run without Docker

If you'd rather hack on it locally:

```bash
cd cuga-apps/chief_of_staff
./start.sh
```

Assumes Python deps for the adapter (cuga, langchain, …) are already in
your active env, and that the MCP servers are running (`python apps/launch.py`).

## Layout

```
backend/
  main.py                 FastAPI shell
  orchestrator.py         coordinates planner + (future) acquisition
  agents/
    base.py               AgentClient Protocol (the swap point)
    cuga_client.py        out-of-process HTTP client to the adapter
  registry/
    store.py              SQLite tool registry
    discovery.py          adapter→registry sync
adapters/
  cuga/
    server.py             FastAPI wrapper around CugaAgent
    requirements.txt      adapter-only deps (assumes cuga env present)
frontend/                 React + Vite + Tailwind UI
  src/components/Chat.tsx
  src/components/ToolsPanel.tsx
  nginx.conf              reverse proxy /api → backend container
Dockerfile.adapter        cuga-deps image
Dockerfile.backend        lightweight FastAPI image
Dockerfile.frontend       multi-stage Vite build + nginx
docker-compose.yml        wires the three services + external cuga network
data/                     SQLite registry + logs (gitignored)
tests/                    isolated test dir (pytest)
```

## Swapping the agent backend

The orchestrator only knows the `AgentClient` Protocol in
[backend/agents/base.py](backend/agents/base.py). To replace cuga, drop a
sibling under `adapters/` (e.g. `adapters/gpt_oss/server.py`) that exposes
the same three endpoints — `/health`, `/tools`, `/chat` — and point
`CUGA_URL` at it. No changes anywhere else in the codebase.
