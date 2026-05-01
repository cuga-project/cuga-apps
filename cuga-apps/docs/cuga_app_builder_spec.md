# CUGA App Builder Spec — MCP Edition

This spec is for **Claude** (or any LLM agent) tasked with building a new
demo app inside the `cuga-apps` repo. Read it end-to-end before you write
any code. Every code snippet here is copy-pasteable; every file path is
real.

The repo you're working in: `/home/amurthi/work/agent-apps/cuga-apps`.

---

## What you're building

A **CUGA agent app**: a single-process FastAPI server that

1. Wraps a `CugaAgent` (from `cuga.sdk`) configured with tools + a system prompt.
2. Loads its tools from one or more **MCP servers** (already running in the same
   compose stack on ports 29100–29107) — not by reimplementing them inline.
3. Serves a self-contained dark-themed HTML UI from `/`, plus a `POST /ask`
   endpoint that round-trips the user's question through the agent.
4. Appears as a tile in the umbrella UI (port 3001) and is covered by the
   integration test suite.

The app itself is **dumb**. All reasoning happens inside `CugaAgent`. Your code
is glue: wire tools, mount endpoints, render the result.

---

## The mental model

```
   ┌──────────────────────────────────────────────────┐
   │ Your new app — apps/<your_app>/main.py           │
   │                                                   │
   │   FastAPI                                         │
   │     ├── POST /ask  →  CugaAgent.invoke(question)  │
   │     ├── GET  /     →  HTMLResponse(_HTML)         │
   │     └── (optional) GET/POST data endpoints        │
   │                                                   │
   │   CugaAgent(                                      │
   │     model = create_llm(provider, model),          │
   │     tools = load_tools(["web", "knowledge"]),  ←──┼─ from _mcp_bridge
   │     special_instructions = _SYSTEM,               │
   │     cuga_folder = ".cuga",                        │
   │   )                                               │
   └────────────────┬──────────────────────────────────┘
                    │ streamable HTTP
                    ▼
       ┌─────────────────────────────┐
       │ 8 MCP servers — already up  │
       │  web · knowledge · geo ·    │
       │  finance · code · local ·   │
       │  text · invocable_apis      │
       └─────────────────────────────┘
```

You almost never need to write tool code. You compose existing MCP tools.

---

## Before you start: read these

In order. They are short and authoritative.

