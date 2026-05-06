# Ouroboros — CUGA finds its next client

Lead generation for CUGA itself. The agent scouts a location for local
businesses that would benefit from an enterprise-grade conversational AI
agent (chat-bot order taker for restaurants, appointment booker for
salons, FAQ + lead-capture for clinics, etc.) and assembles a ranked
shortlist with a tailored CUGA pitch for each.

## Run

```bash
pip install -r requirements.txt
pip install cuga                 # private — see top-level prereqs

export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...
export CUGA_TARGET=ce            # use the public Code Engine MCP URLs

python main.py --port 28822
# open http://127.0.0.1:28822
```

## Tools

**MCP** (hosted on Code Engine — no local key needed):
- `geo.geocode` — place → lat / lon / canonical display name
- `web.web_search` — Tavily; corroborating citations and recent news
- `web.fetch_webpage` — read a business website for signals
- `knowledge.search_wikipedia` — area background blurb (optional)

**Inline** (`@tool` defs in `main.py`):
- `find_local_businesses(thread_id, lat, lon, category, radius_m=4000)` —
  Overpass API over OpenStreetMap. No key, no quota that matters.
  Categories:
  `restaurants, cafes, bars, salons, fitness, clinics, veterinary, auto,
  boutiques, real_estate, lawyers, accountants, hotels, bakeries,
  florists, tutoring`.
- `set_target_location(thread_id, location, lat?, lon?)` — remember the
  active hunt and its coordinates.
- `add_business_category(thread_id, category)` — append to the hunt list.
- `set_pitch_focus(thread_id, focus)` — bias every pitch
  (e.g. `"appointment booking"`, `"order-taking chatbot"`).
- `get_session_state(thread_id)` — recall prior context.
- `save_leads(thread_id, leads_json)` — persist the ranked board the right
  panel renders.

## Card shape

The right panel renders the `leads` object saved by `save_leads`:

```jsonc
{
  "location":      "HSR Layout, Bangalore",
  "display_name":  "HSR Layout, Bengaluru, Karnataka, India",
  "lat":           12.91, "lon": 77.64,
  "summary":       "Dense residential + tech-worker neighborhood with…",
  "leads": [
    {
      "name":      "Aroma Pure Veg",
      "category":  "restaurant",
      "address":   "27th Main, HSR Sector 1",
      "website":   "https://example.com",
      "phone":     "+91 ...",
      "fit_score": 9,
      "use_case":  "Order-taking chatbot for delivery + reservations",
      "pitch":     "Aroma is a busy lunch-rush spot…",
      "evidence":  [{"title": "Aroma Pure Veg | Zomato", "url": "https://…"}],
      "osm":       "https://www.openstreetmap.org/node/…"
    }
  ],
  "next_steps": [
    "Cold-email the 3 top picks with the tailored pitch.",
    "Loop back in 2 weeks to refresh the board."
  ]
}
```

## Example prompts

- `Find leads in Westchester, NY`
- `Restaurants in HSR Layout, Bangalore — pitch order bots`
- `Salons in Brooklyn that need appointment booking`
- `Independent hotels in Lisbon — concierge agent angle`
- `Real estate offices in San Mateo — lead capture pitch`
- `Veterinary clinics near Berkeley — appointment + reminders`
