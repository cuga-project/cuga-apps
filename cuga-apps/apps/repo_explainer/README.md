# Repo Explainer

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Explain any repo: get a newcomer's briefing.

**MCP servers consumed:**
- **mcp-web** — `fetch_webpage` · `fetch_webpage_links`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

A Cuga-powered app that helps to get a newcomers's briefing for any repo.
Paste a repo URL into the chat — the agent explain what the project does, who it's for, how to install and run it, and where a first-time contributor could start.

## Port

**28837**

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Set required env vars (example: Anthropic)
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=<your-key>
export AGENT_SETTING_CONFIG=/path/to/settings.toml

# Run
python main.py --port 28837

# Open in browser
open http://127.0.0.1:28837
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Always | `anthropic` \| `openai` \| `rits` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Always | Model name for the chosen provider (e.g. `claude-sonnet-4-6`, `gpt-4o`) |
| `AGENT_SETTING_CONFIG` | Always | Path to the agent settings TOML file |
| `ANTHROPIC_API_KEY` | When `LLM_PROVIDER=anthropic` | Anthropic API key |
| `OPENAI_API_KEY` | When `LLM_PROVIDER=openai` | OpenAI API key |
| `RITS_API_KEY` | When `LLM_PROVIDER=rits` | IBM RITS API key |

## Example prompts

1. `Explain https://github.com/cuga-project/cuga-agent`
2. `What does https://github.com/psf/requests do?`
3. `How do I get started with https://github.com/fastapi/fastapi?`
4. `Is https://github.com/pallets/flask beginner-friendly?`
5. `Summarize https://github.com/cuga-project/cuga-apps for a new contributor overview`

## Tools

| Tool | Description |
|---|---|
| `fetch_webpage` | Fetches a URL, strips HTML/scripts/nav, returns readable text (truncated to 12 000 chars) |
| `fetch_webpage_links` | Returns the list of external hyperlinks found on a page |
