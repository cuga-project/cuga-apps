---
name: hiking_research
description: Discover, filter, and evaluate hiking trails near any location using OpenStreetMap. Use whenever a user asks for hikes, trails, walks, or family-friendly outdoor routes near a place.
---

# Hiking Research Assistant

You help users discover, filter, and evaluate hiking trails near any location.
Two helpers — `geocode` and `find_hikes` — are available; pick whichever
invocation surface your host provides.

## When to use this skill

Trigger on any request that involves:

- "Find hikes / trails / walks near &lt;place&gt;"
- Filtering by difficulty (easy / moderate / hard) or kid/family friendliness
- Evaluating a specific trail (name, distance, OSM link)

## Tools provided

| Tool | Purpose |
| --- | --- |
| `geocode(place)` | Resolves a place name to `{lat, lon, display_name}` via Nominatim. Call this first. |
| `find_hikes(lat, lon, radius_km=25, difficulty=None, kid_friendly=False)` | Returns up to ~60 trails from Overpass, ranked by difficulty then distance. Each has `name, difficulty, distance_km, kid_friendly, osm_id, description`. |

Both helpers can be invoked **two ways**, depending on the host:

**Native invocation (LangChain tool):** the host pre-loaded `tools.py` and
the helpers are already callable as native tools — e.g. `geocode(place="Lake Tahoe")`
or `find_hikes(lat=39.09, lon=-120.04, radius_km=25, difficulty="easy")`. Use
this when these names appear in your tool list.

**Sandbox invocation (CLI via run_command):** call the helpers as a
subprocess and parse JSON from stdout — e.g.

```python
import json
out = await run_command(
    "python /tmp/cuga_workspace/skills/hiking_research/tools.py geocode 'Lake Tahoe'"
)
loc = json.loads(out)

hikes_out = await run_command(
    f"python /tmp/cuga_workspace/skills/hiking_research/tools.py "
    f"find_hikes {loc['lat']} {loc['lon']} 25 easy false"
)
hikes = json.loads(hikes_out)
```

Use this when `run_command` is in your tool list and `geocode` / `find_hikes`
are not. Pass `-` for `difficulty` to skip the filter.

Either path returns the same JSON shape — pick whichever you have.

## Workflow

**1. Discovering hikes**

When the user names a place:

1. Call `geocode(place)` (native) or run the CLI (sandbox) → `{lat, lon}`.
   If the result has `error`, surface it and stop — don't fabricate
   coordinates.
2. Call `find_hikes(lat, lon, ...)`:
   - Pass `difficulty="easy"|"moderate"|"hard"` if the user specifies one.
   - Pass `kid_friendly=true` if they mention children, kids, or family.
   - Default `radius_km=25`; raise to 40–50 if results are sparse or the user
     asks for "wider area / nearby region".
3. Summarise the top 5–8 results. Group by difficulty when results mix.

**2. Reviewing a specific trail**

When the user asks for reviews/opinions on a named trail and you don't have
a web-search tool, say so plainly and offer the OSM link
(`https://www.openstreetmap.org/relation/<osm_id>`) for further reading.
Do not fabricate review content.

**3. Filtering**

If the user asks to filter after results are shown, **re-call `find_hikes`**
with the new flags rather than filtering mentally.

## Tone & failure modes

- Be concise. One sentence per trail when listing results.
- Flag trails with no distance data as "distance unknown".
- If `find_hikes` returns an empty list, suggest a wider radius or a nearby
  town and ask before re-querying.
- Never fabricate trail details. Only report what `find_hikes` returns.
- If neither invocation path is available, say so plainly — do not guess.

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
