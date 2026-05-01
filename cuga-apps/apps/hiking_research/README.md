# Hiking Research

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Find trails near a place via OSM Overpass + web reviews.

**MCP servers consumed:**
- **mcp-geo** — `geocode` · `find_hikes`
- **mcp-web** — `web_search`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Discover, filter, and compare hiking trails near any location — powered by OpenStreetMap trail data and AI-synthesised user reviews.

**Port:** 28805

## Features

- **Location search** — find hikes near any city, park, or landmark by name
- **Difficulty filter** — easy, moderate, or hard (derived from OSM `sac_scale` tags and distance)
- **Kid-friendly filter** — flags short, easy trails suitable for children
- **Review summaries** — tap "Get Reviews" on any trail to get an AI-synthesised summary of what hikers say
- **No key required for trail discovery** — uses the free OpenStreetMap / Overpass API
- **Browser UI** — chat panel on the left, live trail cards on the right

## Quick Start

```bash
python main.py
# open http://127.0.0.1:28805
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | yes | `rits` \| `anthropic` \| `openai` \| `ollama` \| `watsonx` \| `litellm` |
| `LLM_MODEL` | no | Model override |
| `TAVILY_API_KEY` | no | Enables "Get Reviews" feature (sign up at tavily.com) |

Trail discovery works without any API keys. Review summaries require `TAVILY_API_KEY`.

## Example Prompts

- "Easy hikes near Yosemite, CA"
- "Kid-friendly trails near Boulder, CO"
- "Moderate hikes near Asheville, NC within 40 km"
- "Hard hikes near Denver, CO"
- "Family hikes near Lake Tahoe"
- "Tell me about user reviews for: Half Dome Trail"

## How It Works

1. **`geocode_location`** — converts a place name to lat/lon via Nominatim (OpenStreetMap)
2. **`find_hikes`** — queries the Overpass API for named hiking route relations, then filters and ranks them by difficulty and kid-friendliness
3. **`get_review_summary`** — searches the web via Tavily and synthesises hiker reviews for a specific trail

Difficulty is derived from the OSM `sac_scale` tag where available, with a distance-based fallback:
- `sac_scale=hiking` → easy
- `sac_scale=mountain_hiking` → moderate
- `sac_scale=demanding_mountain_hiking` or above → hard
