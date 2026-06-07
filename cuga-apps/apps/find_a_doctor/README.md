# Find a Doctor — CUGA Demo App

Give a location and (optionally) a specialty or preference — *"find a
cardiologist in Boston"*, *"a really experienced pediatric dentist in Austin
who's good with kids"* — and the agent assembles a ranked board of doctors:
where they are, their specialty, and a **review-grounded summary of pros and
cons** drawn from trusted review sites.

Same spirit as **Ouroboros** (geocode → discover → enrich → synthesize), but
with **inline `@tool` defs only** — no MCP servers.

## How it works

All live data is keyless, via direct `httpx` calls:

| Step      | Source                          | Tool                         |
| --------- | ------------------------------- | ---------------------------- |
| Geocode   | Nominatim (OpenStreetMap)       | `geocode_location`           |
| Listings  | Overpass (OpenStreetMap)        | `find_doctors`               |
| Discovery | DuckDuckGo HTML                 | `web_search`                 |
| Reviews   | DuckDuckGo → trusted health sites | `fetch_reviews`            |
| Persist   | per-session board               | `set_search`, `save_doctors` |

**Two discovery paths, merged.** OSM listings give structured address/phone,
but coverage of individual practitioners is uneven (sparser in the US). So the
agent also runs `web_search("best <specialty> in <location>")` to surface named,
well-regarded doctors, then pulls review snippets per candidate from trusted
sites (Healthgrades, Vitals, Zocdoc, WebMD, RateMDs, Yelp, …) and synthesizes
pros/cons. Nuanced asks like *"really experienced"* or a sub-specialty bias the
search queries and the ranking.

## Run

```bash
cd apps/find_a_doctor
pip install -r requirements.txt    # plus: pip install cuga
python main.py --port 28825
```

Then open <http://127.0.0.1:28825> and try:

- `Find a cardiologist in Boston`
- `A really experienced pediatric dentist in Austin who's good with kids`
- `Top-rated orthopedic surgeon near San Mateo, CA`
- `An OB-GYN in Chicago accepting new patients`

## Endpoints

| Method | Path                   | Purpose                                            |
| ------ | ---------------------- | -------------------------------------------------- |
| GET    | `/`                    | Two-panel UI                                       |
| POST   | `/ask`                 | `{question, thread_id}` → `{answer, thread_id}`    |
| GET    | `/session/{thread_id}` | Session state (search context + ranked doctors)    |
| GET    | `/health`              | `{"ok": true}`                                     |

## Environment

| Var                    | Required | Notes                                       |
| ---------------------- | -------- | ------------------------------------------- |
| `LLM_PROVIDER`         | yes      | rits \| anthropic \| openai \| watsonx \| … |
| `LLM_MODEL`            | no       | model override                              |
| `AGENT_SETTING_CONFIG` | no       | defaulted in `make_agent`                   |

## Important caveats

- **Informational only** — not medical advice, a referral, or an endorsement.
  The UI shows this disclaimer under every result set.
- The system prompt forbids inventing ratings, credentials, or quotes: every
  pro/con must trace to a real retrieved snippet. Thin/conflicting reviews are
  reported as such.
- DuckDuckGo HTML can rate-limit; when searches come back empty the agent falls
  back to whatever structured OSM listings it found and says so.
- Overpass/Nominatim are shared community endpoints — keep request volume
  modest. Swapping in a paid geocoder/places API later is a one-tool change.
