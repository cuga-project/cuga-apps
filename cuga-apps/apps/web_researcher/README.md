# Web Researcher

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

On-demand & scheduled web research via Tavily.

**MCP servers consumed:**
- **mcp-web** — `web_search`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Schedules recurring web research tasks using the Tavily search API. Results are logged to SQLite and can be emailed on a schedule.

**Port:** 28798

## Features

- **Tavily-powered search** — real-time web search via `tavily-python`
- **Scheduled topics** — add topics with hourly / daily / weekly schedule
- **Auto-run** — background scheduler checks for overdue topics every 5 minutes
- **Email results** — optionally email research results when topics run
- **Persistent log** — all research results stored in `research.db`
- **Browser UI** — chat + scheduled topics panel + research log

## Quick Start

```bash
pip install -r requirements.txt
python main.py
# open http://127.0.0.1:28798
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | — | `rits` \| `anthropic` \| `openai` \| `ollama` |
| `LLM_MODEL` | — | Model override |
| `TAVILY_API_KEY` | — | Get one at tavily.com |
| `SMTP_HOST` | — | e.g. `smtp.gmail.com` |
| `SMTP_USERNAME` | — | Your email address |
| `SMTP_PASSWORD` | — | App password |
| `ALERT_TO` | — | Results recipient email |

## Usage

1. Start the server and open the browser UI
2. Enter your Tavily API key in the settings panel
3. Add scheduled topics (e.g. "AI news" → daily)
4. The scheduler runs overdue topics automatically every 5 minutes
5. Chat with the agent for ad-hoc searches: *"Search for latest React 19 features"*

## Example Questions

- "What's the latest news on quantum computing?"
- "Search for Python 3.13 release notes"
- "Find recent papers on RAG architectures"
- "What are the top stories about climate policy this week?"
- "Search for FastAPI best practices"
