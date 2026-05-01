# CUGA App Builder Spec — MCP + Inline Mix

This spec is for **Claude** (or any LLM agent) tasked with building a new
CUGA-agent app that **combines tools from one or more shared MCP servers
with app-specific inline `@tool` defs**. It assumes you have a working clone
of `cuga-apps` and are building inside it under [apps/](apps/).

For "inline-only" apps, see
[`cuga_app_builder_spec_standalone.md`](cuga_app_builder_spec_standalone.md).
For the original "MCP-only" template, see
[`cuga_app_builder_spec.md`](cuga_app_builder_spec.md). This document is the
**hybrid** path — most real apps end up here.

The worked example throughout this spec is
[apps/city_beat/](apps/city_beat/), which combines tools from four MCP
servers (`geo`, `web`, `knowledge`, `finance`) with six inline session-
state tools.

---

## Why mix?

The two tool flavors are complementary:

| | MCP-loaded tools | Inline `@tool` defs |
|---|---|---|
| **Best for** | Generic capabilities reused across apps (web search, geocoding, Wikipedia, weather, prices, code analysis). | App-specific state (sessions, in-memory stores), one-off APIs only this app cares about, or anything that mutates internal app data. |
| **Where they live** | A separate process at `mcp_servers/<name>/server.py`, reachable over streamable HTTP. Already deployed locally, in docker-compose, and on Code Engine. | Defined inside this app's `main.py` with a `from langchain_core.tools import tool` decorator. |
| **State** | Pure functions of arguments + env (`os.getenv(...)`). Cannot close over per-app data. | Can close over module-level dicts, hold session state, mutate the right-panel briefing. |
| **Migration path** | Already shared. | Promote to a new MCP server later if reuse picks up. The envelope is identical so the call site doesn't change. |

A "mixed" app uses MCP tools for the heavy lifting (network, third-party
APIs) and inline tools for the bits that are uniquely about this app
(per-session preferences, the structured card the UI renders).

---

## Available shared MCP servers

All eight servers are running locally on `127.0.0.1:29100–29107`, in the
docker-compose stack under DNS `mcp-<name>:<port>`, and publicly on IBM
Code Engine at
`https://cuga-apps-mcp-<name>.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp`.

Pick any subset by passing the names to `load_tools(...)`:

| Server | Tools (selected — see source for full list + arg shapes) | Source |
|---|---|---|
| `web` | `web_search`, `fetch_webpage`, `fetch_webpage_links`, `fetch_feed`, `search_feeds`, `get_youtube_video_info`, `get_youtube_transcript` | [mcp_servers/web/server.py](mcp_servers/web/server.py) |
| `knowledge` | `search_wikipedia`, `get_wikipedia_article`, `get_article_summary`, `get_article_sections`, `get_related_articles`, `search_arxiv`, `get_arxiv_paper`, `search_semantic_scholar`, `get_paper_references` | [mcp_servers/knowledge/server.py](mcp_servers/knowledge/server.py) |
| `geo` | `geocode`, `find_hikes`, `search_attractions`, `get_weather` | [mcp_servers/geo/server.py](mcp_servers/geo/server.py) |
| `finance` | `get_crypto_price`, `get_stock_quote` | [mcp_servers/finance/server.py](mcp_servers/finance/server.py) |
| `code` | `check_python_syntax`, `extract_code_metrics`, `detect_language` | [mcp_servers/code/server.py](mcp_servers/code/server.py) |
| `local` | `get_system_metrics`, `get_system_metrics_with_alerts`, `list_top_processes`, `check_disk_usage`, `find_large_files`, `get_service_status`, `transcribe_audio` | [mcp_servers/local/server.py](mcp_servers/local/server.py) |
| `text` | `chunk_text`, `count_tokens`, `extract_text`, `extract_text_from_bytes` | [mcp_servers/text/server.py](mcp_servers/text/server.py) |
| `invocable_apis` | dataset-synthesis primitives (rarely needed in app code) | [mcp_servers/invocable_apis/server.py](mcp_servers/invocable_apis/server.py) |

URL resolution is done by [apps/_mcp_bridge.py](apps/_mcp_bridge.py):

