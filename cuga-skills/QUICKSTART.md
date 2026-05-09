# CUGA UI + Skills + OpenSandbox — Quickstart

The minimum to get the **CUGA UI** running with **your own skills** executing
inside **OpenSandbox**. Uses **watsonx** for the LLM (RITS requires extra proxy
plumbing — skip it).

End state: `http://127.0.0.1:7860` chat → asks a question → agent calls
`load_skill(...)` → runs your skill's `tools.py` inside OpenSandbox → answers.

## One-time setup

Skip whatever you already have. Each step is independent.

### 1. `uv` and Docker Desktop

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

Install Docker Desktop and start it (whale icon steady in the menu bar). OpenSandbox runs Python in a Docker container — without Docker, nothing else works.

### 2. Clone CUGA + create its venv

```bash
git clone https://github.com/cuga-project/cuga-agent.git \
  /Users/anu/Documents/GitHub/cuga-agent-skills-branch
cd /Users/anu/Documents/GitHub/cuga-agent-skills-branch
git checkout feat/skills-support   # the branch with skills support

uv venv --python=3.12
source .venv/bin/activate
uv sync --extra opensandbox        # the extra pulls the SDK cuga uses to talk to opensandbox-server
python -c "import cuga; print('cuga ok')"
```

### 3. Watsonx credentials

[ibm.com/watsonx](https://www.ibm.com/watsonx) → API key + Project ID + region URL.

Put them in `cuga-agent-skills-branch/.env`:

```env
WATSONX_APIKEY=<key>
WATSONX_PROJECT_ID=<project-or-space-id>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
AGENT_SETTING_CONFIG=settings.watsonx.toml
```

### 4. OpenSandbox

OpenSandbox needs **its own venv** (separate from cuga's `.venv`):

```bash
uv venv ~/.venv-sandbox
source ~/.venv-sandbox/bin/activate
uv pip install opensandbox-server opensandbox-code-interpreter
opensandbox-server init-config ~/.sandbox.toml --example docker --force
```

Pre-pull the Docker image once so the macOS keychain prompt is dealt with:

```bash
docker pull opensandbox/code-interpreter:v1.0.2
# When Keychain pops up, click "Always Allow"
```

### 5. Install your skill

For each skill you want available, **copy** (not symlink — `Path.rglob` doesn't follow symlinks) into the cuga checkout's project-local skills dir:

```bash
mkdir -p /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills

cp -R /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills/hiking_research \
      /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills/
```

When you update a skill, `rm -rf` the destination and `cp -R` again.

## Each time you run

You need **two terminals**.

### Terminal 1 — OpenSandbox

```bash
source ~/.venv-sandbox/bin/activate
opensandbox-server     # :8080 — type YES at the api_key warning
```

Leave it running.

### Terminal 2 — CUGA backend (bare uvicorn, no demo preset)

`cuga start demo_skills` injects a digital_sales scenario that distracts the agent from your skills. Bypass it:

```bash
source /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.venv/bin/activate
cd /Users/anu/Documents/GitHub/cuga-agent-skills-branch

export DYNACONF_SKILLS__ENABLED=true
export DYNACONF_ADVANCED_FEATURES__OPENSANDBOX_SANDBOX=true
export DYNACONF_ADVANCED_FEATURES__ENABLE_SHELL_TOOL=true
export MCP_SERVERS_FILE=none

python -m uvicorn cuga.backend.server.main:app --host 127.0.0.1 --port 7860
```

Open http://127.0.0.1:7860.

### Verify before you ask anything

```bash
curl -s http://localhost:7860/api/skills | python3 -m json.tool
# expect: your skill name + correct description
```

If `skills` is empty, the cuga backend didn't see them — re-check step 3.

## Asking a question

In the chat panel, ask your skill's canonical query (e.g. for hiking_research:
**"Easy hikes near Chappaqua, NY"**).

The agent should:
1. Call `load_skill("<skill_name>")` first.
2. Run `python /tmp/cuga_workspace/skills/<skill>/tools.py <command> <args>` via `run_command`.
3. Parse the JSON and answer.

If it doesn't, check the events panel in the UI — it shows every tool call. The most common failure is the agent ignoring `<available_skills>` and trying `find_tools` instead; mention the skill name in your prompt to nudge it.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `APIConnectionError: localhost:4000` on first ask | LLM config still pointing at LiteLLM proxy | Check `.env` has `AGENT_SETTING_CONFIG=settings.watsonx.toml` and `WATSONX_*` vars set |
| `OpenSandbox not reachable at localhost:8080` | Terminal 1 not running, or you used `cuga start demo_skills` (which probes :8080 and exits) | Use the bare uvicorn approach in Terminal 2; restart OpenSandbox |
| `Failed to pull image opensandbox/code-interpreter` | macOS keychain dismissed the credential prompt | Run `docker pull opensandbox/code-interpreter:v1.0.2` once and click "Always Allow" |
| Agent says "due to security restrictions, I can't make HTTP requests" | digital_sales preset is loaded; `find_tools` returns no relevant APIs | Use bare uvicorn (skips the preset). Re-ask. |
| Agent uses an old version of the skill | Stale copy in `.cuga/skills/<name>/` | `rm -rf` the destination and `cp -R` from `cuga-skills/` again |
| `/api/skills` returns `[]` | `DYNACONF_SKILLS__ENABLED` not set, or skill folder not in `<cwd>/.cuga/skills/` | Set the env var and check the path |
| `find_hikes` returns 504 | Public Overpass endpoint flake | Retry — usually clears in a few seconds |

## Adding a new skill later

```bash
# Author the skill in cuga-skills/<your_skill>/SKILL.md (+ tools.py if needed)
# Copy into cuga's project-local skills dir
cp -R /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills/<your_skill> \
      /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills/

# Restart Terminal 2 (Ctrl-C, re-run uvicorn). cuga rescans on every chat turn,
# so the restart is only needed when you change the OpenSandbox upload.
```

That's it.
