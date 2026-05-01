# CUGA App Builder Spec — Standalone Edition

This spec is for **Claude** (or any LLM agent) tasked with building a new
CUGA-agent demo app **outside** the `cuga-apps` repo — on a developer's own
machine, in any directory — but whose deliverable must be drop-in compatible
with the `cuga-apps` repo so the maintainers can later integrate it without
rewriting anything.

If you have a clone of `cuga-apps` and are building inside it, read
[`cuga_app_builder_spec.md`](cuga_app_builder_spec.md) instead — that one
walks every per-repo wiring step.

---

## What "compatible artifact" means

The deliverable is a **single folder** containing the app. When the
maintainer drops it into `cuga-apps/apps/<your_app>/`, it must work after
**three small edits**:

1. Delete the local `_llm.py` shim (the repo already provides one at
   `apps/_llm.py`).
2. Add the port to `apps/_ports.py`, `apps/launch.py`, `start.sh`,
   `docker-compose.yml`, and `ui/src/data/usecases.ts`.
3. (Optional) Migrate any of your inline `@tool` defs that turn out to be
   generic-purpose to one of the existing MCP servers
   (`mcp-web`, `mcp-knowledge`, `mcp-geo`, `mcp-finance`, `mcp-code`,
   `mcp-local`, `mcp-text`, `mcp-invocable_apis`). Most apps keep all
   tools inline at delivery — that's fine.

To make the integration that small, **every file you ship must use the same
imports, the same path bootstrap, the same FastAPI shape, the same tool
return contract, and the same environment variables** that the in-repo apps
use. This spec gives you those exact patterns.

---

## What you're building

A single Python process that:

1. Wraps a `CugaAgent` (from `cuga.sdk`) with your tools + your system prompt.
2. Serves a self-contained dark-themed HTML UI from `/`.
3. Accepts `POST /ask` with `{question, thread_id}` and returns
   `{answer: "..."}`.
4. Has a `GET /health` endpoint returning `{ok: true}`.
5. Is configurable purely via env vars — no hardcoded provider, model, or
   API key.
6. Runs on its own port.

Your code is glue. Reasoning lives inside `CugaAgent`. The app is dumb.

---

## Prerequisites

Install the runtime deps. The CUGA SDK and your LLM provider's SDK.

```bash
# 1) The CUGA agent SDK — install from the cuga-agent repo (path will be
#    given to you by whoever assigned the task).
pip install -e /path/to/cuga-agent

# 2) Web framework + LLM client deps (kept minimal; one of these per
#    provider you actually use)
pip install fastapi uvicorn pydantic httpx langchain langchain-core
pip install langchain-anthropic   # only if LLM_PROVIDER=anthropic
pip install langchain-openai      # only if LLM_PROVIDER=openai
pip install langchain-ibm         # only if LLM_PROVIDER=watsonx
pip install langchain-ollama      # only if LLM_PROVIDER=ollama
pip install langchain-litellm     # only if LLM_PROVIDER=litellm
```

Verify the SDK is installed:

```python
python -c "from cuga.sdk import CugaAgent; print('OK')"
```

If that fails, the rest of the spec doesn't apply — fix the install first.

---

## Bundle structure (what you deliver)

A single folder. Pick a snake_case name that matches the app's purpose.

```
<your_app_name>/
├── main.py            REQUIRED — FastAPI + CugaAgent
├── ui.py              REQUIRED — exports _HTML
├── _llm.py            REQUIRED — multi-provider LLM factory (copy verbatim from cuga-apps/apps/_llm.py)
├── README.md          REQUIRED — described below
└── requirements.txt   REQUIRED — pinned deps
```

**Do not include**:
- `__init__.py` — apps are run as scripts, not imported.
- A Dockerfile or docker-compose.yml — packaging is handled at the cuga-apps repo level.
- React / Vue / Tailwind / external CSS — UI is one self-contained string.
- Tests — the maintainer will plug into the integration suite at integration time.
- A `.env` file with real keys — only `.env.example` if you want to document required vars.

---

## `_llm.py` — copy verbatim

This file already exists at `cuga-apps/apps/_llm.py`. Copy it into your
bundle without modification. It is the multi-provider LLM factory used by
all 24 in-repo apps. Supported providers: `rits`, `anthropic`, `openai`,
`watsonx`, `litellm`, `ollama`.

