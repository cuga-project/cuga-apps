# How To Build a New CUGA App, Fast

A 10-minute guide for shipping a new agent-powered app inside this repo. It
condenses [`cuga_app_builder_spec.md`](cuga_app_builder_spec.md) and
[`cuga_app_builder_spec_standalone.md`](cuga_app_builder_spec_standalone.md)
into the smallest checklist that will get you running.

If you want every bolt explained — including envelope rules, MCP migration,
and why each line of the template exists — read the full specs after this.

---

## What you're building

A self-contained Python folder under [apps/](apps/) that:

1. Wraps a `CugaAgent` with **your tools + your system prompt**.
2. Serves a **dark-themed two-panel HTML UI** from `/`.
3. Accepts `POST /ask` with `{question, thread_id}` and returns
   `{answer: "..."}`.
4. Uses ports from [apps/_ports.py](apps/_ports.py).

A finished app is **5 files** (most apps need only 4):

```
apps/<your_app>/
├── main.py            FastAPI + CugaAgent + tools (REQUIRED)
├── ui.py              exports _HTML (REQUIRED)
├── README.md          how to run + tools + env vars (REQUIRED)
├── requirements.txt   only what main.py imports (REQUIRED)
└── ...                any per-app helper modules (optional)
```

**Don't** add: `__init__.py`, a Dockerfile, tests, a React build, or a
local copy of `_llm.py` (the repo provides one at [apps/_llm.py](apps/_llm.py)).

---

## The 6-step build

### 1. Pick a name + a port

Snake_case folder name. Add the port to [apps/_ports.py](apps/_ports.py)
under `APP_PORTS`. Existing apps live in `28xxx`; pick the next free number.

### 2. Decide your tools

Two flavors — pick one or both:

- **Inline `@tool` defs** in `main.py` — for app-specific state (sessions,
  in-memory stores) or one-off APIs only this app cares about. Pure
  functions ideally, plus a couple of session mutators if needed. See
  [apps/recipe_composer/main.py](apps/recipe_composer/main.py) for an
  inline-only example.

- **MCP server tools** loaded via [`load_tools(...)`](apps/_mcp_bridge.py)
  — for anything generic (web search, Wikipedia, geocoding, weather,
  prices, code analysis, …). Already-running servers and their tools:

| Server name | Tools (selected) |
|---|---|
| `web` | `web_search`, `fetch_webpage`, `fetch_webpage_links`, `fetch_feed`, `search_feeds`, `get_youtube_video_info`, `get_youtube_transcript` |
| `knowledge` | `search_wikipedia`, `get_wikipedia_article`, `get_article_summary`, `get_article_sections`, `get_related_articles`, `search_arxiv`, `get_arxiv_paper`, `search_semantic_scholar`, `get_paper_references` |
| `geo` | `geocode`, `find_hikes`, `search_attractions`, `get_weather` |
| `finance` | `get_crypto_price`, `get_stock_quote` |
| `code` | `check_python_syntax`, `extract_code_metrics`, `detect_language` |
| `local` | `get_system_metrics`, `get_system_metrics_with_alerts`, `list_top_processes`, `check_disk_usage`, `find_large_files`, `get_service_status`, `transcribe_audio` |
| `text` | `chunk_text`, `count_tokens`, `extract_text`, `extract_text_from_bytes` |
| `invocable_apis` | dataset-synthesis primitives (rarely needed in app code) |

The MCP servers above are also deployed publicly on IBM Code Engine at
`https://cuga-apps-mcp-<name>.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp`
and the bridge picks them automatically when `CE_APP` / `CE_REVISION` /
`CUGA_TARGET=ce` are set, so the same app code works locally, in
docker-compose, and on Code Engine.

You can mix: load some MCP tools and define inline ones for app state. See
[apps/movie_recommender/main.py](apps/movie_recommender/main.py) and
[apps/city_beat/main.py](apps/city_beat/main.py) for two examples.

### 3. Copy `main.py` from a sibling app and adjust

Pick the closest sibling and use it as a starting point:

- **Inline tools only** → copy [apps/recipe_composer/main.py](apps/recipe_composer/main.py).
- **MCP only** → copy [apps/webpage_summarizer/main.py](apps/webpage_summarizer/main.py).
- **Mix of both** → copy [apps/city_beat/main.py](apps/city_beat/main.py)
  or [apps/movie_recommender/main.py](apps/movie_recommender/main.py).

The non-negotiable bits in `main.py`:

```python
# Path bootstrap (so `from _llm import …` and `from _mcp_bridge import …` resolve)
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Inline tool — ALWAYS returns json.dumps({"ok": true, "data": ...})
@tool
def my_tool(arg1: str) -> str:
    """Docstring is the LLM-readable spec. Be terse and concrete."""
    return json.dumps({"ok": True, "data": {"hello": arg1}})

# MCP tool import
from _mcp_bridge import load_tools
mcp_tools = load_tools(["web", "knowledge"])

# Agent factory
from cuga.sdk import CugaAgent
return CugaAgent(
    model=create_llm(provider=os.getenv("LLM_PROVIDER"),
                     model=os.getenv("LLM_MODEL")),
    tools=[*inline_tools, *mcp_tools],
    special_instructions=_SYSTEM,
    cuga_folder=str(_DIR / ".cuga"),
)

# Routes
@app.post("/ask")  async def api_ask(req: AskReq): ...
@app.get("/")      async def index():            return HTMLResponse(_HTML)
@app.get("/health") async def health():          return {"ok": True}
```

