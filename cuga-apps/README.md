# cuga-apps (MCP edition)

23 demo agent-apps, each a CugaAgent wrapped in a FastAPI UI. Every shared tool
primitive (web search, Wikipedia, arXiv, geocoding, document parsing,
transcription, etc.) lives in a separate **MCP server**; apps connect via a
LangChain↔MCP bridge. One umbrella UI tiles every app; one tool explorer lets
you browse and invoke every MCP tool.

```
                                    ┌──────────────────────────┐
                                    │   umbrella UI :3001      │
                                    │   (links to every app)   │
                                    └────────────┬─────────────┘
                                                 ▼
   ┌─────────────────┐    streamable HTTP   ┌──────────────────────┐
   │ 7 MCP servers   │ ◄──────────────────► │  23 FastAPI apps     │
   │ web/knowledge/  │   apps/_mcp_bridge   │  (CugaAgent inside)  │
   │ geo/finance/    │                      │  ports 28xxx         │
   │ code/local/text │                      │                      │
   │ ports 29100-29106                      └──────────────────────┘
   └────────┬────────┘
            │
            ▼
   ┌────────────────────────────┐
   │  mcp tool explorer :28900  │ ← browse + invoke any tool
   └────────────────────────────┘
```

## Quick start

```bash
cp apps/.env.example apps/.env       # fill in keys (see docs/GETTING_STARTED.md)
docker compose up -d --build         # ~5-10 min on first build
```

Then open:
- **Umbrella UI** — http://localhost:3001
- **MCP Tool Explorer** — http://localhost:28900
- Individual apps — see the umbrella UI, or `apps/_ports.py`

### Local dev (no Docker)