If you don't have access to the cuga-apps clone, ask the assigner for the
file. Do not rewrite it from scratch — divergence from the canonical version
is the fastest way to break integration.

The interface you rely on:

```python
from _llm import create_llm

llm = create_llm(provider="anthropic", model="claude-sonnet-4-6")
# or, with env vars set:
llm = create_llm(
    provider=os.getenv("LLM_PROVIDER"),
    model=os.getenv("LLM_MODEL"),
)
```

---

## `main.py` — canonical template

Copy this template, replace placeholders, and you have a runnable, drop-in
ready app. Every annotated detail below matters.

```python
"""
<App Name> — <one-line tagline>
==============================

<2–4 sentences: what it does, what data it uses, why it's interesting.>

Run:
    python main.py
    python main.py --port 28999
    python main.py --provider anthropic

Then open: http://127.0.0.1:28999

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL            model name override (provider-specific)
    AGENT_SETTING_CONFIG path to a CUGA settings TOML (e.g. settings.openai.toml)
    <APP_KEY>            <what this key gates>   (only if applicable)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ── Path bootstrap — REQUIRED, do not skip ───────────────────────────────
# Puts both the app dir and its parent on sys.path so:
#   from _llm import create_llm   resolves (standalone: same folder;
#                                  in-repo: parent apps/ folder)
#   from ui   import _HTML        resolves (always same folder)
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


# ── Tools — inline @tool defs only (no MCP in standalone) ────────────────
def _make_tools():
    from langchain_core.tools import tool

    # ----- Tool design rules (read these before writing the body) -----
    # 1. Return a JSON string (use json.dumps). Never raw dicts.
    # 2. The docstring is the LLM-readable spec. Be terse and concrete.
    # 3. Each arg is documented with type + meaning.
    # 4. On error, return {"ok": false, "error": "...", "code": "..."} as
    #    a JSON string. On success, {"ok": true, "data": ...}. This
    #    matches the cuga-apps MCP envelope shape, which means your
    #    inline tools can later be migrated to an MCP server with no
    #    callsite changes.
    # 5. Tools are pure functions of their args. No shared state.
    # 6. Read API keys at call time via os.getenv(...), not at import.
    #    Return {"ok": false, "code": "missing_key"} when missing.
    # ------------------------------------------------------------------

    @tool
    def example_search(query: str, n: int = 5) -> str:
        """Search <some source> for results matching the query.

        Args:
            query: Natural-language search string.
            n:     Max results to return (default 5).
        """
        if not query:
            return json.dumps({"ok": False, "error": "query is empty",
                               "code": "bad_input"})
        try:
            # ... do the actual call here ...
            results = [{"title": "...", "url": "..."}]
            return json.dumps({"ok": True, "data": {"results": results,
                                                     "count": len(results)}})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc),
                               "code": "upstream"})

    return [example_search]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# <App Name>

<One sentence describing the agent's identity.>

## Workflow
1. <Step 1 — which tool to call first and why>
2. <Step 2 — …>
3. <Synthesis instructions — how to combine results>

## Output format
<What the response should look like — be specific. The LLM follows this.>

## Rules
- <hard constraint 1>
- <hard constraint 2>
- Always cite source URLs in markdown link format.
- Never fabricate data the tools did not return.
"""


# ── Agent factory ────────────────────────────────────────────────────────
def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    # CUGA reads AGENT_SETTING_CONFIG to pick its internal settings TOML.
    # Default to a sensible per-provider TOML so the app boots without
    # ceremony. Use settings.openai.toml for openai-compatible providers.
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
    parser.add_argument("--port", type=int, default=28999)
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

**Why these specific shapes matter for compatibility:**

| Detail | Why |
|---|---|
| Path bootstrap with `_DIR` and `_DEMOS_DIR` | Lets `from _llm import create_llm` resolve in both standalone (same folder) and in-repo (parent `apps/` folder) without code change. |
| `from cuga.sdk import CugaAgent` | The canonical import. Older code uses `from cuga import CugaAgent`; do not. |
| `cuga_folder=str(_DIR / ".cuga")` | Per-app runtime state lives next to the app code. Same on disk, in or out of the repo. |
| `AGENT_SETTING_CONFIG` defaulted in `make_agent()` | Without it, CUGA uses `settings.openai.toml` and crashes if `OPENAI_API_KEY` is unset. |
| `AskReq` with `question` + `thread_id="default"` | Same shape every in-repo app uses; tests and clients can hit any app the same way. |
| `result = await agent.invoke(question, thread_id=...)` then `result.answer` | The CugaAgent return shape — don't unpack it differently. |
| `POST /ask`, `GET /health`, `GET /` (HTML) | Smoke and wiring tests in cuga-apps assume these exact routes exist. |
| Tools return JSON strings with `{ok, data}` / `{ok: false, error, code}` | Same envelope as the MCP servers. Migration to MCP later is a 1:1 move, not a rewrite. |

---

## `ui.py` — the page

Export a single string `_HTML` — a fully self-contained dark-themed HTML
page. Same conventions as the in-repo apps so your tile blends in.

Hard requirements:

- **Dark theme**: bg `#0f1117`, cards `#1a1a2e`, borders `#2d2d4a`, accent
  indigo `#6366f1`.