1. [README.md](README.md) — the umbrella doc.
2. [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — env vars, ports, what
   each MCP server exposes, how to bring the stack up.
3. [docs/ADDING_AN_APP.md](docs/ADDING_AN_APP.md) — the full add-an-app
   walkthrough with a worked example. **This spec is the LLM-targeted summary
   of that doc plus the code patterns; if you read only one human-doc, read
   that one.**
4. [docs/ADDING_A_TOOL.md](docs/ADDING_A_TOOL.md) — read this only if you
   conclude you must add a new MCP tool or server.
5. [apps/_ports.py](apps/_ports.py) — port registry, single source of truth.
6. Pick a near-twin existing app and read its `main.py` end-to-end. The
   "Reference apps" table at the bottom of this spec tells you which.

---

## Decision tree: where do my tools live?

This is the most important decision. Get it right and the rest is mechanical.

```
Does my tool …
│
├── … hit a public web service / fetch a URL / search the web?
│        → use mcp-web (web_search, fetch_webpage, fetch_feed, …)
│
├── … look up Wikipedia / arXiv / Semantic Scholar?
│        → use mcp-knowledge
│
├── … geocode / find POIs / get weather?
│        → use mcp-geo
│
├── … fetch crypto or stock prices?
│        → use mcp-finance
│
├── … analyze code (Python AST, language detection)?
│        → use mcp-code
│
├── … read host metrics / run faster-whisper / safe shell ops?
│        → use mcp-local
│
├── … extract text from a PDF / chunk / count tokens?
│        → use mcp-text
│
├── … query a SQLite registry of synthesized API tools (Bird-SQL)?
│        → use mcp-invocable_apis
│
├── … touch THIS app's private state (its SQLite, its in-memory store,
│       its inbox folder, its per-session config)?
│        → write it as an inline @tool inside main.py.
│        Examples in the repo: smart_todo, deck_forge, api_doc_gen.
│
└── … not fit any of the above?
         → first ask: should this be added to an existing MCP server?
           Almost always yes — see "Optional: adding a new MCP server".
           Only stand up a new server if the new domain is genuinely
           shared by ≥2 apps.
```

**Inventory of existing tools** (browse interactively at
http://localhost:28900 or read [docs/GETTING_STARTED.md#what-each-mcp-server-exposes](docs/GETTING_STARTED.md#what-each-mcp-server-exposes)):

| Server | Tools |
|---|---|
| mcp-web (29100) | `web_search`, `fetch_webpage`, `fetch_webpage_links`, `fetch_feed`, `search_feeds`, `get_youtube_video_info`, `get_youtube_transcript` |
| mcp-knowledge (29101) | `search_wikipedia`, `get_wikipedia_article`, `get_article_summary`, `get_article_sections`, `get_related_articles`, `search_arxiv`, `get_arxiv_paper`, `search_semantic_scholar`, `get_paper_references` |
| mcp-geo (29102) | `geocode`, `find_hikes`, `search_attractions`, `get_weather` |
| mcp-finance (29103) | `get_crypto_price`, `get_stock_quote` |
| mcp-code (29104) | `check_python_syntax`, `extract_code_metrics`, `detect_language` |
| mcp-local (29105) | `get_system_metrics`, `get_system_metrics_with_alerts`, `list_top_processes`, `check_disk_usage`, `find_large_files`, `get_service_status`, `transcribe_audio` |
| mcp-text (29106) | `chunk_text`, `count_tokens`, `extract_text`, `extract_text_from_bytes` |
| mcp-invocable_apis (29107) | `db_*`, `bird_*`, `tool_*`, `seq_*`, `dataset_*`, `ignore_*` |

---

## Step-by-step: build the app

### Step 1 — Pick a port

Open [apps/_ports.py](apps/_ports.py). Add a row to `APP_PORTS`:

```python
APP_PORTS: dict[str, int] = {
    # ... existing entries ...
    "<your_app_name>": 28816,    # next free 28xxx — confirm uniqueness
}
```

Naming: snake_case, matches the directory name you're about to create.

### Step 2 — Create the folder

```
apps/<your_app_name>/
├── README.md           required
├── main.py             required
├── ui.py               required (the HTML page)
└── requirements.txt    optional — only if you need pip deps beyond the global apps image
```

Do **not** create `__init__.py`. Apps are launched as scripts, not imported.

### Step 3 — `main.py` (canonical template)

```python
"""
<App Name> — <one-line tagline>
==============================

<2–4 sentences: what it does, why it's interesting, what data it pulls.>

Run:
    python main.py
    python main.py --port 28816
    python main.py --provider anthropic

Then open: http://127.0.0.1:28816

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL            model name override (provider-specific)
    AGENT_SETTING_CONFIG path to a CUGA settings TOML (rits → settings.rits.toml, etc.)
    <APP_KEY_NAME>       <what this key gates>   (only if applicable)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# ── Path bootstrap — REQUIRED, do not skip ───────────────────────────────
# Puts apps/ on sys.path so `from _llm import create_llm` and
# `from _mcp_bridge import load_tools` resolve. Also puts THIS app's dir on
# sys.path so `from ui import _HTML` works.
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Tools ────────────────────────────────────────────────────────────────
# Prefer MCP. Mix in inline @tool only for app-specific state.
def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["web", "knowledge"])     # ← edit to your servers


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# <App Name>

<One sentence describing the agent's identity.>

## Workflow
1. <Step 1 — which tool to call first and why>
2. <Step 2 — …>
3. <Synthesis instructions: how to combine results>

## Output format
<What the response should look like — be specific. The LLM follows this.>

## Rules
- <hard constraint 1>
- <hard constraint 2>
- Always cite source URLs in markdown link format.
- Never fabricate data the tools did not return.
"""


# ── Agent ────────────────────────────────────────────────────────────────
def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    # CUGA reads AGENT_SETTING_CONFIG to pick its internal settings TOML.
    # Set a sensible default per-provider so the app boots without ceremony.
    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",  # anthropic uses openai-compat
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        _provider_toml.get(provider, "settings.rits.toml"),
    )

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ── Request models ───────────────────────────────────────────────────────
from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str
    thread_id: str = "default"


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    from ui import _HTML

    app = FastAPI(title="<App Name>", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"],
        allow_methods=["*"], allow_headers=["*"],
    )

    agent = make_agent()

    @app.post("/ask")
    async def api_ask(req: AskReq):
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "Empty question"}, status_code=400)
        try:
            result = await agent.invoke(question, thread_id=req.thread_id)
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("Agent error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    print(f"\n  <App Name>  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="<App Name>")
    parser.add_argument("--port", type=int, default=28816)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
```

That is **a complete, runnable app**. Replace the `<...>` placeholders, point
`load_tools([...])` at the right MCP servers, and write a real system prompt.

#### Mixing MCP tools with inline @tool defs

When your app needs both shared MCP tools and tools that touch this app's
private state (a SQLite, an in-memory store, an inbox folder), do this:

```python
def _make_tools():
    from _mcp_bridge import load_tools
    from langchain_core.tools import tool
    import json as _json
    from store import save as _save, list_all as _list_all

    @tool
    def save_item(content: str, kind: str = "note") -> str:
        """Save an item to this app's local store.

        Args:
            content: The text to save.
            kind:    "todo" | "note" | "reminder".
        """
        item = _save(content=content, kind=kind)
        return _json.dumps(item)

    @tool
    def list_items() -> str:
        """Return all items in this app's local store as JSON."""
        return _json.dumps(_list_all())

    return load_tools(["web"]) + [save_item, list_items]
```

Rules for inline `@tool` defs:
- `@tool` from `langchain_core.tools`.
- Always return a **JSON string** (use `json.dumps`). Never raw dicts.
- Docstring is the LLM-readable spec. Be terse and concrete; document each arg.
- Keep them narrow. One tool per concern.
- Never put shared, stateless tools inline — those belong on an MCP server so
  every app can reuse them.

#### Async background tasks (cron-like apps)

If the app is event-driven (cron, file watcher, polling) — see
[`drop_summarizer`](apps/drop_summarizer/main.py),
[`stock_alert`](apps/stock_alert/main.py) — schedule the loop in
`@app.on_event("startup")`:

```python
@app.on_event("startup")
async def _kickoff():
    asyncio.create_task(_watch_loop(agent))
```

Do **not** use `asyncio.get_event_loop()` — Python 3.13 dropped its
auto-create behavior. Use `asyncio.create_task()` from inside the startup hook.

#### Calling MCP tools without an LLM

For schedulers / file watchers / webhook handlers that need a tool result
without going through the LLM, use the non-LLM path:

```python
from _mcp_bridge import call_tool

result = call_tool("text", "extract_text", {"path": "/data/foo.pdf"})
# returns the parsed `data` field of the {ok, data} envelope, or raises.
```

### Step 4 — `ui.py`

Export a single string `_HTML` — a fully self-contained dark-themed HTML page.

Requirements (deck-quality, consistent across apps):
- Dark theme — bg `#0f1117`, cards `#1a1a2e`, borders `#2d2d4a`, accent indigo
- Sticky header — app name + live status badge
- Two-panel layout — left: chat input + 6–10 clickable example prompts;
  right: rendered result card
- Vanilla JS — no external CSS or JS dependencies
- Calls `POST /ask` with `{question, thread_id}`, renders `answer` from the response
- Auto-refresh polling **only** if the app has genuine background state
  (live feed, ticker). Don't add polling to satisfy a checklist.

The simplest acceptable UI is in
[`docs/ADDING_AN_APP.md`](docs/ADDING_AN_APP.md#3-write-mainpy) (the inline
`_HTML`); a richer reference is
[`apps/web_researcher/main.py`](apps/web_researcher/main.py).

### Step 5 — `README.md`

Short and structured. Required blocks:

```markdown
# <App Name>

<2–3 sentence description.>

**Port:** 28816 → http://localhost:28816

## How it works

1. <Step the agent takes>
2. ...

## Run

\`\`\`bash
python main.py --port 28816
# open http://127.0.0.1:28816
\`\`\`

Env: `LLM_PROVIDER`, `LLM_MODEL`, `AGENT_SETTING_CONFIG`, <other keys>.

## Example prompts

- "<example prompt 1>"
- "<example prompt 2>"
- "<example prompt 3>"

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

<one-line app summary>

**MCP servers consumed:**
- **mcp-<server>** — `tool_a` · `tool_b` · `tool_c`

**Inline `@tool` defs:** none — every tool comes from MCP.
   (or list them if you have inline tools)

<!-- END: MCP usage -->
```

The `MCP usage` block is mirrored in the umbrella UI; keep it accurate.

### Step 6 — Wire it into the stack

Three files plus the umbrella UI registry. Each is mechanical.

**[`apps/launch.py`](apps/launch.py)** — append to `PROCS`:

```python
dict(name="<your_app>", kind="app", port=APP_PORTS["<your_app>"],
     cwd=HERE / "<your_app>", cmd=_app_cmd()),
```

**[`start.sh`](start.sh)** — append at the bottom (above the `wait`):

```sh
log "Starting <your_app>          on :28816"
python <your_app>/main.py --port 28816 &
```

**[`docker-compose.yml`](docker-compose.yml)** — add a port mapping under the
`apps` service's `ports:` list:

```yaml
- "28816:28816"   # <your_app>
```

If your app needs persistent storage, add a bind-mount under the `apps`
service's `volumes:` list:

```yaml
- ./apps/<your_app>/storage:/app/apps/<your_app>/storage
```

**[`ui/src/data/usecases.ts`](ui/src/data/usecases.ts)** — add an entry; copy
the schema from a similar existing app:

```ts
{
  id: '<your-app>',
  name: '<App Name>',
  tagline: '<short tagline>',
  category: 'research' | 'content' | 'documents' | 'productivity'
            | 'ops' | 'developer' | 'ibm',
  type: 'other',
  surface: 'gateway',
  status: 'working',
  channels: [],
  tools: [],   // legacy field; mcpUsage below is what gets rendered
  description: '<full description>',
  demoPath: 'apps/<your_app>',
  howToRun: {
    envVars: ['LLM_PROVIDER', 'LLM_MODEL', '<APP_KEY>'],
    setup: ['cd apps/<your_app>'],
    command: 'python main.py',
  },
  architecture: '<one-line architecture summary>',
  diagram: '',
  cugaContribution: [],
  appUrl: 'http://localhost:28816',
  mcpUsage: [
    { server: 'web', tools: ['web_search'] },
    { server: 'knowledge', tools: ['search_wikipedia'] },
  ],
  inlineTools: [],   // populate if you have inline @tool defs
},
```

### Step 7 — Add tests

The smoke tier auto-covers your app the moment you add it to `APP_PORTS` —
no extra work needed for `tests/test_smoke.py`.

For the wiring tier, add a row to `ENDPOINTS` in
[`tests/test_app_wiring.py`](tests/test_app_wiring.py) for any non-LLM REST
route you exposed:

```python
ENDPOINTS = [
    # ... existing rows ...
    ("<your_app>", "/health", "json_obj"),
]
```

Shape kinds: `json_obj`, `json_list`, `any_2xx`. Use `any_2xx` if you don't
care about response body shape.

If your app has a stateful round-trip (add → list → toggle → delete), copy
the `TestWebResearcherTopicsRoundtrip` class pattern.

If you want an opt-in LLM probe, add an entry to `LLM_PROBES` in
[`tests/test_app_llm.py`](tests/test_app_llm.py). Skip this for first-pass.

### Step 8 — Build, run, verify

```bash
# 1. Build the apps + ui images
docker compose build apps ui

# 2. Bring up
docker compose up -d apps ui

# 3. Confirm the app's process started
docker compose logs apps --tail 80 | grep <your_app>

# 4. Hit it
curl http://localhost:28816/health
# → {"ok": true}

curl -X POST http://localhost:28816/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"<an example prompt>"}'

# 5. Run the test suite
make test
# Expected:  smoke + mcp + wiring tiers pass; your app appears in the
# parametrized smoke output.
```

If the umbrella UI tile 404s, check `docker compose logs apps | grep -B2
<your_app>` — the FastAPI process likely crashed at startup.

---

## Environment variables

CUGA always requires:

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Always | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Always | Model name (e.g. `claude-sonnet-4-6`, `llama-3-3-70b-instruct`) |
| `AGENT_SETTING_CONFIG` | Always | Path to a CUGA settings TOML. Set a per-provider default in `make_agent()` (see template) so the app boots without ceremony. |
| Provider key | When using that provider | `RITS_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `WATSONX_APIKEY` / `LITELLM_API_KEY` |

If your tools need API keys beyond the LLM, add them to
[`apps/.env.example`](apps/.env.example) with a comment explaining what they
gate. Don't hardcode.

If a key is missing, prefer **degraded behavior** over crash: the matching
MCP tool will return `tool_error("KEY not set", code="missing_key")` — your
agent sees the error and can tell the user. Don't pre-validate at boot.

---

## Optional: adding a new MCP server

**You almost certainly don't need to.** Stretch the existing themes (web,
knowledge, geo, finance, code, local, text) before adding a server. Read
[`docs/ADDING_A_TOOL.md`](docs/ADDING_A_TOOL.md) — adding a tool to an
*existing* server is one file edit + one rebuild + one test row.

A new server is justified only when:
- The new domain is genuinely shared by **≥2 apps** (otherwise it's app-private
  state — keep it inline).
- The tools are stateless and stand on their own conceptually (a clear domain:
  "imaging", "audio", "search of internal corpus X").

If those both hold, here's the loop. The server image is shared — same
`Dockerfile.mcp`, different command — so this is mostly registration, not
new infrastructure.

### Files to create

```
mcp_servers/<name>/
├── __init__.py        empty
└── server.py
```

`server.py` template (copy [`mcp_servers/code/server.py`](mcp_servers/code/server.py)
and edit — that's the smallest, stdlib-only example):

```python
"""mcp-<name> — <one-line description of the domain>.

Tools:
  - tool_a(args)  <one-line description>
  - tool_b(args)  <one-line description>
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result, get_json
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_<NAME>_PORT

mcp = make_server("mcp-<name>")


@mcp.tool()
def first_tool(text: str, n: int = 5) -> str:
    """Do <thing>. Return <shape>.

    Args:
        text: <description>.
        n:    <description> (default 5).
    """
    if not text:
        return tool_error("text is empty", code="bad_input")
    try:
        # ... do the work ...
        return tool_result({"result": ..., "count": n})
    except Exception as exc:
        return tool_error(f"failed: {exc}", code="upstream")


if __name__ == "__main__":
    run(mcp, MCP_<NAME>_PORT)
```

**Tool contract — non-negotiable:**
- Return `tool_result(payload)` on success, `tool_error(msg, code=...)` on failure.
  Never return raw dicts/strings.
- Common error codes: `bad_input`, `not_found`, `missing_key`, `upstream`.
- Tools are **pure functions of their args**. No shared state. No mutable caches.
- Read API keys at call time via `os.getenv(...)`, not at import time.
  Return `tool_error("KEY_NAME not set", code="missing_key")` if missing —
  the stack stays up if a key is missing.
- Outbound HTTP goes through `mcp_servers._core.http.get_json` / `get_text` /
  `get_xml` so timeout, user-agent, and follow_redirects are consistent.
- The docstring is what the LLM reads at tool-binding time. Be terse and
  concrete: what each arg means, what shape the response has. Behavior
  documented only in code comments is invisible to the LLM.

### Files to update

| File | What to add |
|---|---|
| [`apps/_ports.py`](apps/_ports.py) | `MCP_<NAME>_PORT = 29108` (next free) and an entry in `MCP_PORTS` |
| [`requirements.mcp.txt`](requirements.mcp.txt) | New pip deps, if any |
| [`Dockerfile.mcp`](Dockerfile.mcp) | Pre-download model files if any (HuggingFace, faster-whisper, tiktoken BPE) so the first runtime call doesn't stall |
| [`docker-compose.yml`](docker-compose.yml) | New service block — copy `mcp-text`'s, change name + command + port + any volumes |
| [`apps/launch.py`](apps/launch.py) | Append entry to `PROCS` (kind="mcp") |
| [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) | Row in the "What each MCP server exposes" table |
| [`tests/test_smoke.py`](tests/test_smoke.py) | Update the "lists all N servers" test count |
| [`tests/test_mcp_tools.py`](tests/test_mcp_tools.py) | New `TestMcp<Name>` class with one test per tool — see existing classes for the pattern |

### Build + verify

```bash
# Rebuild affected images. The tool explorer's image COPYs apps/_ports.py
# so it must rebuild too — otherwise the new server won't appear in the UI.
docker compose build mcp-<name> mcp-tool-explorer apps
docker compose up -d mcp-<name> mcp-tool-explorer apps

# Confirm the server is online and shows the new tools
curl -s http://localhost:28900/api/servers | python3 -m json.tool

# Run tests
make test            # smoke + mcp + wiring; new tier auto-covers your tools
```

---

## Anti-patterns — what NOT to do

These are real footguns observed across the existing 24 apps. Avoid them.

- **Reimplementing an existing MCP tool inline.** If `web_search` exists on
  `mcp-web`, do not write a Tavily-call inline `@tool`. Use `load_tools(["web"])`.
- **Returning raw dicts from inline `@tool` defs.** They must return JSON
  strings (`json.dumps(...)`). The agent will silently mishandle dicts.
- **Hardcoding a provider or model.** Always read from `LLM_PROVIDER` /
  `LLM_MODEL`. The user picks via env vars or `--provider`.
- **Skipping the path bootstrap.** The `for _p in (str(_DIR), str(_DEMOS_DIR))`
  block is required — otherwise `_llm`, `_mcp_bridge`, and `ui` won't import.
- **Shared mutable state across requests.** Use `thread_id` on
  `agent.invoke(question, thread_id=...)` to keep sessions isolated. Don't
  use module-level `global` for anything per-user.
- **Validating env vars at boot.** A missing tool key should not crash the app.
  Let the matching MCP tool return `missing_key` and let the agent surface
  the error to the user. The stack must stay up with partial config.
- **Adding a new MCP server "just because".** The bar is ≥2 consumers.
  Below that, it's app-private state — keep it inline.
- **Adding auto-refresh polling to the UI** when the app has no genuine
  background state. Polling every 10s on a static result wastes everything.
- **External CSS/JS dependencies in `_HTML`.** The UI is one self-contained
  string. Vanilla only.
- **`asyncio.get_event_loop()`** anywhere — dropped in 3.13. Use
  `asyncio.create_task(...)` from inside `@app.on_event("startup")`.
- **Using `from cuga import CugaAgent`.** The canonical import is
  `from cuga.sdk import CugaAgent`. Old apps used the bare path; new ones
  must use `cuga.sdk`.
- **Editing the auto-generated `MCP usage` block** in any app's README by
  hand. It's regenerated from `load_tools([...])` and inline `@tool` defs.
- **Working without the stack up.** Local dev requires the MCP servers
  running. Either `docker compose up -d` or `python apps/launch.py`.

---

## Reference apps — copy from these

When in doubt, **find a near-twin and copy it**. The repo is full of clean
templates.

| Your app's shape | Copy from |
|---|---|
| Pure MCP, single server, single `/ask` endpoint | [`web_researcher`](apps/web_researcher/main.py), [`paper_scout`](apps/paper_scout/main.py), [`code_reviewer`](apps/code_reviewer/main.py), [`wiki_dive`](apps/wiki_dive/main.py) |
| Pure MCP, multiple servers (orchestration across tools) | [`travel_planner`](apps/travel_planner/main.py), [`hiking_research`](apps/hiking_research/main.py) |
| MCP + inline session state | [`movie_recommender`](apps/movie_recommender/main.py), [`voice_journal`](apps/voice_journal/main.py) |
| MCP + heavy app-specific business logic | [`ibm_cloud_advisor`](apps/ibm_cloud_advisor/main.py), [`box_qa`](apps/box_qa/main.py) |
| No MCP — purely app-private state | [`smart_todo`](apps/smart_todo/main.py), [`api_doc_gen`](apps/api_doc_gen/main.py), [`deck_forge`](apps/deck_forge/main.py) |
| Event-driven (cron / file watcher / polling) | [`newsletter`](apps/newsletter/main.py), [`drop_summarizer`](apps/drop_summarizer/main.py), [`stock_alert`](apps/stock_alert/main.py) |
| Web research with research-then-write workflow | [`paper_scout`](apps/paper_scout/main.py), [`hiking_research`](apps/hiking_research/main.py) |
| Synthesis pipeline with closed-loop validation | [`bird_invocable_api_creator`](apps/bird_invocable_api_creator/main.py) — the most ambitious; only model after it if your task is genuinely closed-loop |

---

## Definition of done

Before you call the work complete, every box must check:

- [ ] Port allocated in [`apps/_ports.py`](apps/_ports.py) (no collision)
- [ ] `apps/<your_app>/main.py` written, runs locally with `python main.py`
- [ ] `apps/<your_app>/ui.py` written, page renders dark-themed UI with
      working chat panel + result panel
- [ ] `apps/<your_app>/README.md` written with port, env vars, 3+ example
      prompts, and the `MCP usage` block accurate
- [ ] Entry added to [`apps/launch.py`](apps/launch.py) `PROCS`
- [ ] Line added to [`start.sh`](start.sh)
- [ ] Port mapping in [`docker-compose.yml`](docker-compose.yml); volumes if
      app has persistent storage
- [ ] Any new env vars added to [`apps/.env.example`](apps/.env.example)
- [ ] Entry in [`ui/src/data/usecases.ts`](ui/src/data/usecases.ts) with
      `mcpUsage` populated
- [ ] Wiring test rows in [`tests/test_app_wiring.py`](tests/test_app_wiring.py)
      for non-LLM endpoints
- [ ] `docker compose build apps ui && docker compose up -d apps ui` succeeds
- [ ] `curl http://localhost:<port>/health` returns `{"ok": true}`
- [ ] `curl -X POST http://localhost:<port>/ask -d '{"question":"..."}'`
      returns a real, non-stub response from the agent
- [ ] Umbrella UI tile at http://localhost:3001 renders, links to the app
- [ ] `make test` passes (smoke + mcp + wiring)
- [ ] No hardcoded provider, model, or API key anywhere in `main.py`

---

## TL;DR — for the impatient agent

1. Read [`apps/paper_scout/main.py`](apps/paper_scout/main.py) end-to-end.
2. Copy the structure. Replace tool list, system prompt, port, name.
3. Update `_ports.py`, `launch.py`, `start.sh`, `docker-compose.yml`,
   `usecases.ts`, `tests/test_app_wiring.py`.
4. `docker compose build apps ui && docker compose up -d`. Verify health,
   `/ask`, the umbrella tile, and `make test`.
5. Only consider a new MCP server if the new tools will be shared by ≥2 apps.
   Otherwise inline `@tool` defs are fine.
