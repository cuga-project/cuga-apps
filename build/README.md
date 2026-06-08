# build/ — all-in-one image (every ship-ready app + MCP servers + the umbrella UI)

This directory packages the **complete environment** — the **umbrella UI + all 21
ship-ready cuga-apps + the MCP servers they need** — into a **single Docker image
behind one port (8080)**. One `docker compose up` brings the whole thing up
locally, and the same image deploys to **Code Engine as one microservice**.

Everything here is self-contained — **no existing repo files are modified** and
**no external MCP deployment is required.**

## What's inside the image

```
   ┌──────────────────────────── one container, port 8080 ───────────────────────────┐
   │  nginx (the only exposed port)                                                   │
   │   ├─ /            → umbrella UI (static SPA, built in "single" mode)             │
   │   ├─ /a/<app>/    → reverse-proxy → 127.0.0.1:288xx   (one per app)              │
   │   └─ /healthz     → 200                                                          │
   │                                                                                  │
   │  21 uvicorn apps on 127.0.0.1:288xx  ──MCP tool calls──┐  (started by run_all.sh)│
   │                                                        ▼                         │
   │  5 MCP servers on 127.0.0.1:291xx  (web, knowledge, geo, finance, local)         │
   └──────────────────────────────────────────────────────────────────────────────────┘
            │ outbound only: LLM API + the MCP servers' upstreams
            ▼   (watsonx/RITS/OpenAI · Tavily · OpenTripMap · Alpha Vantage · Wikipedia)
```

- **MCP servers are bundled and run in-container** on loopback (291xx). `run_all.sh`
  boots them first, waits for them to accept connections, then starts the apps.
  Every app is pointed at them via explicit `MCP_<NAME>_URL=http://127.0.0.1:<port>/mcp`
  (set in `run_all.sh`), so they use the in-container servers even on Code Engine.
  Only the 5 servers the ship-ready apps actually call are included — `web`,
  `knowledge`, `geo`, `finance`, `local`. (`text`/`code`/`invocable_apis` serve
  only non-ship-ready apps and aren't bundled; `invocable_apis` also needs
  external BIRD data.)
- The MCP servers are **never exposed through nginx** — they're reachable only
  from inside the container. The only public surface is port 8080.
- The apps' UIs use absolute paths (`fetch('/ask')`, `/static/…`). Under a path
  prefix those would 404, so nginx injects — into each app's `<head>` — a
  `<base href>` + a tiny `window.fetch` shim that re-prefixes same-origin
  absolute URLs. Generic; no app code changes.
- The umbrella UI is built in a **`single`** URL mode so its launch buttons point
  at `/a/<app>/`. That mode is injected into a *copy* of `deployment.ts` at build
  time ([patch-deployment.cjs](patch-deployment.cjs)) — the repo source is never
  touched.
- nginx + the startup script are generated from `apps/_ports.py` at build time
  ([generate.py](generate.py)), so app **and** MCP ports always match the repo.

## Files

| File | Purpose |
| --- | --- |
| `Dockerfile` | multi-stage: build UI (node) → runtime (apps + MCP servers + nginx) |
| `Dockerfile.dockerignore` | keeps the build context small (BuildKit honors it) |
| `requirements.mcp.txt` | lean dep set for the 5 bundled MCP servers |
| `docker-compose.yml` | local one-command bring-up |
| `generate.py` | emits `nginx` conf + `run_all.sh` (apps **+ MCP**) from `_ports.py` |
| `patch-deployment.cjs` | injects the `single` URL mode into the UI build |
| `.env.example` | LLM provider + MCP service keys |

## Run locally

```bash
cd build
cp .env.example .env          # set your LLM provider + key, and the MCP keys
                              # (TAVILY_API_KEY / OPENTRIPMAP_API_KEY /
                              #  ALPHA_VANTAGE_API_KEY) for the apps you'll use
docker compose up --build     # first build is large (cuga + Chromium + MCP deps)
# open http://localhost:8080
```

Missing an MCP key just degrades the apps that need it (that server's tools
return a clear "missing key" error) — the environment still comes up.

The umbrella UI loads at `/`; click any ship-ready app — it opens at
`/a/<app>/` and works end-to-end (chat → agent → live panel), all on port 8080.

> Requires BuildKit (default in modern Docker) so `Dockerfile.dockerignore` is
> honored. If your Docker is old: `DOCKER_BUILDKIT=1 docker compose build`.

