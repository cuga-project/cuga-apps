"""CLI helpers for the city_beat skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/city_tools.py geocode 'Boston'
    python scripts/city_tools.py get_weather 'Boston'
    python scripts/city_tools.py search_attractions 42.36 -71.06 cultural 6
    python scripts/city_tools.py web_search 'Boston news today' 5
    python scripts/city_tools.py get_wikipedia_article 'Boston'
    python scripts/city_tools.py get_crypto_price btc

Env keys (per subcommand):
  TAVILY_API_KEY       — required for web_search
  OPENTRIPMAP_API_KEY  — required for search_attractions

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

_UA = {"User-Agent": "city-beat-skill/1.0 (https://skills.sh)"}

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_WTTR = "https://wttr.in"
_OPENTRIPMAP = "https://api.opentripmap.com/0.1/en/places/radius"
_TAVILY = "https://api.tavily.com/search"
_WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
_COINGECKO = "https://api.coingecko.com/api/v3"


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
    return {
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "display_name": r.get("display_name", place),
    }


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


def search_attractions(
    lat: float, lon: float,
    category: str = "cultural", limit: int = 6, radius_m: int = 20000,
) -> dict:
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
        if not name:
            continue
        out.append({
            "name": name,
            "kinds": p.get("kinds", ""),
            "dist_m": p.get("dist"),
            "xid": p.get("xid"),
        })
    return {"category": category, "attractions": out}


def web_search(query: str, max_results: int = 5) -> dict:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set"}
    try:
        data = _http_post_json(_TAVILY, {
            "api_key": api_key,
            "query": query,
            "max_results": max(1, min(int(max_results), 20)),
            "search_depth": "basic",
        })
    except Exception as e:
        return {"error": f"Tavily failed: {type(e).__name__}: {e}"}
    return {
        "query": query,
        "results": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content") or "")[:800],
            }
            for r in (data.get("results") or [])
        ],
    }


def get_wikipedia_article(title: str) -> dict:
    try:
        data = _http_get_json(
            f"{_WIKI_REST}/page/summary/{urllib.parse.quote(title.replace(' ', '_'))}"
        )
    except Exception as e:
        return {"error": f"Wikipedia failed: {type(e).__name__}: {e}"}
    return {
        "title": data.get("title"),
        "summary": data.get("extract"),
        "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
    }


_CRYPTO_ALIASES = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
    "ada": "cardano", "doge": "dogecoin", "dot": "polkadot",
    "avax": "avalanche-2", "link": "chainlink",
    "matic": "matic-network", "polygon": "matic-network",
    "xrp": "ripple",
}


def get_crypto_price(symbol: str, vs_currency: str = "usd") -> dict:
    slug = _CRYPTO_ALIASES.get(symbol.lower().strip(), symbol.lower().strip())
    try:
        data = _http_get_json(f"{_COINGECKO}/simple/price", {
            "ids": slug, "vs_currencies": vs_currency,
            "include_24hr_change": "true", "include_market_cap": "true",
        })
    except Exception as e:
        return {"error": f"CoinGecko failed: {type(e).__name__}: {e}"}
    if slug not in data:
        return {"error": f"Unknown crypto symbol {symbol!r}"}
    d = data[slug]
    return {
        "symbol": symbol,
        "coingecko_id": slug,
        "vs_currency": vs_currency,
        "price": d.get(vs_currency),
        "change_24h": d.get(f"{vs_currency}_24h_change"),
        "market_cap": d.get(f"{vs_currency}_market_cap"),
    }


_USAGE = """\
usage:
  python scripts/city_tools.py geocode <place>
  python scripts/city_tools.py get_weather <city>
  python scripts/city_tools.py search_attractions <lat> <lon> [category=cultural] [limit=6] [radius_m=20000]
  python scripts/city_tools.py web_search <query> [max_results=5]
  python scripts/city_tools.py get_wikipedia_article <title>
  python scripts/city_tools.py get_crypto_price <symbol> [vs_currency=usd]
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
            if len(argv) < 4: print(_USAGE, file=sys.stderr); return 2
            lat, lon = float(argv[2]), float(argv[3])
            cat = argv[4] if len(argv) > 4 else "cultural"
            limit = int(argv[5]) if len(argv) > 5 else 6
            radius = int(argv[6]) if len(argv) > 6 else 20000
            result = search_attractions(lat, lon, cat, limit, radius)
        elif cmd == "web_search":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 5
            result = web_search(argv[2], n)
        elif cmd == "get_wikipedia_article":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_wikipedia_article(argv[2])
        elif cmd == "get_crypto_price":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            vs = argv[3] if len(argv) > 3 else "usd"
            result = get_crypto_price(argv[2], vs)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
