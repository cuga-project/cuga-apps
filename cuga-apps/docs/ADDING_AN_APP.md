# Adding a new app

Goal: ship a new agent-app — its own FastAPI process, its own port, its own
browser UI — that consumes one or more MCP servers, appears as a tile in the
umbrella UI, and is covered by the integration tests.

This guide walks the loop with a worked example: a "**Recipe Finder**" app
that searches Wikipedia for recipe articles and the web for reviews. It
consumes `mcp-knowledge` and `mcp-web`.

---

## The end state

You'll have:

```
apps/recipe_finder/
├── README.md
├── main.py              FastAPI server + CugaAgent
└── requirements.txt     (optional, for local dev)
```

Plus updates to: `apps/_ports.py`, `apps/launch.py`, `start.sh`,
`docker-compose.yml`, `ui/src/data/usecases.ts`, `tests/test_app_wiring.py`.

---

## 1. Pick a port

Open [apps/_ports.py](../apps/_ports.py). Add to the `APP_PORTS` dict:

```python
APP_PORTS: dict[str, int] = {
    # ... existing 23 entries ...
    "recipe_finder": 28815,    # next free 28xxx
}
```

The naming convention: snake_case keys, matching the directory name.

## 2. Decide which MCP servers your app uses

Look at [docs/GETTING_STARTED.md](GETTING_STARTED.md#what-each-mcp-server-exposes)
or http://localhost:28900 to see what's available. For Recipe Finder we want:

- `mcp-knowledge` — `search_wikipedia`, `get_wikipedia_article` for canonical recipe pages
- `mcp-web` — `web_search` for review aggregation

If your app needs a primitive that doesn't yet exist, see
[ADDING_A_TOOL.md](ADDING_A_TOOL.md) — add the tool to the right server first.

If your app has truly app-specific state (DB, per-user auth, vector store),
those tools stay inline as plain `@tool` functions in your app's `main.py`.
That's fine — see [movie_recommender](../apps/movie_recommender/main.py) for a
worked example of mixing MCP tools with inline state tools.

## 3. Write `main.py`

Easiest path: copy a similar existing app and edit. For Recipe Finder, the
closest template is [apps/web_researcher/main.py](../apps/web_researcher/main.py)
(also a single-MCP-server, single-/ask-endpoint app).

Minimum skeleton:

```python
"""
Recipe Finder — Wikipedia recipe lookup + web review aggregation.

Run:
    python main.py --port 28815

Environment variables:
    LLM_PROVIDER, LLM_MODEL    — LLM backend
    TAVILY_API_KEY             — read by mcp-web for web_search
"""
import argparse, logging, os, sys
from pathlib import Path

_DIR = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for p in (str(_DIR), str(_DEMOS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Tools — delegated to mcp-knowledge + mcp-web ─────────────────────────
def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["knowledge", "web"])

# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# Recipe Finder

You help users find recipes and assess them.

## Workflow
1. Call `search_wikipedia` to find candidate recipe articles.
2. Call `get_wikipedia_article` for the most promising hit.
3. Call `web_search` for "<recipe name> recipe review" to see what cooks
   actually say about the dish.
4. Return: brief description, key ingredients, difficulty hint, 2-3
   reviewer quotes with attribution.

## Rules
- Only suggest recipes you've actually fetched from Wikipedia.
- Always cite source URLs.
"""

# ── Agent ────────────────────────────────────────────────────────────────
def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm
    return CugaAgent(
        model=create_llm(provider=os.getenv("LLM_PROVIDER"),
                         model=os.getenv("LLM_MODEL")),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )

# ── HTTP server ──────────────────────────────────────────────────────────
from pydantic import BaseModel  # noqa: E402

class AskReq(BaseModel):
    question: str

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="Recipe Finder", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    agent = make_agent()

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            result = await agent.invoke(req.question, thread_id="chat")
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

    print(f"\n  Recipe Finder  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


_HTML = """<!doctype html><html><body>
<h1>Recipe Finder</h1>
<form id=f><input id=q size=60><button>Ask</button></form>
<pre id=out></pre>
<script>
f.onsubmit = async (e) => {
  e.preventDefault();
  out.textContent = '...';
  const r = await fetch('/ask', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({question: q.value})});
  out.textContent = (await r.json()).answer || 'error';
};
</script>
</body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=28815)
    parser.add_argument("--provider", "-p", default=None)
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()
    if args.provider: os.environ["LLM_PROVIDER"] = args.provider
    if args.model:    os.environ["LLM_MODEL"] = args.model
    _web(args.port)


if __name__ == "__main__":
    main()
```

That's a complete, runnable app. `_HTML` is intentionally minimal here —
real apps in this repo have richer single-page UIs you can crib from
([web_researcher](../apps/web_researcher/main.py) is a good reference).

## 4. Register in the launcher and Docker stack

### `apps/launch.py`

Add an entry to the `PROCS` list:

```python
dict(name="recipe_finder", kind="app", port=APP_PORTS["recipe_finder"],
     cwd=HERE / "recipe_finder", cmd=_app_cmd()),
```

### `start.sh` (apps container entrypoint)

Append a line:

```sh
log "Starting recipe_finder       on :28815"
python recipe_finder/main.py --port 28815 &
```

### `docker-compose.yml`

Add a port mapping under the `apps` service:

```yaml
ports:
  # ... existing entries ...
  - "28815:28815"   # recipe_finder
```

If your app needs a persistent volume (SQLite, vector store, output dir),
add a bind-mount under `volumes:`. If it consumes any new env var, add it
to [apps/.env.example](../apps/.env.example).

## 5. Add the README

Every app gets a README — at minimum:

```markdown
# Recipe Finder

A FastAPI app that finds recipes via Wikipedia and aggregates reviews
via web search.

**Port:** 28815 → http://localhost:28815

## How it works

1. User asks for a dish.
2. Agent calls `search_wikipedia` (mcp-knowledge) for candidate articles.
3. Agent calls `get_wikipedia_article` for the top match.
4. Agent calls `web_search` (mcp-web) for "recipe reviews".
5. Synthesises a brief with citations.

## Run

\`\`\`bash
python main.py --port 28815
# open http://127.0.0.1:28815
\`\`\`

Env: `LLM_PROVIDER`, `LLM_MODEL`, `TAVILY_API_KEY`.

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Wikipedia recipe lookup + web review aggregation.

**MCP servers consumed:**
- **mcp-knowledge** — `search_wikipedia` · `get_wikipedia_article`
- **mcp-web** — `web_search`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->
```

The MCP-usage block is what the umbrella UI mirrors — see step 7.

## 6. Try it locally

```bash
cd cuga-apps/apps
python recipe_finder/main.py --port 28815
# in another terminal:
curl http://localhost:28815/health
# → {"ok": true}
curl -X POST http://localhost:28815/ask -H 'Content-Type: application/json' \
  -d '{"question":"Find me a good carbonara recipe"}'
```

(Local-dev path requires the MCP servers to be running too — either via
`docker compose up -d` or `python apps/launch.py`.)

## 7. Add to the umbrella UI

Open [ui/src/data/usecases.ts](../ui/src/data/usecases.ts) and add an entry.
Easiest: copy a similar one (e.g. `web-researcher`) and edit. The schema is at
the top of that file; minimum required fields for a runnable tile:

```ts
{
  id: 'recipe-finder',
  name: 'Recipe Finder',
  tagline: 'Find recipes and aggregate reviews',
  category: 'personal',
  type: 'other',
  surface: 'gateway',
  status: 'working',
  channels: [],
  tools: [],   // legacy field; mcpUsage below is what gets rendered
  description: 'Wikipedia recipe lookup + web review aggregation.',
  demoPath: 'apps/recipe_finder',
  howToRun: {
    envVars: ['LLM_PROVIDER', 'LLM_MODEL', 'TAVILY_API_KEY'],
    setup: ['cd apps/recipe_finder', 'pip install -r requirements.txt'],
    command: 'python main.py',
  },
  architecture: 'FastAPI shell, CugaAgent, tools from mcp-knowledge + mcp-web.',
  diagram: '',
  cugaContribution: [],
  appUrl: 'http://localhost:28815',
  mcpUsage: [
    { server: 'knowledge', tools: ['search_wikipedia', 'get_wikipedia_article'] },
    { server: 'web',       tools: ['web_search'] },
  ],
  inlineTools: [],
},
```

The `mcpUsage` field drives the colored chip rendering in the umbrella UI's
Tools column and the "MCP Servers & Tools" section on the detail page.

Rebuild the UI image:

```bash
docker compose build ui && docker compose up -d ui
```

## 8. Add to the test suite

The integration suite parametrizes over the apps registry, so the smoke test
**automatically** covers your new app the moment you add it to `APP_PORTS`.
Run `make test-quick` to confirm:

```bash
make test-quick
# tests/test_smoke.py::test_app_serves_root[recipe_finder] PASSED
```

For the wiring tier, add an entry to the `ENDPOINTS` list in
[tests/test_app_wiring.py](../tests/test_app_wiring.py) for any non-LLM REST
routes you exposed (`/health`, `/settings`, `/reports`, etc.):

```python
ENDPOINTS = [
    # ... existing entries ...
    ("recipe_finder", "/health", "json_obj"),
]
```

If your app has a non-LLM mutating endpoint (like `web_researcher`'s
`/topics/add`), consider adding a stateful round-trip test class — model it
after `TestWebResearcherTopicsRoundtrip`.

If you want an opt-in LLM round-trip, add an entry to `LLM_PROBES` in
[tests/test_app_llm.py](../tests/test_app_llm.py).

## 9. Build + bring up

```bash
docker compose build apps && docker compose up -d apps
```

Then re-run the test suite:

```bash
make test
```

Three tiers run automatically (smoke + mcp + wiring). Your new app is now
covered by:

- a smoke test that verifies it serves on its port
- any wiring test you added for its REST routes
- (opt-in) an LLM round-trip if you added one

## Checklist

- [ ] port allocated in `apps/_ports.py`
- [ ] `apps/<name>/main.py` written
- [ ] `apps/<name>/README.md` written, including the MCP-usage block
- [ ] entry in `apps/launch.py` `PROCS`
- [ ] line in `start.sh`
- [ ] port mapping in `docker-compose.yml`
- [ ] env vars (if new) added to `apps/.env.example`
- [ ] entry in `ui/src/data/usecases.ts` with `mcpUsage` populated
- [ ] wiring test entries for any non-LLM endpoints
- [ ] `docker compose build apps ui && docker compose up -d apps ui`
- [ ] `make test` passes

---

## Patterns to follow

When in doubt, copy from a similar existing app:

| If your app is… | Copy from |
|---|---|
| pure MCP, single-server, single `/ask` endpoint | `web_researcher`, `paper_scout`, `code_reviewer` |
| pure MCP, multiple servers | `travel_planner`, `hiking_research` |
| MCP + inline session state | `movie_recommender`, `voice_journal` |
| MCP + heavy app-specific logic | `ibm_cloud_advisor`, `box_qa` |
| no MCP — purely app-state | `smart_todo`, `api_doc_gen` |
| event-driven (cron, file watcher, polling) | `newsletter`, `drop_summarizer`, `stock_alert` |

The full list is in [the umbrella UI](http://localhost:3001) (Tools column
shows what each app uses).
