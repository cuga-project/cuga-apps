# Dependency Drift Watcher

Our code stays still. Its dependencies don't.

Point it at any public GitHub repo. It inventories the models and Python
packages the repo depends on, finds drift (places where the outside world
changed but the code still assumes the old state), and suggests the fix. Every
finding quotes its source and links it. The app never writes to a repository
and needs no GitHub token.

**Port:** 28843 → http://localhost:28843

## How it works

1. Enter a repo in the left rail: `owner/repo`, `owner/repo@branch` or a
   `github.com/owner/repo` URL (default `cuga-project/cuga-apps`).
2. Pick a watch pack (**Models** or **Packages**) and ask a question, or click
   **Scan this pack**.
3. The app downloads the repo's public snapshot from GitHub (no token), keeps
   only the files the inventory reads (`*.py`, `*.toml`, `requirements*.txt`,
   `.env.example`), and caches it for an hour.
4. The agent reads the repo's side with inline tools:
   - `inventory_models` — every model id in code and config, with `file:line`
   - `inventory_packages` — every package in `requirements*.txt` and
     `pyproject.toml`, with the version specs the repo declares
   - `check_pypi` — the latest release on PyPI, and whether a pin or cap in the
     repo blocks it
   - `get_usage` — real requests per app from `usage_collector` (only for
     `cuga-project/cuga-apps`)
5. It reads the world's side from official sources through **Tavily's hosted
   MCP server** (`tavily_search`, `tavily_extract`, `tavily_map`,
   `tavily_crawl`, `tavily_research`).
6. It answers with a table (dependency · where it's used · quoted change ·
   impact) and a JSON findings block the app stores per repo and shows in the
   **Findings** tab.
7. For a one-line fix it calls `suggest_fix`, which stores a diff in the
   **Suggested fixes** tab for you to copy and apply with `git apply`.

## Governance

| Layer | What it does |
| --- | --- |
| Intent guard (CUGA) | Refuses requests for exploit or attack code |
| Playbook (CUGA) | Drift triage: inventory → scout → evidence → rank → draft |
| Tool guide (CUGA) | Official sources only; quote the exact sentence |
| Output formatter (CUGA) | Keeps the table and the JSON findings block |
| Egress guard (code) | Blocks any Tavily call whose arguments contain secrets, private IPs or internal host names (`DDW_INTERNAL_TERMS` adds your own words) |
| Domain guard (code) | Limits Tavily searches and URLs to the active pack's domains (`packs/*.yaml`); injects them when the agent omits `include_domains` |
| Read-only | No tokens and no writes: public snapshots in, suggested diffs out |
| Safe download | Public github.com repos only; size cap (`DDW_REPO_MAX_MB`); only plain files unpacked, never outside the cache folder |

The **Why** tab shows, for each answer, the CUGA policy decisions, the app
guards that fired, the sources read and the run receipt (tokens, LLM calls,
Tavily and PyPI calls, time).

The app keeps its CUGA policies in its own store (`.cuga/policies.db`, set
through `DYNACONF_POLICY__POLICY_DB_PATH`), so apps sharing a container can't
clear each other's policies.

## Grounding — no invented findings

The model sometimes answers from memory instead of using its tools, with
plausible files, models and quotes. The app doesn't rely on the model to avoid
that:

- **Inventory as fact.** The app runs the inventory itself and puts it in the
  request as the complete list of dependencies.
- **Every finding is checked.** A finding about a dependency the repo doesn't
  have is removed; so is one whose source URL wasn't read in this check (PyPI
  counts for packages the check looked up). When anything is removed, the
  answer is rebuilt from the verified findings and lists what was removed and why.
- **No sources, no answer.** If the agent read nothing outside the repo, the
  app retries once; if it still reads nothing, the user is told nothing was
  verified and nothing is saved.
- **PyPI facts don't need the model.** For packages, pins that block the latest
  release (and projects with no release in 18 months) become findings straight
  from PyPI's data.

These show in the **Why** tab as "Grounding check" events.

## Usage tracking

Tavily calls go through the shared MCP bridge, so the usage dashboard counts
them twice: under **MCP servers & tools** (server `tavily`, per tool) and under
**API calls** (provider `tavily`, app `dependency_drift_watcher`), next to
`mcp-web`'s own Tavily calls. PyPI lookups appear as provider `pypi`.

## Watch packs

Packs are YAML files in [`packs/`](packs/): official domains, seed pages for
map/crawl, crawl instructions, severity rules and, for packages, a priority
list checked first when the repo uses those packages. Add a pack by adding a
file; no code change.

## Run

```bash
python main.py --port 28843
# open http://127.0.0.1:28843   (add ?repo=owner/repo to preselect a repo)
```

Env:

| Variable | Required | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER`, `LLM_MODEL`, `AGENT_SETTING_CONFIG` | yes | Model for the agent |
| `TAVILY_API_KEY` | yes | Tavily's hosted MCP server (`mcp.tavily.com`) |
| `DDW_DEFAULT_REPO` | no | Repo scanned when none is given (default `cuga-project/cuga-apps`) |
| `DDW_REPO_MAX_MB` | no | Refuse repos whose download is larger (default `60`) |
| `DDW_SCAN_EVERY_HOURS` | no | Background scan of the default repo, every pack (default `0`, off) |
| `DDW_INTERNAL_TERMS` | no | Extra comma-separated words the egress guard blocks |
| `USAGE_COLLECTOR_URL`, `USAGE_DASHBOARD_TOKEN` | no | Real usage per app (cuga-apps only) |

HTTP API: `GET /repo?repo=…` checks a repo can be scanned. `POST /ask`
`{question, pack, repo}` and `POST /scan` `{pack, repo}` start a check and return
`202 {id, status}` at once; poll `GET /jobs/{id}` for live steps and, when
`status` is `done`, the `result`. (A Models check reads official sites and can
take several minutes — longer than Code Engine's 300 s request timeout — so it
never runs inside one request.) Also `GET /findings?repo=…&pack=…`,
`POST /decisions`, `GET /suggestions?repo=…`, `GET /status`, `GET /packs`.

Each check is bounded: crawls fetch at most 8 pages and maps 30 URLs, both on
the starting site, and page text is trimmed before the model reads it.

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Drift detection for the models and packages any public GitHub repo depends on.

**MCP servers consumed:**
- **tavily** (hosted by Tavily) — `tavily_search` · `tavily_extract` · `tavily_map` · `tavily_crawl` · `tavily_research`

**Inline `@tool` defs:** `inventory_models` · `inventory_packages` · `check_pypi` · `get_usage` · `get_watch_pack` · `list_accepted_risks` · `suggest_fix`

<!-- END: MCP usage -->
