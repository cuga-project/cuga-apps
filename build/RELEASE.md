# Release runbook — upgrade CUGA, test every app, ship to Code Engine + Hugging Face

How the gallery was moved to **cuga 0.4.5 / MCP 2.x** and released on 2026-11-09/10,
written so the next upgrade is routine. Each step says what to run and what "good"
looks like. Commands run from the repo root unless noted.

| What | Where | Notes |
|---|---|---|
| **Prod gallery** (all-in-one: UI + 22 apps + 5 MCP servers + stats) | CE app `cuga-agent-apps`, project `ce-project-routing` (us-east) | `https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud` · env from secret `cuga-agent-apps-env` · 12 vCPU / 48 GB |
| **Public front door** | HF Space `ibm-research/cuga-apps` (static) | Only the UI; every *Try it* opens prod's `/a/<app>/` |
| **Shared MCP servers** | CE apps `cuga-apps-mcp-<name>` + `cuga-apps-mcp-tool-explorer`, `ce-project-routing` | Env from secret `app-env` (an `app.env` file); explorer lists Tavily |
| **Stats** | `usage_collector` inside the all-in-one → COS bucket `cuga-usage`, object `rollup/usage_db.json` | Dashboard: `<prod>/a/usage-collector/?token=…` |
| **Bharat Core service** | CE app `bharat-core-cuga-agent-app`, `ce-project-routing` | Separate repo; the gallery links to it by fixed URL |

---

## 0. Before you start — two rules that prevent real damage

1. **Never trust the global `ibmcloud` target.** Other sessions/terminals switch
   `ibmcloud ce project select` under you (that is how a deploy once landed in the
   wrong project). Give every CE command its own CLI config:

   ```bash
   export IBMCLOUD_HOME=$(mktemp -d); chmod 700 $IBMCLOUD_HOME; cp -R ~/.bluemix $IBMCLOUD_HOME/
   ibmcloud target -r us-east -g routing && ibmcloud ce project select -n ce-project-routing
   ```
   A copied `IBMCLOUD_HOME` keeps its own region / resource group / CE project.
   `build/mcp_servers/deploy_mcp.sh` also takes `EXPECT_PROJECT=<name>` and aborts
   if the project changes mid-run (checked before every app).

2. **Production needs `CONFIRM_PROD=1`** (`build/ce/ce_build.sh` and `build/ce/deploy.sh`
   refuse the prod name otherwise). Always deploy prod with `SKIP_ENV_SYNC=1` so its
   secret — stats bucket credentials included — is left exactly as it is.

## 1. Upgrade the dependency pins

