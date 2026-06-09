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

> **The other deployment set.** This doc covers the **all-in-one** only. The
> standalone `cuga-apps-mcp-*` MCP servers (what apps reach with
> `CUGA_TARGET=ce` when run from source) are a **separate** deployment with
> their own build/deploy scripts and compose — see
> [build/mcp_servers/](mcp_servers/). The all-in-one bundles its own lean
> 5-server MCP subset internally and does **not** depend on those.

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
cd <repo-root>/build

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
cd <repo-root>
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
cd <repo-root>/build/ce
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

## 2b. Durable stats storage — IBM Cloud Object Storage (COS)

The `usage_collector` app powers the **Stats dashboard** (`/a/usage-collector/`).
It keeps per-app request counts, unique-visitor counts, provider API-call counts
(tavily / alpha_vantage / watsonx), and chat utterances. On Code Engine the
container filesystem is **ephemeral and scales to zero**, so anything written to
local disk is lost on every redeploy. COS is the only durable store, and the
collector already speaks S3 to it ([usage_collector/main.py](../cuga-apps/apps/usage_collector/main.py)) —
this section creates the bucket and wires it to CE.

### What goes in the bucket

One bucket, two prefixes (set `USAGE_S3_KEY=rollup/usage_db.json` so the
aggregate lands under `rollup/`):

```
s3://cuga-usage/
  rollup/usage_db.json          ← aggregate counters: apps, unique users,
                                   provider calls. Small, rewritten ~every 60s,
                                   loaded whole on startup. Anonymous, kept forever.
  utterances/<day>/<batch>.jsonl ← append-only chat-utterance batches (PII).
                                   1-year lifecycle rule auto-expires these.
```

### Step 1 — create the COS instance + bucket

