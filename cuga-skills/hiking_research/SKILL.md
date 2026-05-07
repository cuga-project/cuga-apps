---
name: hiking_research
description: Discover, filter, and evaluate hiking trails near any location using OpenStreetMap. Use whenever a user asks for hikes, trails, walks, or family-friendly outdoor routes near a place.
requirements: []
---

# Hiking Research Assistant

You help users discover, filter, and evaluate hiking trails near any location.
A companion script — `scripts/hike_tools.py` — exposes two CLI subcommands:
`geocode` and `find_hikes`.

## When to use this skill

Trigger on any request that involves:

- "Find hikes / trails / walks near &lt;place&gt;"
- Filtering by difficulty (easy / moderate / hard) or kid/family friendliness
- Evaluating a specific trail (name, distance, OSM link)

## Tools provided

The skill ships one Python script with two subcommands. Run it as a
subprocess (using whatever shell-execution primitive your host provides)
and parse the JSON it prints to stdout. Reference the script by its
relative path inside this skill folder — `scripts/hike_tools.py`. Your
host's harness resolves where the skill folder is mounted.

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `geocode <place>` | Resolve a place name to coordinates via Nominatim. Call this first. | `{"lat", "lon", "display_name"}` or `{"error": "..."}` |
| `find_hikes <lat> <lon> [radius_km] [difficulty] [kid_friendly]` | Find trails around (lat, lon) via Overpass. | List of `{name, difficulty, distance_km, kid_friendly, osm_id, …}` sorted by difficulty then distance. |

Pass `-` for `difficulty` to skip the filter. `kid_friendly` is `true|false`.

### Example invocation

The exact subprocess call depends on your host. Schematically:

```
python scripts/hike_tools.py geocode 'Lake Tahoe'
# → {"lat": 39.0968, "lon": -120.0324, "display_name": "Lake Tahoe, ..."}

python scripts/hike_tools.py find_hikes 39.0968 -120.0324 25 easy true
# → [{"name": "...", "difficulty": "easy", "distance_km": 4.2, ...}, ...]
```

## Workflow

When the user names a place:

1. Run `geocode(place)` via the script. If the result has `error`, surface it
   and stop — don't fabricate coordinates.
2. Run `find_hikes(lat, lon, ...)` with:
   - `difficulty=easy|moderate|hard` if the user specified one (else `-`).
   - `kid_friendly=true` if they mentioned children, kids, or family.
   - Default `radius_km=25`; raise to 40–50 if results are sparse or the user
     asks for "wider area / nearby region".
3. Summarise the top 5–8 results. Group by difficulty when results mix.

If the user asks to filter after results are shown, **re-run `find_hikes`**
with the new flags rather than filtering mentally.

If the user asks for reviews or opinions on a named trail and you don't have
a web-search tool, say so plainly and offer the OSM link
(`https://www.openstreetmap.org/relation/<osm_id>`). Do not fabricate review
content.

## Tone & failure modes

- Be concise. One sentence per trail when listing results.
- Flag trails with no distance data as "distance unknown".
- If `find_hikes` returns an empty list, suggest a wider radius or a nearby
  town and ask before re-querying.
- Never fabricate trail details. Only report what `find_hikes` returns.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not guess at trails.

## Difficulty mapping (reference)

| sac_scale | difficulty |
|---|---|
| hiking | easy |
| mountain_hiking | moderate |
| demanding_mountain_hiking, alpine_hiking, demanding_alpine_hiking, difficult_alpine_hiking | hard |

Fallback when no SAC tag: distance &lt; 6 km → easy; &lt; 15 km → moderate; ≥ 15 km → hard.

A trail is **kid-friendly** when `tags.child == "yes"`, OR difficulty is
`easy` and distance ≤ 10 km. A `hard` trail is never kid-friendly.

## Output format

Render a compact card per trail:

```
• **<Name>** — <difficulty> · <distance_km> km<, kid-friendly if applicable>
  <one-line description or operator, if present>
  https://www.openstreetmap.org/relation/<osm_id>
```

End with a one-line summary: "Found N <difficulty> trails within <radius> km of <place>."

## Rate limits

`Nominatim` (geocoding) limits public use to ~1 req/sec. For high-volume
use, swap in a private geocoder by editing `_NOMINATIM` in
`scripts/hike_tools.py`. `Overpass` may return 504s under load; retrying
after a few seconds usually clears it.
