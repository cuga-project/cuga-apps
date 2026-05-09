"""CLI helpers for the ibm_cloud_advisor skill — stdlib only.

    python scripts/ibm_advisor_tools.py search_ibm_catalog 'message queue' 8
    python scripts/ibm_advisor_tools.py web_search 'site:cloud.ibm.com Code Engine pricing' 5

`search_ibm_catalog` needs no key. `web_search` requires TAVILY_API_KEY.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

_UA = {
    "User-Agent": "ibm-cloud-advisor-skill/1.0 (https://skills.sh)",
    "Accept": "application/json",
}

_CATALOG_API = "https://globalcatalog.cloud.ibm.com/api/v1"
_TAVILY = "https://api.tavily.com/search"


def _http_get_json(url: str, params: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _http_post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={**_UA, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())


def search_ibm_catalog(query: str, limit: int = 8) -> dict:
    """Find real IBM Cloud services in the public Global Catalog."""
    try:
        data = _http_get_json(_CATALOG_API, {
            "q": query, "kind": "service",
            "_limit": str(min(int(limit), 20)), "_sort": "name",
        })
    except Exception as e:
        return {"error": f"IBM Catalog failed: {type(e).__name__}: {e}", "query": query}
    resources = data.get("resources", []) or []
    services = []
    for r in resources:
        name = r.get("name", "")
        ov = (r.get("overview_ui") or {}).get("en", {}) or {}
        services.append({
            "name": name,
            "display_name": ov.get("display_name") or name,
            "description": (ov.get("description") or "")[:300],
            "tags": [t for t in (r.get("tags") or [])
                     if not t.startswith("rc:") and not t.startswith("iam:")][:5],
            "catalog_url": f"https://cloud.ibm.com/catalog/services/{name}",
        })
    return {"query": query, "services": services}


def web_search(query: str, max_results: int = 6) -> dict:
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
    return {
        "query": query,
        "results": [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "content": (r.get("content") or "")[:800]}
            for r in (data.get("results") or [])
        ],
    }


_USAGE = """\
usage:
  python scripts/ibm_advisor_tools.py search_ibm_catalog <query> [limit=8]
  python scripts/ibm_advisor_tools.py web_search <query> [max_results=6]
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "search_ibm_catalog":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            limit = int(argv[3]) if len(argv) > 3 else 8
            result: object = search_ibm_catalog(argv[2], limit)
        elif cmd == "web_search":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result = web_search(argv[2], n)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
