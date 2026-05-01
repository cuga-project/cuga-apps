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
├── requirements.apps.txt
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
