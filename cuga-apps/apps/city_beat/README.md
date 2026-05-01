# City Beat

Type a city name. The agent assembles a one-screen briefing — weather,
today's news, encyclopedia background, optional nearby attractions, optional
crypto spotlight — by combining tools from **four MCP servers** (`geo`,
`web`, `knowledge`, `finance`) with light **inline session-state tools**.

**Port:** 28821 → http://localhost:28821
**Tools:** mix of MCP-loaded (geo / web / knowledge / finance) + 6 inline
@tool defs for per-session state and the briefing card.

## How it works

1. The user names a city. The agent calls the inline `set_current_city`
   to remember it and adds the city to a per-session watchlist.
2. `geocode` (mcp-geo) resolves the city to lat/lon + display name.
3. The agent fans out:
   - `get_weather` (mcp-geo) for current conditions + outlook
   - `web_search` (mcp-web) biased by any focus topics the user has set
   - `get_wikipedia_article` (mcp-knowledge) for the background blurb
   - optional `search_attractions` (mcp-geo) if the user asks for things to do
   - optional `get_crypto_price` (mcp-finance) if a `crypto_spotlight`
     ticker is set on the session
4. The agent calls `save_briefing` with a structured JSON object. The
   right panel polls `/session/{thread_id}` and renders it.

## Run

```bash
pip install -r requirements.txt
pip install -e /path/to/cuga-agent     # if not already installed

export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...

# MCP server selection (defaults below) — typically you don't override
# these unless you're testing against a specific deployment.
#
# Local (default outside docker / CE):  http://localhost:<port>/mcp
# Docker compose (auto-detected):       http://mcp-<name>:<port>/mcp
# Code Engine (auto when CE_APP set):   https://cuga-apps-mcp-<name>.<project>.<region>.codeengine.appdomain.cloud/mcp
#
# Force the public CE endpoints from a laptop:
#   export CUGA_TARGET=ce
#
# Or pin a single server explicitly:
#   export MCP_GEO_URL=https://cuga-apps-mcp-geo.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp

python main.py --port 28821
# open http://127.0.0.1:28821
```

The MCP servers themselves need their own API keys (they live on the MCP
host process, not in this app):

| MCP server | Tool | Key needed | Where to set |
|---|---|---|---|
| `web` | `web_search` | `TAVILY_API_KEY` | mcp-web's environment |
| `geo` | `search_attractions` | `OPENTRIPMAP_API_KEY` | mcp-geo's environment |
| `geo` | `geocode`, `get_weather`, `find_hikes` | none | n/a |
| `knowledge` | all | none | n/a |
| `finance` | `get_crypto_price` | none | n/a |
| `finance` | `get_stock_quote` | `ALPHA_VANTAGE_API_KEY` | mcp-finance's environment |

## Environment variables (this app)

| Var | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | yes | Model name |
| `AGENT_SETTING_CONFIG` | yes (defaulted) | Path to CUGA settings TOML; defaulted per-provider in `make_agent()`. |
| `CUGA_TARGET` | no | Set to `ce` to force the public Code Engine MCP URLs. |
| `MCP_<NAME>_URL` | no | Override the URL for an individual MCP server (`MCP_GEO_URL`, `MCP_WEB_URL`, `MCP_KNOWLEDGE_URL`, `MCP_FINANCE_URL`). |

## Example prompts

- "Brief me on Lisbon"
- "What's happening in Tokyo today? Focus on tech startups."
- "Brief me on Mexico City — and add live music to the focus"
- "Spotlight ETH on the briefing"
- "What can I do in Berlin tonight?"
- "Brief me on Bangalore — focus on weather and transit"

## Tools

**MCP-loaded** (four servers, picked up by `load_tools(["geo", "web",
"knowledge", "finance"])`):

- `geo.geocode`, `geo.get_weather`, `geo.search_attractions`, `geo.find_hikes`
- `web.web_search`, `web.fetch_webpage`, `web.fetch_feed`, `web.search_feeds`,
  `web.get_youtube_video_info`, `web.get_youtube_transcript`
- `knowledge.search_wikipedia`, `knowledge.get_wikipedia_article`,
  `knowledge.get_article_summary`, `knowledge.get_article_sections`,
  `knowledge.get_related_articles`, `knowledge.search_arxiv`,
  `knowledge.get_arxiv_paper`, `knowledge.search_semantic_scholar`,
  `knowledge.get_paper_references`
- `finance.get_crypto_price`, `finance.get_stock_quote`

**Inline** (defined in `main.py`, manage per-session state):

| Tool | Purpose |
|---|---|
| `set_current_city` | Remember the active city + add to watchlist. |
| `add_focus_topic` | Bias the news query for this session. |
| `clear_focus_topics` | Wipe the bias. |
| `set_crypto_spotlight` | Save a ticker for the optional crypto widget. |
| `get_session_state` | Read current city + topics + watchlist. |
| `save_briefing` | Persist the structured briefing object. |

## Integration into cuga-apps

This app already lives at `apps/city_beat/`. Wire it into the rest of the
repo:

1. Add `"city_beat": 28821` to `APP_PORTS` in `apps/_ports.py`.
2. Register it in `apps/launch.py` (`PROCS` list).
3. Add a service block in `docker-compose.yml`.
4. Add a tile entry in `ui/src/data/usecases.ts`.
5. Optionally add the launch line to `start.sh`.

The app needs MCP servers `geo`, `web`, `knowledge`, `finance` to be up.
On Code Engine these are already deployed at
`cuga-apps-mcp-{geo,web,knowledge,finance}.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud`
— `_mcp_bridge` resolves to those URLs automatically when CE env vars are
present. Locally, run `python apps/launch.py` to bring them all up.
