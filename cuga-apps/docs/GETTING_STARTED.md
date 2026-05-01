# Getting started

How to bring the cuga-apps stack up, configure it, and use the apps.

---

## Prerequisites

- Docker + Docker Compose (the only hard dep — everything runs in containers)
- Optional, only if you want to run tests or develop without Docker:
  - Python 3.11+
  - `pip install -r requirements.apps.txt -r requirements.mcp.txt -r requirements.test.txt`

## 1. Configure environment variables

Every credential and runtime knob lives in one file. Start from the template:

```bash
cd cuga-apps/
cp apps/.env.example apps/.env
$EDITOR apps/.env
```

The `.env` is mounted into both the apps container and the MCP server containers
via `env_file:` directives in [docker-compose.yml](../docker-compose.yml). Every
process inherits the same values; per-app vars are silently ignored where unused.

### Variables you almost certainly need

| Variable | Used by | Why |
|---|---|---|
| `LLM_PROVIDER` | every app | one of `rits` / `anthropic` / `openai` / `watsonx` / `litellm` / `ollama` |
| `LLM_MODEL` | every app | model name override (e.g. `claude-sonnet-4-6`) |
| Provider key | every app | one of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `RITS_API_KEY`, … matching `LLM_PROVIDER` |

### Variables for specific MCP tools

If a key isn't set, the corresponding tool returns a clean `missing_key` error
rather than crashing. The agent in the calling app sees the error and tells the
user. None are required to bring the stack up.

| Variable | Used by | Tools it gates |
|---|---|---|
| `TAVILY_API_KEY` | mcp-web | `web_search` |
| `ALPHA_VANTAGE_API_KEY` | mcp-finance | `get_stock_quote` |
| `OPENTRIPMAP_API_KEY` | mcp-geo | `search_attractions` |

### Variables for app-specific behaviour

| Variable | Used by | Effect |
|---|---|---|
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` | newsletter, drop_summarizer, smart_todo, stock_alert, web_researcher | enables outbound email; otherwise emails fall back to log lines |
| `ALERT_TO`, `DIGEST_TO`, `RESEARCH_TO` | the same set | recipient addresses |
| `WHISPER_MODEL` | mcp-local | faster-whisper size: `tiny` / `base` / `small` / `medium` / `large` (default `base`) |
| `CPU_THRESHOLD`, `CPU_CRITICAL`, `RAM_THRESHOLD`, `RAM_CRITICAL`, `DISK_THRESHOLD`, `DISK_CRITICAL` | server_monitor | alerting thresholds; passed through to `get_system_metrics_with_alerts` |
| `WATCH_DIR`, `POLL_SECONDS` | drop_summarizer | folder to watch + poll cadence |

The full annotated list lives in [apps/.env.example](../apps/.env.example).

## 2. Build and start

```bash
docker compose up -d --build
```

First build is slow (~5-10 minutes) because the MCP image pre-downloads:

- Whisper `base` model (~150MB) for `transcribe_audio`
- Docling models (~250MB) for `extract_text`
- tiktoken BPE files (cl100k_base + o200k_base) for `count_tokens`

Subsequent builds use Docker's layer cache and finish in seconds unless those
deps changed.

Verify everything started:

```bash
docker compose ps
```

You should see 11 services running:

```
apps                      Up
mcp-code                  Up
mcp-finance               Up
mcp-geo                   Up
mcp-knowledge             Up
mcp-local                 Up
mcp-text                  Up
mcp-tool-explorer         Up
mcp-web                   Up
ui                        Up
```

## 3. Open the UIs

| URL | What |
|---|---|
| http://localhost:3001 | **Umbrella UI** — clickable tiles for all 23 apps, with the MCP server + tools each one consumes shown in the Tools column |
| http://localhost:28900 | **MCP Tool Explorer** — pick any MCP server, see its tools with their input schemas, fill in args in a form, invoke and see the raw response |

Each app has its own browser-served FastAPI UI on a port in the 28xxx range —
the umbrella links go straight there.

## 4. Try things out

Every app under [the umbrella UI](http://localhost:3001) has a **chat input**
or **trigger form**. The tile cards show example prompts you can paste in.

### Useful first paths

- **Just want to see one work?** Try [paper_scout](http://localhost:28808):
  paste an arXiv ID like `1706.03762` or ask for a topic ("recent papers on
  retrieval-augmented generation"). No API keys needed — arXiv and Semantic
  Scholar are both public.
- **Want to play with the tool layer directly?** Open the
  [tool explorer](http://localhost:28900), pick `mcp-knowledge` →
  `search_arxiv`, type a query, hit invoke. You'll see the raw MCP envelope
  the apps would otherwise unpack for the LLM.
- **Want to see MCP-mediated reasoning?** Try
  [travel_planner](http://localhost:28090) — it loads tools from three
  servers (web + knowledge + geo) and the LLM decides which to call when.

## 5. Stop or restart

```bash
docker compose down       # stop everything; volumes preserved
docker compose down -v    # stop + delete data volumes (drop_summarizer inbox,
                          # voice_journal db, video_qa cache, etc.)