1. If `MCP_<NAME>_URL` is set, use it (explicit override).
2. Otherwise: Code Engine URL (when `CE_APP` / `CE_REVISION` /
   `CUGA_TARGET=ce` are set) → docker-compose DNS (when `/.dockerenv` or
   `CUGA_IN_DOCKER=1` are set) → `http://localhost:<port>/mcp`.

You don't need to think about this at app-write time — `load_tools(...)`
just works.

### Adding a new tool to an MCP server

If you find that a generic capability is missing, the right move is to
add it to the matching MCP server. Don't simulate web search inline.

```python
# mcp_servers/<server>/server.py
from mcp_servers._core import tool_result, tool_error

@mcp.tool()
def my_new_tool(arg1: str, arg2: int = 10) -> str:
    """Description visible to the LLM. Be terse and concrete.

    Args:
        arg1: …
        arg2: …
    """
    try:
        # … do the work …
        return tool_result({"key": "value"})
    except Exception as exc:
        return tool_error(f"upstream failure: {exc}", code="upstream")
```

Restart the server (or `python apps/launch.py`) and `load_tools([...])`
in your app picks it up automatically.

---

## App layout

Same as every other app in this repo — 4 files, no `_llm.py` shim, no
`__init__.py`, no Dockerfile:

```
apps/<your_app>/
├── main.py            FastAPI + CugaAgent + tool composition (REQUIRED)
├── ui.py              exports _HTML (REQUIRED)
├── README.md          how to run + tool list + env vars (REQUIRED)
└── requirements.txt   only what main.py imports (REQUIRED)
```

Optional helper modules (e.g. `store.py`, `compose_parser.py`) live next
to `main.py`.

---

## main.py — the hybrid template

This is the canonical shape. Replace placeholders. Every line is load-
bearing — see the table at the bottom of this file for the *why*.

