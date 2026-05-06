"""Tools and helpers for the hiking_research skill.

This file is *dual-host*: it works as both an importable Python module AND a
standalone CLI.

Native host (cuga-skills-ui)
    `from tools import TOOLS` — TOOLS is a list of LangChain `@tool`
    functions the host passes to `CugaAgent(tools=...)`. Requires
    `langchain_core` (soft dep — TOOLS is `[]` if missing).

Sandbox host (cuga start demo_skills + OpenSandbox)
    `python tools.py <command> <args...>` — stdlib-only CLI. The agent runs
    this via `run_command` and parses JSON from stdout. No langchain dep.

Both paths call the same underlying `_geocode` / `_find_hikes` pure helpers,
so behavior is identical regardless of which host the skill is loaded into.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from typing import Optional

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS = "https://overpass-api.de/api/interpreter"
_UA = {"User-Agent": "cuga-hiking-research/0.1"}

_SAC_DIFFICULTY = {
    "hiking": "easy",
    "mountain_hiking": "moderate",
    "demanding_mountain_hiking": "hard",
    "alpine_hiking": "hard",
    "demanding_alpine_hiking": "hard",
    "difficult_alpine_hiking": "hard",
}


# ---------------------------------------------------------------------------
# Pure helpers — stdlib only, used by both invocation paths.
# ---------------------------------------------------------------------------

def _http_get_json(url: str) -> list | dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _parse_distance_km(tags: dict) -> Optional[float]:
    for key in ("distance", "length"):
        val = tags.get(key, "")
        if not val:
            continue
        try:
            return float(str(val).replace("km", "").replace("mi", "").strip())
        except ValueError:
            pass
    return None


def _infer_difficulty(tags: dict) -> str:
    sac = tags.get("sac_scale", "")
    if sac in _SAC_DIFFICULTY:
        return _SAC_DIFFICULTY[sac]
    dist = _parse_distance_km(tags)
    if dist is None:
        return "unknown"
    if dist < 6:
        return "easy"
    if dist < 15:
        return "moderate"
    return "hard"


def _is_kid_friendly(tags: dict, difficulty: str) -> bool:
    if tags.get("child") == "yes":
        return True
    if difficulty == "hard":
        return False
    dist = _parse_distance_km(tags)
    if dist is not None and dist > 10:
        return False
    return difficulty == "easy"


def _geocode(place: str) -> dict:
    """Resolve a place name to {lat, lon, display_name} via Nominatim."""
    qs = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    results = _http_get_json(f"{_NOMINATIM}?{qs}")
    if not results:
        return {"error": f"No geocode result for {place!r}"}
    r = results[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]),
            "display_name": r.get("display_name", place)}


def _find_hikes(
    lat: float,
    lon: float,
    radius_km: float = 25.0,
    difficulty: Optional[str] = None,
    kid_friendly: bool = False,
) -> list[dict]:
    """Find hiking trails around (lat, lon) via Overpass."""
    radius_m = int(radius_km * 1000)
    query = (
        f'[out:json][timeout:25];'
        f'(relation["route"="hiking"](around:{radius_m},{lat},{lon}););'
        f'out tags center 60;'
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        _OVERPASS, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", **_UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())

    out: list[dict] = []
    for el in body.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("ref")
        if not name:
            continue
        diff = _infer_difficulty(tags)
        kid = _is_kid_friendly(tags, diff)
        if difficulty and diff != difficulty:
            continue
        if kid_friendly and not kid:
            continue
        out.append({
            "name": name,
            "difficulty": diff,
            "distance_km": _parse_distance_km(tags),
            "kid_friendly": kid,
            "osm_id": el.get("id"),
            "from_place": tags.get("from"),
            "to_place": tags.get("to"),
            "operator": tags.get("operator"),
            "description": tags.get("description") or tags.get("note"),
        })
    out.sort(key=lambda h: (
        {"easy": 0, "moderate": 1, "hard": 2, "unknown": 3}[h["difficulty"]],
        h["distance_km"] if h["distance_km"] is not None else 1e9,
    ))
    return out


# ---------------------------------------------------------------------------
# Native-host path: LangChain @tool wrappers (soft dep on langchain_core).
# ---------------------------------------------------------------------------

try:
    from langchain_core.tools import tool

    @tool
    def geocode(place: str) -> dict:
        """Resolve a place name to latitude/longitude via OpenStreetMap Nominatim.

        Returns {"lat": float, "lon": float, "display_name": str}, or
        {"error": str} if no result. Call this before find_hikes.
        """
        return _geocode(place)

    @tool
    def find_hikes(
        lat: float,
        lon: float,
        radius_km: float = 25.0,
        difficulty: Optional[str] = None,
        kid_friendly: bool = False,
    ) -> list[dict]:
        """Find hiking trails around (lat, lon) via OpenStreetMap Overpass.

        Args:
            lat, lon: coordinates from geocode().
            radius_km: search radius (default 25; use 40-50 for sparse areas).
            difficulty: filter to "easy" | "moderate" | "hard" if specified.
            kid_friendly: filter to family-friendly trails.

        Returns up to ~60 trails sorted by difficulty then distance, each:
            {name, difficulty, distance_km, kid_friendly, osm_id,
             from_place, to_place, operator, description}.
        """
        return _find_hikes(lat, lon, radius_km, difficulty, kid_friendly)

    TOOLS = [geocode, find_hikes]
except ImportError:
    # langchain_core not available — sandbox path still works via CLI below.
    TOOLS = []


# ---------------------------------------------------------------------------
# Sandbox-host path: CLI that emits JSON on stdout. Stdlib only.
# Usage:
#   python tools.py geocode "Lake Tahoe"
#   python tools.py find_hikes 41.157 -73.768 25 easy false
# ---------------------------------------------------------------------------

_USAGE = """\
usage:
  python tools.py geocode <place>
  python tools.py find_hikes <lat> <lon> [radius_km=25] [difficulty=-] [kid_friendly=false]

Pass `-` for difficulty to skip the filter.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd = argv[1]
    try:
        if cmd == "geocode":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            result: object = _geocode(argv[2])
        elif cmd == "find_hikes":
            if len(argv) < 4:
                print(_USAGE, file=sys.stderr); return 2
            lat = float(argv[2])
            lon = float(argv[3])
            radius_km = float(argv[4]) if len(argv) > 4 else 25.0
            difficulty = argv[5] if len(argv) > 5 and argv[5] != "-" else None
            kid_friendly = (
                argv[6].lower() in ("1", "true", "yes")
                if len(argv) > 6 else False
            )
            result = _find_hikes(lat, lon, radius_km, difficulty, kid_friendly)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr)
            return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