- **Sticky header** with app name + a live status badge.
- **Two-panel layout** — left: chat input + 6–10 clickable example prompt
  chips; right: rendered result card.
- **Vanilla JS only** — no React, Vue, Tailwind, or external CSS/JS.
- **Calls `POST /ask`** with `{question, thread_id}`; renders `answer` from
  the response.
- **No auto-refresh polling** unless your app has genuine background state
  (live ticker, file watcher, scheduled feed). Don't poll just to satisfy
  a checklist.

Minimum acceptable `_HTML`:

```python
_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>App Name</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 16px 24px;
    background: #1a1a2e;
    border-bottom: 1px solid #2d2d4a;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 700; }
  .badge { font-size: 12px; padding: 4px 10px; border-radius: 999px;
           background: #064e3b; color: #6ee7b7; }
  main { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
         padding: 16px; overflow: hidden; }
  .panel { background: #1a1a2e; border: 1px solid #2d2d4a; border-radius: 12px;
           padding: 16px; overflow-y: auto; }
  .panel h2 { margin: 0 0 12px 0; font-size: 14px; color: #94a3b8;
              text-transform: uppercase; letter-spacing: 0.06em; }
  textarea { width: 100%; min-height: 100px; resize: vertical;
             background: #0f1117; color: #e2e8f0; border: 1px solid #2d2d4a;
             border-radius: 8px; padding: 12px; font: inherit; }
  button { background: #6366f1; color: #fff; border: 0; border-radius: 8px;
           padding: 10px 16px; font-weight: 600; cursor: pointer; margin-top: 8px; }
  button:disabled { opacity: 0.5; cursor: wait; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; }
  .chip { font-size: 12px; padding: 6px 10px; border-radius: 999px;
          background: #0f1117; border: 1px solid #2d2d4a; color: #cbd5e1;
          cursor: pointer; }
  .chip:hover { border-color: #6366f1; color: #fff; }
  pre { white-space: pre-wrap; word-break: break-word; margin: 0;
        font: inherit; line-height: 1.5; }
</style>
</head>
<body>
<header>
  <h1>App Name</h1>
  <span class="badge" id="status">ready</span>
</header>
<main>
  <section class="panel">
    <h2>Ask</h2>
    <textarea id="q" placeholder="Ask the agent…"></textarea>
    <button id="send">Send</button>
    <div class="chips" id="examples">
      <span class="chip">Example prompt 1</span>
      <span class="chip">Example prompt 2</span>
      <span class="chip">Example prompt 3</span>
    </div>
  </section>
  <section class="panel">
    <h2>Result</h2>
    <pre id="out">—</pre>
  </section>
</main>
<script>
  const q = document.getElementById('q');
  const send = document.getElementById('send');
  const out = document.getElementById('out');
  const status = document.getElementById('status');
  document.querySelectorAll('.chip').forEach(c =>
    c.addEventListener('click', () => { q.value = c.textContent; q.focus(); }));
  async function ask() {
    const question = q.value.trim();
    if (!question) return;
    send.disabled = true; status.textContent = 'thinking…'; out.textContent = '…';
    try {
      const r = await fetch('/ask', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question, thread_id: 'default'}),
      });
      const j = await r.json();
      out.textContent = j.answer || j.error || '(no response)';
    } catch (e) {
      out.textContent = 'Network error: ' + e.message;
    } finally {
      send.disabled = false; status.textContent = 'ready';
    }
  }
  send.addEventListener('click', ask);
  q.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ask();
  });
</script>
</body>
</html>
"""
```

