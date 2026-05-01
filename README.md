# agent-apps

A showcase of conversational and pipeline apps built on **CUGA** — a planner /
executor agent runtime. Each app is a single-file FastAPI server wrapping a
`CugaAgent` with a tool list and a system prompt; the right-hand panel of every
app shows live structured state pushed from the agent.

There are 25+ apps in [cuga-apps/apps/](cuga-apps/apps/), spanning personal
productivity (movie recommender, recipe composer, smart todo), enterprise
(code reviewer, IBM cloud advisor, deck forge), event-driven pipelines
(newsletter, drop summarizer), and more. They share 7 hosted MCP servers
(`web`, `knowledge`, `geo`, `finance`, `code`, `local`, `text`) for
generic capabilities, and define inline `@tool`s for their own state.

## Live demo

The full umbrella UI — every app, with launch buttons — is at
**[http://m3bench.vpc.cloud9.ibm.com:3001/](http://m3bench.vpc.cloud9.ibm.com:3001/)**.
Filter by **✦ Ship-ready** to see the polished demo set.

---

## Hosted MCP servers

7 MCP servers are deployed publicly on IBM Code Engine and can be reached
from any CUGA app — no auth, just point at the URL. URL pattern:

```
https://cuga-apps-mcp-<NAME>.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
```

| Server | Endpoint | What it does |
|---|---|---|
| `web` | [cuga-apps-mcp-web.…/mcp](https://cuga-apps-mcp-web.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | `web_search` (Tavily), `fetch_webpage`, `fetch_feed`, YouTube transcripts |
| `knowledge` | [cuga-apps-mcp-knowledge.…/mcp](https://cuga-apps-mcp-knowledge.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | Wikipedia, arXiv, Semantic Scholar |
| `geo` | [cuga-apps-mcp-geo.…/mcp](https://cuga-apps-mcp-geo.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | `geocode`, `get_weather`, `find_hikes`, `search_attractions` |
| `finance` | [cuga-apps-mcp-finance.…/mcp](https://cuga-apps-mcp-finance.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | `get_crypto_price` (CoinGecko), `get_stock_quote` (Alpha Vantage) |
| `code` | [cuga-apps-mcp-code.…/mcp](https://cuga-apps-mcp-code.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | `check_python_syntax`, `extract_code_metrics`, `detect_language` |
| `local` | [cuga-apps-mcp-local.…/mcp](https://cuga-apps-mcp-local.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | system metrics, processes, disk usage, audio transcription |
| `text` | [cuga-apps-mcp-text.…/mcp](https://cuga-apps-mcp-text.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp) | `chunk_text`, `count_tokens`, `extract_text` (PDF/DOCX/HTML → markdown) |

> An 8th server, `invocable_apis`, runs **local-only** — it needs Bird benchmark
> data bind-mounted from the host. Bring it up via `python apps/launch.py`.

A plain `GET` against a `/mcp` endpoint returns HTTP 406 — that's the
streamable-HTTP MCP endpoint rejecting a non-MCP request. Use the bridge
in [`cuga_external_app_spec.md`](cuga_external_app_spec.md) (or
`load_tools(["web", "knowledge", …])` from inside the
[cuga-apps repo](cuga-apps/apps/_mcp_bridge.py)) to talk to them.

### Browse + invoke any tool — MCP Tool Explorer

The **MCP Tool Explorer** lets you list every hosted tool, see its arg
schema, and invoke it with a form — handy for sanity-checking a tool
before you wire it into an agent:

**[https://cuga-apps-mcp-tool-explorer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/](https://cuga-apps-mcp-tool-explorer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/)**

(Locally: `http://localhost:28900` after `python apps/launch.py`.)

---

## Quick start — try an app locally

Pick a small one. **Recipe Composer** is a good first bite: inline tools only,
no MCP servers required, no API keys beyond the LLM provider.

```bash
git clone <this-repo> && cd agent-apps/cuga-apps/apps/recipe_composer

pip install -r requirements.txt
pip install cuga

export LLM_PROVIDER=rits
export LLM_MODEL=gpt-oss-120b
export AGENT_SETTING_CONFIG=settings.rits.toml
export RITS_API_KEY=<>


python main.py --port 28820
# open http://127.0.0.1:28820
```

Type things like *"I have chicken, rice, and broccoli"*, *"I'm vegetarian"*,
or *"What can I cook tonight in under 25 minutes?"*. The pantry, diet, and
recipe cards on the right update as you chat.

For a heavier example with scheduled-pipeline behaviour, try
[**Newsletter Intelligence**](cuga-apps/apps/newsletter/) — it ingests RSS
feeds, deduplicates, scores, and emits a daily digest.

Every app has its own `README.md` with run instructions and example prompts.

---

## Create your own app

There is a single self-contained spec for building a CUGA app from scratch
against the hosted MCP servers — no need to clone the rest of this repo:

**[cuga_external_app_spec.md](cuga_external_app_spec.md)**

It includes the full LLM factory, MCP bridge, `main.py` template, `ui.py`
template, the tool envelope rule, and a definition-of-done checklist.

### Prompt for an LLM coding agent

Hand the spec to Claude (or any capable LLM) with a prompt like:

```
You are an expert in creating Cuga web applications using Cuga Agent.
Follow the spec here: /home/amurthi/work/cuga_external_app_spec.md

Create a new web app to <fill in what you want the app to do> that is
powered by Cuga Agent.
```

Replace the `<…>` with whatever you want the app to do — *"track my reading
list and recommend the next book based on what I've finished"*, *"summarise
the GitHub PRs I'm reviewing today"*, *"build a daily briefing for any
city"*, etc.

### A worked example

[apps/city_beat/](cuga-apps/apps/city_beat/) was built from this exact spec
— it composes 4 hosted MCP servers (`geo`, `web`, `knowledge`, `finance`)
with 6 inline session-state tools to assemble a one-screen city briefing.
Use it as a reference when in doubt about shape.

---

## Repo layout

```
agent-apps/
├── README.md                       you are here
├── cuga_external_app_spec.md       self-contained spec — point an LLM at this to build a new app
├── cuga-apps/                      the umbrella repo: 25+ apps, 8 MCP servers, the umbrella UI
│   ├── apps/                       one folder per app
│   ├── mcp_servers/                hosted MCP servers
│   ├── ui/                         the umbrella SPA (port 3001)
│   ├── HOW_TO_BUILD_AN_APP_FAST.md 10-minute in-repo build guide
│   ├── cuga_app_builder_spec.md    full in-repo build spec (MCP + inline)
│   └── CLOUD_ENGINE_DEPLOYMENT.md  CE deployment runbook
└── apps/                           legacy apps (predates the cuga-apps clone)
```
