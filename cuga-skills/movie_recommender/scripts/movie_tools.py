"""CLI helper for the movie_recommender skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/movie_tools.py get_wikipedia_article 'Sicario (2015 film)'

Wikipedia uses parenthetical disambiguators for films
('Dune (2021 film)' not 'Dune'). The script does no disambiguation;
the agent retries with a disambiguator if the first lookup is wrong.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

_WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
_UA = {
    "User-Agent": "movie-recommender-skill/1.0 (https://skills.sh)",
    "Accept": "application/json",
}


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode(resp.headers.get_content_charset() or "utf-8"))


def get_wikipedia_article(title: str) -> dict:
    """Wikipedia lead summary — confirms title, year, director, premise."""
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
        "type": data.get("type", ""),
        "description": data.get("description", ""),
    }


_USAGE = """\
usage:
  python scripts/movie_tools.py get_wikipedia_article <title>

Use parenthetical disambiguators for films, e.g. 'Dune (2021 film)'.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "get_wikipedia_article":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result: object = get_wikipedia_article(argv[2])
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
