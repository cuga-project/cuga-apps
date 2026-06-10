# Deployment Cheat Sheet

Quick reference for **what gets deployed, where it lives, and what builds it**.
For the full walkthrough (prereqs, COS setup, troubleshooting) see
[DEPLOYMENT.md](DEPLOYMENT.md).

## Shared coordinates (all CE deployments)

| | |
|---|---|
| CE project | `ce-project-routing` (hash `1gxwxi8kos9y`) · region **us-east** · resource group `routing` |
| Registry | `icr.io` (global ICR) · namespace `routing_namespace` · pull secret `icr-secret-1` |
| Secrets | `build/.env` → CE secret `cuga-agent-apps-env` |

## The deployables

### 1. All-in-one gallery — apps + UI + MCP + stats (the real backend)
- **Lives at:** CE app **`cuga-agent-apps`** → `https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud` (nginx :8080)
- **Image:** `icr.io/routing_namespace/cuga-agent-apps:latest`
- **Contains:** 21 ship-ready apps + `usage-collector` (stats) + the umbrella UI + **5 bundled MCP servers** (web, knowledge, geo, finance, local) on loopback. `CUGA_TARGET=local` is baked in — it never calls the standalone MCP servers.
- **Builds from:** `build/Dockerfile` via `build/ce/build_and_push.sh` → `build/ce/deploy.sh`
- **Local:** `build/docker-compose.yml`, or `docker run --network host` on **:8080**

### 2. Umbrella UI — Hugging Face Space (static launcher, no backend)
- **Lives at:** HF Space **`anupamamurthi/cuga-agent-apps`** → `https://anupamamurthi-cuga-agent-apps.hf.space/`
- **What it is:** static React bundle that just *links into* the CE all-in-one (`<base>/a/<app>/`); the CE URL is baked in at build time.
- **Source:** `cuga-apps/ui/` · **Builds from:** `build/hf/build.sh` → `build/hf/dist/` → git push to the Space

### 3. Standalone MCP servers — 7 individual CE apps (separate deployment)
- **Lives at:** `cuga-apps-mcp-{web,knowledge,geo,finance,code,local,text}` → `https://cuga-apps-mcp-<name>.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp`
- **Image:** `icr.io/routing_namespace/mcp:latest` (one shared image, run per-service)
- **Used by:** apps run *from source* with `CUGA_TARGET=ce`, and the "MCP Servers" showcase. **Not** used by the all-in-one gallery.
- **Builds from:** `build/mcp_servers/build_mcp_image.sh mcp` → `build/mcp_servers/deploy_mcp.sh <names>` · Dockerfile `cuga-apps/Dockerfile.mcp` (context = `cuga-apps/`)

### 4. MCP Tool Explorer — its own CE app
- **Lives at:** CE app **`cuga-apps-mcp-tool-explorer`** → `https://cuga-apps-mcp-tool-explorer.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud`
- **Image:** `icr.io/routing_namespace/mcp-tool-explorer:latest`
- **Builds from:** `build/mcp_servers/build_mcp_image.sh tool-explorer` → `build/mcp_servers/deploy_mcp.sh tool-explorer` (same scripts as #3)
- **Pointed to by** the per-server "Tool Explorer ↗" links and the injected per-app banners.

### 5. Stats storage — IBM Cloud Object Storage (durable, not a service)
- **Lives at:** COS bucket **`s3://cuga-usage`** (region **us-south**), instance `cuga-cos`
- **Used by:** the `usage-collector` app *inside* the all-in-one (dashboard at `/a/usage-collector/`). CE filesystem is ephemeral, so counters/utterances persist here.
- **Wired via:** `build/.env` → CE secret. Setup in [DEPLOYMENT.md §2b](DEPLOYMENT.md).

## How they relate

```
HF Space (static UI) ──links──▶ CE: cuga-agent-apps (all-in-one)
                                  ├─ 21 apps + usage-collector + UI
                                  ├─ 5 MCP servers (loopback, CUGA_TARGET=local)
                                  └─ usage-collector ──S3──▶ COS: cuga-usage

CE: cuga-apps-mcp-{web,knowledge,geo,finance,code,local,text}  ◀── from-source apps (CUGA_TARGET=ce)
CE: cuga-apps-mcp-tool-explorer                                 ◀── "Tool Explorer" links / app banners
        (both built from build/mcp_servers/, independent of the all-in-one)
```

## Two build families — what to run for what

| You changed… | Rebuild | Scripts |
|---|---|---|
| Any app / umbrella UI / bundled MCP (e.g. geo) → **gallery** | All-in-one (+ HF if UI changed) | `build/ce/build_and_push.sh && build/ce/deploy.sh`; then `build/hf/build.sh` |
| A standalone MCP server or the **Tool Explorer** | Shared MCP image | `build/mcp_servers/build_mcp_image.sh …` → `build/mcp_servers/deploy_mcp.sh …` |

The two families are independent: the all-in-one bundles its own MCP copy, so the
standalone `cuga-apps-mcp-*` set only matters for from-source `CUGA_TARGET=ce`
runs, the Tool Explorer, and the MCP-servers showcase.

## Local dev ports

| Thing | Port |
|---|---|
| All-in-one (nginx) | 8080 |
| MCP servers (web…text) | 29100–29106 |
| usage-collector | 28827 |
| Individual apps | 288xx (see each app's `main.py`) |

> Names, images, project hash (`1gxwxi8kos9y`), and HF space here are taken from
> the build scripts + DEPLOYMENT.md. To reconcile against what's *actually* live:
> `ibmcloud ce app list`.
