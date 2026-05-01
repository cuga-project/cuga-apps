# Deploying `recipe_composer` and `city_beat`

Step-by-step runbook for getting the two new apps from your laptop onto
IBM Cloud Code Engine and lit up in the umbrella UI as ship-ready tiles.
Both apps share the same image as the existing 19 cuga-apps, so the path
is short.

For the broader CE setup (project creation, ICR registry, secrets, MCP
server deployment), see [CLOUD_ENGINE_DEPLOYMENT.md](CLOUD_ENGINE_DEPLOYMENT.md).
This doc only covers what you do **after** that's all in place.

---

## Wiring summary (already done in this PR)

| File | What changed | Purpose |
|---|---|---|
| [apps/_ports.py](apps/_ports.py) | Added `recipe_composer: 28820`, `city_beat: 28821` to `APP_PORTS` | Single source of truth for ports |
| [apps/launch.py](apps/launch.py) | Added two `dict(name=…, kind="app", …)` rows to `PROCS` | `python apps/launch.py` brings them up locally with the rest |
| [start.sh](start.sh) | Added two `python <app>/main.py --port …` lines | Container startup script (used inside the docker image) |
| [docker-compose.yml](docker-compose.yml) | Added `28820:28820` and `28821:28821` port mappings on the `apps` service | `docker compose up` exposes both apps |
| [deploy_apps.sh](deploy_apps.sh) | Added two rows to `TIER1` (stateless tier, min-scale 0) | Picked up by `./deploy_apps.sh` |
| [ui/src/data/usecases.ts](ui/src/data/usecases.ts) | Added two `UseCase` entries with `id: 'recipe-composer'` and `id: 'city-beat'` | Tiles in the umbrella UI |
| [ui/src/data/deployment.ts](ui/src/data/deployment.ts) | Added both ids to `CE_APP_BY_ID` | "Launch App" button on HF/CE points at the right CE URL |

The umbrella UI's stage filter defaults every app to **ship-ready** (✦
amber badge, sorted to the top of the list) unless the id is listed in
`FOR_LATER_IDS` or `EXPLORATORY_IDS` in
[ui/src/pages/Home.tsx](ui/src/pages/Home.tsx). Neither new id is in
those sets, so both land in ship-ready automatically.

`Dockerfile.apps` does `COPY apps/ ./apps/` — the new app folders are
already inside `apps/`, so no Dockerfile change is required.

---

## Prerequisites

Make sure you've already done these (one-time setup, covered in
`CLOUD_ENGINE_DEPLOYMENT.md`):

```bash
# IBM Cloud auth
ibmcloud login --sso
ibmcloud target -r us-south -g <your-resource-group>

# Code Engine project selected
ibmcloud ce project select --name <your-project>

# CE secrets exist
ibmcloud ce secret get   --name app-env       # bag of LLM_PROVIDER, LLM_MODEL, ANTHROPIC_API_KEY, …
ibmcloud ce registry get --name icr-secret-1  # ICR pull credentials

# 8 MCP servers deployed (recipe_composer doesn't need them, but city_beat does)
ibmcloud ce app list | grep '^cuga-apps-mcp-'
# → expect 8 rows: web, knowledge, geo, finance, code, local, text, invocable_apis

# docker daemon running, ibmcloud CLI on PATH
docker info >/dev/null
ibmcloud --version
```

`city_beat` calls four MCP servers (`geo`, `web`, `knowledge`,
`finance`); confirm those four respond before deploying the app:

```bash
for s in geo web knowledge finance; do
  url="https://cuga-apps-mcp-$s.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp"
  printf "%-12s " "$s"
  curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 "$url"
done
# Each should print "HTTP 406" (the streamable-HTTP MCP endpoint rejecting
# a plain GET). 406 = up. Anything else (404, 502, timeout) = fix that first.
```

`recipe_composer` is inline-only — no MCP dependencies to verify.

---

## Step 1 — Smoke test locally

Before pushing the image, prove both apps actually run on your machine.
This catches missing imports, broken UIs, and bad system prompts in seconds.

```bash
cd /path/to/cuga-apps

export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-…
export CUGA_TARGET=ce        # so city_beat hits the deployed CE MCP servers

# recipe_composer (inline-only; no MCP)
python apps/recipe_composer/main.py --port 28820 &
RC_PID=$!
sleep 2
curl -s http://localhost:28820/health         # → {"ok": true}
curl -s -X POST http://localhost:28820/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"I have chicken, rice, and broccoli. What can I cook?","thread_id":"smoke"}'
kill $RC_PID

# city_beat (MCP + inline)
python apps/city_beat/main.py --port 28821 &
CB_PID=$!
sleep 4
curl -s http://localhost:28821/health
curl -s -X POST http://localhost:28821/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Brief me on Lisbon","thread_id":"smoke"}'
kill $CB_PID
```

If `/ask` for `city_beat` errors with an MCP timeout, double-check
`CUGA_TARGET=ce` is set or pin the URLs explicitly:

```bash
export MCP_GEO_URL=https://cuga-apps-mcp-geo.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
export MCP_WEB_URL=https://cuga-apps-mcp-web.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
export MCP_KNOWLEDGE_URL=https://cuga-apps-mcp-knowledge.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
export MCP_FINANCE_URL=https://cuga-apps-mcp-finance.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
```

---

## Step 2 — Build + push the apps image

The two new apps are baked into the **same shared image** as the other
19 (`Dockerfile.apps` does `COPY apps/ ./apps/`), so this is a single
build that picks them up automatically.