If your tools mutate session state, also expose `GET /session/{thread_id}`
returning the live state (the right-hand panel polls this every 10 s).

### 4. Copy `ui.py` from a sibling app and adjust

`ui.py` exports a single string `_HTML`. Use the closest sibling's UI as a
starting point — every app shares the same look:

- Dark theme: `#0f1117` bg, `#1a1a2e` cards, `#2d2d4a` borders.
- Sticky header with app name + status badge.
- Two-panel layout: left chat (with example chips), right live data.
- Vanilla JS only. No frameworks. No external CSS.
- Calls `POST /ask` with `{question, thread_id}` and renders `answer`.
- If your app has live state, poll `GET /session/{thread_id}` every 10 s.

### 5. Wire it into the repo

Three files need to know your app exists:

- [apps/_ports.py](apps/_ports.py) — add `"<your_app>": 28xxx` to `APP_PORTS`.
- [apps/launch.py](apps/launch.py) — add a `dict(name=..., kind="app", ...)` line to `PROCS`.
- [docker-compose.yml](docker-compose.yml) — add the service block (mirror an existing one).
- [start.sh](start.sh) — add the launch line if you want it in the dev start sequence.
- [ui/src/data/usecases.ts](ui/src/data/usecases.ts) — add the tile entry that
  shows your app in the umbrella UI at port 3001.

### 6. Run it

```bash
cd apps/<your_app>
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --port 28xxx
# open http://127.0.0.1:28xxx

# health check
curl http://localhost:28xxx/health     # → {"ok": true}

# /ask round-trip
curl -X POST http://localhost:28xxx/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"<example prompt>","thread_id":"default"}'
```

Or launch the whole stack at once:

```bash
python apps/launch.py        # starts MCP servers + every app
python apps/launch.py status
python apps/launch.py logs
```

---

## Tool envelope — one rule

**Every** tool returns a JSON string in this shape:

```python
# Success
return json.dumps({"ok": True, "data": <whatever>})

# Failure
return json.dumps({"ok": False, "error": "human message", "code": "bad_input"})
# code values: "bad_input" | "not_found" | "missing_key" | "upstream"
```

This applies to inline `@tool` defs **and** MCP `@mcp.tool()` defs (use
`tool_result(...)` / `tool_error(...)` from `mcp_servers/_core/`). The
matching contract is what makes inline → MCP migration a copy-paste move
later.

---

## System prompt — the shape that works

The system prompt is the agent's identity + workflow. Keep it static
(`_SYSTEM = """..."""`), not dynamically composed per request.

```text
# <App Name>

<One sentence describing the agent's identity.>

## Workflow
1. <Step 1 — which tool to call first and why>
2. <Step 2 — …>
3. <Synthesis instructions — how to combine results>

## Output format
<What the response should look like — be specific.>

## Rules
- <hard constraint 1>
- <hard constraint 2>
- Always cite sources as markdown links.
- Never fabricate data the tools did not return.

## Thread ID  (only if your app has session state)
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every
tool call that requires thread_id.
```

---

## Common pitfalls

- **Returning a raw `dict` from a tool.** The agent silently mishandles it.
  Always `json.dumps(...)`.
- **Hardcoded API keys, providers, or models.** Read everything from
  `os.getenv(...)`. The user picks at runtime.
- **Importing `from cuga import CugaAgent`.** Use `from cuga.sdk import CugaAgent`.
- **Auto-refresh polling without a reason.** Only poll `/session/...` if
  your app has live state visible in the right panel.
- **Composing the system prompt per request.** Don't. Pin it in `_SYSTEM`.
- **A bundled `_llm.py`.** Don't add one — `apps/_llm.py` is the canonical
  copy and the path bootstrap reaches it.
- **A bundled Dockerfile / compose / tests.** Don't — they live at the repo
  root and the integration suite plugs in at integration time.

---

## Two reference apps in this repo

- [apps/recipe_composer/](apps/recipe_composer/) — **inline tools only**.
  9 inline `@tool`s wrap an in-memory pantry / diet / allergies /
  recipes-for-tonight session. No MCP, no API keys.

- [apps/city_beat/](apps/city_beat/) — **mix of MCP + inline**. Pulls
  `geo.geocode` + `geo.get_weather` + `geo.search_attractions` +
  `web.web_search` + `knowledge.get_wikipedia_article` +
  `finance.get_crypto_price` from MCP servers, and adds inline tools for
  per-session state and the structured briefing card.

For a more rigorous spec — including envelope rules, dev-loop tips, and
how to migrate inline tools to a shared MCP server — read
[`cuga_app_builder_spec.md`](cuga_app_builder_spec.md) (in-repo) or
[`cuga_app_builder_spec_standalone.md`](cuga_app_builder_spec_standalone.md)
(when delivering an app from outside the repo).
