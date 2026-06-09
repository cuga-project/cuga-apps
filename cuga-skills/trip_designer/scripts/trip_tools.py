"""CLI helpers for the trip_designer skill — stdlib only.

Wraps the same APIs as travel_planner (Nominatim, wttr.in, OpenTripMap,
Tavily, Wikipedia) but exposed as a flat toolkit — the agent decides the
order of calls.

    python scripts/trip_tools.py geocode 'Reykjavik'
    python scripts/trip_tools.py get_weather 'Reykjavik'
    python scripts/trip_tools.py search_attractions 64.15 -21.94 natural 10
    python scripts/trip_tools.py web_search 'Iceland geothermal pools' 4
    python scripts/trip_tools.py get_wikipedia_article 'Reykjavik'
    python scripts/trip_tools.py search_wikipedia 'Reykjavik' 5

Env (per subcommand):
  TAVILY_API_KEY       — required for web_search
  OPENTRIPMAP_API_KEY  — required for search_attractions

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request

_UA = {"User-Agent": "trip-designer-skill/1.0 (https://skills.sh)"}

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_WTTR = "https://wttr.in"
_OPENTRIPMAP = "https://api.opentripmap.com/0.1/en/places/radius"
_TAVILY = "https://api.tavily.com/search"
_WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
_WIKI_ACTION = "https://en.wikipedia.org/w/api.php"


def _http_get_json(url: str, params: dict | None = None) -> dict | list:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode(resp.headers.get_content_charset() or "utf-8"))


def _http_post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={**_UA, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())


def geocode(place: str) -> dict:
    try:
        results = _http_get_json(_NOMINATIM, {"q": place, "format": "json", "limit": 1})
    except Exception as e:
        return {"error": f"Geocode failed: {type(e).__name__}: {e}"}
    if not results:
        return {"error": f"No geocode result for {place!r}"}
    r = results[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]),
            "display_name": r.get("display_name", place)}


def get_weather(city: str) -> dict:
    try:
        data = _http_get_json(f"{_WTTR}/{urllib.parse.quote(city)}", {"format": "j1"})
    except Exception as e:
        return {"error": f"wttr.in failed: {type(e).__name__}: {e}"}
    if not isinstance(data, dict):
        return {"error": "wttr.in returned an unexpected payload"}
    cur = (data.get("current_condition") or [{}])[0]
    forecast = []
    for day in data.get("weather", []) or []:
        hourly = day.get("hourly") or []
        desc = (hourly[4] if len(hourly) > 4 else {}).get("weatherDesc", [{}])
        forecast.append({
            "date": day.get("date", ""),
            "min_c": day.get("mintempC"),
            "max_c": day.get("maxtempC"),
            "summary": desc[0].get("value", "") if desc else "",
        })
    return {
        "city": city,
        "current": {
            "temp_c": cur.get("temp_C"),
            "feels_like_c": cur.get("FeelsLikeC"),
            "humidity": cur.get("humidity"),
            "desc": (cur.get("weatherDesc") or [{}])[0].get("value", ""),
        },
        "forecast": forecast,
    }


def search_attractions(lat: float, lon: float, category: str = "interesting_places",
                       limit: int = 10, radius_m: int = 20000) -> dict:
    api_key = os.getenv("OPENTRIPMAP_API_KEY")
    if not api_key:
        return {"error": "OPENTRIPMAP_API_KEY not set"}
    try:
        places = _http_get_json(_OPENTRIPMAP, {
            "radius": radius_m, "lon": lon, "lat": lat,
            "kinds": category, "limit": min(int(limit), 20),
            "apikey": api_key, "format": "json", "rate": 2,
        })
    except Exception as e:
        return {"error": f"OpenTripMap failed: {type(e).__name__}: {e}"}
    out = []
    for p in places or []:
        name = (p.get("name") or "").strip()
        if not name: continue
        out.append({"name": name, "kinds": p.get("kinds", ""),
                    "dist_m": p.get("dist"), "xid": p.get("xid")})
    return {"category": category, "attractions": out}


def web_search(query: str, max_results: int = 5) -> dict:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set"}
    try:
        data = _http_post_json(_TAVILY, {
            "api_key": api_key, "query": query,
            "max_results": max(1, min(int(max_results), 20)),
            "search_depth": "basic",
        })
    except Exception as e:
        return {"error": f"Tavily failed: {type(e).__name__}: {e}"}
    return {"query": query, "results": [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "content": (r.get("content") or "")[:800]}
        for r in (data.get("results") or [])
    ]}


def get_wikipedia_article(title: str) -> dict:
    try:
        data = _http_get_json(
            f"{_WIKI_REST}/page/summary/{urllib.parse.quote(title.replace(' ', '_'))}"
        )
    except Exception as e:
        return {"error": f"Wikipedia summary failed: {type(e).__name__}: {e}"}
    return {
        "title": data.get("title"),
        "summary": data.get("extract"),
        "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
    }


def search_wikipedia(query: str, max_results: int = 6) -> dict:
    try:
        data = _http_get_json(_WIKI_ACTION, {
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": min(max_results, 20), "format": "json",
        })
    except Exception as e:
        return {"error": f"Wikipedia search failed: {type(e).__name__}: {e}"}
    hits = data.get("query", {}).get("search", []) or []
    return {"results": [{
        "title": h.get("title"),
        "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", "") or "").strip(),
        "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote((h.get('title') or '').replace(' ', '_'))}",
    } for h in hits]}


_USAGE = """\
usage:
  python scripts/trip_tools.py geocode <place>
  python scripts/trip_tools.py get_weather <city>
  python scripts/trip_tools.py search_attractions <lat> <lon> <category> [limit=10] [radius_m=20000]
  python scripts/trip_tools.py web_search <query> [max_results=5]
  python scripts/trip_tools.py get_wikipedia_article <title>
  python scripts/trip_tools.py search_wikipedia <query> [max_results=6]

Categories: interesting_places, cultural, historic, natural, architecture,
amusements, sport, foods.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "geocode":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result: object = geocode(argv[2])
        elif cmd == "get_weather":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_weather(argv[2])
        elif cmd == "search_attractions":
            if len(argv) < 5: print(_USAGE, file=sys.stderr); return 2
            lat, lon = float(argv[2]), float(argv[3])
            cat = argv[4]
            limit = int(argv[5]) if len(argv) > 5 else 10
            radius = int(argv[6]) if len(argv) > 6 else 20000
            result = search_attractions(lat, lon, cat, limit, radius)
        elif cmd == "web_search":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 5
            result = web_search(argv[2], n)
        elif cmd == "get_wikipedia_article":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_wikipedia_article(argv[2])
        elif cmd == "search_wikipedia":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result = search_wikipedia(argv[2], n)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
