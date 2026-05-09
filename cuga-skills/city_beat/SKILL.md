---
name: city_beat
description: Assemble a one-screen city briefing — weather, today's news, encyclopedia background, optional attractions, optional crypto spotlight — for any city the user names. Use when the user asks for a "briefing", "what's happening in", or "tell me about &lt;city&gt; today".
requirements: []
examples:
  - "What's happening in Boston today"
  - "Brief me on Lisbon"
  - "City briefing for Boulder, CO"
  - "Tell me about Tokyo today, focus on tech news"
---

# City Beat — one-screen city briefing

You assemble a glanceable briefing for any city the user names: weather,
news, encyclopedia background, plus optional attractions and a crypto
spotlight if the user asked for one.

A companion script — `scripts/city_tools.py` — wraps five free APIs:
`geocode` (Nominatim), `get_weather` (wttr.in), `search_attractions`
(OpenTripMap), `web_search` (Tavily, for news), `get_wikipedia_article`,
plus an optional `get_crypto_price` (CoinGecko).

## When to use this skill

Trigger on any request that involves:

- "What's happening in / brief me on / tell me about &lt;city&gt; today"
- "City briefing for &lt;X&gt;"
- "Catch me up on &lt;city&gt;"
- A bare city name with no other ask — produce the standard briefing

## Setup

- `web_search` requires `TAVILY_API_KEY` (free at tavily.com).
- `search_attractions` requires `OPENTRIPMAP_API_KEY` (free 500/day at
  opentripmap.com).
- `get_weather`, `geocode`, `get_wikipedia_article`, `get_crypto_price`
  need no keys.

When a key is missing, the corresponding subcommand returns
`{"error": "..."}`. Skip that section in the briefing and tell the user
plainly which one was unavailable.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `geocode <place>` | Nominatim — resolve city → lat/lon. | `{lat, lon, display_name}` or `{error}` |
| `get_weather <city>` | wttr.in — current conditions + 3-day forecast. | `{current: {...}, forecast: [...]}` |
| `search_attractions <lat> <lon> [category=cultural] [limit=6] [radius_m=20000]` | OpenTripMap — POIs near a coordinate. | `{category, attractions: [{name, kinds, dist_m}, ...]}` |
| `web_search <query> [max_results=5]` | Tavily — current web results (use for news). | `{results: [{title, url, content}, ...]}` |
| `get_wikipedia_article <title>` | Wikipedia REST — lead summary of an article. | `{title, summary, url}` |
| `get_crypto_price <symbol> [vs_currency=usd]` | CoinGecko — price + 24h change. | `{symbol, price, change_24h, market_cap}` |

### Example invocation

```
python scripts/city_tools.py geocode 'Boston'
# → {"lat": 42.36, "lon": -71.06, "display_name": "Boston, MA, USA"}

python scripts/city_tools.py get_weather 'Boston'
python scripts/city_tools.py search_attractions 42.36 -71.06 cultural 6
python scripts/city_tools.py web_search 'Boston news today' 5
python scripts/city_tools.py get_wikipedia_article 'Boston'
python scripts/city_tools.py get_crypto_price btc
```

## Workflow

1. `geocode(city)`. If it errors, ask the user to clarify and stop.
2. Run these in any order; each must succeed for its section to appear:
   - `get_weather(city)` for the weather widget.
   - `web_search("<city> news today")` (or with focus topics) for
     headlines. Cap `max_results` at 5.
   - `get_wikipedia_article(<city>)` for the background blurb. If it
     returns empty, search-then-fetch the top hit.
3. Optional sections:
   - **Attractions** — only if the user asked about things to do, OR the
     briefing would otherwise feel sparse. Use category `cultural`,
     `historic`, or `interesting_places`.
   - **Crypto** — only if the user mentioned a ticker (`btc`, `eth`,
     `sol`, etc.). Skip otherwise.
4. Assemble the briefing in the format below. Each `news` item must have
   a real `url` from the search result.
5. End with a one-sentence **tagline** capturing the city's vibe today.

## Tone & failure modes

- Cite news as inline markdown links. Wikipedia gets a single
  "[More on Wikipedia](url)" link.
- **Never invent** headlines, weather numbers, or coordinates. If a
  tool fails, say so and skip that section.
- Tagline must reflect the *actual* feel of the briefing — not a generic
  platitude.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not guess at a city's news or weather.

## Output format

```
**City Beat: <City>** — <display_name>

*<one-line tagline reflecting the day>*

**Weather**
<Current: temperature + condition + feels-like.>
<Forecast: 1-2 line outlook covering the next 3 days.>

**Today's news**
- [<Headline>](url) — <1-2 sentence snippet from the search result>
- ...

**Background**
<2-4 sentence Wikipedia lead, verbatim or lightly trimmed>
[More on Wikipedia](url)

**Things to do** (optional)
- <Attraction> — <kind>, ~<distance>m
- ...

**Market** (optional, only if user asked)
- <ticker>: $<price> (<+/-X% 24h>)
```
