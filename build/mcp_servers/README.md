# MCP servers — build, run, deploy

The single home for deploying the **shared MCP servers** that cuga-apps call
(`web`, `knowledge`, `geo`, `finance`, `code`, `local`, `text`, plus a
local-only `invocable_apis`). These are the standalone `cuga-apps-mcp-*`
services on IBM Cloud Code Engine — *not* the all-in-one bundle in
[../](../) (that bakes a lean 5-server subset into one image).

> **Why some files live elsewhere.** The image build inputs — `Dockerfile.mcp`,
> `entrypoint.sh`, `requirements.mcp.txt`, and the `mcp_servers/` source — stay
> in the inner source root [../../cuga-apps/](../../cuga-apps/) because the
> image `COPY`s `apps/_ports.py` + `mcp_servers/` from there, and
> `entrypoint.sh` / `requirements.mcp.txt` are shared with the **apps** image.
> The scripts here reference them by relative path; you don't move them.

## What's here

| File | Purpose |
|---|---|
| [docker-compose.yml](docker-compose.yml) | Run the MCP servers **locally** (8 servers + tool-explorer). MCP-only subset of the full dev stack. |
| [build_mcp_image.sh](build_mcp_image.sh) | Build + push the two CE images: `icr.io/<ns>/mcp` and `icr.io/<ns>/mcp-tool-explorer`. |
| [deploy_mcp.sh](deploy_mcp.sh) | Deploy 7 MCP servers + tool-explorer to Code Engine (idempotent, retries). |
| [code_engine.yaml](code_engine.yaml) | Declarative mirror of the CE deployment + ready-to-paste MCP-client config. |

## The servers

| Server | Port | CE app | What it provides |
|---|---|---|---|
| `web` | 29100 | `cuga-apps-mcp-web` | Tavily search, fetch_webpage, RSS, YouTube transcripts |
| `knowledge` | 29101 | `cuga-apps-mcp-knowledge` | Wikipedia, arXiv, Semantic Scholar |
| `geo` | 29102 | `cuga-apps-mcp-geo` | Nominatim, Overpass, OpenTripMap, wttr.in |
| `finance` | 29103 | `cuga-apps-mcp-finance` | CoinGecko, Alpha Vantage |
| `code` | 29104 | `cuga-apps-mcp-code` | stdlib code analysis (`ast`) |
| `local` | 29105 | `cuga-apps-mcp-local` | psutil metrics, faster-whisper transcription |
| `text` | 29106 | `cuga-apps-mcp-text` | docling extraction, tiktoken counting, chunking |
| `invocable_apis` | 29107 | *(local only)* | sqlite-backed BIRD harness — needs host data mounts |

Ports come from [../../cuga-apps/apps/_ports.py](../../cuga-apps/apps/_ports.py).
Per-server local-dev dependency notes:
[../../cuga-apps/mcp_servers/README.md](../../cuga-apps/mcp_servers/README.md).

## Run locally

```bash
# from this directory (build/mcp_servers/)
cp ../../cuga-apps/apps/.env.example ../../cuga-apps/apps/.env   # one-time; add keys
docker compose up --build                       # all servers + tool-explorer
docker compose up --build mcp-web mcp-knowledge  # or just a couple
```

Smoke-test a server (streamable-HTTP `initialize` handshake):

```bash
curl -sS http://localhost:29100/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Or browse every server's tools in the **MCP Tool Explorer** at
`http://localhost:28900`.

## Deploy to Code Engine

Prereqs (one-time): `ibmcloud login`, `ibmcloud ce project select`, `ibmcloud cr
login`, and CE secrets `icr-secret-1` (registry pull) + `app-env` (env file).
Full operator runbook:
[../../cuga-apps/docs/CLOUD_ENGINE_DEPLOYMENT.md](../../cuga-apps/docs/CLOUD_ENGINE_DEPLOYMENT.md).

```bash
# from this directory (build/mcp_servers/)
./build_mcp_image.sh              # build + push both images (linux/amd64)
./deploy_mcp.sh                   # all 7 MCPs + tool-explorer
./deploy_mcp.sh web knowledge     # a subset
./deploy_mcp.sh tool-explorer     # just the explorer
```

`deploy_mcp.sh` prints each public URL on success; the MCP endpoint is
`<url>/mcp`. Apps reach these automatically with `CUGA_TARGET=ce` (see the MCP
URL resolution in
[../../cuga-apps/apps/_mcp_bridge.py](../../cuga-apps/apps/_mcp_bridge.py)).

## Connect an MCP client

The deployed servers speak streamable-HTTP at `/mcp`. Paste the `mcpServers:`
block from [code_engine.yaml](code_engine.yaml) into a Claude Desktop / Claude
Code config (converted to JSON), or use the Python / LangChain snippets in that
same file.