The bucket is **Regional** in `us-south` (this project's bucket). That's a
different region than the CE app (`us-east`), which is fine: COS `direct`
endpoints route over IBM Cloud's private network and are reachable from CE
cross-region, so the collector still avoids public egress.

```bash
# Instance (skip if you already have a COS instance)
ibmcloud resource service-instance-create cuga-cos cloud-object-storage standard global

# Bucket — console is easiest (COS instance → Create bucket → Customize →
# Regional, region = us-south, name = cuga-usage), or via the COS CLI plugin:
ibmcloud plugin install cloud-object-storage
ibmcloud cos config crn                                   # set to your COS instance CRN once
ibmcloud cos bucket-create --bucket cuga-usage --region us-south --class smart
```

### Step 2 — create HMAC credentials

boto3 (what the collector uses) needs **HMAC** keys, not the default IAM bearer
key. The `{"HMAC":true}` parameter is the part people miss:

```bash
ibmcloud resource service-key-create cuga-usage-hmac Writer \
  --instance-name cuga-cos \
  --parameters '{"HMAC":true}'

# Read the keys (the table view masks them as REDACTED — use JSON):
ibmcloud resource service-key cuga-usage-hmac --output json \
  | jq 'if type=="array" then .[0] else . end | .credentials.cos_hmac_keys'
```

From `cos_hmac_keys`: `access_key_id` → `AWS_ACCESS_KEY_ID`,
`secret_access_key` → `AWS_SECRET_ACCESS_KEY`.

> **`null` / `REDACTED` gotchas.** If `jq` prints `null`, the structure had no
> `cos_hmac_keys` → the `{"HMAC":true}` param didn't take; delete and recreate the
> key (`ibmcloud resource service-key-delete cuga-usage-hmac -f`, then re-run the
> create). If JSON output still shows `REDACTED`, secret-hiding is on globally:
> `ibmcloud config --hide-secrets false`, re-read, then set it back to `true`.

### Step 3 — pick the endpoint

The endpoint region must match the **bucket** region (`us-south`), not the CE
region. The collector (running in CE) uses the **direct** endpoint — private,
no egress charge, reachable cross-region over IBM's network. From your **laptop**
use the **public** endpoint instead (the direct one isn't routable off-cloud):

```
direct (collector/CE) : https://s3.direct.us-south.cloud-object-storage.appdomain.cloud
public (your laptop)  : https://s3.us-south.cloud-object-storage.appdomain.cloud
```

### Step 4 — set the 1-year lifecycle rule on `utterances/`

This auto-expires only the raw-text objects after 365 days; the anonymous
`rollup/` counters are untouched. Using the AWS CLI with the HMAC creds:

```bash
export AWS_ACCESS_KEY_ID=<access_key_id>
export AWS_SECRET_ACCESS_KEY=<secret_access_key>

aws --endpoint-url https://s3.us-south.cloud-object-storage.appdomain.cloud \
  s3api put-bucket-lifecycle-configuration --bucket cuga-usage \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "utterances-1yr",
      "Filter": {"Prefix": "utterances/"},
      "Status": "Enabled",
      "Expiration": {"Days": 365}
    }]
  }'
```

(Console equivalent: bucket → *Configuration* → *Expiration rules* → add rule,
prefix `utterances/`, 365 days.)

### Step 5 — wire it into CE

Add to `build/.env` (which `deploy.sh` syncs into the `cuga-agent-apps-env`
secret — values never hit the command line):

```bash
USAGE_S3_BUCKET=cuga-usage
USAGE_S3_ENDPOINT=https://s3.direct.us-south.cloud-object-storage.appdomain.cloud
USAGE_S3_KEY=rollup/usage_db.json
AWS_ACCESS_KEY_ID=<access_key_id>
AWS_SECRET_ACCESS_KEY=<secret_access_key>
# while you're here, lock down the collector:
USAGE_TOKEN=<long-random-string>
USAGE_DASHBOARD_TOKEN=<another-random-string>
```

Then redeploy: `cd build/ce && ./deploy.sh`.

### Step 6 — verify

```bash
# logs: "loaded usage snapshot" on startup; "usage snapshot saved (S3)" within ~60s
ibmcloud ce app logs --name cuga-agent-apps --follow | grep -i snapshot

# objects appear (use the PUBLIC endpoint from your laptop — the `direct`
# endpoint the collector uses is private/in-cloud only):
aws --endpoint-url https://s3.us-south.cloud-object-storage.appdomain.cloud \
  s3 ls --recursive s3://cuga-usage/
#   rollup/usage_db.json            ← aggregate (apps, users, provider calls)
#   utterances/<day>/<batch>.jsonl  ← chat utterance text (1-year lifecycle)
```

> **Endpoint regions must match the bucket.** The `s3.direct.<region>…`
> endpoint is private (reachable only from CE); from your laptop use the public
> `s3.<region>…` endpoint, and `<region>` must equal the bucket's actual region.
> This project's bucket is in `us-south`; if you recreate it elsewhere,
> substitute that region in **both** `build/.env`'s `USAGE_S3_ENDPOINT` and
> these commands.

> Grant `Writer` (the collector both reads on startup and writes). Use a
> dedicated `cuga-usage-hmac` key so it can be rotated independently. The
> non-HMAC `apikey` field in the same credential is **not** what boto3 wants —
> only `cos_hmac_keys` works for the S3 client.

### What the collector tracks

The dashboard at `/a/usage-collector/?token=<USAGE_DASHBOARD_TOKEN>` now shows,
across all apps:

| Metric | Source | Persistence |
| --- | --- | --- |
| Requests / unique users / per-app sparklines | request middleware | `rollup/` (forever) |
| Provider API calls (tavily, alpha_vantage, watsonx, …) | `track_call()` at the MCP servers + an LLM callback in `_llm.py` | `rollup/` (forever) |
| Chat utterances — counts | `track_utterance()` in each app's ask endpoint | `rollup/` (forever) |
| Chat utterances — full text | same | `utterances/` (1-year lifecycle) |

Optional tuning env (sensible defaults; set in `build/.env` if needed):
`USAGE_UTTERANCE_MAXLEN` (default 2000 — text truncation), `USAGE_UTTERANCE_RECENT`
(default 200 — how many recent utterances the live dashboard shows),
`USAGE_UTTERANCE_PREFIX` (default `utterances`).

---

## 3. Hugging Face — build static UI, republish

```bash
cd <repo-root>/build/hf
ALLINONE_BASE=https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud ./build.sh     # bakes the CE URL into the bundle → dist/

rm -rf /tmp/space
git clone git@hf.co:spaces/anupamamurthi/cuga-agent-apps /tmp/space
cp -r <repo-root>/build/hf/dist/. /tmp/space/
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

Durable-stats (COS) vars live in `build/.env`, not the scripts — see
[2b. Durable stats storage](#2b-durable-stats-storage--ibm-cloud-object-storage-cos):

| Var | Example | Used by |
| --- | --- | --- |
| `USAGE_S3_BUCKET` | `cuga-usage` | usage_collector |
| `USAGE_S3_ENDPOINT` | `https://s3.direct.us-south.cloud-object-storage.appdomain.cloud` | usage_collector |
| `USAGE_S3_KEY` | `rollup/usage_db.json` | usage_collector |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | COS HMAC keys | usage_collector |
| `USAGE_TOKEN` / `USAGE_DASHBOARD_TOKEN` | random secrets | usage_collector |

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
| Stats reset to zero after a CE redeploy | COS isn't wired. The collector falls back to ephemeral local disk when `USAGE_S3_BUCKET` is unset. Complete [2b. Durable stats storage](#2b-durable-stats-storage--ibm-cloud-object-storage-cos). |
| COS HMAC creds show `REDACTED` / `jq` returns `null` | Use `--output json`; if still masked, `ibmcloud config --hide-secrets false`. `null` from `.cos_hmac_keys` means the key was made without `{"HMAC":true}` — recreate it. See Step 2 of 2b. |
| Collector logs `snapshot save failed` against COS | Usually a `SignatureDoesNotMatch`/`AccessDenied`: wrong endpoint region, or you pasted the IAM `apikey` instead of the HMAC `access_key_id`/`secret_access_key`. Endpoint region must match the bucket's region (`us-south`). |
| Local `docker compose up` fails: `failed to create network … iptables: No chain/target/match by that name` | Docker's iptables chains were flushed (usually a firewalld reload). Fix: `sudo systemctl restart docker`. If you can't restart the daemon, use [Option B — host networking](#option-b--host-networking-no-bridge-use-this-if-compose-fails-to-create-a-network), which needs no bridge network. |

---

## Deploy order summary

1. **CE first** — it's the backend; note its URL.
2. **HF second** — bake that URL into the static umbrella UI and push.
3. **Local** — independent; rebuild any time to test changes before shipping.
