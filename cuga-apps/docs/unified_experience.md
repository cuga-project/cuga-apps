# Toolsmith — architecture, workflow, and how to test

> **Updated through phase 4.** Five services now (browser-runner joined). For the full 70-test benchmark, see [chief_of_staff/benchmark.md](chief_of_staff/benchmark.md).

## The big picture

Five services. Each owns one concern. They talk over HTTP, never via direct imports.

```
                            ┌──────────────────────┐
                            │ Frontend (port 5174) │   dumb React UI
                            │ React + nginx        │   shows what happened
                            └──────────┬───────────┘
                                       │ /api/*
                                       ▼
                            ┌──────────────────────┐
                            │ Backend (port 8765)  │   thin orchestrator
                            │ FastAPI              │   no business logic
                            └────┬───────────────┬─┘
                       /chat,    │               │   /acquire,
                       /reload   │               │   /effective_state,
                                 ▼               ▼   /tools (CRUD)
                        ┌────────────────┐ ┌──────────────────────┐
                        │ Cuga adapter   │ │ Toolsmith service     │
                        │ port 8000      │ │ port 8001             │
                        │                │ │                       │
                        │ SWAPPABLE      │ │ DURABLE                │
                        │ wraps cuga.sdk │ │ LangGraph ReAct agent │
                        └────────────────┘ └──────────┬────────────┘
                                                      │
                                                ┌─────┴─────┐
                                                ▼           ▼
                                        ┌────────────┐ ┌──────────┐
                                        │ Coder      │ │ disk     │
                                        │ swappable  │ │ data/    │
                                        │ gpt-oss /  │ │  tools/  │
                                        │ Claude     │ │ <id>/    │
                                        └────────────┘ └──────────┘
```

| Service | Port | Role | Code |
|---|---|---|---|
| **Frontend** | 5174 | Show chat + tools panel + acquisition notices. **Zero logic.** | `chief_of_staff/frontend/` |
| **Backend** | 8765 | Coordinator: forwards chat to cuga, forwards gaps to Toolsmith, syncs cuga with effective state, proxies vault calls. | `chief_of_staff/backend/orchestrator.py` |
| **Cuga adapter** | 8000 | Wraps `cuga.sdk.CugaAgent` over HTTP. Loads MCP servers + execs generated Python tools + dispatches browser-task tools. | `chief_of_staff/adapters/cuga/server.py` |
| **Toolsmith** | 8001 | LangGraph ReAct agent. Owns the "build a tool" loop. | `chief_of_staff/toolsmith/` |
| **Browser runner** *(phase 4)* | 8002 | Playwright + Chromium driver. Executes browser_task DSL steps. Persistent profiles per provider. | `chief_of_staff/browser_runner/` |

## Inside Toolsmith

Toolsmith itself is a small ecosystem:

```
                    ┌─────────────────────────────────────┐
                    │    Toolsmith FastAPI (server.py)    │
                    │                                     │
                    │   /acquire {gap}                    │
                    │   /tools, /tools/{id}, /effective_state │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                ┌─────────────────────────────────────┐
                │ Toolsmith agent (agent.py)          │
                │ ┌─────────────────────────────────┐ │
                │ │ LangGraph ReAct loop            │ │
                │ │ orchestration LLM = gpt-oss-120b│ │
                │ │                                 │ │
                │ │ "Got gap → reason about it →    │ │
                │ │  call a tool → see result →     │ │
                │ │  call another → done"           │ │
                │ └──────────────┬──────────────────┘ │
                └────────────────┼────────────────────┘
                                 │ ReAct picks one of:
       ┌──────────────────┬──────┴─────────┬──────────────────┬──────────────┐
       ▼                  ▼                ▼                  ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│search_       │  │search_openapi│  │generate_     │  │probe_        │  │register_     │
│catalog       │  │_index        │  │tool_code     │  │generated_    │  │tool_artifact │
│              │  │              │  │              │  │tool          │  │              │
│reads         │  │reads         │  │calls Coder   │  │httpx +       │  │writes to     │
│catalog.yaml  │  │spec_index.   │  │(swappable)   │  │structural+   │  │data/tools/   │
│              │  │yaml          │  │              │  │LLM judge     │  │              │
└──────────────┘  └──────────────┘  └──────┬───────┘  └──────────────┘  └──────────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │  Coder          │
                                  │  ┌──────────┐   │
                                  │  │ LLMCoder │   │  TOOLSMITH_CODER=gpt_oss
                                  │  └──────────┘   │
                                  │  ┌──────────┐   │
                                  │  │ ClaudeCoder │  TOOLSMITH_CODER=claude
                                  │  └──────────┘   │
                                  └─────────────────┘
```

