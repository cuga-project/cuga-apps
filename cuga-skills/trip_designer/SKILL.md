---
name: trip_designer
description: Design a multi-day travel itinerary with a goal-shaped planner — you decide the decomposition, themes, and tool order. Use when the user wants a custom or unconventional itinerary, or when their constraints don't fit a generic "morning/afternoon/evening per day" template.
requirements: []
examples:
  - "Design a 5-day Iceland trip — must include geothermal sites and hiking, mid-budget"
  - "Plan 3 days in Tokyo for someone who hates crowds, prefers neighbourhoods over landmarks"
  - "4 nights in Lisbon with mobility limits — can't walk more than 1 km/day"
  - "Anniversary trip, 4 nights, $5k budget, somewhere walkable in Europe"
---

# Trip Designer — goal-shaped itinerary planner

You design travel itineraries by gathering real information (weather,
geography, attractions, practicalities) and composing them into a plan
that respects the user's constraints. Unlike `travel_planner`, this
skill prescribes **no fixed workflow** — you decide the decomposition,
order of investigation, and final shape of the itinerary.

A companion script — `scripts/trip_tools.py` — gives you a toolkit:
geocoding, weather, attractions, web search, Wikipedia. Use whichever
combination fits the user's brief.

## When to use this skill

Trigger on requests where a generic day-by-day template is the wrong
shape:

- Hard constraints (mobility, budget cap, must-include themes,
  return-by times)
- Off-template structures (a route trip, a 4-night anniversary, a
  themed crawl, a backcountry plan)
- The user explicitly wants a "custom" / "unconventional" / "themed"
  itinerary
- The user pushes back on a previous template and wants a redesign

For straightforward "X-day trip to Y, mid-budget, foodie focus", prefer
the sibling `travel_planner` skill — its prescribed workflow is the
right shape there.

## Setup

- `web_search` requires `TAVILY_API_KEY`.
- `search_attractions` requires `OPENTRIPMAP_API_KEY` (free 500/day).
- The other tools need no keys.

If a key is missing, the tool returns `{"error": "..."}`. Adapt — drop
that step from your plan, and tell the user which one was unavailable.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `geocode <place>` | Resolve place → lat/lon. | `{lat, lon, display_name}` |
| `get_weather <city>` | wttr.in current + 3-day forecast. | `{current, forecast}` |
| `search_attractions <lat> <lon> <category> [limit=10] [radius_m=20000]` | OpenTripMap POIs. Categories: `interesting_places`, `cultural`, `historic`, `natural`, `architecture`, `amusements`, `sport`, `foods`. | `{category, attractions: [{name, kinds, dist_m}, ...]}` |
| `web_search <query> [max_results=5]` | Tavily — current web results. | `{results: [{title, url, content}, ...]}` |
| `get_wikipedia_article <title>` | Wikipedia lead summary. | `{title, summary, url}` |
| `search_wikipedia <query> [max_results=6]` | Find article titles by keyword. | `{results: [{title, snippet, url}, ...]}` |

### Example invocation

```
python scripts/trip_tools.py geocode 'Reykjavik'
python scripts/trip_tools.py search_attractions 64.15 -21.94 natural 10
python scripts/trip_tools.py web_search 'Iceland geothermal pools opening hours' 4
```

## How to work

Two requirements; the rest is up to you.

### 1. Plan first, in your reply

Before calling any tool, write a short **Plan** section in your reply:

```
**Plan**
- Decomposition: <how you'll break this trip up — by day, by region, by theme>
- Research intent: <what you'll look up and why>
- Output shape: <what the final itinerary will look like>
```

The user reads this verbatim. If you replan as you learn, write a
revised Plan and explain what changed.

### 2. Cite real sources for every claim

Every claim about a place, time, cost, or fact must come from something
a tool returned. Never invent attractions, distances, prices, opening
hours, or names.

If the user supplied **hard constraints** (budget caps, return-by
times, must-include themes, mobility limits), respect them as
constraints, not suggestions. Build the itinerary around them.

## Tone & failure modes

- Show your reasoning. The plan is part of the deliverable, not
  scaffolding.
- If a tool errors, say so plainly and adapt the plan — don't silently
  drop a step.
- **Never** invent attractions, distances, prices, opening hours, or
  names. If the data isn't there, say it isn't there.
- If the user's ask doesn't actually need a custom approach (a routine
  3-day city break), say so and recommend they use `travel_planner`
  instead. Don't manufacture complexity.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly and stop.

## Output format

There's no fixed template. Common shapes:

- **By day** when the trip is dense and chronological.
- **By region** when it's a route trip with travel days.
- **By theme** when the user asked for "geothermal + hiking" or
  "neighbourhoods, not landmarks".
- **By budget bucket** when the user has a hard cap.

Whatever shape you pick, end with:

```
**Practical**
- Getting there / around: <citing tool sources>
- Estimated cost: <broken down per the shape; cite sources for prices>
- Key bookings to make in advance: <list>

**Constraint check**
- <constraint 1>: <how the itinerary respects it>
- <constraint 2>: ...
```

The constraint check is mandatory — it shows the user your itinerary
actually answers their brief.