```python
"""
<App Name> — <one-line tagline>
==============================

<2–4 sentences: what it does, what data it uses, why it's interesting.>

Run:
    python main.py
    python main.py --port 28xxx
    python main.py --provider anthropic

Then open: http://127.0.0.1:28xxx

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  CUGA settings TOML path (defaulted in make_agent)
    CUGA_TARGET           set to "ce" to force public Code Engine MCP URLs
    MCP_<NAME>_URL        per-server URL override (web/knowledge/geo/finance/...)
    <APP_KEY>             only if your inline tools need a key
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# ── Path bootstrap (resolves _llm and _mcp_bridge from apps/) ────────────
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ui import _HTML


# ── Per-thread session store ────────────────────────────────────────────
# thread_id → {whatever your app needs to track per-conversation}
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            # initialise every key your inline tools or the UI panel reads
            "items":     [],
            "card":      None,
        }
    return _sessions[thread_id]


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    """Compose MCP-loaded tools with inline @tool defs.

    The returned list is what gets handed to CugaAgent. Order doesn't matter
    semantically, but putting MCP tools first makes the system prompt
    easier to scan when you reference tool names.
    """
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools

    # ── 1. MCP tools ────────────────────────────────────────────────────
    # Pick the servers your app actually uses. Each name must be in
    # apps/_ports.py:MCP_PORTS. Loading is blocking — it round-trips to
    # each server to discover tool schemas.
    mcp_tools = load_tools(["geo", "web", "knowledge", "finance"])

    # ── 2. Inline tools ─────────────────────────────────────────────────
    # Inline tools own everything that doesn't make sense as a shared
    # server: per-session state, app-specific glue, and the structured
    # card the UI renders.

    @tool
    def remember_thing(thread_id: str, item: str) -> str:
        """Add an item to this session's tracked list.

        Args:
            thread_id: The current session/thread ID (always pass through).
            item:      Plain English item.
        """
        if not item:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "item is empty"})
        session = _get_session(thread_id)
        if item not in session["items"]:
            session["items"].append(item)
        return json.dumps({"ok": True, "data": {"items": session["items"]}})

    @tool
    def save_card(thread_id: str, card_json: str) -> str:
        """Persist the structured card the right panel renders.

        Args:
            thread_id: The current session/thread ID.
            card_json: JSON object — see the system prompt for required keys.
        """
        session = _get_session(thread_id)
        try:
            session["card"] = json.loads(card_json)
            return json.dumps({"ok": True, "data": {"saved": True}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    inline_tools = [remember_thing, save_card]

    return [*mcp_tools, *inline_tools]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# <App Name>

<One sentence describing the agent's identity.>

## Workflow
1. <Listening rules — when to call inline state tools eagerly>
2. <On-request rules — which MCP tools to call and in what order>
3. <Synthesis rules — when to call save_card, what shape the card has>
4. <Reply rules — how to talk to the user once the card is saved>

## Output format
<What the response should look like — be specific. Mention that the right
panel shows the structured detail so the prose can stay short.>

## Rules
- <hard constraint 1>
- <hard constraint 2>
- Cite all sources as markdown links.
- Never fabricate data the tools did not return.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every
inline tool that requires thread_id.
"""


# ── Agent factory ────────────────────────────────────────────────────────
def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",
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


# ── Request models + HTTP server ─────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="<App Name>", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = _get_agent()
            result = await agent.invoke(augmented, thread_id=thread_id)
            return {"answer": str(result), "thread_id": thread_id}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(
                status_code=500,
                content={"answer": f"Error: {exc}", "thread_id": thread_id},
            )

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    print(f"\n  <App Name>  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="<App Name>")
    parser.add_argument("--port", type=int, default=28xxx)
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

---

## How to design a mixed app — the questions to answer first

Before you write code, write down your answers to these. They drive the
shape of `_make_tools()`, `_SYSTEM`, and the right-panel UI.

1. **What's the user-facing thing?** ("a city briefing card", "a stock
   alert ticker", "a recipe list with cook steps"). The card shape that
   answers this question is the contract for `save_<thing>`.
2. **What capabilities do I need from MCP servers?** Walk the table above.
   Note the exact tool names (e.g. `geo.geocode`, `web.web_search`).
   These names appear verbatim in the system prompt.
3. **What state needs to live across turns?** Anything the user might
   want preserved between messages (preferences, watchlists, the last
   card) is per-session inline state.
4. **What inline mutator tools do I need?** Roughly one per state field
   ("set X", "add to Y", "clear Z") plus the "save the card" tool.
5. **Which MCP tools should the agent call eagerly vs. on-demand?** Eager
   ones go first in the workflow section. On-demand ones are framed as
   "OPTIONAL: call X if Y" so the agent skips them when they're not
   needed.

The worked example — [apps/city_beat/](apps/city_beat/) — answers these
as:

1. A city briefing card with weather + news + wiki + (optional)
   attractions + (optional) crypto.
2. `geo.geocode`, `geo.get_weather`, `geo.search_attractions`,
   `web.web_search`, `knowledge.get_wikipedia_article`,
   `finance.get_crypto_price`.
3. The active city, focus topics, watchlist, optional crypto ticker, and
   the most recent briefing.
4. `set_current_city`, `add_focus_topic`, `clear_focus_topics`,
   `set_crypto_spotlight`, `get_session_state`, `save_briefing`.
5. Eager: geocode + weather + news + wiki on every turn. Optional:
   attractions (only when the user mentions things to do) and crypto
   (only when a spotlight ticker is set).

---

## The tool envelope — one rule

**Every** tool returns a JSON string in this shape:

```python
# success
return json.dumps({"ok": True, "data": <whatever>})

# failure
return json.dumps({"ok": False, "error": "human message", "code": "bad_input"})
# valid codes: "bad_input" | "not_found" | "missing_key" | "upstream"
```

This applies to inline `@tool` defs **and** MCP `@mcp.tool()` defs (use
`tool_result(...)` / `tool_error(...)` from `mcp_servers/_core/`). The
matching contract is what makes inline → MCP migration a copy-paste move
later, with no callsite changes.

For inline tools that **don't** use this envelope (the agent silently
mishandles raw dicts), you'll see the agent burn turns retrying or
asking the user to clarify.

---

## The system prompt — workflow, not procedure

The system prompt should describe **what** to do and **what shape** to
return — not the literal HTTP calls. The agent figures the calls out from
the tool docstrings.

A workable shape, taken from `city_beat`:

```
# <App Name>
You are a <role>. Your job is to <one sentence>.

