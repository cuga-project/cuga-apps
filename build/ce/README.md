# build/ce/ — deploy the all-in-one image to IBM Code Engine

Two scripts push the **single all-in-one image** to IBM Container Registry and
run it as **one Code Engine service** — the umbrella UI + every ship-ready app +
the 5 MCP servers + the stats dashboard, all in one instance behind port 8080.

> One image, one CE application, one URL. No per-app fan-out (that's what the
> repo-root `deploy_apps.sh` / `deploy_mcp.sh` do). This is the "one big
> microservice" deployment.

| Script | What it does |
| --- | --- |
| `build_and_push.sh` | Build `build/Dockerfile` (context = repo root) for `linux/amd64` and push `icr.io/<ns>/cuga-allinone:<tag>` |
| `deploy.sh` | Sync `build/.env` → a CE secret, then `ce app create/update` the single service |

## One-time prerequisites

```bash
# 1. Log in and target your region + resource group
ibmcloud login --sso
ibmcloud target -r us-south -g <your-resource-group>

# 2. Select (or create) the Code Engine project — deploys land in the SELECTED project
ibmcloud ce project select --name <your-project>

# 3. Log local docker into ICR (for build_and_push.sh)
ibmcloud cr region-set us-south
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
ibmcloud ce app get --name cuga-allinone --output url
```

Update later (new image): re-run both. `deploy.sh` re-syncs the env secret and
updates the running app in place.

## How env / secrets are handled

`deploy.sh` reads `build/.env`, turns each `KEY=VALUE` line into a CE secret
(`<app>-env`), and attaches it with `--env-from-secret`. Values live in the
secret, not on the app's command line. `CUGA_TARGET=local` is forced so the apps
use the in-container MCP servers (never set it to `ce` for this image).

## Sizing

Defaults: `--cpu 4 --memory 16G --min-scale 1 --max-scale 1`. The image runs ~26
Python processes (21 apps + 5 MCP) plus nginx; measured idle footprint is ~8 GB,
so **16 GB** leaves headroom for request load and Chromium (`meetup_finder`).
Keep **one instance** — per-app session state and the rate limiter assume it.
Override per deploy:

```bash
CPU=6 MEMORY=24G ./deploy.sh
```

## Config knobs (env overrides)

| Var | Default | Used by |
| --- | --- | --- |
| `NAMESPACE` | `routing_namespace` | both |
| `IMAGE_TAG` | `latest` | both |
| `REGISTRY` | `icr.io` | both |
| `APP_NAME` | `cuga-allinone` | deploy |
| `REGISTRY_SECRET` | `icr-secret-1` | deploy |
| `ENV_FILE` | `build/.env` | deploy |
| `CPU` / `MEMORY` | `4` / `16G` | deploy |
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