### What lives in each file

| File | Role |
|---|---|
| `toolsmith/server.py` | FastAPI entry: `/acquire`, `/tools`, `/effective_state`, `/health` |
| `toolsmith/agent.py` | ReAct loop + deterministic fallback when no LLM is configured |
| `toolsmith/tools/build.py` | The 9 internal tools — what the ReAct agent calls |
| `toolsmith/coders/base.py` | `CoderClient` Protocol — the swap point |
| `toolsmith/coders/llm_coder.py` | LangChain-based Coder; gpt-oss-120b default |
| `toolsmith/coders/claude_coder.py` | Anthropic SDK Coder; Sonnet 4.6 |
| `toolsmith/artifact.py` | `ToolArtifact` + `ArtifactStore` — persistence layer |

### The two paths inside `Toolsmith.acquire(gap)`

There's an LLM-driven path and a deterministic fallback. The fallback is what ships when you don't have RITS keys — useful for tests and demos.

**LLM path (ReAct loop):**

```
1. agent.ainvoke({messages: [{user: "build a tool for gap X"}]})
2. Loop:
   a. LLM emits: "tool_call(search_catalog, capability='X')"
   b. Tool runs, returns JSON list of catalog matches
   c. LLM emits: "tool_call(search_openapi_index, capability='X')"
   d. Tool returns OpenAPI candidates
   e. LLM emits: "tool_call(describe_openapi_endpoint, spec_id='countries')"
   f. Tool returns endpoint detail
   g. LLM emits: "tool_call(generate_tool_code, name='get_country_by_name', ...)"
   h. Coder runs, returns Python source
   i. LLM emits: "tool_call(probe_generated_tool, ...)"
   j. Probe runs, returns ok/fail
   k. If ok: "tool_call(register_tool_artifact, ...)"
   l. Tool persists to disk, calls /internal/artifacts_changed on backend
3. Final message: "Built get_country_by_name. Probe passed."
```

**Deterministic path (no LLM):**

```
1. Score gap against catalog matcher
2. Score gap against OpenAPI matcher
3. Pick the higher-scoring source
4. If catalog: write a catalog-mount artifact (no probe — local MCP servers are trusted)
5. If OpenAPI: realize → probe → if pass: codegen via Coder → register
6. Failed probe → return success=false
```

The deterministic path is also what proves the architecture in tests — 86 tests pass without any LLM running.

## End-to-end workflow trace

You ask: *"Tell me a random joke."*

```
t=0.0s  Frontend sends POST /api/chat with {message}.

t=0.1s  Backend orchestrator forwards to cuga adapter:
        POST http://chief-of-staff-adapter:8000/chat

t=0.5s  Cuga has [web,local,code] tools loaded. None do jokes.
        Cuga emits: "I don't have a joke tool. [[TOOL_GAP]] {capability:"random joke"}"

t=0.6s  Cuga adapter regex-extracts the [[TOOL_GAP]] marker, sends back:
        {response: "...", gap: {capability:"random joke"}, error: null}

t=0.7s  Backend orchestrator sees gap. Posts to Toolsmith:
        POST http://chief-of-staff-toolsmith:8001/acquire
        {gap: {capability:"random joke"}}

t=0.8s  Toolsmith starts the ReAct loop with gpt-oss-120b.

        ReAct step 1:
          tool: search_catalog(capability="random joke")
          obs:  []  (catalog has no joke entry)

        ReAct step 2:
          tool: search_openapi_index(capability="random joke")
          obs:  [{id: "openapi:jokes", name: "Official Joke API",
                  base_url: "https://official-joke-api.appspot.com",
                  preview_endpoint: "get_random_joke", score: 0.667}]

        ReAct step 3:
          tool: describe_openapi_endpoint(spec_id="jokes")
          obs:  {tool_name: "get_random_joke", method: "GET",
                 path: "/random_joke", params: {}, probe_input: {}}

        ReAct step 4:
          tool: generate_tool_code(name="get_random_joke", ...)
          obs:  Coder (gpt-oss) returns Python source:
                "async def get_random_joke():
                     import httpx
                     async with httpx.AsyncClient() as c:
                         r = await c.get('https://official-joke-api.../random_joke')
                         r.raise_for_status()
                         return r.json()"

        ReAct step 5:
          tool: probe_generated_tool(name="get_random_joke", ...)
          obs:  {ok: true, status_code: 200,
                 response: {type: "general", setup: "Why...", punchline: "..."},
                 reason: "structural ok"}

        ReAct step 6:
          tool: register_tool_artifact(...)
          obs:  {id: "openapi__get_random_joke", mounted: true}

        Final message: "Built get_random_joke. Probe returned a real joke."

t=15s   Toolsmith persists to data/tools/openapi__get_random_joke/{manifest.yaml, tool.py, probe.json}
        Toolsmith calls back to backend: POST /internal/artifacts_changed

t=15.1s Backend receives notification, calls toolsmith /effective_state:
        {mcp_servers: [], extra_tools: [{tool_name:"get_random_joke", ...}]}

t=15.2s Backend calls cuga adapter /agent/reload with extra_tools.

t=45s   Cuga rebuilds (~30s for MCP handshake + new agent init).
        Tools panel in UI grows; header tool count increments.

t=46s   Original POST /api/chat returns:
        {response: "I don't have a joke tool",
         acquisition: {success: true, artifact_id: "openapi__get_random_joke",
                       summary: "Built get_random_joke. Probe returned a real joke.",
                       transcript: [...steps 1-6...]}}

t=46.1s UI shows green "Toolsmith built a tool" notice with the artifact id.

You re-ask "Tell me a random joke."

t=50s   Cuga now has get_random_joke; calls it; returns a real joke.
```

