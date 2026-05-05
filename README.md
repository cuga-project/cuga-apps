# cuga-apps

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
### Browse + invoke any tool — MCP Tool Explorer

The **MCP Tool Explorer** lets you list every hosted tool, see its arg
schema, and invoke it with a form — handy for sanity-checking a tool
before you wire it into an agent:

**[https://cuga-apps-mcp-tool-explorer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/](https://cuga-apps-mcp-tool-explorer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/)**

(Locally: `http://localhost:28900` after `python apps/launch.py`.)

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

### Point an app at the hosted MCP servers

The bridge in [`cuga-apps/apps/_mcp_bridge.py`](cuga-apps/apps/_mcp_bridge.py)
resolves each MCP server URL in this order: `MCP_<NAME>_URL` env var → Code
Engine → docker compose DNS → `localhost`. So you have two knobs:

**All servers → CE** (the common case — run an app on your laptop, hit the
hosted MCPs):

```bash
export CUGA_TARGET=ce
python apps/launch.py travel_planner
```

This rewrites every `load_tools([...])` lookup to
`https://cuga-apps-mcp-<name>.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp`.
If your CE project hash or region differs, also set `CE_SUBDOMAIN=<hash>`
and/or `CE_REGION=<region>`.

**One server only** (e.g. mix local `web` with CE `knowledge`): set
`MCP_<NAME>_URL` — it always wins over the defaults. The URL must end in
`/mcp`:

```bash
export MCP_KNOWLEDGE_URL=https://cuga-apps-mcp-knowledge.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
```

Valid names: `web`, `knowledge`, `geo`, `finance`, `code`, `local`, `text`,
`invocable_apis`.


---

## Quick start — try an app locally

Pick a small one. **Recipe Composer** is a good first bite: inline tools only,
no MCP servers required, no API keys beyond the LLM provider.

```bash
git clone <this-repo> && cd agent-apps/cuga-apps/apps/recipe_composer

pip install -r requirements.txt
pip install cuga
```

Then export credentials for **one** LLM provider — RITS or watsonx:

```bash
# Option A — RITS (IBM Research inference)
export LLM_PROVIDER=rits
export LLM_MODEL=gpt-oss-120b
export RITS_API_KEY=<your-rits-key>

# Option B — watsonx
export LLM_PROVIDER=watsonx
export LLM_MODEL=meta-llama/llama-3-3-70b-instruct
export WATSONX_APIKEY=<your-watsonx-key>
export WATSONX_PROJECT_ID=<your-project-id>     # or WATSONX_SPACE_ID
```

`AGENT_SETTING_CONFIG` is auto-defaulted to `settings.<provider>.toml` so
you don't need to set it explicitly. Then:

```bash
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

## Run any ship-ready app locally

Each app folder has its own `requirements.txt` listing exactly what that
app imports, so you can install **only the deps for the one app you want**.
The table below pairs every ship-ready app with its `cd` + `pip install` +
launch command — copy a row, paste into your shell, done.

If you'd rather install once and switch between many apps without
reinstalling, the umbrella file covers every app at once:

```bash
cd cuga-apps && pip install -r requirements.apps.txt && pip install cuga
```

Set your LLM credentials once in your shell — every app inherits these.
Pick **one** of the two provider blocks:

```bash
# Option A — RITS
export LLM_PROVIDER=rits
export LLM_MODEL=gpt-oss-120b
export RITS_API_KEY=<your-rits-key>

# Option B — watsonx
export LLM_PROVIDER=watsonx
export LLM_MODEL=meta-llama/llama-3-3-70b-instruct
export WATSONX_APIKEY=<your-watsonx-key>
export WATSONX_PROJECT_ID=<your-project-id>     # or WATSONX_SPACE_ID
```

```bash
export CUGA_TARGET=ce        # use the hosted MCP servers — Tavily,
                             # OpenTripMap, etc. keys already live on CE,
                             # so your laptop doesn't need them
```

(`AGENT_SETTING_CONFIG` is auto-defaulted to `settings.<provider>.toml` per
provider, so you don't need to set it.)

The 16 ship-ready apps. Server names in the **MCP servers** column link to
the [Hosted MCP servers](#hosted-mcp-servers) table above, which lists every
server's Code Engine `/mcp` endpoint. The **Setup + run** column assumes
you're at the repo root and that `cuga` is already installed (`pip install
cuga`):

| App | MCP servers | Setup + run | Notes |
|---|---|---|---|
| [Recipe Composer](cuga-apps/apps/recipe_composer) | — (inline only) | `cd cuga-apps/apps/recipe_composer && pip install -r requirements.txt && python main.py --port 28820` | inline tools only — no MCP needed |
| [Stock & Crypto Alert](cuga-apps/apps/stock_alert) | [finance](#hosted-mcp-servers) | `cd cuga-apps/apps/stock_alert && pip install -r requirements.txt && python main.py --port 28801` | Alpha Vantage key pasted in browser per session |
| [Server Monitor](cuga-apps/apps/server_monitor) | [local](#hosted-mcp-servers) | `cd cuga-apps/apps/server_monitor && pip install -r requirements.txt && python main.py --port 28767` | optional `CPU_THRESHOLD` / `RAM_THRESHOLD` overrides |
| [Newsletter Intelligence](cuga-apps/apps/newsletter) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/newsletter && pip install -r requirements.txt && python main.py --port 28793` | |
| [Web Researcher](cuga-apps/apps/web_researcher) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/web_researcher && pip install -r requirements.txt && python main.py --port 28798` | |
| [Travel Planner](cuga-apps/apps/travel_planner) | [web](#hosted-mcp-servers), [knowledge](#hosted-mcp-servers), [geo](#hosted-mcp-servers) | `cd cuga-apps/apps/travel_planner && pip install -r requirements.txt && python main.py --port 28090` | |
| [YouTube Research](cuga-apps/apps/youtube_research) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/youtube_research && pip install -r requirements.txt && python main.py --port 28803` | |
| [Architecture Diagram](cuga-apps/apps/arch_diagram) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/arch_diagram && pip install -r requirements.txt && python main.py --port 28804` | |
| [Hiking Research](cuga-apps/apps/hiking_research) | [geo](#hosted-mcp-servers), [web](#hosted-mcp-servers) | `cd cuga-apps/apps/hiking_research && pip install -r requirements.txt && python main.py --port 28805` | |
| [Movie Recommender](cuga-apps/apps/movie_recommender) | [knowledge](#hosted-mcp-servers) | `cd cuga-apps/apps/movie_recommender && pip install -r requirements.txt && python main.py --port 28806` | |
| [Webpage Summarizer](cuga-apps/apps/webpage_summarizer) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/webpage_summarizer && pip install -r requirements.txt && python main.py --port 28071` | |
| [Paper Scout](cuga-apps/apps/paper_scout) | [knowledge](#hosted-mcp-servers) | `cd cuga-apps/apps/paper_scout && pip install -r requirements.txt && python main.py --port 28808` | |
| [Wiki Dive](cuga-apps/apps/wiki_dive) | [knowledge](#hosted-mcp-servers) | `cd cuga-apps/apps/wiki_dive && pip install -r requirements.txt && python main.py --port 28809` | |
| [IBM Cloud Advisor](cuga-apps/apps/ibm_cloud_advisor) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/ibm_cloud_advisor && pip install -r requirements.txt && python main.py --port 28812` | |
| [IBM Docs Q&A](cuga-apps/apps/ibm_docs_qa) | [web](#hosted-mcp-servers) | `cd cuga-apps/apps/ibm_docs_qa && pip install -r requirements.txt && python main.py --port 28813` | |
| [City Beat](cuga-apps/apps/city_beat) | [geo](#hosted-mcp-servers), [web](#hosted-mcp-servers), [knowledge](#hosted-mcp-servers), [finance](#hosted-mcp-servers) | `cd cuga-apps/apps/city_beat && pip install -r requirements.txt && python main.py --port 28821` | mixes 4 hosted MCPs + 7 inline session tools |

After running the command, open `http://127.0.0.1:<port>` in your browser.
The pip step is idempotent — if you already installed the deps for an
earlier app, it'll be a no-op for any overlapping packages.

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

### Apps that mix hosted MCP tools with inline `@tool`s

The common pattern is **MCP for generic, stateless capabilities** (web
search, geocoding, weather, finance quotes, Wikipedia) and **inline
`@tool`s for app-specific session state** that mutates a Python dict and
triggers the right-panel UI to re-render. Concatenate both lists and pass
to the agent as `tools=mcp_tools + [inline_tool_a, inline_tool_b, ...]`.

| App | MCP servers (from CE) | Inline `@tool`s | What the inline tools do |
|---|---|---|---|
| [city_beat](cuga-apps/apps/city_beat/main.py) | geo, web, knowledge, finance | 7 | current city, focus topics, watchlist, crypto ticker, save briefing |
| [server_monitor](cuga-apps/apps/server_monitor/main.py) | local | 5 | thresholds, alerts, watchlist, snapshot persistence |
| [voice_journal](cuga-apps/apps/voice_journal/main.py) | local | 3 | save entry, summarize, mood tracking |
| [movie_recommender](cuga-apps/apps/movie_recommender/main.py) | knowledge | 3 | watchlist, ratings, preferences |
| [trip_designer](cuga-apps/apps/trip_designer/main.py) | web, knowledge, geo | 1 | save itinerary |
| [brief_budget](cuga-apps/apps/brief_budget/main.py) | web, knowledge | 1 | budget state |
| [ibm_cloud_advisor](cuga-apps/apps/ibm_cloud_advisor/main.py) | web | 1 | save recommendation |

[city_beat](cuga-apps/apps/city_beat/main.py) is the cleanest reference —
see [city_beat/main.py:104](cuga-apps/apps/city_beat/main.py#L104) for the
`load_tools([...])` call and
[city_beat/main.py:108-225](cuga-apps/apps/city_beat/main.py#L108-L225)
for the inline `@tool` defs.

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
