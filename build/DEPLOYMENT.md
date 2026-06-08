# Deploying CUGA Apps — local, Code Engine, Hugging Face

One end-to-end guide for shipping the **all-in-one** CUGA Apps image and its
lightweight launcher UI. Everything here is consolidated from
[build/README.md](README.md), [build/ce/README.md](ce/README.md), and
[build/hf/README.md](hf/README.md) — read those for deeper detail on any single
target.

---

## What gets deployed

There are **three deployment targets**, built from the same source tree:

```
   ┌──────────────────────────┐        ┌────────────────────────────────────────┐
   │  Hugging Face Space       │ links  │  Code Engine: ONE all-in-one service    │
   │  (static umbrella UI)     │ ─────▶ │  nginx :8080                            │
   │  no backend — just a       │        │   /a/<app>/         → 21 ship-ready apps │
   │  public "front door"       │        │   /a/usage-collector/ → stats dashboard │
   └──────────────────────────┘        │   5 MCP servers (loopback)              │
                                         └────────────────────────────────────────┘
            ▲                                          ▲
            │ build/hf/                                │ build/ce/
            │                                          │
            └───────────  build/Dockerfile  ──────────┘
                          (one image bundles UI + apps + MCP + stats)

   Local dev: the SAME image via build/docker-compose.yml → http://localhost:8080
```

- **Local** ([build/](.)) — run the all-in-one image on your machine with
  `docker compose`. Fastest way to see changes.
- **Code Engine** ([build/ce/](ce)) — the real backend: one CE service running
  the all-in-one image. Heavy, stateful, single instance.
- **Hugging Face** ([build/hf/](hf)) — a static umbrella UI that only *links*
  into the CE service. No backend of its own; the CE URL is baked into the build.

The CE and HF builds compile the UI **fresh from your working tree** inside their
own build steps — so source edits are picked up automatically. You do **not**
need to commit first, and a local rebuild is **not** a prerequisite for CE/HF.

---

## The deployment's fixed coordinates

These are stable for this project (public, safe to commit):

| Thing | Value |
| --- | --- |
| CE app name | `cuga-agent-apps` |
| ICR image | `icr.io/routing_namespace/cuga-agent-apps:latest` |
| Registry | `icr.io` (the **global** ICR registry) |
| IBM Cloud region | `us-east` |
| Resource group | `routing` |
| CE project | `ce-project-routing` (hash `1gxwxi8kos9y`) |
| CE registry secret | `icr-secret-1` (server `icr.io`) |
| Sizing | 12 vCPU / 48 GB / 5 GB disk, scale 1..1 |
| HF Space | `anupamamurthi/cuga-agent-apps` → `https://anupamamurthi-cuga-agent-apps.hf.space/` |