## How to test it

### Setup once

```bash
cd cuga-apps/chief_of_staff

# Configure
export TOOLSMITH_LLM_PROVIDER=rits
export TOOLSMITH_LLM_MODEL=gpt-oss-120b
export TOOLSMITH_CODER=gpt_oss            # the A/B switch — flip to "claude" later

# Bring up all four services
docker compose down
docker compose build --no-cache           # mandatory — toolsmith image is new
docker compose up -d
sleep 30
docker compose ps                         # all 4 Up

# Sanity checks on each service
curl -s http://localhost:8001/health | jq          # toolsmith
curl -s http://localhost:8000/health | jq          # cuga adapter
curl -s http://localhost:8765/health | jq          # backend
```

Expect Toolsmith health like:
```json
{"status":"ok","coder":"gpt_oss","orchestration_llm":true,"artifact_count":0}
```

### Test 1 — The headline: autonomous tool creation

Open http://localhost:5174 in incognito.

| You | Expected | What it proves |
|---|---|---|
| *"Tell me a random joke."* | Green notice "Toolsmith built a tool" with artifact id `openapi__get_random_joke`. Tools panel grows. | The whole loop end-to-end. |
| *"Tell me another joke."* (after the first) | Real joke. **No new acquisition** (the tool already exists). | Toolsmith doesn't rebuild what's already there. |

To watch the ReAct trace live:
```bash
docker logs cuga-apps-cos-toolsmith -f
# Look for:
#   "search_catalog called with..."
#   "search_openapi_index called with..."
#   "Generated tool code via gpt_oss..."
#   "Probe ok"
#   "Registered openapi__get_random_joke"
```

### Test 2 — The other two seeded APIs

| Ask | Expected artifact | API hit |
|---|---|---|
| *"What's the weather at lat 35.67, lon 139.65?"* | `openapi__get_open_meteo_forecast` | open-meteo.com |
| *"Tell me about France: capital, population, currency."* | `openapi__get_country_by_name` | restcountries.com |

### Test 3 — Coder A/B (gpt-oss vs Claude)

```bash
# Note current artifact's source/coder
curl -s http://localhost:8001/tools/openapi__get_random_joke | jq '.provenance'
# {"source":"openapi","spec_id":"jokes","coder":"gpt_oss",...}

# Switch coder
TOOLSMITH_CODER=claude docker compose up -d chief-of-staff-toolsmith
sleep 5
curl -s http://localhost:8001/health | jq '.coder'
# "claude"

# Remove the existing tool so Toolsmith rebuilds it
curl -s -X DELETE http://localhost:8765/toolsmith/artifacts/openapi__get_random_joke

# Trigger again from UI: "Tell me a random joke."
# Now it'll be built by Claude.
curl -s http://localhost:8001/tools/openapi__get_random_joke | jq '.provenance.coder'
# "claude"

# Compare the generated code
docker exec cuga-apps-cos-toolsmith cat /app/chief_of_staff/data/tools/openapi__get_random_joke/tool.py
```

You're looking for: **does Claude's code feel cleaner / better-handled errors / more idiomatic?** It usually does. That's the A/B point — pick the right Coder for the right cost/quality tradeoff.

### Test 4 — Persistence (reusability)

```bash
# Build a tool through the UI.
# Then restart just the backend (NOT toolsmith — toolsmith owns the disk).
docker compose restart chief-of-staff-backend
sleep 20

# The tool should still be in the cuga adapter:
curl -s http://localhost:8000/health | jq '.extra_tool_count'
# > 0
```

This proves: tools are persisted to disk, backend re-reads them on cold start, cuga gets the full set without re-acquiring.

