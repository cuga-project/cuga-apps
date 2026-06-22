# cuga-apps

**Real agentic apps you can read in one sitting, built on [CUGA](https://cuga.dev).**

The model is rarely the hard part of an agent. The work is wiring up tools,
holding state together across a long task, adding guardrails, and growing from
one agent to several without a rewrite. **CUGA** — the **C**onfigurable
**G**eneralist **A**gent, an open-source harness from IBM Research
(`pip install cuga`) — handles that plumbing, so the part you write shrinks to
**a tool list and a system prompt**. It plans before it acts, executes with a mix
of tool calls and generated code, holds intermediate state across a long run, and
self-corrects — the machinery behind **#1 on [AppWorld](https://appworld.dev/)
and [WebArena](https://webarena.dev/)**.

**cuga-apps** is what that feels like in practice: **35 apps** in
[`cuga-apps/apps/`](cuga-apps/apps/) (**21 in the polished showcase set**), each a
single-file FastAPI server wrapping one `CugaAgent` with a tool list and a system
prompt. The right-hand panel of every app shows live structured state the agent
pushes as it works. If you've written a FastAPI route, you can read every line.

> **Heads up — the real catalog is the *inner* [`cuga-apps/`](cuga-apps/)
> directory**, not the repo root. Apps live in [`cuga-apps/apps/`](cuga-apps/apps/).

## Who this is for

| If you… | …start here |
|---|---|
| want to **try a CUGA agent** without building one | the [live gallery](#try-it-live), or the [one-command Docker stack](#run-the-whole-stack-locally-with-docker) |
| are **building an agent app** | clone the app closest to your idea and edit its tool list + prompt ([Quick start](#quick-start)) |
| want to **learn the patterns** — MCP + inline tools, multi-agent, RAG, web grounding | read one app end to end; they all share the same skeleton |
| just want a **working `CugaAgent` example** to copy | [Recipe Composer](cuga-apps/apps/recipe_composer) (inline tools only, ~one file) |

## Try it live

Every app, behind a launch button, no install:

**[cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud ↗](https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/)**

Filter by **✦ Showcase** for the polished set.

---

## Quick start

> **Prerequisite — Python 3.13.** `cuga` supports `>=3.10,<3.14` (3.14 is
> unsupported). The cleanest setup is a `uv` venv on 3.13. You also need
> credentials for **one** LLM provider — the example below uses watsonx; CUGA
> also speaks OpenAI, Anthropic, Ollama, and LiteLLM (set `LLM_PROVIDER`
> accordingly — point at a local Ollama model for zero API cost).

### 1 — An inline-tools-only app (fastest path)

**Recipe Composer** is the easiest first run: its tools are plain Python
functions, so there are **no MCP servers and no API keys beyond your LLM
provider**.

```bash
git clone https://github.com/cuga-project/cuga-apps
cd cuga-apps/cuga-apps/apps/recipe_composer

uv venv --python 3.13 .venv && source .venv/bin/activate
pip install -r requirements.txt cuga

export LLM_PROVIDER=watsonx
export LLM_MODEL=meta-llama/llama-3-3-70b-instruct
export WATSONX_APIKEY=<your-key>
export WATSONX_PROJECT_ID=<your-project-id>     # or WATSONX_SPACE_ID

python main.py --port 28820
# open http://127.0.0.1:28820
```

`AGENT_SETTING_CONFIG` auto-defaults to `settings.<provider>.toml`, so you don't
set it. Try: *"I have chicken, rice, and broccoli — what can I cook in under 25
minutes?"* The pantry, diet, and recipe cards on the right update as the agent
works.

### 2 — An app that mixes inline tools with MCP servers

**Movie Recommender** adds the shared `knowledge` MCP server (Wikipedia / arXiv /
Semantic Scholar) to its inline tools. Rather than run MCP locally, point it at
the hosted set with `CUGA_TARGET=ce` — those servers already hold their own keys,
so your laptop still only needs the LLM provider:

```bash
cd cuga-apps/cuga-apps/apps/movie_recommender
uv venv --python 3.13 .venv && source .venv/bin/activate    # or reuse the one above
pip install -r requirements.txt cuga

# LLM provider vars from step 1 still apply
export CUGA_TARGET=ce        # use the hosted MCP servers; no extra keys needed

python main.py --port 28806
# open http://127.0.0.1:28806
```

Try: *"I loved Inception and Arrival — recommend 5 cerebral sci-fi films."* Same
shape as Recipe Composer; the only difference is one extra line in `_make_tools()`
(`load_tools(["knowledge"])`) and the prompt.

Every app folder has its own `requirements.txt` and `README.md` with example
prompts — the run pattern is always `cd cuga-apps/apps/<app> && pip install -r
requirements.txt cuga && python main.py --port <port>` (ports in the
[reference table](#app-reference)).

## Run the whole stack locally with Docker

One command brings up **the umbrella UI + all 21 showcase apps + the MCP servers
they need** in a single container on port 8080:

```bash
cd build
cp .env.example .env          # set your LLM provider + key; add TAVILY_API_KEY /
                              # OPENTRIPMAP_API_KEY / ALPHA_VANTAGE_API_KEY for the
                              # apps that use them
docker compose up --build     # first build is large (cuga + Chromium + MCP deps)
# open http://localhost:8080
```

The UI loads at `/`; click any showcase app — it opens at `/a/<app>/` and works
end-to-end (chat → agent → live panel). A missing optional key just degrades the
apps that need it (that tool returns a clear "missing key" error) — everything
still comes up. Details in [`build/README.md`](build/README.md).

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
[live gallery](https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/).

### App reference

The 21 showcase apps, with the MCP servers each uses and a local port to run it
on. Run pattern: `cd cuga-apps/apps/<app> && pip install -r requirements.txt cuga
&& python main.py --port <port>`.

| App | MCP servers | Port | Notes |
|---|---|---|---|
| [Recipe Composer](cuga-apps/apps/recipe_composer) | — | 28820 | inline tools only; no keys beyond LLM |
| [Movie Recommender](cuga-apps/apps/movie_recommender) | knowledge | 28806 | |
| [Travel Planner](cuga-apps/apps/travel_planner) | web, knowledge, geo | 28090 | |
| [City Beat](cuga-apps/apps/city_beat) | geo, web, knowledge, finance | 28821 | 4 MCPs + 7 inline session tools |
| [Wiki Dive](cuga-apps/apps/wiki_dive) | knowledge | 28809 | |
| [Paper Scout](cuga-apps/apps/paper_scout) | knowledge | 28808 | |
| [Web Researcher](cuga-apps/apps/web_researcher) | web | 28798 | |
| [Webpage Summarizer](cuga-apps/apps/webpage_summarizer) | web | 28071 | |
| [YouTube Research](cuga-apps/apps/youtube_research) | web | 28803 | |
| [Newsletter Intelligence](cuga-apps/apps/newsletter) | web | 28793 | |
| [Architecture Diagram](cuga-apps/apps/arch_diagram) | web | 28804 | |
| [Hiking Research](cuga-apps/apps/hiking_research) | geo, web | 28805 | |
| [Find a Doctor](cuga-apps/apps/find_a_doctor) | — | 28825 | keyless; OSM + DuckDuckGo reviews |
| [GitHub Trending](cuga-apps/apps/github_trending) | — | 28823 | keyless; optional `GITHUB_TOKEN` raises rate limit |
| [AI Labs News](cuga-apps/apps/ai_labs_news) | — | 28824 | keyless; reads each lab's RSS/Atom feed |
| [Meetup Finder](cuga-apps/apps/meetup_finder) | — (+ Playwright) | 28826 | browser-driven; `python -m playwright install chromium` first |
| [Server Monitor](cuga-apps/apps/server_monitor) | local | 28767 | optional `CPU_THRESHOLD` / `RAM_THRESHOLD` |
| [Stock & Crypto Alert](cuga-apps/apps/stock_alert) | finance | 28801 | Alpha Vantage key pasted in browser per session |
| [IBM Cloud Advisor](cuga-apps/apps/ibm_cloud_advisor) | web | 28812 | |
| [IBM Docs Q&A](cuga-apps/apps/ibm_docs_qa) | web | 28813 | |
| [Ouroboros](cuga-apps/apps/ouroboros) | — | 28822 | multi-agent (supervisor + 7 specialists); give it `APP_MEM=4G` |

Apps using an MCP server need either a local MCP server or `export CUGA_TARGET=ce`
(see [Shared MCP servers](#shared-mcp-servers)).

---

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
- **Every tool returns the same envelope** — `{"ok": true, "data": {...}}` on
  success, `{"ok": false, "code": "...", "error": "..."}` on failure. CUGA's
  planner recovers from a *declared* failure ("geocoding returned nothing — skip
  that section and keep going") and derails on a raw stack trace. Boring, but
  load-bearing.

State is a per-`thread_id` Python dict that only the agent writes to, through its
tools; the live panel polls it and redraws the moment a tool fires. No database.

## Build your own app

There is a single self-contained spec for building a CUGA app from scratch
against the hosted MCP servers — no need to clone the rest of this repo:

**[`cuga_external_app_spec.md`](cuga_external_app_spec.md)**

It includes the LLM factory, MCP bridge, `main.py` / `ui.py` templates, the
tool-envelope rule, and a definition-of-done checklist. Building *inside* the
repo? See
[`docs/HOW_TO_BUILD_AN_APP_FAST.md`](cuga-apps/docs/HOW_TO_BUILD_AN_APP_FAST.md)
and [`docs/ADDING_AN_APP.md`](cuga-apps/docs/ADDING_AN_APP.md).

Hand the spec to any capable LLM coding agent:

```
You are an expert in creating Cuga web applications using Cuga Agent.
Follow the spec here: <path to> cuga_external_app_spec.md

Create a new web app to <what you want it to do> that is powered by Cuga Agent.
```

Replace `<…>` with your idea — *"track my reading list and recommend the next
book,"* *"summarise the GitHub PRs I'm reviewing today,"* *"a daily briefing for
any city."* A few apps here were generated exactly this way — regular enough for a
model to reproduce means regular enough for you to learn.

[`apps/city_beat/`](cuga-apps/apps/city_beat/) is the cleanest worked example: 4
hosted MCP servers (`geo`, `web`, `knowledge`, `finance`) + 7 inline session
tools. See [main.py:104](cuga-apps/apps/city_beat/main.py#L104) for the
`load_tools([...])` call and
[main.py:108-225](cuga-apps/apps/city_beat/main.py#L108-L225) for the inline
`@tool` defs.

## Shared MCP servers

Generic capabilities live in shared MCP servers so apps don't reimplement them.
Apps reach them with `load_tools(["web", ...])`. Run them locally, or use the
hosted set with `export CUGA_TARGET=ce` (their upstream keys already live
server-side, so your laptop only needs an LLM provider):

| Server | Capabilities |
|---|---|
| `web` | `web_search` (Tavily), `fetch_webpage`, `fetch_feed`, YouTube transcripts |
| `knowledge` | Wikipedia, arXiv, Semantic Scholar |
| `geo` | `geocode`, `get_weather`, `find_hikes`, `search_attractions` |
| `finance` | `get_crypto_price` (CoinGecko), `get_stock_quote` (Alpha Vantage) |
| `code` | `check_python_syntax`, `extract_code_metrics`, `detect_language` |
| `local` | system metrics, processes, disk usage, audio transcription |
| `text` | `chunk_text`, `count_tokens`, `extract_text` (PDF/DOCX/HTML → markdown) |

An 8th server, `invocable_apis`, runs local-only (it needs BIRD benchmark data
bind-mounted from the host). The bridge in
[`apps/_mcp_bridge.py`](cuga-apps/apps/_mcp_bridge.py) resolves each server's URL
automatically; set `MCP_<NAME>_URL` to override a single one.

## Repo layout

```
cuga-apps/
├── README.md                       you are here
├── cuga_external_app_spec.md       self-contained spec — point an LLM at this to build a new app
├── build/                          all-in-one image (UI + showcase apps + MCP on port 8080) + docker compose
└── cuga-apps/                      the umbrella repo: 35 apps, 8 MCP servers, the umbrella UI
    ├── apps/                       one folder per app (main.py + ui.py + requirements.txt)
    ├── mcp_servers/                MCP servers (7 hosted-capable + invocable_apis)
    ├── ui/                         the umbrella SPA
    └── docs/
        ├── HOW_TO_BUILD_AN_APP_FAST.md  10-minute build guide
        ├── ADDING_AN_APP.md             register a new app end-to-end
        └── cuga_app_builder_spec.md     full in-repo build spec (MCP + inline)
```

## Choosing an LLM provider (Docker stack)

CUGA has **two model layers** and both must point at a provider: the **outer
model** (`LLM_PROVIDER` + `LLM_MODEL`) and CUGA's **internal nodes** (planner,
coder, final_answer, …) configured by the settings TOML named in
`AGENT_SETTING_CONFIG`. The all-in-one image reads these from
[`build/.env`](build/.env.example) — pick **one** block; no rebuild needed when
you switch. CUGA ships native settings for watsonx/openai/litellm/… but **not**
for `anthropic` or `ollama`, so those route their internal nodes through the
`openai` platform (point its `OPENAI_BASE_URL` at the right endpoint).

| Provider | `build/.env` variables |
|---|---|
| **watsonx** (image default) | `LLM_PROVIDER=watsonx`, `LLM_MODEL=openai/gpt-oss-120b`, `AGENT_SETTING_CONFIG=/app/apps/settings.watsonx.toml`, `WATSONX_APIKEY=…`, `WATSONX_PROJECT_ID=…` (or `WATSONX_SPACE_ID`), `WATSONX_URL=https://us-south.ml.cloud.ibm.com` |
| **Ollama** (local, free) | `LLM_PROVIDER=ollama`, `LLM_MODEL=gpt-oss:20b`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `AGENT_SETTING_CONFIG=settings.openai.toml`, `OPENAI_BASE_URL=http://host.docker.internal:11434/v1`, `OPENAI_API_KEY=ollama`, `MODEL_NAME=gpt-oss:20b` |
| **OpenAI** | `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4o`, `AGENT_SETTING_CONFIG=settings.openai.toml`, `OPENAI_API_KEY=sk-…`, `MODEL_NAME=gpt-4o` |
| **Anthropic** | `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-4-6`, `ANTHROPIC_API_KEY=sk-ant-…`, `AGENT_SETTING_CONFIG=settings.openai.toml`, `OPENAI_BASE_URL=https://api.anthropic.com/v1/`, `OPENAI_API_KEY=sk-ant-…`, `MODEL_NAME=claude-sonnet-4-6` |

**Ollama specifics:** use `host.docker.internal` (not `localhost`) so the
container reaches Ollama on the host, and start Ollama beyond loopback with
`OLLAMA_HOST=0.0.0.0:11434 ollama serve` (the macOS app binds `127.0.0.1` only —
quit it first). `gpt-oss:20b` is the smallest model that drives CUGA's
planner/coder reliably; expect minutes per query on a laptop.

**Anthropic specifics:** the outer model is native Claude, but CUGA has no
anthropic platform, so its internal nodes use the `openai` platform. The row
above keeps them on Claude via Anthropic's OpenAI-compatible endpoint; supply a
real `OPENAI_API_KEY` instead if you'd rather run the internal nodes on GPT.

After editing `build/.env`, recreate the container:
`docker compose -f build/docker-compose.yml up -d` (add `--build` only if you
changed code). Full annotated reference in
[`build/.env.example`](build/.env.example).

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
Contributions welcome; see [`CONTRIBUTING.md`](CONTRIBUTING.md).
