"""CLI helpers for the hiking_research skill — stdlib only.

The agent invokes this script via `run_command` and parses JSON from stdout:

    python scripts/hike_tools.py geocode 'Lake Tahoe'
    python scripts/hike_tools.py find_hikes 39.09 -120.04 25 easy false

Pass `-` for difficulty to skip the filter.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from typing import Optional

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS = "https://overpass-api.de/api/interpreter"
_UA = {"User-Agent": "hiking-research-skill/1.0 (https://skills.sh)"}

_SAC_DIFFICULTY = {
    "hiking": "easy",
    "mountain_hiking": "moderate",
    "demanding_mountain_hiking": "hard",
    "alpine_hiking": "hard",
    "demanding_alpine_hiking": "hard",
    "difficult_alpine_hiking": "hard",
}


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


def geocode(place: str) -> dict:
    """Resolve place → {lat, lon, display_name} via Nominatim."""
    qs = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    results = _http_get_json(f"{_NOMINATIM}?{qs}")
    if not results:
        return {"error": f"No geocode result for {place!r}"}
    r = results[0]
    return {
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "display_name": r.get("display_name", place),
    }


def find_hikes(
    lat: float,
    lon: float,
    radius_km: float = 25.0,
    difficulty: Optional[str] = None,
    kid_friendly: bool = False,
) -> list[dict]:
    """Find hiking trails around (lat, lon) via Overpass."""
    radius_m = int(radius_km * 1000)
    query = (
        f"[out:json][timeout:25];"
        f'(relation["route"="hiking"](around:{radius_m},{lat},{lon}););'
        f"out tags center 60;"
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        _OVERPASS,
        data=data,
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
# CLI
# ---------------------------------------------------------------------------

_USAGE = """\
usage:
  python scripts/hike_tools.py geocode <place>
  python scripts/hike_tools.py find_hikes <lat> <lon> [radius_km=25] [difficulty=-] [kid_friendly=false]

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
                print(_USAGE, file=sys.stderr)
                return 2
            result: object = geocode(argv[2])
        elif cmd == "find_hikes":
            if len(argv) < 4:
                print(_USAGE, file=sys.stderr)
                return 2
            lat = float(argv[2])
            lon = float(argv[3])
            radius_km = float(argv[4]) if len(argv) > 4 else 25.0
            difficulty = argv[5] if len(argv) > 5 and argv[5] != "-" else None
            kid_friendly = (
                argv[6].lower() in ("1", "true", "yes")
                if len(argv) > 6 else False
            )
            result = find_hikes(lat, lon, radius_km, difficulty, kid_friendly)
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