### Test 5 — Direct service interaction (skip the UI)

The Toolsmith service is independently usable. You can drive it directly:

```bash
# Acquire a tool with a synthetic gap
curl -s -X POST http://localhost:8001/acquire \
  -H 'Content-Type: application/json' \
  -d '{"gap":{"capability":"weather forecast"}}' | jq

# List artifacts
curl -s http://localhost:8001/tools | jq

# Get one in detail (manifest + code)
curl -s http://localhost:8001/tools/openapi__get_open_meteo_forecast | jq

# What does the cuga adapter need to mount? (effective state)
curl -s http://localhost:8001/effective_state | jq

# Remove a tool
curl -s -X DELETE http://localhost:8001/tools/openapi__get_random_joke | jq
```

This is the "Toolsmith is a real, independently usable service" check. Other consumers (CLI scripts, other agents) can hit these endpoints without touching cuga or the backend.

### Test 6 — The probe still gates registration

Force a probe failure:

```bash
# Stop network access from the toolsmith container so the probe times out
docker network disconnect cuga-apps_default cuga-apps-cos-toolsmith

# Try to acquire something that needs network
curl -s -X POST http://localhost:8001/acquire \
  -H 'Content-Type: application/json' \
  -d '{"gap":{"capability":"weather forecast"}}' | jq '{success, summary}'
# {"success": false, "summary": "...probe failed: network error..."}

# Confirm nothing was persisted
docker exec cuga-apps-cos-toolsmith ls /app/chief_of_staff/data/tools/

# Reconnect
docker network connect cuga-apps_default cuga-apps-cos-toolsmith
```

This proves: failed probes block registration. Phase 3's autoresearch gate is intact.

### Test 7 — The dumb UI is, in fact, dumb

```bash
# Watch backend logs while you trigger an acquisition
docker logs cuga-apps-cos-backend -f
```

You should see only:
- `POST /chat` from the frontend
- HTTP calls out to cuga adapter `/chat`
- HTTP calls out to toolsmith `/acquire`
- HTTP calls out to cuga adapter `/agent/reload`

No business logic in the backend logs — it's a forwarder. The UI logs are even thinner.

## What to expect

| Behavior | Where to look |
|---|---|
| Acquisitions take ~15–45 seconds (ReAct steps + probe + cuga rebuild) | Chat shows pending dots; tools panel updates when done |
| `acquisition_count` in the toolsmith health grows over time | `curl http://localhost:8001/health` |
| `data/tools/*/manifest.yaml` is human-readable, hand-editable | `cat`, `vim`, etc. |
| Repeating the same question after acquisition gets a real answer | UI |
| Removing a tool unmounts it from cuga within seconds | Tools panel + `curl http://localhost:8000/health` |

## What's still stubbed honestly

| Caveat | What it means |
|---|---|
| **Adapter still uses parameter-substitution wrapping**, not raw `exec()` of artifact code | Coder-generated code gets persisted but the *running* tool in cuga is the simpler param-binding closure. They're equivalent for GET endpoints with simple params; the difference matters once we want multi-step / transformation tools. **3.6 flips on real exec.** |
| **No web spec discovery** — only the 3 entries in spec_index.yaml | Phase 3.7 |
| **No code-revise loop** — failed probe means give up on that path | Phase 3.8 |
| **No auth UX** — vault scaffolded, no credential modal | Phase 3.6 |
| **LangGraph deprecation warning** — `create_react_agent` moved in V1.0 | Cosmetic; flips when we migrate import |

## Quick failure-mode cheat sheet

| Symptom | Likely cause | Fix |
|---|---|---|
| `toolsmith health shows orchestration_llm: false` | RITS key didn't propagate | `docker exec cuga-apps-cos-toolsmith env \| grep RITS` |
| Acquisition succeeds but UI doesn't show new tool | Backend didn't get the `/internal/artifacts_changed` call | `docker logs cuga-apps-cos-toolsmith \| grep notify` |
| Cuga doesn't seem to use the new tool | Adapter rebuild failed | `docker logs cuga-apps-cos-adapter \| tail -30` |
| All acquisitions return success=false even for jokes | Public APIs unreachable from the container | check with `docker exec cuga-apps-cos-toolsmith curl https://official-joke-api.appspot.com/random_joke` |
| Probe judge keeps rejecting things | LLM judge is being overzealous | unset `TOOLSMITH_LLM_PROVIDER` (disables judge); falls back to structural check only |

If you spin it up and something looks wrong, the highest-value diagnostic is:
```bash
docker logs cuga-apps-cos-toolsmith --tail 60
```
That'll show the ReAct trace which reveals exactly where in the loop things went sideways.