```bash
cd /path/to/cuga-apps

# Login to ICR if you haven't recently
ibmcloud cr login

# Build + push :latest (linux/amd64, required by CE)
./build_apps_image.sh

# Or pin a tag for traceability
IMAGE_TAG=v$(date +%Y%m%d-%H%M) ./build_apps_image.sh

# Build only — skip the push (useful for local docker-compose runs)
./build_apps_image.sh --no-push
```

Verify the image landed in ICR:

```bash
ibmcloud cr image-list --restrict "$NAMESPACE/apps" | head
```

The defaults are `REGION=us-south`, `NAMESPACE=routing_namespace`,
`IMAGE_TAG=latest`. Override via env for a different project. The image
ends up at `icr.io/<NAMESPACE>/apps:<TAG>`.

---

## Step 3 — Deploy the two CE apps

Both apps are listed in the `TIER1` array in `deploy_apps.sh` (stateless
posture, `min-scale 0` so they cold-start on first request). Deploy
them — alone or alongside the rest:

```bash
# Just the two new apps
./deploy_apps.sh recipe_composer city_beat

# Or every app — picks up the two new ones automatically
./deploy_apps.sh
```

The script is idempotent: if the CE app already exists it does
`ibmcloud ce app update --image <…> --force` (which rolls the new image
in); if not, it does `ibmcloud ce app create` with the right
secret-mount + entrypoint flags.

A successful run prints public URLs at the end:

```
recipe_composer        https://cuga-apps-recipe-composer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud
city_beat              https://cuga-apps-city-beat.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud
```

### Verify

```bash
# Recipe Composer — inline-only, should respond on the first warm request
RC_URL=https://cuga-apps-recipe-composer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud
curl -s "$RC_URL/health"
curl -s -X POST "$RC_URL/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"I have eggs, spinach, and tomato. What can I cook?","thread_id":"prod-smoke"}'

# City Beat — MCP-backed, may take 5–10 s on cold start while the bridge
# handshakes with the four MCP servers.
CB_URL=https://cuga-apps-city-beat.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud
curl -s "$CB_URL/health"
curl -s -X POST "$CB_URL/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Brief me on Lisbon","thread_id":"prod-smoke"}'
curl -s "$CB_URL/session/prod-smoke" | python3 -m json.tool | head -40
```

If something fails, debug per-app:

```bash
ibmcloud ce app events --name cuga-apps-recipe-composer | tail -30
ibmcloud ce app logs   --name cuga-apps-recipe-composer --tail 100

ibmcloud ce app events --name cuga-apps-city-beat | tail -30
ibmcloud ce app logs   --name cuga-apps-city-beat   --tail 100
```

Common gotchas (full list in
[CLOUD_ENGINE_DEPLOYMENT.md § Troubleshooting](CLOUD_ENGINE_DEPLOYMENT.md#troubleshooting)):

- **`OPENAI_API_KEY must be set`** — the CE secret `app-env` doesn't
  have the key your `LLM_PROVIDER` requires. `ibmcloud ce secret update
  --name app-env --from-literal=ANTHROPIC_API_KEY=…` and re-deploy.
- **`ImagePullBackOff … EOF`** — transient ICR error. The script retries
  3× automatically; if it still fails, wait 30 s and re-run.
- **City Beat `/ask` returns `tool error`** — one of the four MCP
  servers is down. Re-run the curl loop in "Prerequisites" above to find
  which one.

---

## Step 4 — Rebuild + redeploy the umbrella UI

The UI tiles + ship-ready bucketing live in
`ui/src/data/{usecases.ts, deployment.ts}` — already updated in this PR.
You need to re-bake those into the UI bundle and redeploy:

```bash
# Rebuild + push the UI image (linux/amd64)
./build_ui_image.sh

# Redeploy to whichever surface you use:
./deploy_ui.sh                  # Code Engine
# or
./deploy_ui.sh --target hf      # Hugging Face Space (if that's your demo surface)
```

Open the umbrella UI; both new apps appear at the top of the list
(✦ ship-ready badge, amber). Clicking the tile opens the CE URL via
`resolveAppUrl`.

If the tile renders but "Launch App" is missing, check that the id is
in `CE_APP_BY_ID` in
[ui/src/data/deployment.ts](ui/src/data/deployment.ts) — the app needs
to be in that map for the HF/CE bundle to expose a URL for it.

---

## One-liner — the whole thing end-to-end

For the impatient, after the prerequisites are in place:

```bash
cd /path/to/cuga-apps

export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-…

ibmcloud cr login
./build_apps_image.sh                              # 1) rebuild shared image
./deploy_apps.sh recipe_composer city_beat         # 2) roll the two CE apps
./build_ui_image.sh && ./deploy_ui.sh              # 3) refresh umbrella UI

# 4) confirm both apps are live
for app in cuga-apps-recipe-composer cuga-apps-city-beat; do
  url=$(ibmcloud ce app get --name "$app" --output url 2>/dev/null)
  printf "%-32s %s\n" "$app" "$url"
  curl -s -o /dev/null -w "  /health → HTTP %{http_code}\n" --max-time 10 "$url/health"
done
```

---

## Rolling back

The `deploy_apps.sh` `update` path defaults to `:latest`, so re-deploying
with the prior image tag rolls back:

```bash
IMAGE_TAG=<previous-tag> ./deploy_apps.sh recipe_composer city_beat
```

To remove an app entirely:

```bash
ibmcloud ce app delete --name cuga-apps-recipe-composer --force
ibmcloud ce app delete --name cuga-apps-city-beat       --force
```

Then drop them from `TIER1` in `deploy_apps.sh`, the two `UseCase`
entries in `usecases.ts`, the two ids in `deployment.ts`, the two port
mappings in `docker-compose.yml`, the two lines in `start.sh`, and the
two entries in `apps/_ports.py` + `apps/launch.py`. Rebuild + redeploy
the UI to make the tiles disappear.