## Verify it's working — `smoke.sh`

After `docker compose up`, run the smoke test. It only hits the public port, so
it works against localhost or a deployed CE URL, and its output is HTTP statuses
+ structural checks (**no secrets**):

```bash
./smoke.sh                                   # http://localhost:8080
./smoke.sh https://<ce-url>                  # a deployed CE URL
./smoke.sh http://localhost:8080 --ask       # also do one real /ask (needs LLM creds)
./smoke.sh http://localhost:8080 --ask find-a-doctor "cardiologist in Boston"
```

It checks `/` (UI) and `/healthz`, then every ship-ready app at `/a/<app>/` —
confirming the proxy works **and** that nginx injected the `<base href>` + fetch
shim (so the app's absolute URLs resolve under the prefix). `--ask` posts one
real agent request to prove the end-to-end path. Exit code is non-zero on any
failure.

## Deploy to Code Engine (single microservice)

```bash
# 1. Build + push the image to your registry (ICR shown; any registry works)
docker build -f build/Dockerfile -t icr.io/<namespace>/cuga-allinone:latest .   # run from repo root
docker push icr.io/<namespace>/cuga-allinone:latest

# 2. Create the CE app — ONE service, port 8080
ibmcloud ce app create \
  --name cuga-allinone \
  --image icr.io/<namespace>/cuga-allinone:latest \
  --registry-secret <your-icr-secret> \
  --port 8080 \
  --cpu 4 --memory 16G \
  --min-scale 1 --max-scale 1 \
  --env LLM_PROVIDER=watsonx \
  --env LLM_MODEL=meta-llama/llama-3-3-70b-instruct \
  --env WATSONX_APIKEY=<key> --env WATSONX_PROJECT_ID=<id> \
  --env TAVILY_API_KEY=<key> \
  --env OPENTRIPMAP_API_KEY=<key> \
  --env ALPHA_VANTAGE_API_KEY=<key>

ibmcloud ce app get --name cuga-allinone --output url   # open it
```

Leave `CUGA_TARGET` unset (the image defaults to `local`) — the MCP servers run
inside this same container, so the apps must not be redirected to a hosted MCP
deployment. The explicit `MCP_<NAME>_URL` exports in `run_all.sh` keep that true
even though Code Engine injects `CE_APP`.

Use `--mount-secret` / a CE secret instead of `--env` for real keys. CE health
checks hit the port (the UI at `/` returns 200; `/healthz` is also available).

## Sizing & caveats

- **Memory**: all 21 apps **and the 5 MCP servers** share one container. The MCP
  servers are lightweight (httpx-based) and start at boot; the apps import `cuga`
  lazily (on the first `/ask`), so idle is moderate, but each *used* app loads the
  full cuga stack. Start at **4 vCPU / 16 GB** and adjust. `meetup_finder`
  (Chromium) and `ouroboros` (7-agent supervisor) are the heaviest.
- **One instance** (`--max-scale 1`): the per-app in-memory session state and the
  rate limiter assume a single instance. Don't scale out without externalizing
  state.
- **Rate limiting + usage tracking** ship with the apps ([../cuga-apps/apps/_ratelimit.py](../cuga-apps/apps/_ratelimit.py),
  [_usage.py](../cuga-apps/apps/_usage.py)) and are active here too; tune via the
  `RL_*` / `USAGE_*` env (see `.env.example`). No usage collector runs in this
  image — point `USAGE_COLLECTOR_URL` at one if you want the dashboard.
- **Non-root CE policy**: the image runs nginx as root (default). If your CE
  project forces non-root containers, nginx needs writable pid/temp paths — ask
  and I'll add the non-root nginx tweaks.
- This image deliberately excludes the heavy apps (`video_qa`, `deck_forge`) and
  the MCP servers they'd need (`text` → docling/torch, `code`, `invocable_apis`
  → external BIRD data). The 5 MCP servers the ship-ready apps use **are**
  bundled. To add another MCP server, append it to `MCP_SERVERS` in
  [generate.py](generate.py) and add its deps to [requirements.mcp.txt](requirements.mcp.txt).

## How it stays in sync

Adding/removing a ship-ready app = update `SHIP_READY` in [generate.py](generate.py)
(and the umbrella UI's ship-ready set). nginx routes + the launcher regenerate on
the next image build; ports always come from `apps/_ports.py`.
