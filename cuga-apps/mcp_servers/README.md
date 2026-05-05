# MCP servers — local dev guide

There are **8 MCP server packages** here. They share a single image (`Dockerfile.mcp`) and a single bundled requirements file ([requirements.mcp.txt](../requirements.mcp.txt)) — there are **no per-server requirements files**. This README documents the per-server deps so you can install the minimum you need to run **one** server locally without Docker.

## The servers

| Package | Port | Purpose |
|---|---|---|
| [web/](web/server.py) | 29100 | Tavily search, fetch_webpage, RSS, YouTube transcripts |
| [knowledge/](knowledge/server.py) | 29101 | Wikipedia, arXiv, Semantic Scholar |
| [geo/](geo/server.py) | 29102 | Nominatim, Overpass, OpenTripMap, wttr.in |
| [finance/](finance/server.py) | 29103 | CoinGecko, Alpha Vantage |
| [code/](code/server.py) | 29104 | stdlib code analysis (`ast`) |
| [local/](local/server.py) | 29105 | psutil metrics, faster-whisper transcription |
| [text/](text/server.py) | 29106 | docling extraction, tiktoken counting, chunking |
| [invocable_apis/](invocable_apis/server.py) | 29107 | sqlite-backed BIRD invocable-APIs harness |

Ports come from [apps/_ports.py](../apps/_ports.py).

## Per-server dependencies

**Common to every server** (always install these):

```
mcp>=1.0
httpx
pydantic
```

**Plus, per server:**

| Server | Extra deps | Notes |
|---|---|---|
| `web` | `tavily-python`, `beautifulsoup4`, `feedparser`, `youtube-transcript-api` | `bs4` is required (used by `_core/html.py`); the others are imported lazily inside tool functions, so the server boots without them — only the tool that needs them fails. |
| `knowledge` | *(none)* | stdlib + `httpx` |
| `geo` | *(none)* | stdlib + `httpx` |
| `finance` | *(none)* | stdlib + `httpx` |
| `code` | *(none)* | stdlib only |
| `local` | `psutil`, `faster-whisper` | `faster-whisper` also needs `ffmpeg` and `libgomp` system libs (`brew install ffmpeg libomp`). First call downloads the whisper `base` model (~150 MB). |
| `text` | `docling`, `tiktoken` | First call downloads docling models (~250 MB) and tiktoken BPE files. |
| `invocable_apis` | *(none)* | stdlib + `httpx` + `sqlite3`. Needs `BIRD_DEV_JSON` and `BIRD_DBS_DIR` env vars to point at BIRD data. |

## Run a single server locally

From the repo root (`cuga-apps/`):

```bash
# 1) one-time: create a venv and install common + the server's extras
python3.11 -m venv .venv
source .venv/bin/activate
pip install "mcp>=1.0" httpx pydantic

# 2) install just the extras for the server you want, e.g. mcp-web:
pip install tavily-python beautifulsoup4 feedparser youtube-transcript-api

# 3) export any keys that server's tools need (optional — missing keys
#    return a clean missing_key error, the server still starts):
export TAVILY_API_KEY=...

# 4) run it (must be from cuga-apps/ — server.py imports apps._ports)
python -m mcp_servers.web.server
```

You should see:

```
HH:MM:SS  INFO     [...]  Uvicorn running on http://0.0.0.0:29100
```

Verify it's alive in another shell:

```bash
curl -s http://localhost:29100/mcp -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Or point the **MCP Tool Explorer** ([mcp_tool_explorer/](../mcp_tool_explorer/), port 28900) at it.

### Pick-your-server one-liners

```bash
# mcp-web (29100)
pip install "mcp>=1.0" httpx pydantic tavily-python beautifulsoup4 feedparser youtube-transcript-api
python -m mcp_servers.web.server

# mcp-knowledge (29101) — no extras
pip install "mcp>=1.0" httpx pydantic
python -m mcp_servers.knowledge.server

# mcp-geo (29102) — no extras
pip install "mcp>=1.0" httpx pydantic
python -m mcp_servers.geo.server

# mcp-finance (29103) — no extras
pip install "mcp>=1.0" httpx pydantic
python -m mcp_servers.finance.server

# mcp-code (29104) — no extras
pip install "mcp>=1.0" httpx pydantic
python -m mcp_servers.code.server

# mcp-local (29105)
brew install ffmpeg libomp
pip install "mcp>=1.0" httpx pydantic psutil faster-whisper
python -m mcp_servers.local.server

# mcp-text (29106)
pip install "mcp>=1.0" httpx pydantic docling tiktoken
python -m mcp_servers.text.server

# mcp-invocable_apis (29107)
pip install "mcp>=1.0" httpx pydantic
export BIRD_DEV_JSON=/path/to/dev.json
export BIRD_DBS_DIR=/path/to/dbs
python -m mcp_servers.invocable_apis.server
```

### Override the bind/port

```bash
MCP_BIND_HOST=127.0.0.1 MCP_PORT_OVERRIDE=29200 python -m mcp_servers.web.server
```

(Both env vars are read in [_core/serve.py](_core/serve.py).)

## If you'd rather just install everything

```bash
pip install -r ../requirements.mcp.txt
python -m mcp_servers.<name>.server
```

Heavier (`docling`, `faster-whisper` pull a lot in), but you don't have to think about which extras a server needs.

## Or just use Docker

The whole point of [Dockerfile.mcp](../Dockerfile.mcp) is that you don't have to wrangle native deps (`ffmpeg`, `libgomp`) or model downloads. To bring up just one server:

```bash
docker compose up -d --build mcp-web      # or mcp-knowledge, mcp-geo, ...
```

Each service in [docker-compose.yml](../docker-compose.yml) overrides `CMD` with its own `python -m mcp_servers.<name>.server`.