Replace "App Name" and the example chips with content for your app. That's
the entire `ui.py`.

---

## `requirements.txt` — pin the deps you actually use

Be conservative. Only list deps your code touches. The in-repo image already
has fastapi/uvicorn/pydantic/langchain installed, so on integration these
are no-ops; in standalone they're load-bearing.

```txt
# CUGA SDK installed separately via -e (see prerequisites). DO NOT pin a
# version here — the assigner controls which commit you target.

fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.0
httpx>=0.27
langchain-core>=0.3

# Pick exactly the providers your app supports (or all of them, if you
# want to defer the choice to the user). At least one must be present.
langchain-anthropic>=0.2     # for LLM_PROVIDER=anthropic
langchain-openai>=0.2        # for LLM_PROVIDER=openai
# langchain-ibm>=0.3
# langchain-ollama>=0.2
# langchain-litellm>=0.1

# App-specific deps (httpx is enough for most simple HTTP tools; only add
# more when you genuinely need them):
# beautifulsoup4>=4.12
# feedparser>=6.0
```

---

## `README.md` — required structure

```markdown
# <App Name>

<2–3 sentence description.>

**Port:** 28999 → http://localhost:28999  
**Status:** standalone · drop-in compatible with cuga-apps

## How it works

1. <Step the agent takes>
2. <…>

## Run

\`\`\`bash
pip install -r requirements.txt
pip install -e /path/to/cuga-agent       # if not already installed

export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...
# Optional, only if your tools require keys:
# export <YOUR_TOOL_KEY>=...

python main.py --port 28999
# open http://127.0.0.1:28999
\`\`\`

## Environment variables

| Var | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | yes | Model name |
| `AGENT_SETTING_CONFIG` | yes (defaulted) | Path to CUGA settings TOML; defaulted per-provider in `make_agent()`. |
| `<APP_KEY>` | conditional | <what this gates> |

## Example prompts

- "<example 1>"
- "<example 2>"
- "<example 3>"

## Tools

Inline `@tool` defs in `main.py`:
- `tool_a` — <one-line description>
- `tool_b` — <one-line description>

(See "Integration into cuga-apps" for the migration plan if any of these
should become MCP tools.)

## Integration into cuga-apps

When merging into `cuga-apps`:

1. Move this folder to `cuga-apps/apps/<app_name>/`.
2. Delete the local `_llm.py` (the repo provides one at `apps/_llm.py`).
3. Add the port to `apps/_ports.py`, `apps/launch.py`, `start.sh`,
   `docker-compose.yml`, `ui/src/data/usecases.ts`.
4. (Optional) Promote any of these inline tools to MCP if they're general-
   purpose: <list which ones, if any, are candidates>.
```

---

## Migrating tools to MCP later (planning ahead)

You ship inline `@tool` defs only. The maintainer may decide to promote
some of them to existing MCP servers at integration time. To make that a
clean swap, follow these rules now:

- **Same envelope.** Inline tools return JSON strings of
  `{"ok": true, "data": ...}` or `{"ok": false, "error": "...", "code": "..."}`.
  This is the exact contract MCP tools follow. Migration becomes a copy.
- **Pure functions.** Inline tool body must depend only on its arguments
  and `os.getenv(...)` — no closure over per-app state. State-coupled tools
  cannot move to MCP.
- **Standard error codes.** Use `bad_input`, `not_found`, `missing_key`,
  `upstream` for the `code` field — those are the codes the in-repo MCP
  servers use, and the cuga-apps tests assert against them.
- **HTTP outbound through `httpx`** with explicit `timeout` and a
  `User-Agent` header — same posture as `mcp_servers/_core/http.py`.

If a tool is truly app-specific (touches a SQLite the app owns, mutates an
inbox folder, holds session state), it stays inline forever. That's fine —
several in-repo apps do this (`smart_todo`, `deck_forge`, `api_doc_gen`).

---

## Anti-patterns — what NOT to do

These mistakes break compatibility and force the integrator to rewrite your
code. Don't.

- **Don't hardcode a provider, model, or API key.** Read every credential
  from `os.getenv(...)`. The user picks via env vars or `--provider`.
- **Don't return raw dicts from inline `@tool` defs.** Tools return
  `json.dumps(...)`. The agent silently mishandles dicts.
- **Don't skip the path bootstrap.** Without it, `_llm` resolution breaks
  on integration.
