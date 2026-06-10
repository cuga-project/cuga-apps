"""mcp-geo — location primitives: geocoding, POIs, hikes, weather.

Tools:
  - geocode(place)                               Nominatim (OpenStreetMap)
  - find_hikes(lat, lon, radius_km, ...)         Overpass API (OSM)
  - search_attractions(lat, lon, category, limit) Overpass API (OSM)
  - get_weather(city, travel_month)              wttr.in

All free, no API keys required.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result, get_json
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_GEO_PORT  # noqa: E402

mcp = make_server("mcp-geo")

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS  = "https://overpass-api.de/api/interpreter"
_WTTR = "https://wttr.in"

# OpenTripMap-compatible category names → OSM tag filters (key, value-regex).
# Keyless: served from the same Overpass API that powers find_hikes. We keep
# the public category vocabulary identical to the old OpenTripMap version so
# callers (travel_planner, city_beat, hiking_research) need no changes.
_ATTRACTION_TAGS: dict[str, list[tuple[str, str]]] = {
    "interesting_places": [
        ("tourism", "attraction|museum|gallery|viewpoint|artwork|theme_park|zoo|aquarium"),
        ("historic", "monument|memorial|castle|ruins|archaeological_site|fort|monastery|tower"),
        ("leisure",  "park|garden"),
    ],
    "cultural": [
        ("tourism", "museum|gallery|artwork|arts_centre"),
        ("amenity", "theatre|arts_centre"),
        ("historic", "monument|memorial|monastery"),
    ],
    "historic": [
        ("historic", "monument|memorial|castle|ruins|archaeological_site|fort|"
                     "city_gate|tower|monastery|building|church|temple"),
        ("tourism", "museum"),
    ],
    "natural": [
        ("leisure", "park|nature_reserve|garden"),
        ("natural", "peak|beach|waterfall|cave_entrance|spring"),
        ("tourism", "viewpoint"),
    ],
    "architecture": [
        ("tourism", "attraction"),
        ("historic", "monument|castle|tower|city_gate|building"),
        ("man_made", "tower|lighthouse|bridge"),
    ],
    "amusements": [
        ("tourism", "theme_park|zoo|aquarium"),
        ("leisure", "water_park|amusement_arcade"),
    ],
    "sport": [
        ("leisure", "stadium|sports_centre|track|pitch|golf_course"),
    ],
    "foods": [
        ("amenity", "marketplace"),
        ("tourism", "attraction"),
    ],
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Great-circle distance in meters between two lat/lon points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return int(round(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))))


@mcp.tool()
def geocode(place: str) -> str:
    """Geocode a place name to latitude/longitude via Nominatim (OpenStreetMap).

    Returns lat, lon, and a canonical display_name. Use this before any tool
    that needs coordinates (find_hikes, search_attractions).

    Args:
        place: Place name, city, or address (e.g. "Prague", "Mount Rainier WA").
    """
    try:
        results = get_json(
            _NOMINATIM,
            params={"q": place, "format": "json", "limit": 1},
        )
        if not results:
            return tool_error(f"Could not geocode '{place}'.", code="not_found")
        r = results[0]
        return tool_result({
            "query":        place,
            "lat":          float(r["lat"]),
            "lon":          float(r["lon"]),
            "display_name": r.get("display_name", ""),
        })
    except Exception as exc:
        return tool_error(f"Geocode failed: {exc}", code="upstream")


@mcp.tool()
def find_hikes(
    lat: float,
    lon: float,
    radius_km: float = 25,
    difficulty: str = "any",
    kid_friendly: bool = False,
) -> str:
    """Find hiking trails near a coordinate via OpenStreetMap Overpass.

    Returns named paths tagged as hiking/foot/bridleway within the radius,
    optionally filtered by difficulty and kid-friendliness (length-based proxy).

    Args:
        lat: Center latitude (from geocode).
        lon: Center longitude.
        radius_km: Search radius in km (default 25).
        difficulty: "easy", "moderate", "hard", or "any" (default "any").
        kid_friendly: If True, prefer shorter, gentler trails (default False).
    """
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:25];
    (
      way["highway"~"path|footway|bridleway"]["name"](around:{radius_m},{lat},{lon});
    );
    out tags center 40;
    """
    try:
        data = get_json(_OVERPASS, params={"data": query})
        hikes = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            sac = tags.get("sac_scale", "")
            diff = _classify_sac(sac)
            if difficulty != "any" and diff != difficulty:
                continue
            if kid_friendly and diff == "hard":
                continue
            center = el.get("center") or {}
            hikes.append({
                "name":       name,
                "difficulty": diff,
                "sac_scale":  sac,
                "surface":    tags.get("surface", ""),
                "lat":        center.get("lat"),
                "lon":        center.get("lon"),
                "osm_id":     el.get("id"),
            })
        return tool_result({"hikes": hikes, "count": len(hikes)})
    except Exception as exc:
        return tool_error(f"Overpass query failed: {exc}", code="upstream")