You can use either `pip` or [`uv`](https://docs.astral.sh/uv/). **uv is
~8× faster** on this requirements file (~10 s vs ~85 s, warm cache) because
it parallelizes downloads + extraction and hardlinks wheels from a global
cache. Pick whichever you prefer — they install the same packages.

#### Option A — uv (recommended)

```bash
cd cuga-apps
uv venv --python 3.13                            # creates ./.venv
uv pip install -r requirements.apps.txt          # lite — covers 21 of 23 apps
source .venv/bin/activate
```

#### Option B — pip

```bash
cd cuga-apps
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.apps.txt             # lite — covers 21 of 23 apps
```

The lite install **skips `chromadb` and `sentence-transformers`**. Only two
apps need them:

- `apps/video_qa` — local RAG over video transcripts
- `apps/deck_forge` — slide-deck RAG + embeddings

If you want those, install the heavy file too:

```bash
uv pip install -r requirements.apps.heavy.txt    # or: pip install -r ...
                                                  # ~100 MB extra (chromadb + onnxruntime)
```

> **Note on torch.** Even the lite install includes `torch` (~400 MB) — it's a
> hard dep of the `cuga` framework itself and of `docling-ibm-models`, so the
> split can't avoid it. Expect the venv to weigh in at **~1.5–1.9 GB** either
> way. The heavy file's incremental cost is mostly chromadb's native stack
> (onnxruntime, ~67 MB) plus the sentence-transformers wrapper.

#### uv day-to-day

```bash
# rebuild the venv from scratch (fast — wheels come from the cache)
rm -rf .venv && uv venv --python 3.13 && uv pip install -r requirements.apps.txt

# add or remove a single package without re-resolving everything
uv pip install psutil
uv pip uninstall psutil

# list what's installed
uv pip list
uv pip show cuga                                 # see what cuga pulls in

# clean the global wheel cache (frees disk; next install re-downloads)
uv cache clean                                   # nukes ~/.cache/uv entirely
uv cache prune                                   # keeps cache, drops unused wheels
uv cache dir                                     # show where the cache lives

# pin Python explicitly (defaults to whatever uv finds on PATH)
uv venv --python 3.13                            # this repo targets 3.13
```

> **When to `uv cache clean`.** Almost never — uv hardlinks from the cache, so
> a 1.9 GB venv only costs disk *once*, and a fresh `uv pip install` is
> seconds when wheels are cached. Reach for it only if you're chasing a
> corrupted wheel or a stale resolver result.

Once installed, launch any app via `apps/launch.py` (the MCP servers still
need to be running — start them with `docker compose up -d` for the `mcp-*`
services, or run `mcp_servers/run_all.py`).

The Docker image always installs both files, so `docker compose` users get
the full stack regardless.

To verify everything's healthy:

```bash
make install-test-deps               # one-time
make test                            # ~13s, 120 integration tests, no LLM cost
```

## Documentation

Read these in order if you're new:

1. [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — bring up the stack, env
   vars, what each port is, how to interact with the apps.
2. [docs/TESTING.md](docs/TESTING.md) — the test tiers, what each catches, how
   to run them.
3. [docs/ADDING_A_TOOL.md](docs/ADDING_A_TOOL.md) — add a new MCP tool, rebuild,
   verify with tests.
4. [docs/ADDING_AN_APP.md](docs/ADDING_AN_APP.md) — full new-app walkthrough
   with a worked example.

## Layout

```
cuga-apps/
├── mcp_servers/             7 MCP servers + shared _core
│   ├── _core/               http, errors, html, FastMCP bootstrap
│   ├── web/                 Tavily, fetch, RSS, YouTube
│   ├── knowledge/           Wikipedia, arXiv, Semantic Scholar
│   ├── geo/                 Nominatim, Overpass, OpenTripMap, wttr.in
│   ├── finance/             CoinGecko, Alpha Vantage
│   ├── code/                stdlib code analysis
│   ├── local/               psutil, faster-whisper
│   └── text/                docling, tiktoken, recursive chunking
├── apps/                    23 FastAPI demo apps
│   ├── _mcp_bridge.py       LangChain↔MCP adapter
│   ├── _llm.py              multi-provider LLM factory
│   ├── _ports.py            single source of truth for ALL ports
│   ├── launch.py            local-dev launcher
│   └── <app>/               per-app code
├── mcp_tool_explorer/       browse + invoke MCP tools (port 28900)
├── ui/                      React/Vite umbrella (port 3001)
├── tests/                   pytest integration suite
├── docker-compose.yml
├── Dockerfile.apps
├── Dockerfile.mcp           one image, 7 entrypoints
├── requirements.apps.txt        lite — every app except video_qa/deck_forge
├── requirements.apps.heavy.txt  chromadb + sentence-transformers (video_qa, deck_forge)
├── requirements.mcp.txt
├── requirements.test.txt
├── start.sh                 apps container entrypoint
└── Makefile                 test + lifecycle shortcuts
```

## Ports

This stack is designed to coexist with the original `agent-apps` stack — every
port is shifted into a non-overlapping range.

| Component | Port range |
|---|---|
| Umbrella UI | **3001** |
| Apps (23) | **28xxx** (28071, 28090, 28766–28814) |
| MCP servers (7) | **29100–29106** |
| Tool explorer | **28900** |

See [apps/_ports.py](apps/_ports.py) for the authoritative registry.

## Make targets

```
make up                  bring the full stack up
make down                stop the stack
make build               rebuild all images
make logs                tail combined apps logs

make install-test-deps   pip install -r requirements.test.txt (one-time)
make test                smoke + mcp + wiring (default; no LLM cost)
make test-quick          smoke only (~5s)
make test-mcp            mcp tier only
make test-wiring         app-wiring tier only
make test-llm            opt-in LLM round-trips (slow, costs tokens)
make test-all            everything
```

## Tool inventory

**36 MCP tools across 7 servers.** Browse them at http://localhost:28900 or
read [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md#what-each-mcp-server-exposes)
for the full list.

## Docker compose — full reference

The Quick start above covers the happy path (`docker compose up -d --build`).
Day-to-day commands once the stack is built:

```bash
# Bring everything up in the background (rebuild changed images first)
docker compose up -d --build

# Tail logs for one service or all services
docker compose logs -f apps                # the FastAPI apps container
docker compose logs -f mcp-web mcp-text    # specific MCP servers
docker compose logs -f                     # everything, multiplexed

# Stop the stack (containers stay around, restart is fast)
docker compose stop

# Stop and remove containers/networks (keeps named volumes like video_qa_cache)
docker compose down

# Nuke everything including named volumes (forces re-download of video caches)
docker compose down -v

# Rebuild a single image (e.g. after changing requirements.apps.txt)
docker compose build apps

# Restart one service without rebuilding
docker compose restart apps

# One-off shell inside the apps container for debugging
docker compose exec apps bash

# Check what's running and on which ports
docker compose ps
```

Subsequent builds reuse the cached pip-install layer unless
`requirements.apps.txt`, `requirements.apps.heavy.txt`, or
`requirements.mcp.txt` change.

Environment / secrets are read at runtime from `apps/.env` — see the Quick
start at the top. They're mounted read-only as `/run/secrets/app.env` and
sourced by `entrypoint.sh`, so they never appear in `docker inspect` or in
the image itself.
