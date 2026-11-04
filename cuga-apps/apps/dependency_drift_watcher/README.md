# Dependency Drift Watcher

Our code stays still. Its dependencies don't.

A FastAPI app that watches the models and Python packages our apps depend on,
finds drift (places where the outside world changed but our code still assumes
the old state), and drafts the fix for a person to approve. Every finding quotes
its source and links it.

**Port:** 28843 → http://localhost:28843

## How it works

1. Pick a watch pack (**Models** or **Packages**) and ask a question, or click **Scan this pack**.
2. The agent inventories our side with inline tools:
   - `inventory_models` — every model id in code and config, with `file:line`
   - `inventory_packages` — every package in `requirements*.txt`, its specs, and the installed version
   - `get_usage` — real requests per app from `usage_collector`
3. It reads the world's side from official sources through **Tavily's hosted MCP server**
   (`tavily_search`, `tavily_extract`, `tavily_map`, `tavily_crawl`, `tavily_research`)
   and upstream releases through **GitHub's MCP server** (`get_latest_release`, `list_releases`).
4. It answers with a table (dependency · where we use it · quoted change · impact) and a
   JSON findings block the app stores and shows in the **Findings** tab.
5. For a one-line fix it calls `propose_fix`, which only queues a diff. A person approves it
   in the **Approvals** tab. With `GITHUB_TOKEN` and `DDW_GITHUB_REPO` set, approval opens a
   draft PR through GitHub MCP; otherwise you get the diff to apply locally.

## Governance

| Layer | What it does |
| --- | --- |
| Intent guard (CUGA) | Refuses requests for exploit or attack code |
| Playbook (CUGA) | Drift triage: inventory → scout → evidence → rank → draft |
| Tool guide (CUGA) | Official sources only; quote the exact sentence |
| Output formatter (CUGA) | Keeps the table and the JSON findings block |
| Egress guard (code) | Blocks any Tavily call whose arguments contain secrets, private IPs or internal host names (`DDW_INTERNAL_TERMS` adds your own words) |
| Domain guard (code) | Limits Tavily searches and URLs to the active pack's domains (`packs/*.yaml`); injects them when the agent omits `include_domains` |
| Human approval (app) | The agent never writes. GitHub writes happen only after **Approve**, made by the app, not the agent |

The **Why** tab shows, for each answer, the CUGA policy decisions, the app guards that fired,
the sources read and the run receipt (tokens, LLM calls, Tavily and GitHub calls, time).

The app keeps its CUGA policies in its own store (`.cuga/policies.db`, set through
`DYNACONF_POLICY__POLICY_DB_PATH`), so apps sharing a container can't clear each other's policies.

## Watch packs

Packs are YAML files in [`packs/`](packs/): official domains, seed pages for map/crawl,
crawl instructions, severity rules and, for packages, a watch list with GitHub repos.
Add a pack by adding a file; no code change.

## Run

```bash
python main.py --port 28843
# open http://127.0.0.1:28843
```

Env:

| Variable | Required | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER`, `LLM_MODEL`, `AGENT_SETTING_CONFIG` | yes | Model for the agent |
| `TAVILY_API_KEY` | yes | Tavily's hosted MCP server (`mcp.tavily.com`) |
| `GITHUB_TOKEN` | no | GitHub's MCP server: release data; PRs on approval |
| `DDW_GITHUB_REPO`, `DDW_GITHUB_BASE` | no | Fork + base branch for approved fixes (default base `main`) |
| `DDW_GITHUB_PATH_PREFIX` | no | Repo path of this checkout's root (default `cuga-apps/`) |
| `DDW_REPO_PATH` | no | Directory to inventory (default: the cuga-apps root) |
| `DDW_SCAN_EVERY_HOURS` | no | Background scan of every pack (default `0`, off) |
| `USAGE_COLLECTOR_URL`, `USAGE_DASHBOARD_TOKEN` | no | Real usage per app |

Use a fork and a fine-grained token (contents + pull requests on that fork only).

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Drift detection for the models and packages our apps depend on.

**MCP servers consumed:**
- **tavily** (hosted by Tavily) — `tavily_search` · `tavily_extract` · `tavily_map` · `tavily_crawl` · `tavily_research`
- **github** (hosted by GitHub) — `get_latest_release` · `list_releases` · `list_tags` · `get_file_contents`; app-side on approval: `create_branch` · `create_or_update_file` · `create_pull_request`

**Inline `@tool` defs:** `inventory_models` · `inventory_packages` · `get_usage` · `get_watch_pack` · `list_accepted_risks` · `propose_fix`

<!-- END: MCP usage -->
