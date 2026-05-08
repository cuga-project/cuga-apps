---
name: travel_planner
description: Generate a structured multi-day travel itinerary for any destination by combining Wikipedia background, real weather, geocoding, attractions search, and live web search. Use when the user asks to "plan a trip", "build an itinerary", or "X-day itinerary for &lt;place&gt;".
requirements: []
examples:
  - "5-day trip to Tokyo, mid-budget, foodie focus"
  - "Plan 3 days in Lisbon for a family with young kids in March"
  - "Build a 7-day Iceland itinerary, $5k budget"
  - "Itinerary for Marrakech in October"
---

# Travel Itinerary Planner

You produce structured day-by-day travel itineraries. The skill is
prescriptive: it pins a research workflow (Wikipedia → weather →
geocode → attractions → web → write) so every itinerary is grounded in
real data. For a planner that decides its own decomposition, see the
sibling `trip_designer` skill.

A companion script — `scripts/travel_tools.py` — wraps five free APIs:
`get_wikipedia_article`, `search_wikipedia`, `geocode`, `get_weather`,
`search_attractions`, and `web_search`.

## When to use this skill

Trigger on any request that involves:

- "Plan a trip / itinerary / vacation to &lt;place&gt;"
- "&lt;N&gt;-day itinerary for &lt;X&gt;"
- "What should I do in &lt;city&gt; for a week"
- "Build me a &lt;style&gt; itinerary for &lt;place&gt;"

## Setup

- `web_search` requires `TAVILY_API_KEY`.
- `search_attractions` requires `OPENTRIPMAP_API_KEY` (free 500/day).
- The other tools need no keys.

If a key is missing, the affected subcommand returns
`{"error": "..."}`. Skip its section in the itinerary and tell the user
plainly which one was unavailable. Do NOT fabricate the data the
unavailable tool would have returned.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `get_wikipedia_article <title>` | Lead summary of a Wikipedia article. | `{title, summary, url}` |
| `search_wikipedia <query> [max_results=6]` | Find article titles when you don't know the exact one. | `{results: [{title, snippet, url}, ...]}` |
| `geocode <place>` | Resolve city → lat/lon (needed for attractions). | `{lat, lon, display_name}` |
| `get_weather <city>` | wttr.in current + 3-day forecast (use to seed packing/season tips). | `{current: {...}, forecast: [...]}` |
| `search_attractions <lat> <lon> <category> [limit=10] [radius_m=20000]` | OpenTripMap POIs near a point. | `{category, attractions: [{name, kinds, dist_m}, ...]}` |
| `web_search <query> [max_results=5]` | Tavily — current web results (visa rules, transport costs, festivals). | `{results: [{title, url, content}, ...]}` |

OpenTripMap categories: `interesting_places`, `cultural`, `historic`,
`natural`, `architecture`, `amusements`, `sport`, `foods`.

### Example invocation

```
python scripts/travel_tools.py get_wikipedia_article 'Tokyo'
python scripts/travel_tools.py geocode 'Tokyo'
python scripts/travel_tools.py get_weather 'Tokyo'
python scripts/travel_tools.py search_attractions 35.68 139.76 cultural 8
python scripts/travel_tools.py web_search 'Tokyo visa requirements' 4
```

## Prescribed workflow

Run these in order — don't write the itinerary until all six steps
finish:

1. `get_wikipedia_article(<destination>)` for background. If the title
   isn't an exact match, run `search_wikipedia` and pick the top hit.
2. `get_weather(<destination>)` to factor in climate / packing.
3. `geocode(<destination>)` for lat/lon.
4. `search_attractions(lat, lon, category)` **at least twice** with two
   categories that match the traveller's interests. Examples:
   - "general sightseeing" → `cultural` + `historic`
   - "family with kids" → `interesting_places` + `amusements`
   - "outdoorsy" → `natural` + `historic`
   - "foodie" → `foods` + `cultural`
5. `web_search` **at least twice**:
   - visa / entry requirements (skip for domestic trips)
   - local transport options + approximate costs
   - notable events or festivals during the travel month
6. Only then, write the itinerary.

## Itinerary format

```
**<N>-Day <Destination> Itinerary** — <Travel Month>

<2-3 sentence destination intro from Wikipedia, lightly trimmed>

**Weather & packing** (use the forecast + travel month)
<2-3 sentences>

**Day 1: <Theme>**
- **Morning** (~3h) — <Attraction> — booking tip if needed
- **Afternoon** (~3h) — <Attraction>
- **Evening** (~2h) — <Activity> — dinner suggestion if relevant

**Day 2: <Theme>**
... (repeat per day)

**Practical**
- Getting there: <flights / trains, citing the web search>
- Getting around: <transit, ride apps, walkability>
- Budget (per person/day): accommodation $X · food $X · activities $X · transport $X
- Visa / entry: <short note, citing the web search>

**Top 3 insider tips**
1. ...
2. ...
3. ...
```

## Tone & failure modes

- Use **real attraction names** from `search_attractions`. Don't invent
  POIs.
- Cite practical claims (visa, transport cost, festivals) inline as
  markdown links to the web-search hit.
- If `search_attractions` returns very few hits, broaden the radius
  (`radius_m=40000`) before giving up. Don't pad the day with filler.
- If `get_weather` errors, say "weather data unavailable" and skip the
  packing tips; do not invent temperatures.
- Never invent prices. If the web search didn't surface a number, say
  "expect mid-range pricing for this region" and move on.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not write an ungrounded itinerary.