docker compose restart apps   # bounce just the apps container
```

To rebuild a single image after a code change:

```bash
docker compose build mcp-web && docker compose up -d mcp-web
docker compose build apps    && docker compose up -d apps
```

## What each MCP server exposes

| Server | Port | Tools |
|---|---|---|
| `mcp-web` | 29100 | `web_search`, `fetch_webpage`, `fetch_webpage_links`, `fetch_feed`, `search_feeds`, `get_youtube_video_info`, `get_youtube_transcript` |
| `mcp-knowledge` | 29101 | `search_wikipedia`, `get_wikipedia_article`, `get_article_summary`, `get_article_sections`, `get_related_articles`, `search_arxiv`, `get_arxiv_paper`, `search_semantic_scholar`, `get_paper_references` |
| `mcp-geo` | 29102 | `geocode`, `find_hikes`, `search_attractions`, `get_weather` |
| `mcp-finance` | 29103 | `get_crypto_price`, `get_stock_quote` |
| `mcp-code` | 29104 | `check_python_syntax`, `extract_code_metrics`, `detect_language` |
| `mcp-local` | 29105 | `get_system_metrics`, `get_system_metrics_with_alerts`, `list_top_processes`, `check_disk_usage`, `find_large_files`, `get_service_status`, `transcribe_audio` |
| `mcp-text` | 29106 | `chunk_text`, `count_tokens`, `extract_text`, `extract_text_from_bytes` |

The browser version of this — with input schemas and a "try it" form — is
the [tool explorer](http://localhost:28900).

## What each app uses

See the umbrella UI's Tools column, or [apps/<app>/README.md](../apps/), or:

```bash
grep -rn "load_tools(\[" apps/ --include="*.py" | grep -v __pycache__
```

## Running without Docker

If you'd rather run on the host (faster iteration during dev):

```bash
pip install -r requirements.apps.txt -r requirements.mcp.txt
cd apps
python launch.py            # spawns 7 MCP servers + 23 apps as background processes
python launch.py status     # who's running
python launch.py logs newsletter   # tail one app's log
python launch.py stop       # kill them all
```

The launcher uses the same ports as Docker, so the umbrella UI and tool
explorer keep working as long as the rest of the stack is up.

## Troubleshooting

**An app's tile in the UI 404s.** The app's container is up but its FastAPI
process crashed at startup. Check `docker compose logs apps | grep -B2 <app>`.

**MCP tool returns `missing_key`.** Set the corresponding env var in
`apps/.env`, then `docker compose restart mcp-<server>` (the server reads env
vars at boot).

**Tests fail with "stack appears down".** Run `docker compose up -d` first
and wait ~30s for the apps container to finish launching all 23 processes.

**`make test` complains about pytest not installed.** Run
`make install-test-deps` once.

**The mcp-text image keeps rebuilding the docling/whisper layers.** That layer
caches by `requirements.mcp.txt` content — make sure you're not editing it
unnecessarily.