## On every new request
1. If the user named a <thing>, call set_X to remember it.
2. Call get_session_state(thread_id=...) to recall prior context.
3. Call <fast MCP tool> to ground the request.

## Build the result
Call these — the order doesn't matter, but each must run:
  - <MCP tool 1>(...) for <reason>
  - <MCP tool 2>(...) for <reason>
  - OPTIONAL: <MCP tool 3>(...) only if <condition>

## Synthesize and persist
4. Build the result object (see save_X docstring for the shape).
5. Call save_X(thread_id=..., x_json=...).
6. Reply with a short prose summary.

## Rules
- Cite sources as markdown links.
- Never fabricate. If a tool fails, say so and skip that section.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every
inline tool that requires thread_id.
```

Put the JSON shape requirements in the **`save_<thing>` docstring**, not
in the system prompt — the agent re-reads tool docstrings every call but
the system prompt is one shot.

---

## ui.py — same shape as every other app

A self-contained `_HTML` string. Same conventions:

- Dark theme: `#0f1117` bg, `#1a1a2e` cards, `#2d2d4a` borders. Pick one
  accent color per app (`city_beat` is sky blue `#38bdf8`,
  `recipe_composer` is warm orange `#fb923c`).
- Sticky header with app name + status badge.
- Two-panel layout: left chat (with 6–9 example chips), right live data.
- Vanilla JS only. Calls `POST /ask` with `{question, thread_id}` and
  renders `answer`. Polls `GET /session/{thread_id}` every 10 s and
  re-renders the structured card.
- The right-panel renderer is a pure function of the session JSON — it
  diffs on a hash and only repaints when the JSON actually changes.

Copy the closest sibling app's `ui.py` and adjust the renderer
(`renderHero`, `renderWeather`, `renderNews`, …) to match your card
shape.

---

## Wiring into the repo (3 files)

After your app folder is created and runs locally on its own port, wire
it into the umbrella infrastructure:

1. **[apps/_ports.py](apps/_ports.py)** — add `"<your_app>": 28xxx` to
   the `APP_PORTS` dict.
2. **[apps/launch.py](apps/launch.py)** — add a
   `dict(name=..., kind="app", port=APP_PORTS[...], cwd=HERE / "<your_app>", cmd=_app_cmd())`
   line to `PROCS`.
3. **[docker-compose.yml](docker-compose.yml)** — copy an existing app
   service block and adjust name + port + path.
4. **[ui/src/data/usecases.ts](ui/src/data/usecases.ts)** — add the tile
   entry the umbrella UI shows at port 3001.
5. **[start.sh](start.sh)** — optionally add the launch line if you want
   it in the dev start sequence.

---

## Definition of done

Before opening a PR, every box must check:

- [ ] App folder is one of `apps/<your_app>/{main.py, ui.py, README.md, requirements.txt}` (+ optional helpers)
- [ ] No `_llm.py` shim in the app folder; the path bootstrap reaches `apps/_llm.py`
- [ ] No `__init__.py` in the app folder
- [ ] No Dockerfile / compose / tests in the app folder
- [ ] `from cuga.sdk import CugaAgent` (not `from cuga import …`)
- [ ] `_make_tools()` returns the union of MCP-loaded + inline `@tool` defs
- [ ] Every inline tool returns `json.dumps({"ok": ..., ...})` — no raw dicts, no Python objects
- [ ] Every inline tool docstring documents its args
- [ ] Inline tools that mutate session state take `thread_id` as their first positional argument
- [ ] `_SYSTEM` is static (defined as a module-level string), not composed per request
- [ ] `_SYSTEM` references each MCP tool by name and explains when to call it
- [ ] The `save_<thing>` tool's docstring documents the exact JSON shape the UI expects
- [ ] `POST /ask` accepts `{question, thread_id}` and returns `{answer}`
- [ ] `GET /session/{thread_id}` returns the live session state (used by the right-panel polling)
- [ ] `GET /health` returns `{"ok": true}`
- [ ] `GET /` returns the `_HTML` string
- [ ] UI is dark-themed, vanilla JS, single self-contained string
- [ ] UI polls `/session/{thread_id}` every 10 s and re-renders the card
- [ ] Port is in `apps/_ports.py:APP_PORTS`
- [ ] App is registered in `apps/launch.py:PROCS`
- [ ] App has a tile in `ui/src/data/usecases.ts`
- [ ] README documents port, env vars, MCP servers used, the tool list, and 3+ example prompts
- [ ] Standalone bring-up works: `python main.py --port 28xxx` → `/health` ok, `/ask` returns a real agent response, UI loads and the card populates

