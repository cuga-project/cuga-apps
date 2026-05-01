# IBM What's New Monitor

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

IBM Cloud release notes / what-is-new digest with email reports.

**MCP servers consumed:**
- **mcp-web** — `web_search` · `fetch_webpage`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Tracks IBM Cloud service release notes and "What's New" announcements. Configure which services to watch, schedule a daily or weekly digest, and get email alerts when updates land.

## Port

`28814`

## Run

```bash
cd apps/ibm_whats_new
pip install -r requirements.txt
python main.py
```

Then open: http://127.0.0.1:28814

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Yes | Model name for the chosen provider |
| `AGENT_SETTING_CONFIG` | Yes | Path to agent settings TOML |
| `TAVILY_API_KEY` | Yes | Tavily search key — searches scoped to ibm.com / cloud.ibm.com |
| `SMTP_HOST` | Optional | SMTP server (default: smtp.gmail.com) |
| `SMTP_USERNAME` | Optional | Sender email address |
| `SMTP_PASSWORD` | Optional | App password |
| `DIGEST_TO` | Optional | Recipient email for digests |

## Example Prompts

- `What is new in IBM Code Engine in 2026?`
- `Latest changes to IBM Cloud Object Storage`
- `Any IBM Cloud breaking changes in the last 30 days?`
- `Summarize IBM watsonx.ai release notes from this month`
- `What IBM Cloud services had pricing or plan updates recently?`

## How It Works

1. Add IBM Cloud services to the watch list (Code Engine, watsonx.ai, Event Streams, etc.)
2. Set a schedule (daily / weekly) — the agent auto-checks for release notes at each interval
3. If updates are found, they appear in the Digest Log and are emailed if SMTP is configured
4. Use the chat panel to ask ad-hoc questions about any IBM Cloud service changes

**Tools:**
- `search_ibm_updates(query)` — Tavily search scoped to ibm.com and cloud.ibm.com
- `fetch_release_notes(url)` — reads a specific release notes page (IBM URLs only)
