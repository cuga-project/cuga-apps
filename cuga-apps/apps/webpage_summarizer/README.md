# Webpage Summarizer

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Fetch and summarise any webpage; follow links.

**MCP servers consumed:**
- **mcp-web** — `fetch_webpage` · `fetch_webpage_links`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

A Cuga-powered demo app that fetches and summarises any webpage you provide.
Paste a URL into the chat — the agent retrieves the page, strips boilerplate, and
returns a structured summary.

## Port

**28071**

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
python main.py --port 28071

# Open in browser
open http://127.0.0.1:28071
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

1. `Summarize https://en.wikipedia.org/wiki/Large_language_model`
2. `What is this page about? https://python.org`
3. `Key takeaways from https://openai.com/blog`
4. `List all links on https://news.ycombinator.com`
5. `https://github.com/langchain-ai/langchain — give me a one-paragraph overview`

## Tools

| Tool | Description |
|---|---|
| `fetch_webpage` | Fetches a URL, strips HTML/scripts/nav, returns readable text (truncated to 12 000 chars) |
| `fetch_webpage_links` | Returns the list of external hyperlinks found on a page |