All of these are overridable via env vars on the build/deploy scripts — see the
[config knobs](#config-knobs) table.

---

## One-time prerequisites

```bash
# 1. Log in and target the region + resource group
ibmcloud login --sso
ibmcloud target -r us-east -g routing

# 2. Select the Code Engine project (deploys land in the SELECTED project)
ibmcloud ce project select --name ce-project-routing

# 3. Log local docker into the GLOBAL ICR registry (icr.io) — must match
#    REGISTRY=icr.io in the scripts and --server icr.io in the pull secret.
ibmcloud cr region-set global
ibmcloud cr login

# 4. Create the registry pull secret CE uses (one-time; name = REGISTRY_SECRET).
#    Use an IBM Cloud API key with registry pull access.
ibmcloud ce registry create \
  --name icr-secret-1 \
  --server icr.io \
  --username iamapikey \
  --password <your-icr-apikey>

# 5. Fill in build/.env  (LLM provider keys + TAVILY / OPENTRIPMAP / ALPHA_VANTAGE)
```

> **Registry gotcha.** `cr region-set us-south` logs docker into `us.icr.io`,
> which would NOT match the `icr.io` pull secret → `ImagePullBackOff`. Always use
> `region-set global` for this project.

---

## 1. Local — stop, rebuild, run

### Option A — docker compose (default)

```bash
cd /home/amurthi/cuga-apps/build

# Stop & remove any running container
docker compose down
docker rm -f cuga-allinone cuga-agent-apps 2>/dev/null || true   # clears an old-named one too

# Rebuild the image from source + start fresh
docker compose up -d --build

# Verify
curl http://localhost:8080/healthz        # -> ok
# open http://localhost:8080  — confirm Apps shows by default
```

### Option B — host networking (no bridge; use this if compose fails to create a network)

On RHEL/this box, `docker compose up` can fail at the network-create step with
`failed to create network build_default … iptables: No chain/target/match by
that name` — Docker's iptables chains got flushed (usually a firewalld reload)
and `sudo systemctl restart docker` would normally fix it. If you **can't restart
the daemon**, run with `--network=host` instead: it needs no bridge network and
no `DOCKER-FORWARD` chain, so it sidesteps the failure entirely. (It also avoids
the bridge's DNS-resolver issues on this host.)

```bash
# Build the image (the build itself uses host networking, so it's unaffected)
cd /home/amurthi/cuga-apps
docker build -f build/Dockerfile --network=host -t cuga-apps-allinone:latest .

# Run on the host network — no bridge created, no iptables chain needed
docker rm -f cuga-allinone cuga-agent-apps 2>/dev/null || true
docker run -d --name cuga-agent-apps --network=host --env-file build/.env cuga-apps-allinone:latest

# Verify
curl http://localhost:8080/healthz        # -> ok
```

With `--network=host` the container binds directly to the host's `:8080` — there
is no `-p 8080:8080` mapping (and none is needed). Manage it with plain docker:
`docker logs -f cuga-agent-apps`, `docker restart cuga-agent-apps`,
`docker rm -f cuga-agent-apps`.

Restart vs rebuild: a `restart` reuses the existing image (good for `.env`
changes, read at process start). Source / Dockerfile changes need a rebuild
(`compose up -d --build`, or the `docker build` + `docker run` above).

---

## 2. Code Engine — build, push, deploy

```bash
cd /home/amurthi/cuga-apps/build/ce
./build_and_push.sh        # rebuild + push icr.io/routing_namespace/cuga-agent-apps:latest
./deploy.sh                # create/update the CE app (12 vCPU / 48G / 5G disk)
ibmcloud ce app get --name cuga-agent-apps --output url     # note this URL for step 3
```

- `deploy.sh` syncs `build/.env` into a CE secret (`cuga-agent-apps-env`) and
  attaches it with `--env-from-secret` — secrets never go on the command line.
- Updates happen **in place** (a new revision); the URL stays the same.
- `CUGA_TARGET=local` is forced so the in-container MCP servers are used. Never
  set it to `ce` for this image.

---

## 3. Hugging Face — build static UI, republish

```bash
cd /home/amurthi/cuga-apps/build/hf
ALLINONE_BASE=https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud ./build.sh     # bakes the CE URL into the bundle → dist/

rm -rf /tmp/space
git clone git@hf.co:spaces/anupamamurthi/cuga-agent-apps /tmp/space
cp -r /home/amurthi/cuga-apps/build/hf/dist/. /tmp/space/
cd /tmp/space && git add -A && git commit -m "umbrella UI" && git push
```

- The CE URL is **baked into the static bundle**. If the CE URL ever changes,
  rebuild and re-push.
- After pushing, hard-refresh the Space and confirm Apps renders immediately and
  the nav is **Apps / MCP Servers / Stats ↗ / Feedback ↗**.
- The Space serves at `https://anupamamurthi-cuga-agent-apps.hf.space/`.

---

## Typical update flow

When you change app/UI/MCP source and want it live everywhere:

```bash
# CE (the real backend)
cd build/ce && ./build_and_push.sh && ./deploy.sh
URL=$(ibmcloud ce app get --name cuga-agent-apps --output url)

# HF (the launcher) — only needed if you changed the umbrella UI or the CE URL
cd ../hf && ALLINONE_BASE="$URL" ./build.sh
rm -rf /tmp/space && git clone git@hf.co:spaces/anupamamurthi/cuga-agent-apps /tmp/space
cp -r "$(pwd)/dist/." /tmp/space/ && cd /tmp/space && git add -A && git commit -m "ui" && git push
```

---

## Config knobs

Env-var overrides on the build/deploy scripts (defaults shown):

| Var | Default | Used by |
| --- | --- | --- |
| `NAMESPACE` | `routing_namespace` | build + deploy |
| `IMAGE_NAME` | `cuga-agent-apps` | build + deploy |
| `IMAGE_TAG` | `latest` | build + deploy |
| `REGISTRY` | `icr.io` | build + deploy |
| `APP_NAME` | `cuga-agent-apps` | deploy |
| `REGISTRY_SECRET` | `icr-secret-1` | deploy |
| `ENV_FILE` | `build/.env` | deploy |
| `CPU` / `MEMORY` | `12` / `48G` | deploy |
| `EPHEMERAL_STORAGE` | `5G` | deploy |
| `MIN_SCALE` / `MAX_SCALE` | `1` / `1` | deploy |
| `DOCKER_BUILD_NETWORK` | `host` | build |
| `ALLINONE_BASE` | repo's CE URL | hf/build.sh |

Examples:
```bash
CPU=6 MEMORY=24G EPHEMERAL_STORAGE=2G ./deploy.sh     # smaller CE instance
IMAGE_TAG=v3 ./build_and_push.sh && IMAGE_TAG=v3 ./deploy.sh   # pin a tag
```

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `ImagePullBackOff` on CE | Docker pushed to the wrong registry. Use `ibmcloud cr region-set global` (icr.io) — it must match the `--server icr.io` pull secret. If the ICR key was rotated: `ibmcloud ce registry update --name icr-secret-1 --password <new-key>`. |
| `Probe readiness.interval … too low` | CE readiness-probe interval minimum is **1s** (default 10). Don't set it to 0. The deploy script uses CE's default probe, so this only bites if you add `--probe-ready` manually. Probe `type` must be `http` or `tcp` (not `readiness`). |
| `Property … invalid value` / revision won't create | Check sizing is a valid CE combo. Max is **12 vCPU / 48 GB**; ephemeral storage must be ≤ memory. 64 GB is not supported. |
| CE `app create` fails on quota | 12 vCPU / 48 GB is large — confirm project quota: `ibmcloud ce project get --name ce-project-routing`. |
| HF push rejected: `contains binary files` | The bundle must ship no raw binaries. The umbrella UI was trimmed so it ships none; if you re-add images, either drop them or track via Git LFS (`git lfs track "*.png"` before the first commit). |
| `fatal: not a git repository` on HF push | You copied `dist/` into a folder that was never `git clone`d. Clone the Space **first**, then copy in. |
| HF: Apps blank until you click the tab | Fixed — `App.tsx` has a catch-all route (`path="*" → /`) so any unmatched initial path lands on Apps. If it recurs, confirm that route exists. |
| `ibmcloud login --sso` expired mid-deploy | Re-login and re-`ce project select`, then re-run. Both scripts are idempotent. |
| Local `docker compose up` fails: `failed to create network … iptables: No chain/target/match by that name` | Docker's iptables chains were flushed (usually a firewalld reload). Fix: `sudo systemctl restart docker`. If you can't restart the daemon, use [Option B — host networking](#option-b--host-networking-no-bridge-use-this-if-compose-fails-to-create-a-network), which needs no bridge network. |

---

## Deploy order summary

1. **CE first** — it's the backend; note its URL.
2. **HF second** — bake that URL into the static umbrella UI and push.
3. **Local** — independent; rebuild any time to test changes before shipping.
