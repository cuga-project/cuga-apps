# Travel Itinerary Planner

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Multi-MCP itinerary planning across web, knowledge, and geo.

**MCP servers consumed:**
- **mcp-web** — `web_search`
- **mcp-knowledge** — `get_wikipedia_article`
- **mcp-geo** — `geocode` · `search_attractions` · `get_weather`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

A conversational travel planning API powered by **CUGAAgent**.  
Post your destination and preferences — the agent autonomously calls real data sources,
reasons across the results, and writes a detailed day-by-day itinerary.

---

## Architecture

```
Client
  │
  │  POST /plan  or  POST /chat
  ▼
FastAPI Server  (main.py)
  │
  │  await agent.invoke(prompt, thread_id=...)
  ▼
CUGAAgent  ◄──── SYSTEM_INSTRUCTIONS (research workflow)
  │
  │  tool calls (autonomous, multi-step)
  ├──► get_city_overview   →  Wikipedia REST API
  ├──► get_weather         →  wttr.in
  ├──► get_coordinates     →  Nominatim (OpenStreetMap)
  ├──► search_attractions  →  OpenTripMap
  └──► search_web          →  Tavily
```

### The app's role (FastAPI server)

The server has two responsibilities:

1. **Define and own the tools.** Each tool is a Python async function decorated with
   LangChain's `@tool`. The function contains all the HTTP logic for its data source —
   auth, request shaping, response parsing, and formatting into clean text that the
   agent can reason over. The server passes these tools to `CugaAgent` at startup.

2. **Expose the HTTP API.** `/plan` and `/chat` translate incoming JSON requests into
   agent prompts and return the agent's responses. The server is stateless — conversation
   memory lives inside the agent via `thread_id`.

### CUGAAgent's role

CUGAAgent is the reasoning layer. It receives a natural-language prompt and a set of
tools, and autonomously decides:

- **Which tools to call** — based on what information is still missing.
- **In what order** — e.g. geocoding must happen before attraction search.
- **How many times** — it may call `search_attractions` multiple times with different
  categories, or `search_web` with different queries, until it has enough to write.
- **What to synthesise** — it combines outputs from all tools into a coherent,
  personalised itinerary rather than just concatenating raw results.

Multi-turn memory is handled automatically: the same `thread_id` in `/chat` lets the
agent refine or extend a plan it already wrote, with full context of prior tool results.

---

## Tools

### `get_city_overview(city)`
**Source:** Wikipedia REST API (no auth required)

Returns an encyclopedic summary of the city — history, geography, culture, and what
makes it a travel destination. Used as the agent's first call to orient itself before
planning activities.

### `get_weather(city, travel_month)`
**Source:** wttr.in (no auth required)

Returns current weather conditions and a 3-day forecast for the city, plus a contextual
note about the requested travel month. The agent uses this to recommend appropriate
clothing, flag rain seasons, and suggest indoor vs outdoor activity mixes.

### `get_coordinates(city)`
**Source:** Nominatim / OpenStreetMap (no auth required)

Geocodes a city name to `lat`/`lon`. This is a prerequisite step — the agent must call
this before `search_attractions` because OpenTripMap queries are coordinate-based, not
name-based.

### `search_attractions(lat, lon, city, category, limit)`
**Source:** OpenTripMap API (free tier, 500 req/day — API key required)

Returns named points of interest within 20 km of the city centre, filtered by category.
The agent calls this multiple times with different categories tailored to the traveller's
stated interests.

Available categories:
| Category | What it returns |
|---|---|
| `interesting_places` | General top sights (default) |
| `cultural` | Museums, galleries, theatres |
| `historic` | Castles, monuments, ancient sites |
| `natural` | Parks, mountains, lakes, nature reserves |
| `architecture` | Notable buildings and structures |
| `amusements` | Theme parks, entertainment |
| `sport` | Stadiums, outdoor sports venues |
| `foods` | Local food markets and culinary spots |

### `search_web(query)`
**Source:** Tavily (API key required)

Searches the live web and returns summaries of the top 5 results. Used by the agent for
anything structured databases can't provide: visa requirements, transport options and
prices, neighbourhood guides, seasonal events, safety advisories, and current restaurant
recommendations. The agent composes focused queries rather than asking about everything
at once.

---

## Data sources

| Source | Auth | Rate limit |
|---|---|---|
| Wikipedia REST API | None | Generous, fair-use |
| wttr.in | None | Fair-use |
| Nominatim (OpenStreetMap) | None | 1 req/sec, must set User-Agent |
| OpenTripMap | Free API key | 500 req/day on free tier |
| Tavily | API key | Depends on plan |

---

## Setup

### 1. Get API keys

- **OpenTripMap** (free, 500 req/day): https://opentripmap.io/product
- **Tavily**: https://tavily.com
- **Anthropic**: https://console.anthropic.com

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your keys
```

### 3. Install and run

```bash
# From this directory
uv run --project . main.py
```

Or with uvicorn directly:

```bash
uv run --project . uvicorn main:app --host 0.0.0.0 --port 28090 --reload
```

Server starts at `http://localhost:28090`.  
Interactive API docs: `http://localhost:28090/docs`

---

## API

### `POST /plan` — Generate an itinerary

```json
{
  "destination": "Kyoto",
  "days": 5,
  "interests": ["temples", "food", "traditional arts"],
  "travel_style": "mid-range",
  "travel_month": "April",
  "origin_city": "New York"
}
```

`travel_style` options: `budget` | `mid-range` | `luxury`

**Response:**
```json
{
  "destination": "Kyoto",
  "days": 5,
  "travel_month": "April",
  "itinerary": "## 5-Day Kyoto Itinerary — April ..."
}
```

### `POST /chat` — Follow-up conversation

Use the same `thread_id` as your `/plan` call to continue in context.

```json
{
  "message": "Can you swap Day 3 for something more outdoorsy?",
  "thread_id": "plan-kyoto"
}
```

### `GET /health`

```json
{ "status": "ok" }
```

---

## Example curl

```bash
# Generate a 7-day Tokyo itinerary
curl -s -X POST http://localhost:28090/plan \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "Tokyo",
    "days": 7,
    "interests": ["anime", "street food", "technology", "nature"],
    "travel_style": "mid-range",
    "travel_month": "October"
  }' | jq .

# Follow-up in the same conversation thread
curl -s -X POST http://localhost:28090/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the best way to do a day trip to Mount Fuji from Tokyo?",
    "thread_id": "plan-tokyo"
  }' | jq .
```
