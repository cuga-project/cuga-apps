"""mcp-geo — location primitives: geocoding, POIs, hikes, weather.

Tools:
  - geocode(place)                               Nominatim (OpenStreetMap)
  - find_hikes(lat, lon, radius_km, ...)         Overpass API (OSM)
  - search_attractions(lat, lon, category, limit) OpenTripMap
  - get_weather(city, travel_month)              wttr.in

All free except search_attractions (OPENTRIPMAP_API_KEY, free tier 500/day).
"""
from __future__ import annotations

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
_OPENTRIPMAP = "https://api.opentripmap.com/0.1/en/places/radius"
_WTTR = "https://wttr.in"


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
    """Find top attractions near a coordinate via OpenTripMap.

    Use geocode first to obtain lat/lon. Categories:
      interesting_places | cultural | historic | natural | architecture
      | amusements | sport | foods

    Args:
        lat: Latitude.
        lon: Longitude.
        category: One of the categories listed above.
        limit: Max results (default 15, max 20).
        radius_m: Search radius in meters (default 20000).

    Env:
        OPENTRIPMAP_API_KEY required.
    """
    api_key = os.getenv("OPENTRIPMAP_API_KEY")
    if not api_key:
        return tool_error("OPENTRIPMAP_API_KEY not set on the MCP server.", code="missing_key")
    try:
        places = get_json(
            _OPENTRIPMAP,
            params={
                "radius": radius_m,
                "lon": lon,
                "lat": lat,
                "kinds": category,
                "limit": min(int(limit), 20),
                "apikey": api_key,
                "format": "json",
                "rate": 2,
            },
        )
        results = []
        for p in places or []:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            results.append({
                "name":     name,
                "kinds":    p.get("kinds", ""),
                "dist_m":   p.get("dist"),
                "xid":      p.get("xid"),
                "point":    p.get("point"),
            })
        return tool_result({"category": category, "attractions": results})
    except Exception as exc:
        return tool_error(f"OpenTripMap failed: {exc}", code="upstream")


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