* All app/server `requirements*.txt`: `cuga>=0.4.5,<0.5`, `mcp>=2.0,<3`,
  `fastmcp>=4.1,<5`, `langchain[mcp]>=1.4.6,<1.5`. `langchain-mcp-adapters` is gone
  (archived upstream; cuga 0.4.5 uses LangChain's own `langchain.mcp.MCPAdapter`).
* Regenerate the image pins (`build/constraints.allinone.txt`) for linux/amd64:

  ```bash
  uv pip compile cuga-apps/requirements.apps.txt build/requirements.mcp.txt \
      --python-version 3.13 --python-platform x86_64-manylinux_2_28 --no-header --no-annotate -o /tmp/c.txt
  ```
  then drop the CUDA wheels (`nvidia-*`, `triton`) and pin `torch==X+cpu` /
  `torchvision==Y+cpu` (check the CPU index has them for cp313), and set the same
  versions in the Dockerfile's CPU-torch `pip install` line. Keep the file's header
  comment up to date.
* The sandboxed shell can't reach PyPI; installs need network access.

## 2. Code that had to change for MCP 2.x (already done — re-check on the next bump)

| File | Change |
|---|---|
| `cuga-apps/apps/_mcp_bridge.py` | `load_tools` → `MCPAdapter(mcp_client(name)).list_tools()`; new `mcp_client()` (fastmcp `Client` + `StreamableHttpTransport`, `MCP_TOOL_EXPLORER_URL`-style overrides, `MCP_TOOL_TIMEOUT` default 300 s); `call_tool` uses fastmcp. Result shape is unchanged (`(content, artifact)`), so the unwrap/shim code stays. |
| `cuga-apps/mcp_servers/_core/serve.py` | Standalone `fastmcp` first: `run(transport="http", host, port, path="/mcp")`. FastMCP 4 only checks the Host header on loopback binds. |
| `cuga-apps/mcp_servers/_core/client.py` (new) | `open_session(url, headers)` — old `ClientSession`-like API (`.isError`, `.inputSchema`) over either SDK; used by tests, `list_tools.py`, `test_mcp.py`, the tool explorer. |
| `cuga-apps/mcp_servers/invocable_apis/server.py` | Generated servers use fastmcp when available. |

## 3. Behaviour changes in cuga 0.4.5 that broke apps (and the fixes)

1. **Shared policy store → one app's policies fire in another.** cuga's default store
   is `<cuga package>/dbs/cuga.db`, shared by every app on one Python. city_beat
   answered with ai_labs_news's `save_digest(...)` text. **Fix:** each app gets its
   own `CUGA_DBS_DIR=<app>/.cuga/dbs` (set in `launch.py`, in `generate.py`'s
   `run_all.sh`, and defaulted in the 5 apps that register policies), and every app
   now runs from its own directory in the image (its own `.cuga/` folder).
2. **Output formatters can't call tools.** Four apps' formatters said "ALWAYS call
   save_X"; the formatter LLM wrote the call as text. Formatters now describe the
   reply only; the system prompts already require the save call.
3. **Any ```` ```python ```` block in a reply is executed**, and code that uses no
   tool is rejected. code_reviewer looped to the 70-step limit printing its fix.
   **Fix:** example fixes go in ```` ```diff ```` blocks.
4. **Easy facts get answered from memory** (with the model's plan text left in).
   wiki_dive now says its first step is always a tool call.

Lesson: run real questions, not just startup checks — all four only showed up in answers.

## 4. Test locally

```bash
cd cuga-apps && uv venv --python 3.13 .venv045 && VIRTUAL_ENV=.venv045 uv pip install \
    -r requirements.apps.txt -r requirements.mcp.txt -r requirements.test.txt -r requirements.apps.heavy.txt
cd apps && ../.venv045/bin/python launch.py start            # all MCP servers + all apps (keys from build/.env)
cd ../.. && cuga-apps/.venv045/bin/python build/probe_apps.py host                    # 22 showcase apps
cuga-apps/.venv045/bin/python build/probe_apps.py host --set additional              # the rest
cd cuga-apps && .venv045/bin/python -m pytest tests/test_mcp_tools.py tests/test_app_wiring.py tests/test_smoke.py -n 6
```
`tests/test_smoke.py` also needs the tool explorer (`python mcp_tool_explorer/server.py`)
and skips everything unless something listens on :3001. Known, not regressions:
Overpass (`search_attractions`) upstream timeouts; wiring tests for routes the apps
no longer have; the dashboard 401 without a token.

## 5. Build images in Code Engine (no local Docker needed)

```bash
IMAGE_NAME=cuga-agent-apps-1 IMAGE_TAG=<date>-<what> build/ce/ce_build.sh        # all-in-one
IMAGE_TAG=<date>-<what> build/mcp_servers/ce_build_mcp.sh                        # mcp + mcp-tool-explorer
```
Both stage only git-tracked files (no `.env`, no venvs), abort on secret-looking
files, build in `ce-project-routing` (it holds the ICR push secret `icr-secret-1`)
and restore your CLI target. The local Podman VM is ~93 % full of other projects'
images — don't prune those. Building under the non-prod name and deploying that
image to prod is fine (and keeps the build step free of `CONFIRM_PROD`).

## 6. Deploy

**MCP servers + explorer** (`ce-project-routing` defaults: pull `icr-secret-1`, env `app-env`):
```bash
EXPECT_PROJECT=ce-project-routing IMAGE_TAG=<mcp tag> build/mcp_servers/deploy_mcp.sh web knowledge geo finance code local text
EXPECT_PROJECT=ce-project-routing IMAGE_TAG=<explorer tag> build/mcp_servers/deploy_mcp.sh tool-explorer
```
For another project pass `REGISTRY_SECRET=` / `ENV_SECRET=` (the env secret must hold
an `app.env` file). The script runs on macOS's bash 3.2.

**Prod gallery:**
```bash
CONFIRM_PROD=1 SKIP_ENV_SYNC=1 APP_NAME=cuga-agent-apps IMAGE_NAME=cuga-agent-apps-1 IMAGE_TAG=<tag> \
  REGISTRY_SECRET=icr-secret-1 CPU=12 MEMORY=48G build/ce/deploy.sh
```
Wait ~5 min for the apps to warm up, then:
```bash
bash build/smoke.sh https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud     # 24/24
cuga-apps/.venv045/bin/python build/probe_apps.py https://cuga-agent-apps.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud   # 22/22
```
and open the stats dashboard: history must still start at its first day.
**Rollback:** redeploy the previous image tag (before 2026-11-10: `cuga-agent-apps:2026-10-12-bharat`).

## 7. Publish the Hugging Face Space

```bash
build/hf/build.sh                     # default backend = prod; bakes it into the bundle
git clone https://huggingface.co/spaces/ibm-research/cuga-apps /tmp/space
cd /tmp/space && git lfs install --local && git lfs track "*.png"
git rm -rq assets && cp -r <repo>/build/hf/dist/. . && rm -rf usecases && git add -A && git commit -m "…"
export HF_TOK=$(cat ~/.cache/huggingface/token)
git -c credential.helper= -c credential.helper='!f(){ echo username=<hf-user>; echo "password=$HF_TOK"; }; f' push origin HEAD:main
```
* HF rejects plain binaries → PNGs (the logo) go through LFS.
* Use a credential helper, not an `Authorization` header: a header is also sent to
  the LFS storage upload URL and that upload fails.
* Check the clone's only remote is the Space before pushing. Then confirm the live
  Space (`https://ibm-research-cuga-apps.static.hf.space/`) loads the new
  `assets/index-*.js`, the logo returns 200, and *Try it* links point at prod.

## 8. Things the gallery now does that are easy to forget

* **"← All CUGA Apps"** in every app's top banner (`apps/_chrome.py`) → the HF Space
  (`CUGA_APPS_HOME_URL` overrides). The "MCP Tools" pill follows the CE project the
  app runs in.
* **Counted outbound links**: `/a/usage-collector/go/<link>?src=<where>-<button>`
  counts and 302s to an allow-listed URL (`USAGE_LINKS`; default `bharat-core`). The
  Bharat Core buttons are tracked as `ce-band|card|stats` / `hf-band|card|stats`;
  see the dashboard's **Link clicks** tab. Add a link: extend `USAGE_LINKS`, then use
  `trackedLink(id, button, url)` in the UI.
* **Tavily in the tool explorer**: listed when `TAVILY_API_KEY` is in its env; calls
  share an hourly budget (`EXPLORER_TAVILY_CALLS_PER_HOUR`, default 30).
* **UI**: cuga.dev styling; app order in `SHOWCASE_ORDER` (`ui/src/pages/Home.tsx`);
  Bharat Core content in `ui/src/data/bharatServices.ts` (fixed service URL — it
  lives in its own project); the UI reads its CE project from its own hostname, or
  from `VITE_ALLINONE_BASE` on the Space.
