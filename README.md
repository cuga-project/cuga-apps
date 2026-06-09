# cuga-apps

**Real agentic apps you can read in one sitting, built on [CUGA](https://cuga.dev).**

The model is rarely the hard part of an agent. The work is wiring up tools,
holding state together across a long task, adding guardrails, and growing from
one agent to several without a rewrite. **CUGA** — the **C**onfigurable
**G**eneralist **A**gent, an open-source harness from IBM Research
(`pip install cuga`) — handles that plumbing, so the part you write shrinks to
**a tool list and a system prompt**. It plans before it acts, executes with a
mix of tool calls and generated code, holds intermediate state across a long
run, and self-corrects — the machinery behind **#1 on
[AppWorld](https://appworld.dev/) and [WebArena](https://webarena.dev/)**.

**cuga-apps** is what that feels like in practice: **35 apps** in
[cuga-apps/apps/](cuga-apps/apps/) (**27 deployable · 21 showcase**), each a
single-file FastAPI server wrapping one `CugaAgent` with a tool list and a
system prompt. The right-hand panel of every app shows live structured state the
agent pushes as it works. If you've written a FastAPI route, you can read every
line.

> **Heads up — the real catalog is the *inner* [`cuga-apps/`](cuga-apps/)
> directory**, not the repo root. Apps live in
> [`cuga-apps/apps/`](cuga-apps/apps/); the outer root is just the wrapper and
> this README.

## Three ways in

- **Try one in the browser** — the [live gallery](https://cuga-apps-ui.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/)
  tiles every app behind a launch button; no install. Filter by **✦ Showcase**
  for the polished set.
- **Run it all locally** — one `docker compose up` brings up the whole stack
  ([below](#run-everything-locally-with-docker)); or run a single app from source.
- **Build your own** — point an LLM coding agent at
  [`cuga_external_app_spec.md`](cuga_external_app_spec.md) and describe the app
  you want ([below](#create-your-own-app)).

---

## What's in the catalog

Once you've read one app you've read them all — they share the skeleton; only the
tools and the prompt change. They fan out across families, so whatever you're
building, one already exercises the piece you need:

- **Research & knowledge** — [Paper Scout](cuga-apps/apps/paper_scout) (arXiv +
  Semantic Scholar, ranked by citations), [Wiki Dive](cuga-apps/apps/wiki_dive)
  and [Web Researcher](cuga-apps/apps/web_researcher) (cited synthesis),
  [YouTube Research](cuga-apps/apps/youtube_research) (from transcripts),
  [Webpage Summarizer](cuga-apps/apps/webpage_summarizer),
  [GitHub Trending](cuga-apps/apps/github_trending),
  [AI Labs News](cuga-apps/apps/ai_labs_news).
- **Everyday & local** — [Travel Planner](cuga-apps/apps/travel_planner)
  (multi-day itinerary), [City Beat](cuga-apps/apps/city_beat) (daily city
  briefing), [Recipe Composer](cuga-apps/apps/recipe_composer) (pantry-driven),
  [Movie Recommender](cuga-apps/apps/movie_recommender),
  [Hiking Research](cuga-apps/apps/hiking_research),
  [Find a Doctor](cuga-apps/apps/find_a_doctor) (OSM + reviews),
  [Meetup Finder](cuga-apps/apps/meetup_finder) (browser-driven events),
  [Smart Todo](cuga-apps/apps/smart_todo).
- **Content & pipelines** — [Newsletter Intelligence](cuga-apps/apps/newsletter)
  (RSS → scored daily digest), [Architecture Diagram](cuga-apps/apps/arch_diagram),
  [Deck Forge](cuga-apps/apps/deck_forge),
  [API Doc Gen](cuga-apps/apps/api_doc_gen).
- **Documents & media Q&A** — [Box Q&A](cuga-apps/apps/box_qa),
  [Drop Summarizer](cuga-apps/apps/drop_summarizer),
  [Video Q&A](cuga-apps/apps/video_qa),
  [Voice Journal](cuga-apps/apps/voice_journal) — ingest PDFs / audio / video and
  answer over them with RAG.
- **Ops & alerts** — [Server Monitor](cuga-apps/apps/server_monitor) (live system
  metrics + thresholds), [Stock & Crypto Alert](cuga-apps/apps/stock_alert)
  (market prices).
- **IBM stack** — [IBM Cloud Advisor](cuga-apps/apps/ibm_cloud_advisor)
  (recommends real catalog services), [IBM Docs Q&A](cuga-apps/apps/ibm_docs_qa),
  [IBM What's New](cuga-apps/apps/ibm_whats_new).
- **Developer & eval** — [Code Reviewer](cuga-apps/apps/code_reviewer),
  [BIRD Invocable API](cuga-apps/apps/bird_invocable_api_creator).
- **Multi-agent** — [Ouroboros](cuga-apps/apps/ouroboros), a seven-specialist
  lead-gen system under a `CugaSupervisor` — open this one for the multi-agent
  shape.

The full, filterable list with launch buttons is in the
[live gallery](https://cuga-apps-ui.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/);
every app folder also has its own `README.md` with run instructions and example
prompts.

## The shape of every app

The whole agent is four arguments:

```python
return CugaAgent(
    model=create_llm(provider=os.getenv("LLM_PROVIDER"), model=os.getenv("LLM_MODEL")),
    tools=_make_tools(),                 # MCP tools + inline @tools
    special_instructions=_SYSTEM,        # the procedure, written as ordered steps
    cuga_folder=str(_DIR / ".cuga"),     # state + policies live here
)
```

Two conventions do the heavy lifting:

- **MCP for generic capabilities, inline `@tool`s for app state.** Stateless
  primitives (web search, Wikipedia/arXiv, geocoding, weather, finance quotes)
  come from shared MCP servers via `load_tools(["web", ...])` — you host nothing.
  Anything specific to the app is a normal Python function whose docstring tells
  the agent when to call it. Concatenate both: `tools=mcp_tools + [my_tool, ...]`.
- **Every tool returns the same envelope** —
  `{"ok": true, "data": {...}}` on success, `{"ok": false, "code": "...",
  "error": "..."}` on failure. CUGA's planner recovers from a *declared* failure
  ("geocoding returned nothing — skip that section and keep going") and derails
  on a raw stack trace. Boring, but load-bearing.

State is a per-`thread_id` Python dict that only the agent writes to, through its
tools; the live panel polls it and redraws the moment a tool fires. No database.

---

## Run everything locally with Docker

One command brings up the whole stack — **the umbrella UI + all 21 showcase apps
+ the MCP servers they need** — in a single container on port 8080:

```bash
cd build
cp .env.example .env          # set your LLM provider + key; add TAVILY_API_KEY /
                              # OPENTRIPMAP_API_KEY / ALPHA_VANTAGE_API_KEY for the
                              # apps that use them
docker compose up --build     # first build is large (cuga + Chromium + MCP deps)
# open http://localhost:8080
```

The umbrella UI loads at `/`; click any showcase app — it opens at `/a/<app>/`
and works end-to-end (chat → agent → live panel), all on port 8080. A missing
optional key just degrades the apps that need it (that tool returns a clear
"missing key" error) — the environment still comes up. The same image deploys to
Code Engine as one microservice; see [`build/README.md`](build/README.md).

## Run a single app from source

Pick a small one. **Recipe Composer** is a good first bite: inline tools only, no
MCP servers required, no API keys beyond the LLM provider.

> Use **Python 3.13** — `cuga` requires `>=3.10,<3.14` (3.14 is unsupported). The
> cleanest setup is a `uv` venv on 3.13.

```bash
git clone https://github.com/cuga-project/cuga-apps
cd cuga-apps/cuga-apps/apps/recipe_composer

uv venv --python 3.13 .venv && source .venv/bin/activate
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

`AGENT_SETTING_CONFIG` is auto-defaulted to `settings.<provider>.toml`, so you
don't need to set it. Then:

```bash
python main.py --port 28820
# open http://127.0.0.1:28820
```

Type *"I have chicken, rice, and broccoli"* or *"What can I cook tonight in under
25 minutes?"* — the pantry, diet, and recipe cards on the right update as the
agent works.

### Run the whole stack from source (`launch.py`)

To bring up **all 8 MCP servers + every app + the usage dashboard** at once
(needed for the MCP-backed apps) without Docker, use the launcher:

```bash
cd cuga-apps
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -r requirements.apps.txt -r requirements.mcp.txt   # cuga + every app + MCP deps
# heavy extras (only if you want video_qa / deck_forge): uv pip install -r requirements.apps.heavy.txt
# meetup_finder's browser: python -m playwright install chromium

cd apps
export CUGA_TARGET=ce                 # use the hosted MCP servers — their keys
                                      # (Tavily, OpenTripMap, …) already live on CE,
                                      # so your laptop doesn't need them
python launch.py                      # start everything
python launch.py status               # see what's up
python launch.py kill --ship-ready    # free the ports of just the 21 showcase apps
python launch.py stop                 # stop everything it started
```

Set your LLM credentials once in the shell (one of the two provider blocks above)
— every app inherits them. `launch.py` spawns each app with the interpreter that
has `cuga`; if you run it from a Python that lacks cuga, it **auto-detects a
sibling `.venv`** (printing a `[PYTHON] …` line) — or set
`CUGA_PYTHON=/path/to/venv/bin/python` to force one.

### Run a specific showcase app on its own

Each app folder has its own `requirements.txt` listing exactly what that app
imports, so you can install **only the deps for the one app you want**. The table
pairs every showcase app with its `cd` + `pip install` + launch command — copy a
row, paste into your shell, done. Server names in the **MCP servers** column link
to the [Hosted MCP servers](#hosted-mcp-servers) table. Assumes you're at the
repo root with `cuga` installed (`pip install cuga`):

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
| [GitHub Trending](cuga-apps/apps/github_trending) | — (inline only) | `cd cuga-apps/apps/github_trending && pip install -r requirements.txt && python main.py --port 28823` | keyless (GitHub REST); optional `GITHUB_TOKEN` raises rate limit |
| [AI Labs News](cuga-apps/apps/ai_labs_news) | — (inline only) | `cd cuga-apps/apps/ai_labs_news && pip install -r requirements.txt && python main.py --port 28824` | keyless; reads each lab's RSS/Atom feed |
| [Find a Doctor](cuga-apps/apps/find_a_doctor) | — (inline only) | `cd cuga-apps/apps/find_a_doctor && pip install -r requirements.txt && python main.py --port 28825` | keyless; OSM (Nominatim/Overpass) + DuckDuckGo reviews |
| [Ouroboros](cuga-apps/apps/ouroboros) | — (inline only) | `cd cuga-apps/apps/ouroboros && pip install -r requirements.txt && python main.py --port 28822` | multi-agent (CugaSupervisor + 7 specialists); watsonx; give it `APP_MEM=4G` |
| [Meetup Finder](cuga-apps/apps/meetup_finder) | — (inline + Playwright) | `cd cuga-apps/apps/meetup_finder && pip install -r requirements.txt && python -m playwright install chromium && python main.py --port 28826` | browser-driven (Meetup/Luma/Eventbrite); needs Chromium |

Open `http://127.0.0.1:<port>` after launch. The pip step is idempotent — if you
already installed an earlier app's deps, overlapping packages are a no-op.

---

## Create your own app

There is a single self-contained spec for building a CUGA app from scratch
against the hosted MCP servers — no need to clone the rest of this repo:

**[`cuga_external_app_spec.md`](cuga_external_app_spec.md)**

It includes the full LLM factory, MCP bridge, `main.py` template, `ui.py`
template, the tool-envelope rule, and a definition-of-done checklist. (Building
*inside* the repo instead? See
[`docs/HOW_TO_BUILD_AN_APP_FAST.md`](cuga-apps/docs/HOW_TO_BUILD_AN_APP_FAST.md)
and [`docs/ADDING_AN_APP.md`](cuga-apps/docs/ADDING_AN_APP.md).)

### Prompt for an LLM coding agent

Hand the spec to Claude (or any capable LLM) with a prompt like:

```
You are an expert in creating Cuga web applications using Cuga Agent.
Follow the spec here: <path to> cuga_external_app_spec.md

Create a new web app to <fill in what you want the app to do> that is
powered by Cuga Agent.
```

Replace the `<…>` with whatever you want — *"track my reading list and recommend
the next book based on what I've finished"*, *"summarise the GitHub PRs I'm
reviewing today"*, *"build a daily briefing for any city"*. A few apps in this
repo were generated exactly this way — regular enough for a model to reproduce
means regular enough for you to learn.

### A worked example

[`apps/city_beat/`](cuga-apps/apps/city_beat/) was built from this exact spec —
it composes 4 hosted MCP servers (`geo`, `web`, `knowledge`, `finance`) with 7
inline session-state tools to assemble a one-screen city briefing. See
[city_beat/main.py:104](cuga-apps/apps/city_beat/main.py#L104) for the
`load_tools([...])` call and
[main.py:108-225](cuga-apps/apps/city_beat/main.py#L108-L225) for the inline
`@tool` defs. The common split — **MCP for generic, stateless capabilities;
inline `@tool`s for app-specific session state** — shows up across the catalog:

| App | MCP servers (from CE) | Inline `@tool`s | What the inline tools do |
|---|---|---|---|
| [city_beat](cuga-apps/apps/city_beat/main.py) | geo, web, knowledge, finance | 7 | current city, focus topics, watchlist, crypto ticker, save briefing |
| [server_monitor](cuga-apps/apps/server_monitor/main.py) | local | 5 | thresholds, alerts, watchlist, snapshot persistence |
| [voice_journal](cuga-apps/apps/voice_journal/main.py) | local | 3 | save entry, summarize, mood tracking |
| [movie_recommender](cuga-apps/apps/movie_recommender/main.py) | knowledge | 3 | watchlist, ratings, preferences |
| [trip_designer](cuga-apps/apps/trip_designer/main.py) | web, knowledge, geo | 1 | save itinerary |
| [ibm_cloud_advisor](cuga-apps/apps/ibm_cloud_advisor/main.py) | web | 1 | save recommendation |

---

## Hosted MCP servers

8 MCP server packages exist; 7 are deployed publicly on IBM Code Engine and can
be reached from any CUGA app — no auth, just point at the URL:

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

> An 8th server, `invocable_apis`, runs **local-only** — it needs BIRD benchmark
> data bind-mounted from the host. Bring it up via `python apps/launch.py`.

A plain `GET` against a `/mcp` endpoint returns HTTP 406 — that's the
streamable-HTTP MCP endpoint rejecting a non-MCP request. Use the bridge in
[`cuga_external_app_spec.md`](cuga_external_app_spec.md) (or
`load_tools(["web", "knowledge", …])` from
[`apps/_mcp_bridge.py`](cuga-apps/apps/_mcp_bridge.py)) to talk to them.

### Browse + invoke any tool — MCP Tool Explorer

The **MCP Tool Explorer** lists every hosted tool, shows its arg schema, and
invokes it from a form — handy for sanity-checking a tool before you wire it into
an agent:
**[Tool Explorer ↗](https://cuga-apps-mcp-tool-explorer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/)**
(locally: `http://localhost:28900` after `python apps/launch.py`).

### Point an app at the hosted MCP servers

The bridge in [`apps/_mcp_bridge.py`](cuga-apps/apps/_mcp_bridge.py) resolves each
MCP server URL in this order: `MCP_<NAME>_URL` env var → Code Engine → docker
compose DNS → `localhost`. So you have two knobs:

- **All servers → CE** (the common case — run an app on your laptop, hit the
  hosted MCPs): `export CUGA_TARGET=ce`. Rewrites every `load_tools([...])`
  lookup to the CE `/mcp` URL. If your CE project hash or region differs, also
  set `CE_SUBDOMAIN=<hash>` and/or `CE_REGION=<region>`.
- **One server only** (e.g. mix local `web` with CE `knowledge`): set
  `MCP_<NAME>_URL` — it always wins. The URL must end in `/mcp`. Valid names:
  `web`, `knowledge`, `geo`, `finance`, `code`, `local`, `text`, `invocable_apis`.

---

## Operating a public deployment

These apps run publicly on Code Engine, so two shared, install-once helpers
protect and observe them — both wired into every app with a single line and tuned
entirely via env:

- **Rate limiting** — [`apps/_ratelimit.py`](cuga-apps/apps/_ratelimit.py).
  Layered, in-memory limits on **POST** (the expensive agent calls; GET stays
  free): per-IP token bucket + per-IP daily cap + a global backstop + a
  concurrency gate + a body-size cap. Denied requests get `429`/`413` +
  `Retry-After`. Tune via `RL_PER_MIN`, `RL_BURST`, `RL_PER_DAY`,
  `RL_GLOBAL_PER_MIN`, `RL_CONCURRENCY`, `RL_MAX_BODY_BYTES` (see
  `apps/.env.example`). Per-IP uses `X-Forwarded-For` (spoofable) — front with
  IBM CIS WAF for a hard guarantee.
- **Usage tracking** — [`apps/_usage.py`](cuga-apps/apps/_usage.py) +
  [`apps/usage_collector`](cuga-apps/apps/usage_collector). Every app
  fire-and-forgets an anonymized ping (visitor = daily-salted IP hash, no PII) to
  a central collector that serves a cross-app dashboard. Local works out of the
  box; on CE set `USAGE_COLLECTOR_URL` (+ `USAGE_TOKEN`, optional IBM COS for
  durable history).

## Deploying to Code Engine

`cuga-apps/deploy_apps.sh` ships **27 apps** from one shared image
(`build_apps_image.sh` / `Dockerfile.apps`, baking in cuga, sqlite-vec,
feedparser, a headless Chromium for meetup_finder, and boto3). See
[`docs/CLOUD_ENGINE_DEPLOYMENT.md`](cuga-apps/docs/CLOUD_ENGINE_DEPLOYMENT.md) for
the full runbook. The all-in-one image (UI + showcase apps + MCP on one port)
deploys from [`build/`](build/) — see [`build/README.md`](build/README.md).

## Repo layout

```
cuga-apps/
├── README.md                       you are here
├── cuga_external_app_spec.md       self-contained spec — point an LLM at this to build a new app
├── build/                          all-in-one image (UI + showcase apps + MCP on port 8080) + docker compose
├── cuga-apps/                      the umbrella repo: 35 apps (27 deployable), 8 MCP servers, the umbrella UI
│   ├── apps/                       one folder per app
│   │   ├── _ratelimit.py           shared rate limiting (install_rate_limit)
│   │   ├── _usage.py               shared usage tracking (install_usage)
│   │   ├── usage_collector/        cross-app usage dashboard (port 28827)
│   │   └── launch.py               local orchestrator: start/stop/kill/status
│   ├── mcp_servers/                MCP servers (7 hosted + invocable_apis)
│   ├── ui/                         the umbrella SPA
│   └── docs/
│       ├── HOW_TO_BUILD_AN_APP_FAST.md  10-minute in-repo build guide
│       ├── ADDING_AN_APP.md             register a new app end-to-end
│       ├── cuga_app_builder_spec.md     full in-repo build spec (MCP + inline)
│       └── CLOUD_ENGINE_DEPLOYMENT.md   CE deployment runbook
└── apps/                           legacy apps (predates the cuga-apps clone)
```

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
Contributions welcome; see [`CONTRIBUTING.md`](CONTRIBUTING.md).
