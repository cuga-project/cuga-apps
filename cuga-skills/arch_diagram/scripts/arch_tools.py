"""CLI helper for the arch_diagram skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/arch_tools.py web_search 'Apache Pulsar architecture' 5

Requires TAVILY_API_KEY in the environment. Without it, returns
{"error": "TAVILY_API_KEY not set"} and exits 1.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 6) -> dict:
    """Tavily search → {results: [{title, url, content}, ...]}."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set"}
    body = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max(1, min(int(max_results), 20)),
        "search_depth": "basic",
    }).encode()
    req = urllib.request.Request(
        _TAVILY_URL, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {"error": f"Tavily search failed: {type(e).__name__}: {e}"}
    return {
        "query": query,
        "results": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content") or "")[:1000],
            }
            for r in (data.get("results") or [])
        ],
    }


_USAGE = """\
usage:
  python scripts/arch_tools.py web_search <query> [max_results=6]

Requires TAVILY_API_KEY in environment.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "web_search":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result: object = web_search(argv[2], n)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