- **Don't import `from cuga import CugaAgent`.** The canonical import is
  `from cuga.sdk import CugaAgent`.
- **Don't use `asyncio.get_event_loop()`** anywhere. Python 3.13 dropped
  its auto-create. For background tasks, schedule from inside
  `@app.on_event("startup")` via `asyncio.create_task(...)`.
- **Don't add a Dockerfile, docker-compose.yml, or ./Makefile.** Packaging
  is the cuga-apps repo's job.
- **Don't include node_modules / a React build / Tailwind / external JS.**
  UI is one self-contained `_HTML` string.
- **Don't pre-validate env vars at boot.** A missing tool key should not
  crash the app. The matching tool returns `missing_key`; the agent
  surfaces it. The app stays up with partial config.
- **Don't auto-refresh the UI** (10s/15s polling) unless the app has
  genuine background state.
- **Don't write tests in the bundle.** The maintainer will plug into the
  cuga-apps integration suite at integration time. If you want a sanity
  check during dev, use a separate `scratch_test.py` outside the bundle
  and remove it before delivery.
- **Don't depend on packages outside `requirements.txt`.** The integrator
  builds the apps Docker image from the cuga-apps `requirements.apps.txt`
  plus a per-app `requirements.txt` if you ship one. Anything you don't
  list will silently break.
- **Don't write a different system prompt every time.** Pin it in `_SYSTEM`.
  Tweak there. Don't compose prompts dynamically per request unless you
  have a specific reason — the integration test suite assumes prompts are
  static.
- **Don't change the CugaAgent constructor signature** (the keyword args
  `model`, `tools`, `special_instructions`, `cuga_folder`). Use exactly
  these four.

---

## Quick path: how a fresh standalone build looks

A useful sanity check — if your build can do all six steps below, it'll
integrate cleanly.

```bash
# 1. Create the bundle
mkdir my_app && cd my_app

# 2. Drop in the four files
#    main.py, ui.py, _llm.py, README.md, requirements.txt

# 3. Install
pip install -e /path/to/cuga-agent
pip install -r requirements.txt

# 4. Configure
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...

# 5. Run
python main.py --port 28999

# 6. Verify
curl http://localhost:28999/health
# → {"ok": true}

curl -X POST http://localhost:28999/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"<an example prompt>","thread_id":"default"}'
# → {"answer": "<real, non-empty response from the agent>"}

open http://localhost:28999    # UI loads, dark theme, chat works
```

---

## Definition of done

Before delivering the bundle, every box must check:

- [ ] Bundle is one folder; matches the structure above; no extra files
- [ ] `main.py` follows the canonical template — same imports, same path
      bootstrap, same `make_agent()`, same `AskReq`, same routes (`POST /ask`,
      `GET /health`, `GET /`)
- [ ] `ui.py` exports `_HTML`; dark theme; vanilla JS; calls `POST /ask`
      with `{question, thread_id}`; renders `answer`
- [ ] `_llm.py` is a verbatim copy of `cuga-apps/apps/_llm.py`
- [ ] `requirements.txt` lists only what `main.py` actually imports
- [ ] `README.md` documents port, env vars, 3+ example prompts, the tool
      list, and the integration steps
- [ ] No hardcoded provider, model, or API key anywhere in `main.py`
- [ ] All inline `@tool` defs return JSON strings of `{ok, data}` /
      `{ok: false, error, code}` envelopes
- [ ] All tools document their args in the docstring
- [ ] Standalone bring-up works: `python main.py --port <port>` →
      `/health` returns ok, `/ask` returns a real agent response, UI loads
- [ ] Bundle is the agent + UI + LLM factory only — no Dockerfile,
      compose file, tests, or React build

---

## TL;DR — for the impatient agent

1. Make `<your_app>/` with five files: `main.py`, `ui.py`, `_llm.py`,
   `README.md`, `requirements.txt`.
2. Copy `_llm.py` verbatim from `cuga-apps/apps/_llm.py`.
3. Copy the `main.py` template above. Replace placeholders. Write your
   tools as inline `@tool` defs that return `{ok, data}` JSON strings.
4. Copy the `ui.py` `_HTML` template. Replace name + chips.
5. Pin deps in `requirements.txt`.
6. Verify standalone: `python main.py --port <port>`; `/health` ok; `/ask`
   returns real agent text; UI works in browser.
7. Ship the folder.