def _classify_sac(sac_scale: str) -> str:
    sac = (sac_scale or "").lower()
    if sac in ("hiking", "mountain_hiking"):
        return "easy"
    if sac == "demanding_mountain_hiking":
        return "moderate"
    if sac in ("alpine_hiking", "demanding_alpine_hiking", "difficult_alpine_hiking"):
        return "hard"
    return "moderate"


@mcp.tool()
def search_attractions(
    lat: float,
    lon: float,
    category: str = "interesting_places",
    limit: int = 15,
    radius_m: int = 20000,
) -> str:
    """Find top attractions near a coordinate via OpenStreetMap (Overpass).

    Keyless — no API key required. Use geocode first to obtain lat/lon.
    Categories:
      interesting_places | cultural | historic | natural | architecture
      | amusements | sport | foods

    Returns named, real places only (museums, monuments, parks, galleries,
    viewpoints, etc.) sorted nearest-first, each with the distance from the
    search point and any website/wikipedia tag OSM carries for grounding.

    Args:
        lat: Latitude.
        lon: Longitude.
        category: One of the categories listed above.
        limit: Max results (default 15, max 40).
        radius_m: Search radius in meters (default 20000, max 50000).
    """
    tag_filters = _ATTRACTION_TAGS.get(category)
    if tag_filters is None:
        return tool_error(
            f"Unknown category '{category}'. Valid: "
            f"{', '.join(sorted(_ATTRACTION_TAGS))}.",
            code="bad_input",
        )
    radius_m = min(max(int(radius_m), 500), 50000)
    limit = min(max(int(limit), 1), 40)

    # Build a union over node+way for every (key, value-regex) in the category.
    blocks = []
    for key, val in tag_filters:
        for kind in ("node", "way"):
            blocks.append(f'{kind}["{key}"~"^({val})$"]["name"](around:{radius_m},{lat},{lon});')
    query = f"[out:json][timeout:25];({' '.join(blocks)});out tags center 80;"

    try:
        data = get_json(_OVERPASS, params={"data": query})
        seen: set[str] = set()
        results = []
        for el in data.get("elements", []):
            tags = el.get("tags", {}) or {}
            name = (tags.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            center = el.get("center") or {}
            plat = el.get("lat", center.get("lat"))
            plon = el.get("lon", center.get("lon"))
            dist = (_haversine_m(lat, lon, plat, plon)
                    if plat is not None and plon is not None else None)
            # "kinds" mirrors OpenTripMap's comma-joined descriptor so existing
            # callers that read .kinds keep working.
            kinds = ",".join(
                str(tags[k]) for k in ("tourism", "historic", "leisure",
                                       "natural", "amenity", "man_made")
                if tags.get(k)
            )
            results.append({
                "name":      name,
                "kinds":     kinds,
                "dist_m":    dist,
                "lat":       plat,
                "lon":       plon,
                "address":   tags.get("addr:street", ""),
                "website":   tags.get("website") or tags.get("contact:website") or "",
                "wikipedia": tags.get("wikipedia", ""),
                "osm":       f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
            })
        results.sort(key=lambda r: (r["dist_m"] is None, r["dist_m"] or 0))
        return tool_result({
            "category": category,
            "count":    len(results[:limit]),
            "attractions": results[:limit],
        })
    except Exception as exc:
        return tool_error(f"Overpass query failed: {exc}", code="upstream")


@mcp.tool()
def get_weather(city: str, travel_month: str = "") -> str:
    """Fetch current weather + 3-day forecast for a city via wttr.in.

    Args:
        city: City name.
        travel_month: Optional month of travel (e.g. "March"); included in
                      the response as planning context — wttr.in only returns
                      the next 3 days so the LLM should supplement with web
                      search for seasonal patterns.
    """
    try:
        data = get_json(f"{_WTTR}/{city.replace(' ', '+')}", params={"format": "j1"})
    except Exception as exc:
        return tool_error(f"wttr.in failed: {exc}", code="upstream")
    cur = (data.get("current_condition") or [{}])[0]
    forecast = []
    for day in data.get("weather", []):
        hourly = day.get("hourly") or []
        desc = (hourly[4] if len(hourly) > 4 else {}).get("weatherDesc", [{}])
        forecast.append({
            "date":     day.get("date", ""),
            "min_c":    day.get("mintempC"),
            "max_c":    day.get("maxtempC"),
            "summary":  (desc[0].get("value", "") if desc else ""),
        })
    return tool_result({
        "city":         city,
        "travel_month": travel_month,
        "current": {
            "temp_c":       cur.get("temp_C"),
            "feels_like_c": cur.get("FeelsLikeC"),
            "humidity":     cur.get("humidity"),
            "desc":         (cur.get("weatherDesc") or [{}])[0].get("value", ""),
        },
        "forecast": forecast,
    })


if __name__ == "__main__":
    run(mcp, MCP_GEO_PORT)
