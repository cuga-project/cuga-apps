# Running the whole stack locally from source

> **Internal doc — not linked from the public README.** This is the
> pip-install + `launch.py` path for contributors who want to run all the MCP
> servers and apps natively (no Docker). For end users, the public README
> points at the hosted gallery and the per-app quick starts; for a containerised
> local run, see the root [README](../../README.md) Docker section.

There are two ways to run everything locally:

| Way | Command | When |
|---|---|---|
| **Docker compose** | `docker compose up --build` (full dev stack: MCP + apps + UI) from [cuga-apps/](../) | Zero host setup; you have Docker; you don't need to edit/debug Python live. |
| **pip + launch.py** (this doc) | `pip install -r requirements.txt` → `python apps/launch.py …` | You want to hack on apps/MCP servers with a normal Python toolchain, fast restarts, per-process logs. |

---

## 1. Virtualenv + one install

Python **3.13** (cuga supports `>=3.10,<3.14`; 3.13-slim is what the images use).
From [cuga-apps/](../):

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

That **one file** ([requirements.txt](../requirements.txt)) is an aggregate of
the three component files — install it and you have the whole stack:

| Component | Brings in |
|---|---|
| [requirements.apps.txt](../requirements.apps.txt) | `cuga` framework + every app's deps + the MCP client (`_mcp_bridge.py`) |
| [requirements.apps.heavy.txt](../requirements.apps.heavy.txt) | `chromadb` + `sentence-transformers` — only `video_qa` and `deck_forge` need these |
| [requirements.mcp.txt](../requirements.mcp.txt) | the MCP servers' own deps — `tavily-python`, `docling`, `faster-whisper`, `tiktoken`, `psutil`, … |

> **Heads up — first run downloads models.** `requirements.mcp.txt` pulls
> `faster-whisper` (mcp-local) and `docling` (mcp-text); their models
> (~150 MB + ~250 MB) download on first tool call, not at install. `mcp-local`
> also needs system `ffmpeg` + `libgomp` (`brew install ffmpeg libomp` on macOS).

Each **app's own** `requirements.txt` is also self-contained now (every one
declares `cuga`), so you can install + run a single app in isolation — see
[§4](#4-running-one-app-on-its-own).

---

## 2. Secrets

```bash
cp apps/.env.example apps/.env
```

Then edit `apps/.env`: set your LLM provider keys (watsonx / OpenAI / Anthropic
/ Ollama — see `LLM_PROVIDER`) and any tool keys you want live (`TAVILY_API_KEY`
for mcp-web search, `ALPHA_VANTAGE_API_KEY` for finance, etc.). Missing tool
keys return a clean `missing_key` error — the server still starts.

`launch.py` loads `apps/.env` automatically and points every app at the local
usage collector out of the box.

---

## 3. Launch the stack

```bash
# the ship-ready stack: 7 MCP servers + the 21 ship-ready apps
python apps/launch.py start --ship-ready

# OR everything: all 8 MCP servers + ~34 apps + the usage dashboard
python apps/launch.py
```

`--ship-ready` brings up the **7 MCP servers** (`web`, `knowledge`, `geo`,
`finance`, `code`, `local`, `text`) **and** the **21 ship-ready apps** together —
MCP first, so the MCP-backed apps (travel_planner, city_beat, movie_recommender,
…) can connect. (`invocable_apis` is excluded — it's BIRD-only and needs host
data mounts; no ship-ready app uses it.)

### Managing processes

```bash
python apps/launch.py status                 # what's running, ports, PIDs
python apps/launch.py logs                   # tail every process' log
python apps/launch.py logs city_beat --tail 80
python apps/launch.py stop --ship-ready      # graceful SIGTERM
python apps/launch.py kill --ship-ready      # force-free the ports (catches orphans)
python apps/launch.py start travel_planner   # one (or more) by name
```

- Per-process logs land at `apps/.<name>.log`; tracked PIDs in `apps/.launch_pids`.
- Ports come from [apps/_ports.py](../apps/_ports.py) — never hardcode them.
- The umbrella **UI** is not started by `launch.py`. For UI dev run it
  separately from [ui/](../ui/) (`npm install && npm run dev`); the apps are
  reachable on their own ports without it.

### The #1 gotcha: a Python without `cuga`

Every app builds a `CugaAgent`, so the interpreter that spawns them must have
`cuga`. `launch.py` auto-detects one (`$CUGA_PYTHON` → the current interpreter →
a sibling `*/.venv/bin/python`) and warns if none has it. If apps crash at
startup, that's almost always the cause — fix with:

```bash
CUGA_PYTHON=/path/to/.venv/bin/python python apps/launch.py start --ship-ready
```

---

## 4. Running one app on its own

Because each app's `requirements.txt` now declares `cuga`, a single app is a
two-step run:

```bash
cd apps/recipe_composer
pip install -r requirements.txt        # cuga + the app's deps
python main.py --port 28820
```

For an MCP-backed app (e.g. `movie_recommender`, `city_beat`) without running
the MCP servers locally, point it at the **hosted** servers instead:

```bash
cd apps/movie_recommender
pip install -r requirements.txt
export CUGA_TARGET=ce                   # use the hosted cuga-apps-mcp-* servers
python main.py --port 28806
```

(See the MCP URL resolution in [apps/_mcp_bridge.py](../apps/_mcp_bridge.py).)

### MCP servers only

To run just the MCP servers in one terminal (no apps):

```bash
python -m mcp_servers.run_all            # all 8, multiplexed logs
```

---

## How this relates to deployment

This doc is **local dev only**. The two Code Engine deployment sets are
separate and documented elsewhere:

- [../../build/](../../build/) — the all-in-one `cuga-agent-apps` image (UI +
  apps + 5 internal MCP servers).
- [../../build/mcp_servers/](../../build/mcp_servers/) — the standalone
  `cuga-apps-mcp-*` servers (what `CUGA_TARGET=ce` hits).

The old per-app fan-out deploy scripts in this directory's parent are **legacy**
(see their banners) and not part of the current model.
