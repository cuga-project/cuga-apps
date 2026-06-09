# build/ce/ — deploy the all-in-one image to IBM Code Engine

Two scripts push the **single all-in-one image** to IBM Container Registry and
run it as **one Code Engine service** — the umbrella UI + every ship-ready app +
the 5 MCP servers + the stats dashboard, all in one instance behind port 8080.

> One image, one CE application, one URL. No per-app fan-out (that's what
> `cuga-apps/deploy_apps.sh` and [../mcp_servers/deploy_mcp.sh](../mcp_servers/deploy_mcp.sh)
> do). This is the "one big microservice" deployment.

| Script | What it does |
| --- | --- |
| `build_and_push.sh` | Build `build/Dockerfile` (context = repo root) for `linux/amd64` and push `icr.io/<ns>/cuga-agent-apps:<tag>` |
| `deploy.sh` | Sync `build/.env` → a CE secret, then `ce app create/update` the single service |

## One-time prerequisites

```bash
# 1. Log in and target your region + resource group
ibmcloud login --sso
ibmcloud target -r us-east -g routing

# 2. Select (or create) the Code Engine project — deploys land in the SELECTED project
ibmcloud ce project select --name ce-project-routing

# 3. Log local docker into ICR — use the GLOBAL registry (icr.io) so it matches
#    REGISTRY=icr.io in the scripts and --server icr.io in the pull secret below.
ibmcloud cr region-set global
ibmcloud cr login

# 4. Create the registry pull secret CE uses (one-time; name must match REGISTRY_SECRET)
#    Use an IBM Cloud API key with registry pull access.
ibmcloud ce registry create \
  --name icr-secret-1 \
  --server icr.io \
  --username iamapikey \
  --password <your-icr-apikey>
```

## Deploy

```bash
cd build/ce

# fill in build/.env first (LLM provider keys + TAVILY/OPENTRIPMAP/ALPHA_VANTAGE)
./build_and_push.sh        # build + push the image to ICR
./deploy.sh                # create/update the single CE service

# the URL is printed at the end; or:
ibmcloud ce app get --name cuga-agent-apps --output url
```

Update later (new image): re-run both. `deploy.sh` re-syncs the env secret and
updates the running app in place.

## How env / secrets are handled

`deploy.sh` reads `build/.env`, turns each `KEY=VALUE` line into a CE secret
(`<app>-env`), and attaches it with `--env-from-secret`. Values live in the
secret, not on the app's command line. `CUGA_TARGET=local` is forced so the apps
use the in-container MCP servers (never set it to `ce` for this image).

## Sizing

Defaults: `--cpu 12 --memory 48G --ephemeral-storage 5G --min-scale 1
--max-scale 1`. The image runs ~26 Python processes (21 apps + 5 MCP) plus
nginx; measured idle footprint is ~8 GB, and **12 vCPU / 48 GB** (the platform
maximum) leaves ample headroom for request load and Chromium (`meetup_finder`).
Ephemeral storage must be ≤ memory; 5 GB covers build/scratch space. Keep **one
instance** — per-app session state and the rate limiter assume it. Override per
deploy:

```bash
CPU=6 MEMORY=24G EPHEMERAL_STORAGE=2G ./deploy.sh
```

## Config knobs (env overrides)

| Var | Default | Used by |
| --- | --- | --- |
| `NAMESPACE` | `routing_namespace` | both |
| `IMAGE_TAG` | `latest` | both |
| `IMAGE_NAME` | `cuga-agent-apps` | both |
| `REGISTRY` | `icr.io` | both |
| `APP_NAME` | `cuga-agent-apps` | deploy |
| `REGISTRY_SECRET` | `icr-secret-1` | deploy |
| `ENV_FILE` | `build/.env` | deploy |
| `CPU` / `MEMORY` | `12` / `48G` | deploy |
| `EPHEMERAL_STORAGE` | `5G` | deploy |
| `MIN_SCALE` / `MAX_SCALE` | `1` / `1` | deploy |
| `DOCKER_BUILD_NETWORK` | `host` | build |

## Gotchas

- **Project is global**: deploys go to whatever `ibmcloud ce project current`
  shows. Select the right one first.
- **Session expiry**: `ibmcloud login --sso` times out after hours — re-login and
  re-`ce project select`, then re-run. Both scripts are idempotent.
- **Registry secret**: if the ICR API key is rotated, pulls fail with
  `ImagePullBackOff` — `ibmcloud ce registry update --name icr-secret-1
  --password <new-key>`.
- **Health checks** hit the port: `/` (UI) returns 200 and `/healthz` is also
  available.