---

## Quick start

```bash
# 1. Pick a name + port (28822 is the next free; double-check apps/_ports.py)
APP=my_app
PORT=28822
mkdir -p apps/$APP

# 2. Copy the closest existing mixed app as a starting point
cp apps/city_beat/main.py        apps/$APP/main.py
cp apps/city_beat/ui.py          apps/$APP/ui.py
cp apps/city_beat/README.md      apps/$APP/README.md
cp apps/city_beat/requirements.txt apps/$APP/requirements.txt
$EDITOR apps/$APP/main.py        # change name, tools, prompt, default port
$EDITOR apps/$APP/ui.py          # change title, accent color, chips, renderer
$EDITOR apps/$APP/README.md      # rewrite for your app

# 3. Make sure MCP servers are up
python apps/launch.py            # starts MCP servers + every app
# … or just the MCP servers if you want to run your app on its own:
#   python -m mcp_servers.web.server &
#   python -m mcp_servers.geo.server &

# 4. Run your app standalone
cd apps/$APP
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --port $PORT

# 5. Verify
curl http://localhost:$PORT/health
curl -X POST http://localhost:$PORT/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"<example prompt>","thread_id":"default"}'
open http://localhost:$PORT
```

---

## Why each detail in `main.py` matters

| Detail | Why |
|---|---|
| `_DIR` + `_DEMOS_DIR` path bootstrap | Lets `from _llm import create_llm` and `from _mcp_bridge import load_tools` resolve from the parent `apps/` folder. |
| `from cuga.sdk import CugaAgent` | Canonical import. The legacy `from cuga import CugaAgent` works in some installs but is brittle. |
| `cuga_folder=str(_DIR / ".cuga")` | Per-app runtime state goes next to the app code, not in a shared scratch dir. |
| `AGENT_SETTING_CONFIG` defaulted in `make_agent()` | Without it, CUGA picks `settings.openai.toml` and crashes if `OPENAI_API_KEY` is unset. The defaults pick a TOML matching the chosen `LLM_PROVIDER`. |
| `_get_agent()` lazily inside the FastAPI factory | Lets the server start even if `make_agent()` would block on slow MCP handshakes — the first `/ask` triggers the load. |
| `AskReq` with `question` + `thread_id=""` | Matches every other app's API surface. Tests and clients hit any app the same way. |
| `[thread:<UUID>] question` augmentation | Smuggles `thread_id` into the agent's input so inline tools can read it. The agent extracts and passes it via the `thread_id` arg in tool calls. |
| `result = await agent.invoke(augmented, thread_id=thread_id)` then `str(result)` | The CugaAgent return is a typed object — coerce to str to get the human reply. |
| `POST /ask`, `GET /health`, `GET /`, `GET /session/{thread_id}` | The four routes the umbrella UI + integration tests assume exist. |
| Tools return `json.dumps({"ok": ..., ...})` strings | Same envelope as the MCP servers, so an inline tool can be moved to MCP later with no callsite changes. Raw dicts confuse the agent. |
| `_sessions` keyed by `thread_id` | The UI generates a UUID per browser session and reuses it across calls; the server keeps in-memory state per UUID. |

---

## TL;DR

1. Copy [apps/city_beat/](apps/city_beat/) as your starting point.
2. Decide your **card shape** (what the right panel renders) and your
   **MCP tool set** (which servers you need).
3. Inline-define a `save_<thing>` tool whose docstring spells out the
   card shape, plus 3–5 small `set_X` / `add_Y` / `get_session_state`
   tools for per-session state.
4. Write a `_SYSTEM` prompt that names each MCP tool and frames the
   workflow as eager + on-demand.
5. Build the UI by adapting the closest sibling — vanilla JS, polls
   `/session/...`, dark theme, two panels.
6. Wire into `apps/_ports.py`, `apps/launch.py`, `docker-compose.yml`,
   and `ui/src/data/usecases.ts`. Ship.
