"""Tools for the scout skill — geocode + OSM Overpass business search.

Dual-host: importable as a module (TOOLS list) and runnable as a CLI for
sandbox hosts.

Native host:
    from skills.scout.tools import TOOLS
    agent = CugaAgent(tools=TOOLS, ...)

Sandbox host:
    python tools.py geocode "Westchester, NY"
    python tools.py find_local_businesses 41.12 -73.79 restaurants 4000
"""
from __future__ import annotations

import json
import sys
from typing import Optional

import httpx


_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS  = "https://overpass-api.de/api/interpreter"
_UA        = {"User-Agent": "ouroboros-scout/1.0"}


_CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "restaurants":  [("amenity", "restaurant")],
    "cafes":        [("amenity", "cafe")],
    "bars":         [("amenity", "bar"), ("amenity", "pub")],
    "salons":       [("shop", "hairdresser"), ("shop", "beauty")],
    "fitness":      [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "clinics":      [("amenity", "clinic"), ("amenity", "doctors"),
                     ("amenity", "dentist"), ("amenity", "hospital"),
                     ("amenity", "pharmacy"), ("healthcare", "centre"),
                     ("healthcare", "physiotherapist"),
                     ("healthcare", "psychotherapist"),
                     ("healthcare", "alternative")],
    "veterinary":   [("amenity", "veterinary")],
    "auto":         [("shop", "car_repair"), ("amenity", "car_wash")],
    "boutiques":    [("shop", "clothes"), ("shop", "shoes"), ("shop", "jewelry")],
    "real_estate":  [("office", "estate_agent")],
    "lawyers":      [("office", "lawyer")],
    "accountants":  [("office", "accountant"), ("office", "financial")],
    "hotels":       [("tourism", "hotel"), ("tourism", "guest_house"), ("tourism", "motel")],
    "bakeries":     [("shop", "bakery"), ("shop", "pastry")],
    "florists":     [("shop", "florist")],
    "tutoring":     [("amenity", "language_school"), ("amenity", "tutoring")],
}


def _envelope_ok(data) -> str:
    return json.dumps({"ok": True, "data": data})


def _envelope_err(msg: str, code: str = "upstream") -> str:
    return json.dumps({"ok": False, "error": msg, "code": code})


# ── Pure helpers (used by both native + CLI paths) ───────────────────────

def _geocode(place: str) -> dict:
    r = httpx.get(
        _NOMINATIM,
        params={"q": place, "format": "json", "limit": 1},
        headers=_UA, timeout=15.0,
    )
    r.raise_for_status()
    hits = r.json() or []
    if not hits:
        raise ValueError(f"no geocode hit for {place!r}")
    h = hits[0]
    return {
        "lat":          float(h["lat"]),
        "lon":          float(h["lon"]),
        "display_name": h.get("display_name", place),
    }


def _overpass_query(lat: float, lon: float, radius_m: int, category: str) -> str:
    tags = _CATEGORY_TAGS[category]
    blocks = []
    for k, v in tags:
        for kind in ("node", "way", "relation"):
            blocks.append(f'{kind}["{k}"="{v}"](around:{radius_m},{lat},{lon});')
    return f"[out:json][timeout:25];({' '.join(blocks)});out tags center 60;"


def _businesses_from_overpass(elements: list[dict]) -> list[dict]:
    out: list[dict] = []
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name":     name,
            "category": tags.get("amenity") or tags.get("shop")
                          or tags.get("office") or tags.get("leisure")
                          or tags.get("tourism") or "",
            "address":  ", ".join(filter(None, [
                tags.get("addr:housenumber"), tags.get("addr:street"),
                tags.get("addr:city"), tags.get("addr:postcode"),
            ])),
            "phone":    tags.get("phone") or tags.get("contact:phone") or "",
            "website":  tags.get("website") or tags.get("contact:website") or "",
            "email":    tags.get("email") or tags.get("contact:email") or "",
            "osm":      f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        })
    seen, unique = set(), []
    for b in out:
        key = b["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    return unique


def _find_local_businesses(lat: float, lon: float, category: str,
                            radius_m: int = 4000) -> dict:
    if category not in _CATEGORY_TAGS:
        raise ValueError(
            f"unknown category {category!r}. Valid: {sorted(_CATEGORY_TAGS)}"
        )
    query = _overpass_query(float(lat), float(lon), int(radius_m), category)
    with httpx.Client(timeout=30.0, headers=_UA) as client:
        r = client.post(_OVERPASS, data={"data": query})
        r.raise_for_status()
        payload = r.json()
    businesses = _businesses_from_overpass(payload.get("elements") or [])
    # Cap at 8 (was 15) — scout's CugaLite has to regenerate this list
    # in its final answer, and longer payloads sometimes get truncated
    # by the underlying LLM despite max_tokens caps. 8 is enough for
    # deep-dive on top 3 + a candidate pool.
    return {
        "category":   category,
        "count":      len(businesses),
        "businesses": businesses[:8],
    }


# ── Native host: LangChain @tool wrappers ────────────────────────────────

try:
    from langchain_core.tools import tool

    @tool
    def geocode(place: str) -> str:
        """Resolve a place name (city, neighborhood, address) to lat/lon.
        Always call this before find_local_businesses on a new request.

        Args:
            place: Free-form location string ("Westchester, NY", "HSR Layout").
        """
        try:
            return _envelope_ok(_geocode(place))
        except Exception as e:
            return _envelope_err(f"geocode failed: {e}")

    @tool
    def find_local_businesses(lat: float, lon: float, category: str,
                                radius_m: int = 4000) -> str:
        """List businesses in one category around (lat, lon) via OSM Overpass.

        Args:
            lat:       Latitude (from geocode).
            lon:       Longitude.
            category:  One of: restaurants, cafes, bars, salons, fitness,
                       clinics, veterinary, auto, boutiques, real_estate,
                       lawyers, accountants, hotels, bakeries, florists,
                       tutoring.
            radius_m:  Search radius in meters (default 4000).
        """
        try:
            return _envelope_ok(_find_local_businesses(lat, lon, category, radius_m))
        except ValueError as e:
            return _envelope_err(str(e), code="bad_input")
        except Exception as e:
            return _envelope_err(f"overpass failed: {e}")

    TOOLS = [geocode, find_local_businesses]
except ImportError:
    TOOLS = []


# ── Sandbox host: CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "geocode":
            print(json.dumps(_geocode(sys.argv[2])))
        elif cmd == "find_local_businesses":
            print(json.dumps(_find_local_businesses(
                float(sys.argv[2]), float(sys.argv[3]),
                sys.argv[4],
                int(sys.argv[5]) if len(sys.argv) > 5 else 4000,
            )))
        else:
            print(json.dumps({"error": f"unknown command {cmd!r}"}), file=sys.stderr)
            sys.exit(2)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
