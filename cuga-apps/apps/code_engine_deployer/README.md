# Code Engine Deployer

Conversational deployment assistant for IBM Cloud Code Engine. Hand it a
`docker-compose.yml`, get a classified verdict per service (CE-ready /
needs-work / won't-fit), then walk through build → push → deploy with
confirmation gates and live error diagnosis.

**Port:** 28818 → http://localhost:28818

> **Local-only.** Unlike the other cuga-apps, this one is NOT started by
> `docker compose up` — it shells out to your host's `ibmcloud` and
> `docker` CLIs and uses your existing IBM Cloud auth. Run it from your
> workstation. See [Why local-only](#why-local-only) below for the
> reasoning.

---

## Table of contents

- [How it works](#how-it-works)
- [Why local-only](#why-local-only)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [Configure](#configure)
- [Run](#run)
- [First-time deploy walkthrough](#first-time-deploy-walkthrough)
- [Troubleshooting](#troubleshooting)
- [Safety model](#safety-model)
- [Example prompts](#example-prompts)

---

## How it works

1. **Triage.** The agent calls `classify_compose_services(path)` on your
   compose file and returns a table — each service is `ce_ready`,
   `needs_work` (architectural decision required), or `wont_fit` (multi-port,
   writable bind mounts, etc.). Quoting the actual reasons, not paraphrasing.
2. **Scope.** You pick which services to deploy. Default: the CE-ready set.
   `needs_work` services get a walkthrough of their todos first.
3. **One-time setup** (first deploy in a CE project): ICR namespace,
   registry secret so CE can pull, env secret to translate any `.env` bind
   mount into a mounted CE Secret.
4. **Per service.** `docker build --platform linux/amd64` → `docker push` →
   `ibmcloud ce app create`. Each command shown to you BEFORE it runs.
5. **On failure.** The agent reads `ibmcloud ce app events` + logs, matches
   the error to a known pattern (ImagePullBackOff, port mismatch, missing
   secret mount, OOM), and proposes ONE specific fix — never retries blindly.

---

## Why local-only

Other cuga-apps run inside the shared apps container. The deployer can't,
for three real reasons:

1. **Shared-image bloat.** Adding the `ibmcloud` CLI + plugins (~150 MB)
   to `Dockerfile.apps` would hit every one of the 26 other apps.
2. **Docker socket is privileged.** Mounting `/var/run/docker.sock` into
   the apps container would give every other agent root-equivalent access
   to your host's docker daemon — a real security concern, not theoretical.
3. **IBM Cloud auth is per-user.** `ibmcloud login` writes to `~/.bluemix`.
   Sharing that across all the apps via a baked-in path is awkward;
   re-authenticating inside a container every session is painful.

The cuga-app convention assumes stateless web/API processes. The deployer
fundamentally isn't one — it needs host docker + persistent IBM auth. So
it's a host-Python app that lives in this repo for the cuga UI + tooling,
not a compose service.

---

## Prerequisites

### CLI tools (host)

| Requirement | Install / check |
|---|---|
| `ibmcloud` CLI | `curl -fsSL https://clis.cloud.ibm.com/install/linux \| sh` |
| `code-engine` plugin | `ibmcloud plugin install code-engine` |
| `container-registry` plugin | `ibmcloud plugin install container-registry` |
| `docker` CLI + daemon | `docker version` (any recent version) |
| Authenticated session | `ibmcloud login --sso` then `ibmcloud target -r <region> -g <rg>` |

The agent's `check_prereqs` tool reports any of these as missing — if you
skip ahead and one isn't there, it'll tell you which.

### Python

**Python 3.10, 3.11, 3.12, or 3.13.** NOT 3.14.

cuga 0.2.x supports `>=3.10,<3.14`. Many of cuga's transitive deps
(numpy, pandas, torch, opencv) don't ship Python 3.14 wheels yet, so pip
falls back to building from source and dies on machines without a C
compiler. Don't use 3.14.

On RHEL 9 you already have `python3.11` at `/usr/bin/python3.11`. On
Debian/Ubuntu: `apt install python3.11 python3.11-venv`.

### IBM Cloud account state

- A Code Engine project. Create one in the
  [console](https://cloud.ibm.com/codeengine/projects) — the deployer
  doesn't have a `create_project` tool because that's a one-time
  account-level decision worth doing manually.
- (Optional) An ICR namespace. The agent will create it via
  `cr_namespace_add` when you ask, or you can pre-create with
  `ibmcloud cr namespace-add <ns>`.
- (Optional) An IBM Cloud API key for the registry pull secret. The agent
  will ask for this when creating the registry secret. Generate one with:
  ```bash
  ibmcloud iam api-key-create ce-icr -d "CE pull from ICR" --file ce-icr-key.json
  cat ce-icr-key.json | python -c "import sys,json; print(json.load(sys.stdin)['apikey'])"
  ```

---

## Install

From the cuga-apps repo root:

```bash
cd /path/to/agent-apps/cuga-apps

# Use Python 3.11 explicitly — see "Python" section above for why
python3.11 -m venv .venv_cuga_deployer
source .venv_cuga_deployer/bin/activate

python --version              # MUST say 3.11.x — verify before continuing

pip install --upgrade pip
pip install -r apps/code_engine_deployer/requirements.txt
```

Install takes 2–5 minutes — cuga pulls a long transitive list (langchain
1.x, langchain-ibm, torch, transformers, playwright, opencv, etc.). When
it finishes:

```bash
pip list | grep cuga          # cuga 0.2.26 (or newer)
```

Verified working as of 2026-04-29 with Python 3.11.13 on RHEL 9: cuga
**0.2.26**, langchain **1.2.16**, langchain-ibm **1.0.7** — all from
public PyPI, no `--no-deps` workarounds needed.

If you use a provider other than Anthropic (which is in the slim
requirements explicitly), `langchain-openai` and `langchain-ibm` are
already pulled in transitively. For others (groq, ollama, watsonx via
RITS, …) the matching `langchain-*` package may already be present —
check `pip list | grep langchain` before adding more.

---

## Configure

Set whichever LLM provider you actually use. The deployer reads the same
env vars as every other cuga-app:

```bash
# Anthropic
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=...

# OR OpenAI
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4.1
export OPENAI_API_KEY=...

# OR RITS (IBM internal)
export LLM_PROVIDER=rits
export LLM_MODEL=...
export RITS_API_KEY=...
export AGENT_SETTING_CONFIG=settings.rits.toml
```

If your `apps/.env` already has these set up for the other cuga-apps, you
can source it instead:

```bash
set -a && source apps/.env && set +a
```

---

## Run

```bash
# Make sure the venv is active and env vars are set, then:
cd apps/code_engine_deployer
python main.py --port 28818
```

Boot takes ~15 seconds (cuga warms up langchain + tools). When you see
`Created DirectLangChainToolsProvider with 19 tools`, the agent is ready.

Open http://127.0.0.1:28818 in your browser.

---

## First-time deploy walkthrough

### 1. Sanity-check classification (no LLM, fast)

The compose path field is pre-filled with the cuga-apps compose. Click
**Classify** on the left panel.

You should get an 11-row verdict table:

| Service | Verdict |
|---|---|
| mcp-web, mcp-knowledge, mcp-geo, mcp-finance, mcp-code, mcp-local, mcp-text | needs_work |
| ui, mcp-tool-explorer | needs_work |
| apps, mcp-invocable_apis | wont_fit |

`needs_work` here means: build-only services need an image tag, and the
`.env` bind mount needs translating to a CE Secret. `wont_fit` is the
27-port `apps` service and the writable-bind-mount `mcp-invocable_apis`.

If this works, your parser + classifier are both fine.

### 2. Prereq check (chat, ~5–10s)

In the right-side chat:

> Check prereqs and tell me what's missing. I'm logged into ibmcloud already.

The agent calls `check_prereqs` and reports `ibmcloud` / `docker` paths,
plugin presence, and your active region/RG/account. Fix anything missing
before continuing.

### 3. Pick a Code Engine project

> List my Code Engine projects.

If you don't have one yet, create one in the console first
(`https://cloud.ibm.com/codeengine/projects`). Then:

> Target the project `<name>`.

### 4. First-time ICR + secret setup

> Walk me through first-time setup for region us-south. Use namespace
> `cuga-apps`. My API key for the registry pull secret is `<paste>`. The
> env file to translate is `/path/to/apps/.env`.

The agent will sequence: `cr_region_set` → `cr_namespace_add` →
`cr_login` → `create_ce_registry_secret` → `create_ce_secret_from_env_file`,
showing each command before running.

### 5. Deploy ONE MCP server first (validate the path end-to-end)

> Deploy just `mcp-web` first. Use image tag
> `us.icr.io/cuga-apps/mcp:latest`. Mount the env secret at
> `/run/secrets`. Show me the build/push/deploy plan before doing anything.

The agent proposes three commands (`docker_build`, `docker_push`,
`deploy_ce_app`), waits for confirmation, runs them, then calls
`get_ce_app` to verify. If `mcp-web` ends up `Ready`, the loop works.

### 6. The rest of the MCP servers

> Now deploy mcp-knowledge, mcp-geo, mcp-finance, mcp-code, mcp-local,
> mcp-text using the same image. They each need a different
> `--command python -m mcp_servers.<name>.server` and the port from the
> compose file. One at a time, with confirmation.

`mcp-invocable_apis` will need extra discussion — it has writable bind
mounts the agent will flag.

### 7. If anything fails

> Read the events and logs for `<failed-app>` and tell me what broke.

The agent calls `get_ce_app_events` + `get_ce_app_logs`, matches the
error pattern, and proposes ONE fix.

Common patterns it knows:
- **ImagePullBackOff** → registry secret misconfigured or wrong tag
- **CrashLoopBackOff with exit immediately** → entrypoint or missing env
- **port mismatch** → app inside container listens on a different port
- **OOMKilled** → bump memory; if at the 32 GB ceiling, split the service

---

## Troubleshooting

### Install hangs on "INFO: This is taking longer than usual" / pip backtracking

You're on Python 3.14. Recreate the venv with 3.11 (see
[Prerequisites](#prerequisites)). Don't bother with `--no-deps`
workarounds — they were a wrong turn during development.

### `Cannot install ... ResolutionImpossible` for langchain-ibm

Same as above — Python 3.14. Newer langchain-ibm versions have wheels
only for ≤3.13.

### `numpy ... ERROR: Unknown compiler(s): [['cc'], ['gcc'], …]`

Python 3.14 trying to build numpy from source on a host without a C
compiler. Use Python 3.11 instead.

### `ModuleNotFoundError: No module named 'langchain_anthropic'` at boot

You're using Anthropic but `langchain-anthropic` isn't installed.
`langchain-openai`, `langchain-ibm`, `langchain-ollama`, `langchain-groq`,
and `langchain-litellm` come transitively with cuga;
`langchain-anthropic` doesn't and is in the slim requirements explicitly.
If you removed it: `pip install langchain-anthropic`.

### Agent returns 500s on every chat message

Almost always a missing or wrong provider API key. Check that
`LLM_PROVIDER`, `LLM_MODEL`, and the matching key (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `RITS_API_KEY`, …) are exported in the same shell where
you ran `python main.py`. If you set them in `apps/.env`, source it with
`set -a && source apps/.env && set +a` so they end up in the environment.

### `ibmcloud` not found from inside the agent

You're running the deployer somewhere other than your workstation — maybe
inside the apps container. Run it locally; classification still works
elsewhere but the deploy tools shell out to the host CLIs.

### Tool returns `binary_missing` even though `ibmcloud` is on PATH

Python's `shutil.which` looks at the `PATH` of the launching process. If
you launched `python main.py` from a shell that didn't inherit
`/usr/local/bin` (or wherever ibmcloud lives), the tool can't find it.
Confirm `which ibmcloud` in the same shell where you started the
deployer, and add the dir to PATH if needed before launching.

### `ImagePullBackOff` on every deploy

Either:
- The registry secret was created against the wrong namespace/region.
  Re-run step 4 with `cr_region_set` matching where the project lives.
- The IBM Cloud API key used in the registry secret has been deleted or
  rotated. Generate a new one and recreate the registry secret.

---

## Safety model

- All shell calls use `subprocess.run` with **list args** (no `shell=True`,
  no string interpolation). The LLM cannot inject shell metacharacters
  through a malformed service name or tag.
- Every name, tag, and region is matched against an allowlist regex
  (lowercase DNS labels, k8s-style) before the command is constructed.
- Destructive tools (`delete_ce_app`) require an explicit `force=True`
  argument; the system prompt instructs the agent to confirm the exact
  app name with the user first.
- Each tool returns a structured envelope (`ok`, `command`, `returncode`,
  `stdout`, `stderr`) so the agent can read the actual error from CE and
  propose targeted fixes instead of retrying blindly.

---

## Example prompts

- *"Classify the compose file at /path/to/docker-compose.yml"*
- *"Deploy just the 8 MCP servers to my `cuga-apps` Code Engine project"*
- *"My `mcp-web` deploy is in `ImagePullBackOff` — what's wrong?"*
- *"Walk me through first-time setup: ICR namespace, registry secret, env secret"*
- *"Update `mcp-knowledge` to image `us.icr.io/cuga-apps/mcp:v2` and roll"*
- *"Show me the events and logs for `mcp-finance` — it keeps crashing"*

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Code Engine deployment assistant — reads docker-compose, classifies CE
readiness, builds + pushes + deploys with conversational confirmation.

**MCP servers consumed:** none. This app's domain (Code Engine ops) doesn't
fit any existing shared MCP server, and a new server isn't justified for a
single consumer.

**Inline `@tool` defs:**
- `parse_compose_file` — load + normalise a docker-compose.yml
- `classify_compose_services` — verdict + reasons per service
- `check_prereqs` — verify ibmcloud + docker + plugins + login state
- `list_ce_projects` · `target_ce_project`
- `list_ce_apps` · `get_ce_app` · `get_ce_app_logs` · `get_ce_app_events` · `delete_ce_app`
- `create_ce_secret_from_env_file` · `create_ce_registry_secret`
- `cr_login` · `cr_region_set` · `cr_namespace_add`
- `docker_build` · `docker_push`
- `deploy_ce_app` · `update_ce_app`

<!-- END: MCP usage -->
