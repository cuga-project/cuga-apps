# Movie Recommender

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Personalised movie picks; sessionful preferences.

**MCP servers consumed:**
- **mcp-knowledge** — `get_wikipedia_article`

**Inline `@tool` defs (kept local because they touch app-specific state):** `save_preference` · `get_preferences` · `save_recommendations`

<!-- END: MCP usage -->

A CUGA-powered demo app that collects your movie preferences through natural conversation
and generates personalised watch-next suggestions. Tell the agent about films you love,
genres you enjoy, favourite directors and actors, or just your mood — it builds a taste
profile and recommends what to watch next.

Movie details are looked up via the free Wikipedia REST API — no additional API key required.

## Port

**28806**

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
python main.py --port 28806

# Open in browser
open http://127.0.0.1:28806
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

1. `I love Inception and The Dark Knight — what should I watch next?`
2. `I enjoy sci-fi and psychological thrillers, suggest 5 films`
3. `My favourite director is Denis Villeneuve`
4. `I'm in the mood for something light and funny tonight`
5. `I dislike jump-scare horror — what else is good?`
6. `Recommend something with Tom Hanks I might have missed`

## Tools

| Tool | Description |
|---|---|
| `lookup_movie` | Fetches a Wikipedia summary for a given movie title (plot, cast, director) |
| `save_preference` | Persists a user preference (genre, liked/disliked movie, actor, director, mood) |
| `get_preferences` | Retrieves all saved preferences for the current session |
| `save_recommendations` | Stores the structured recommendation list so the UI can render it as cards |

## UI layout

- **Left panel** — Chat interface with 9 clickable prompt chips to get started quickly
- **Right panel** — Live view of your taste profile (auto-refreshes every 10 s) plus
  recommendation cards that appear after the agent generates suggestions
