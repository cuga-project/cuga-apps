# Deploying cuga-apps to IBM Cloud Code Engine

Operator playbook for deploying the cuga-apps stack to IBM Cloud Code Engine
(CE). Captures the one-time setup, the per-image build/push, the per-service
deploy, and every footgun we hit getting there.

For the conversational deployment assistant version of this, see the
[code_engine_deployer cuga-app](apps/code_engine_deployer/README.md) — it does
much of this interactively. This doc is for hand-deployment from a terminal.

---

## Table of contents

- [What's in scope (and what isn't)](#whats-in-scope-and-what-isnt)
- [Script reference (build vs deploy)](#script-reference-build-vs-deploy)
- [Prerequisites](#prerequisites)
- [Step 1 — IBM Cloud project + ICR](#step-1--ibm-cloud-project--icr)
- [Step 2 — Secrets](#step-2--secrets)
- [Step 3 — Build + push the images](#step-3--build--push-the-images)
- [Step 4 — Deploy the 7 MCP servers](#step-4--deploy-the-7-mcp-servers)
- [Step 5 — Deploy mcp-tool-explorer](#step-5--deploy-mcp-tool-explorer)
- [Step 6 — Deploy the umbrella UI (Code Engine *or* Hugging Face)](#step-6--deploy-the-umbrella-ui-code-engine-or-hugging-face)
- [Step 7 — Deploy the FastAPI apps](#step-7--deploy-the-fastapi-apps)
- [Step 8 — Connect the UI to your Code Engine deployment](#step-8--connect-the-ui-to-your-code-engine-deployment)
- [Step 9 — What's still pending](#step-9--whats-still-pending)
- [Troubleshooting](#troubleshooting)

---

## What's in scope (and what isn't)

The cuga-apps compose has 11 services. Their CE-readiness verdicts (from the
deployer's classifier) are:

| Service | Verdict | Plan |
|---|---|---|
| `mcp-web`, `mcp-knowledge`, `mcp-geo`, `mcp-finance`, `mcp-code`, `mcp-local`, `mcp-text` | needs_work → ready | one shared image, 7 CE apps |
| `mcp-tool-explorer` | needs_work → ready | own image, env vars wire it to MCP URLs |
| `ui` | needs_work → ready | own image |
| `apps` (26 FastAPI processes in one container) | wont_fit | split into 26 CE apps from one shared image |
| `mcp-invocable_apis` | wont_fit | needs BIRD data + writable state — see [Step 9](#step-9--whats-still-pending) |

**Out of scope:** the [chief_of_staff](chief_of_staff/) stack lives in its own
compose file and isn't covered here.

**Local-only:** the [code_engine_deployer](apps/code_engine_deployer/) cuga-app
isn't deployed to CE — it shells out to `ibmcloud` and `docker` and needs your
local IBM auth.

---

## Script reference (build vs deploy)

The repo ships six shell scripts that do the heavy lifting. They split cleanly
into **builders** (produce + push images) and **deployers** (push images into
running services on Code Engine, Docker Hub, or Hugging Face Spaces).

| Layer | Build (image) | Deploy (running service) |
|---|---|---|
| MCP servers + tool-explorer | [build_mcp_image.sh](build_mcp_image.sh) → `icr.io/<ns>/mcp` and `icr.io/<ns>/mcp-tool-explorer` | [deploy_mcp.sh](deploy_mcp.sh) → 7 CE apps + tool-explorer |
| 19 cuga-apps (one shared image) | [build_apps_image.sh](build_apps_image.sh) → `icr.io/<ns>/apps` | [deploy_apps.sh](deploy_apps.sh) → 19 CE apps |
| Umbrella UI | [build_ui_image.sh](build_ui_image.sh) → Docker Hub `<user>/cuga-apps-ui` | [deploy_ui.sh](deploy_ui.sh) → Docker Hub push + HF Space sync |

All three builders default to `--platform linux/amd64`, default tag `latest`,
default ICR namespace `routing_namespace` (apps + MCP) or Docker Hub user
`amurthi44g1wd` (UI). All three accept `--no-push` to build only. All three
deployers are idempotent (create-or-update) and continue past per-service
failures with a summary at the end.

Two helper scripts are *not* deployers — they run inside containers:

- [entrypoint.sh](entrypoint.sh) — sources the mounted `app.env` secret before
  exec'ing the real command.
- [start.sh](start.sh) — launches all 19 `python <app>/main.py` background
  processes inside the local-only `cuga-apps-apps` compose container.

The end-to-end order, when changing anything:

```bash
# Build
./build_mcp_image.sh         # MCPs + tool-explorer
./build_apps_image.sh        # 19 cuga-apps
./build_ui_image.sh          # umbrella UI (to Docker Hub)

# Deploy
./deploy_mcp.sh              # MCPs (must come before apps — apps need MCP URLs)
./deploy_apps.sh             # 19 apps
HF_TOKEN=hf_xxx ./deploy_ui.sh   # UI to HF Space (or skip and serve UI from CE — see Step 6)
```

The rest of this doc walks each step in detail.

---

## Prerequisites

### CLI tools (operator workstation)

```bash
# IBM Cloud CLI + plugins
ibmcloud plugin install code-engine
ibmcloud plugin install container-registry

# Confirm docker daemon is running
docker version
```

### Authenticate

```bash
ibmcloud login --sso
ibmcloud target -r us-south -g <your-resource-group>   # change region/RG
```

### Decide on three values you'll reuse

```bash
export REGION=us-south
export PROJECT=<your-CE-project-name>
export NAMESPACE=cuga-apps                 # ICR namespace
export REPO_ROOT=/home/amurthi/work/agent-apps/cuga-apps
export REG=$REGION.icr.io/$NAMESPACE
```

---

## Step 1 — IBM Cloud project + ICR

### Create / select your CE project

```bash
ibmcloud ce project list
ibmcloud ce project create --name "$PROJECT"        # if it doesn't exist
ibmcloud ce project select --name "$PROJECT"
ibmcloud ce project current                          # confirm
```

### Set up ICR

```bash
ibmcloud cr region-set "$REGION"
ibmcloud cr namespace-add "$NAMESPACE"               # idempotent
ibmcloud cr login                                    # logs local docker into icr.io
```

You should see `Login Succeeded` at the end of `cr login`.

### Generate a pull-credentials API key

CE needs a credential to pull images from ICR.

```bash
ibmcloud iam api-key-create ce-icr -d "CE pull from ICR" --file ~/ce-icr-key.json
APIKEY=$(python3 -c "import json; print(json.load(open('$HOME/ce-icr-key.json'))['apikey'])")

ibmcloud ce registry create \
  --name icr-secret \
  --server "$REGION.icr.io" \
  --username iamapikey \
  --password "$APIKEY"

ibmcloud ce registry list                            # confirm "icr-secret" appears
```

> **Footgun avoided:** the API key gets baked into the registry secret. If you
> ever delete or rotate the key, you must re-run `ibmcloud ce registry update`
> with the new key, otherwise every deploy fails with `ImagePullBackOff`.

---

## Step 2 — Secrets

The local stack mounts `apps/.env` as a single read-only file at
`/run/secrets/app.env`, and [entrypoint.sh](entrypoint.sh) `source`s it at
container start. We need to replicate that on CE.

### Create the env secret

> **Footgun avoided.** The natural-looking `--from-env-file` produces a CE
> secret with one *key per line* of the .env file, not one secret containing
> the whole file. Mounting that produces files like `/run/secrets/RITS_API_KEY`
> instead of `/run/secrets/app.env`. The cuga-apps entrypoint won't find what
> it expects, env vars never get loaded, and tool calls silently fail with
> `missing_key` errors. Use `--from-file` instead, with a literal key name:

```bash
ibmcloud ce secret create \
  --name app-env \
  --from-file app.env="$REPO_ROOT/apps/.env"

ibmcloud ce secret get --name app-env                # should show ONE key: "app.env"
```

That produces a secret with one key (`app.env`) whose value is the entire
.env file's contents. Mounting it gives the entrypoint exactly what it
expects.

---

## Step 3 — Build + push the images

Three build scripts cover everything except `mcp-invocable_apis` (see
[Step 9](#step-9--whats-still-pending)). All three build for `linux/amd64`
and push by default; pass `--no-push` to build only.

```bash
cd "$REPO_ROOT"

./build_mcp_image.sh          # icr.io/<ns>/mcp + mcp-tool-explorer
./build_apps_image.sh         # icr.io/<ns>/apps  (only needed for Step 7)
./build_ui_image.sh           # docker.io/<user>/cuga-apps-ui (Docker Hub, not ICR)
```

Override defaults via env vars (consistent across all three):

```bash
IMAGE_TAG=v3 ./build_mcp_image.sh           # versioned tag instead of :latest
NAMESPACE=my-other-ns ./build_apps_image.sh # different ICR namespace
DOCKERHUB_USER=me ./build_ui_image.sh       # different Docker Hub user
```

The `build_mcp_image.sh` script can also build just one of its two images:

```bash
./build_mcp_image.sh mcp              # only the shared MCP image
./build_mcp_image.sh tool-explorer    # only the explorer
```

> **Why is the UI on Docker Hub instead of ICR?** The umbrella UI is consumed
> by a public Hugging Face Space. HF Spaces pull from public registries; ICR
> would require a registry secret on every Space. Docker Hub keeps it simple.
> See [Step 6](#step-6--deploy-the-umbrella-ui-code-engine-or-hugging-face)
> for the alternative path of serving it from CE alongside the apps.

> **Apple Silicon note.** The scripts pin `--platform linux/amd64`. CE runs
> amd64; an arm64 image silently builds and pushes from an M-series Mac and
> then fails to start with `exec format error` on CE. Don't drop the flag.

Confirm the tags landed:

```bash
ibmcloud cr image-list | grep -E "mcp|apps"
docker manifest inspect amurthi44g1wd/cuga-apps-ui:latest >/dev/null && echo "UI ok"
```

---

## Step 4 — Deploy the 7 MCP servers

Use [deploy_mcp.sh](deploy_mcp.sh) — idempotent, retries on transient registry errors,
mounts the secret at a non-conflicting path (more on this below).

```bash
cd "$REPO_ROOT"
./deploy_mcp.sh                            # all 7
./deploy_mcp.sh text                       # one
./deploy_mcp.sh web knowledge geo          # subset
```

> **Footgun avoided — secret mount path.** Don't mount your secret at
> `/run/secrets`. Kubernetes (which CE runs on top of) auto-mounts a
> serviceaccount token at `/var/run/secrets/kubernetes.io/serviceaccount`,
> and `/var/run` is a symlink to `/run` in most images. Mounting your own
> secret at `/run/secrets` makes that path read-only, blocking the kube
> mount. Containers fail with:
>
> ```
> mkdirat ...rootfs/run/secrets/kubernetes.io: read-only file system
> ```
>
> deploy_mcp.sh mounts at `/etc/cuga-secrets` instead and sets the
> `CUGA_SECRETS_FILE` env var so the entrypoint reads from the new path.

Capture the URLs — needed for the next step:

```bash
for name in web knowledge geo finance code local text; do
  url=$(ibmcloud ce app get --name "cuga-apps-mcp-$name" --output url)
  echo "MCP_${name^^}_URL=$url/mcp"
done
```

---

## Step 5 — Deploy mcp-tool-explorer

`deploy_mcp.sh` includes the explorer by default, so if you ran it in Step 4
you're already done. To deploy *only* the explorer (e.g. when re-running after
URL changes):

```bash
./deploy_mcp.sh tool-explorer
```

Under the hood the script reads the public CE URL of every `cuga-apps-mcp-*`
app that's already deployed and passes them as `MCP_<NAME>_URL=...` env vars
to the explorer container. Locally, the explorer uses docker compose service
DNS (`http://mcp-web:29100/mcp`); on CE there's no service DNS, hence the
explicit env-var injection.

Open `ibmcloud ce app get --name cuga-apps-mcp-tool-explorer --output url` in a
browser — all 7 MCPs should show as online. Any that you skipped in Step 4 will
appear offline; rerun `./deploy_mcp.sh tool-explorer` later to pick them up.

---

## Step 6 — Deploy the umbrella UI (Code Engine *or* Hugging Face)

You can serve the umbrella UI from either Code Engine (private to your CE
project) or a public Hugging Face Space. Pick one — the same image works for
both.

The image carries **no secrets** (build context is `ui/` only,
[ui/.dockerignore](ui/.dockerignore) explicitly excludes `*.env` / `*.key` /
`*.pem` / `credentials*.json`, and the only env var the SPA reads is
`VITE_DEPLOYMENT_TARGET`). It's safe to publish on a public registry.

### 6a — Code Engine (private, internal only)

If you only want CE-internal access, deploy the UI image straight to CE
alongside everything else:

```bash
ibmcloud ce app create \
  --name cuga-apps-ui \
  --image "amurthi44g1wd/cuga-apps-ui:latest" \
  --port 7860 \
  --cpu 0.5 --memory 512M \
  --min-scale 0 --max-scale 1
```

> **Why port 7860 and not 80?** The image's nginx listens on 7860 (a
> non-privileged port) because Hugging Face Spaces rejects `app_port < 1025`
> and we want the same image on both targets. Local `docker-compose.yml`
> still maps host `:3001` → container `:7860`, so nothing changes for local
> dev. See the troubleshooting entry
> [HF Space rejects "app_port must be greater than or equal to 1025"](#hf-space-rejects-app_port-must-be-greater-than-or-equal-to-1025).

### 6b — Hugging Face Space (public, recommended for demos)

This is the path the repo is set up for. The Space at
`https://huggingface.co/spaces/<user>/<space>` is just a Dockerfile that does
`FROM amurthi44g1wd/cuga-apps-ui:<tag>` — `deploy_ui.sh` writes that file,
commits it, and pushes to the Space repo. HF rebuilds whenever the Dockerfile
changes (or whenever `deploy_ui.sh` bumps `.deploy-marker`, which it does on
every run).

```bash
# One-time: log into Docker Hub as amurthi44g1wd (or override DOCKERHUB_USER).
docker login -u amurthi44g1wd          # use a Docker Hub access token, not the password

# One-time: create the Space at https://huggingface.co/new-space
#   - Owner: anupamamurthi (or override HF_USER)
#   - Name:  agent-agents-apps (or override HF_SPACE)
#   - SDK:   Docker

# One-time: generate an HF token at https://huggingface.co/settings/tokens
#   - Scope: "Write" on Spaces
export HF_TOKEN=hf_xxx

# Then on every UI change:
./build_ui_image.sh                    # build + push to Docker Hub
./deploy_ui.sh                         # push (again, idempotent) + sync HF Space
```

`deploy_ui.sh` is two stages and you can run them independently:

```bash
./deploy_ui.sh --skip-hf               # only the Docker Hub push
./deploy_ui.sh --skip-dockerhub        # only the HF Space sync (image already on Hub)
./deploy_ui.sh --dry-run               # plan only, no I/O
```

It writes a fresh `Dockerfile`, `README.md` (with the `sdk: docker, app_port:
7860` frontmatter HF requires) and a `.deploy-marker` timestamp into the
Space, then `git push`es. The `.deploy-marker` is what forces HF to rebuild
even when the image tag string didn't change (e.g. you republished `:latest`
to Docker Hub).

> **What if the UI image is on ICR instead of Docker Hub?** HF Spaces can pull
> from any public registry, but private ICR repos would need an HF
> registry-credential secret. Docker Hub avoids that — that's why
> `build_ui_image.sh` targets `docker.io/<user>/cuga-apps-ui` instead of
> `icr.io/<ns>/ui`.

Note that the umbrella UI's tiles link to the FastAPI apps under `apps/`.
Until [Step 7](#step-7--deploy-the-fastapi-apps) is done those tiles will
load but most clicks will 404. Step 8 covers how the UI is wired to find your
specific CE project's app URLs at runtime.

---

## Step 7 — Deploy the FastAPI apps

This is the hard part. The local stack runs all 26 cuga-apps as background
processes inside a single `apps` container, each on its own port (28xxx).
Code Engine routes one HTTP port per app, so we need **26 separate CE apps
from one shared image**.

### 7.1 — Pattern: deploy ONE FastAPI app

Take `web_researcher` (port 28798) as the example:

```bash
ibmcloud ce app create \
  --name cuga-apps-web-researcher \
  --image "$REG/apps:latest" \
  --registry-secret icr-secret \
  --port 28798 \
  --command python \
  --argument /app/apps/web_researcher/main.py --argument --port --argument 28798 \
  --mount-secret /etc/cuga-secrets=app-env \
  --env CUGA_SECRETS_FILE=/etc/cuga-secrets/app.env \
  --env CUGA_IN_DOCKER=1 \
  --env "MCP_WEB_URL=$(ibmcloud ce app get --name cuga-apps-mcp-web --output url)/mcp" \
  --env "MCP_KNOWLEDGE_URL=$(ibmcloud ce app get --name cuga-apps-mcp-knowledge --output url)/mcp" \
  --cpu 1 --memory 2G \
  --min-scale 0 --max-scale 1
```

Three things to notice:

1. **Same image, different command.** `--image $REG/apps:latest` is shared;
   `--command` + `--argument` selects which `main.py` inside the image runs.
   Cheaper to maintain than 26 images.
2. **MCP_*_URL env vars** point each FastAPI app at the deployed MCP servers
   from Step 4. Only pass the ones each app actually uses (see each app's
   README for its `mcpUsage` block) — extra env vars are harmless but noisy.
3. **`min-scale 0`** — apps scale to zero when idle, save money. First
   request to a cold app pays a 5–10s cold-start. Bump to `min-scale 1`
   for any app you want always-warm.

### 7.2 — Storage tiers

Each cuga-app falls into one of three tiers based on its persistence needs.
This determines how cleanly it deploys to CE:

| Tier | Apps | Deploys cleanly? |
|---|---|---|
| **Stateless** — no host writes; pure MCP-mediated work | web_researcher, paper_scout, travel_planner, code_reviewer, hiking_research, movie_recommender, webpage_summarizer, wiki_dive, youtube_research, arch_diagram, brief_budget, trip_designer, ibm_cloud_advisor, ibm_docs_qa, ibm_whats_new, api_doc_gen, stock_alert | ✅ yes |
| **In-memory state, lost on restart** — session-scoped state, no persistence | newsletter (feed history), server_monitor (alert log), code_reviewer (review history) | ⚠️ yes, but state resets on every cold start. Acceptable for demos. |
| **Persisted local state** — the local stack uses bind-mounted directories or SQLite files | smart_todo (SQLite + reminder watcher), voice_journal (audio storage), drop_summarizer (file-watched inbox), deck_forge (output files), video_qa (heavy ML cache), box_qa (PDFs + Box auth), bird_invocable_api_creator (BIRD data + outputs) | ❌ no — needs storage migration before deploy |

### 7.3 — Deploying tier 1 (stateless apps)

Use [deploy_apps.sh](deploy_apps.sh) — same shape as `deploy_mcp.sh`,
idempotent (create-or-update), retries on transient registry pulls,
continues past per-app failures with a final summary.

```bash
./deploy_apps.sh                                     # all 19
./deploy_apps.sh web_researcher                      # one
./deploy_apps.sh paper_scout code_reviewer api_doc_gen   # subset
```

It uses `--mount-secret /etc/cuga-secrets=app-env` and
`CUGA_SECRETS_FILE=/etc/cuga-secrets/app.env` exactly like `deploy_mcp.sh` —
same secret-mount-path footgun avoidance.

> **Per-app MCP URLs.** `deploy_apps.sh` *doesn't* inject `MCP_*_URL` env vars
> per app. Instead, every cuga-app's [_mcp_bridge.py](apps/_mcp_bridge.py)
> auto-detects Code Engine at runtime (CE injects `CE_APP` / `CE_REVISION`)
> and constructs the public CE URL of the matching `cuga-apps-mcp-*` app on
> the fly. The CE project hash + region default to constants in
> `_mcp_bridge.py`; CE injects `CE_SUBDOMAIN` and `CE_REGION` at runtime,
> which override the constants. You can still pin a specific MCP server with
> an explicit `MCP_<NAME>_URL=...` env var if needed (e.g. to point at a
> tunnel).

The 17 tier-1 apps each take ~30–60s to come `ready`.

### 7.4 — Tier 2 — accept ephemeral state

For `newsletter`, `server_monitor`, etc., the in-memory state just resets on
each cold start. Two ways to handle:

- **Run with `--min-scale 1`** so the container never restarts as long as the
  CE app exists. State persists for the lifetime of the deployment but is
  lost on `app update` or rolling restart.
- **Accept the reset.** For demo apps showing "what could the agent do," a
  fresh state on each cold start is often fine.

Same `deploy_app` pattern as tier 1, with `--min-scale 1`.

### 7.5 — Tier 3 — needs storage migration

The 7 apps in tier 3 each have a slightly different persistence shape. Three
generic strategies:

#### Strategy A — IBM Cloud Object Storage (COS)

Replace local file paths with `s3://...` and point the app at COS via
boto3 / s3fs. Clean for blob-shaped data (audio, PDFs, generated decks),
but requires changes to the app's storage layer. Moderate effort.

For each affected app:
1. Provision a COS bucket per app.
2. Generate HMAC credentials and store them in the app-env secret.
3. Edit `apps/<name>/store.py` (or wherever the app touches local FS) to
   use S3 instead.

#### Strategy B — CE PVC (persistent volume)

CE supports persistent volumes, but each one needs to be provisioned and
mounted. Less code change than COS but per-app provisioning overhead, and
PVCs aren't on every CE plan tier.

```bash
# Example pattern — adapt per app
ibmcloud ce pv create --name smart-todo-data --size 1G
ibmcloud ce app update --name cuga-apps-smart-todo \
  --mount-pv /app/apps/smart_todo/storage=smart-todo-data
```

#### Strategy C — managed external service

For SQLite-backed apps (`smart_todo`), point them at a managed Postgres
(IBM Cloud Databases for PostgreSQL). Most invasive — touches data model
and the entire app's persistence layer — but produces the most production-
ready deployment.

#### Recommendation

For first-pass deploys: **skip tier-3 apps**. They work fine when run locally
and pointed at the deployed MCPs (set `MCP_*_URL` in your local shell to the
CE URLs). Migrate them one at a time as actual usage demands persistence.

---

## Step 8 — Connect the UI to your Code Engine deployment

The umbrella UI is a static SPA. The "Try it out" / "Launch App" links in
[ui/src/data/usecases.ts](ui/src/data/usecases.ts) are written as
`http://localhost:28xxx`, which obviously won't work for a remote visitor.
[ui/src/data/deployment.ts](ui/src/data/deployment.ts) rewrites those URLs at
runtime based on where the UI is being served from.

### Detection — three contexts in priority order

1. **Build-time override** — `VITE_DEPLOYMENT_TARGET=huggingface` baked into
   the bundle via `./build_ui_image.sh --target huggingface`. Always wins
   when set.
2. **Runtime hostname** — `window.location.hostname` ends in `.hf.space` or
   `.huggingface.co`. Auto-detected, no rebuild needed.
3. **Otherwise (local)** — links rewritten so `localhost` becomes
   `window.location.hostname`, so the UI works over remote IP / SSH tunnel /
   reverse proxy.

### URL rewriting — what the SPA actually does

When the target is `huggingface`, every `appUrl` in `usecases.ts` is replaced
with the public CE URL of the corresponding app:

```
http://localhost:28798
   ↓
https://cuga-apps-web-researcher.<project-hash>.<region>.codeengine.appdomain.cloud
```

Apps that aren't in the hardcoded `CE_APP_BY_ID` map get their "Launch App"
button suppressed (rather than showing a broken link).

### Two hardcodes you must verify

These live at the top of [ui/src/data/deployment.ts](ui/src/data/deployment.ts):

```ts
export const CE_PROJECT_HASH = '1gxwxi8kos9y'   // your CE project's subdomain hash
export const CE_REGION       = 'us-east'        // your CE region
```

If you redeploy in a different CE project or region, edit those constants
and rebuild the UI. They're public information (visible in any
`*.codeengine.appdomain.cloud` URL), so they're safe to ship in a
client-side bundle — no secret handling required.

### Adding a new app to the UI

If you deploy a new cuga-app and want it linkable from the umbrella UI on HF:

1. Add an entry to `CE_APP_BY_ID` in
   [ui/src/data/deployment.ts](ui/src/data/deployment.ts) mapping the
   `usecases.ts` `id` → the `cuga-apps-<name>` CE app name.
2. Re-run `./build_ui_image.sh && ./deploy_ui.sh` to publish the new bundle.

Without that entry, the tile still renders but the "Launch App" button is
suppressed.

---

## Step 9 — What's still pending

### `mcp-invocable_apis`

Two real blockers:

1. **BIRD dataset** — the server bind-mounts `dev.json` and a `dbs/`
   directory of SQLite snapshots that together can run tens of GB. Options:
   - Bake a pruned subset into a custom image (smaller is better — under 5 GB
     keeps push times reasonable).
   - Stage the data to COS and pull at startup.
2. **Writable `state/` directory** — holds the SQLite registry of
   synthesized API tools. Needs a CE PVC or a managed database.

For first pass: **keep this server running locally** and have your CE-hosted
apps reach it via tunnel (Tailscale, cloudflared, or CE Private Endpoints
if you're on the right plan).

### Tier-3 FastAPI apps

See [Step 7.5](#75--tier-3--needs-storage-migration). Each is its own
storage-migration project.

---

## Troubleshooting

### `ImagePullBackOff` — `failed to resolve image to digest: ... EOF`

Transient ICR connection drop. Re-run the deploy; deploy_mcp.sh retries
automatically up to 3× with backoff. If it still fails:

- `ibmcloud cr image-list | grep <image>` — confirm the tag is in ICR.
- `ibmcloud ce registry get --name icr-secret` — confirm the registry
  secret exists.
- Regenerate the API key (Step 1) if the old one was rotated/deleted, then
  `ibmcloud ce registry update --name icr-secret --password <new-key>`.

### `mkdirat .../rootfs/run/secrets/kubernetes.io: read-only file system`

You mounted your own secret at `/run/secrets`, blocking the
kube-serviceaccount mount. Move the mount to `/etc/cuga-secrets` (or any
path outside `/run/secrets`) and set `CUGA_SECRETS_FILE` to the new path.
deploy_mcp.sh does this correctly; for hand-rolled `app create` calls, mirror
the pattern.

### Tool calls return `missing_key` even though .env has the key

The CE secret was created with `--from-env-file` (one key per line) instead
of `--from-file app.env=...` (single key with the whole file). The
entrypoint can't find `/etc/cuga-secrets/app.env`. Recreate the secret per
[Step 2](#step-2--secrets) and `app update --force` each app to remount.

### `binary_missing` errors from the deployer cuga-app

You're running [code_engine_deployer/main.py](apps/code_engine_deployer/main.py)
inside the apps container or some other host without `ibmcloud` / `docker`
on PATH. Run it from your workstation —
[apps/code_engine_deployer/README.md](apps/code_engine_deployer/README.md)
has the local-install instructions.

### App scales but never serves traffic / 502s

The app inside the container is listening on a different port than what
you passed to `--port`. Confirm the cuga-app's `main.py --port <X>` matches
the `--port X` flag on `ibmcloud ce app create`.

### `OOMKilled`

Bump `--memory`. If you're at the 32 GB ceiling, the service likely has to
be split (the local `apps` container hit this — that's why it's deployed
as 26 separate CE apps instead of one).

### Search / synthesis apps return "No answer found" with the LLM clearly producing a response in logs

Logs show `Routing to FinalAnswerAgent with answer: No answer found` after
the model successfully calls tools and produces output, with `state.final_answer`
ending up as an empty string in cuga's `sdk_callback_node`.

Root cause: [apps/_llm.py](apps/_llm.py) (and
[apps/travel_planner/llm.py](apps/travel_planner/llm.py), which has its own
copy) was constructing `ChatWatsonx` with:

```python
params={"temperature": 0, "max_new_tokens": 4096}
```

Recent `langchain_ibm` switched to OpenAI-style chat completions on the
wire. It **silently ignores `params={"max_new_tokens": ...}`** — the field
isn't surfaced as `max_tokens` in the actual request. With no max set,
watsonx defaults to ~1024 output tokens. For reasoning models like
`openai/gpt-oss-120b`, the (private) `reasoning_content` channel can
consume the entire 1024-token budget on its own, leaving zero tokens for
visible `content`. cuga sees an empty assistant message → falls into the
NL-only path with `planning_response = ""` → routes to END with
`final_answer = ""` → SDK callback substitutes `"No answer found"`.

Fix: pass `temperature` / `max_tokens` as **top-level kwargs**, not nested
inside `params`:

```python
return ChatWatsonx(
    model_id=...,
    url=...,
    project_id=project_id,
    temperature=0,
    max_tokens=16000,
)
```

Direct repro on the watsonx endpoint:

```
params={"max_new_tokens": 4096}  → content len: 0  finish_reason: length  output_tokens: 1024
max_tokens=16000 (top-level)     → content len: 6981  finish_reason: stop  output_tokens: 1654
```

Both files in this repo are now patched. If you fork or vendor either, keep
the kwargs at the top level — there's a comment in
[apps/_llm.py](apps/_llm.py) warning against the regression.

### Docker Hub push: `insufficient_scope: ... push access denied, repository does not exist or may require authorization`

Three usual causes:

1. **Not logged in (or as the wrong user).** Check with
   `docker info | grep Username`. If empty or wrong, run
   `docker logout && docker login -u <hub-user>` and supply a
   **Personal Access Token** (not your account password — that no longer
   works for `docker login` on most setups). Generate the token at
   <https://hub.docker.com/settings/security>.
2. **Token has read-only scope.** A "Public Repo Read" PAT will pass
   `docker login` but fail at push. Re-issue the token with
   **Read & Write** (or **Read, Write, Delete**) and re-`docker login`.
3. **Pushing to a namespace you don't own.** Docker Hub auto-creates a repo
   on first push *only* if you're authenticated as the namespace owner.
   Switch via env override:
   ```
   DOCKERHUB_USER=<your-actual-user> ./build_ui_image.sh
   DOCKERHUB_USER=<your-actual-user> ./deploy_ui.sh
   ```

### HF Space rejects `"app_port" must be greater than or equal to 1025`

Hugging Face Spaces runs containers without root and rejects any
privileged port (`<1025`) in the README frontmatter or Dockerfile `EXPOSE`.
The default nginx port is 80, which is privileged.

The repo is set up around port **7860** (HF's traditional default and the
one `deploy_ui.sh` writes into the Space's `app_port` frontmatter):

- [ui/Dockerfile](ui/Dockerfile) — `EXPOSE 7860`
- [ui/nginx.conf](ui/nginx.conf) — `listen 7860;`
- [docker-compose.yml](docker-compose.yml) — host port 3001 maps to
  container 7860 (`ports: ["3001:7860"]`); local dev URL is unchanged.
- [deploy_ui.sh](deploy_ui.sh) — frontmatter `app_port: 7860`

If you change the port, update **all four** in the same commit, then
rebuild + redeploy.

### HF Space push: `pre-receive hook declined` after auth succeeded

Two likely causes:

1. **YAML frontmatter validation failure** — like the `app_port` rejection
   above, or any field HF's schema doesn't recognise. The remote message
   tells you which field. Edit the frontmatter block written by
   `deploy_ui.sh` and re-run.
2. **Token missing the right scope.** Generate a new token at
   <https://huggingface.co/settings/tokens> with **Write** scope on Spaces
   (a generic "read" token will succeed at clone but fail at push). Pass
   the new value via `HF_TOKEN`.

### HF Space rebuilds but old image is still served

HF caches Docker layers aggressively. `deploy_ui.sh` writes a fresh
`.deploy-marker` timestamp on every run so the Dockerfile commit produces a
non-empty diff and HF's build trigger fires. If you bypassed the script and
hand-edited the Space, make sure your push contains *some* change — an
unchanged `Dockerfile` produces no commit and HF sees nothing to do.

### "Launch App" buttons missing or broken on HF

The umbrella UI's
[deployment.ts](ui/src/data/deployment.ts) only rewrites links for apps in
its hardcoded `CE_APP_BY_ID` map. If the tile shows but the launch button
is missing, the app isn't in the map — see
[Step 8 — Adding a new app to the UI](#adding-a-new-app-to-the-ui).

If launch buttons go to wrong URLs (`*.codeengine.appdomain.cloud` 404s),
verify the `CE_PROJECT_HASH` and `CE_REGION` constants at the top of
`deployment.ts` match your actual CE project. Edit + rebuild + redeploy
the UI.
