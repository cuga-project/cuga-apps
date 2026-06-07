# GitHub Trending — CUGA Demo App

Ask what's trending on GitHub — overall, by language, or by topic — and the
agent returns a ranked board of repositories, each with a plain-English
summary of **what the project actually offers**: what it's for, who it's for,
and why it's gaining attention right now.

All tools are **inline `@tool` defs**. The live data comes from GitHub's
public REST API via direct `httpx` calls — no MCP servers, no keys required
(set `GITHUB_TOKEN` to raise the rate limit).

## What it does

- **find_trending_repos** — approximates "trending" as recently-created repos
  that have gained the most stars in a window (daily / weekly / monthly), with
  optional `language:` and `topic:` qualifiers, via the GitHub Search API.
- **get_repo_readme / get_repo_languages** — pull each repo's README (raw) and
  language breakdown so the agent can summarize the project accurately.
- **set_filters / save_repos** — per-session filters + the structured card
  board the right panel renders.

The agent: records any filters → finds trending repos → reads the top READMEs
→ writes a `summary`, an `offers` bullet list, and a `why_trending` line per
repo → saves the board → replies with a short numbered list.

## Run

```bash
cd apps/github_trending
pip install -r requirements.txt    # plus: pip install cuga
python main.py --port 28823
# optional, for higher GitHub rate limits:
#   export GITHUB_TOKEN=ghp_...
```

Then open <http://127.0.0.1:28823> and try:

- `What's trending this week?`
- `Trending Python repos`
- `New LLM agent frameworks gaining stars`
- `Today's hottest Rust CLI tools`
- `Trending this month in the devtools topic`

## Endpoints

| Method | Path                   | Purpose                                            |
| ------ | ---------------------- | -------------------------------------------------- |
| GET    | `/`                    | Two-panel UI                                       |
| POST   | `/ask`                 | `{question, thread_id}` → `{answer, thread_id}`    |
| GET    | `/session/{thread_id}` | Session state (filters + ranked repo cards)        |
| GET    | `/health`              | `{"ok": true}`                                     |

## Environment

| Var                    | Required | Notes                                            |
| ---------------------- | -------- | ------------------------------------------------ |
| `LLM_PROVIDER`         | yes      | rits \| anthropic \| openai \| watsonx \| …      |
| `LLM_MODEL`            | no       | model override                                   |
| `AGENT_SETTING_CONFIG` | no       | defaulted in `make_agent`                        |
| `GITHUB_TOKEN`         | no       | raises the GitHub API rate limit                 |

## Notes

- "Trending" has no official GitHub API; this uses `created:>DATE sort=stars`
  as a stable, key-free proxy. It surfaces *new* repos rising fast — not the
  same as github.com/trending, which weights commits/contributors too.
- Unauthenticated search is rate-limited (~10 req/min). If you hit it, the
  tool returns a `rate_limited` code and the agent tells the user to set
  `GITHUB_TOKEN` or retry shortly.
