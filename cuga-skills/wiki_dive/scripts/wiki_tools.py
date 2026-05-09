"""CLI helpers for the wiki_dive skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/wiki_tools.py search_wikipedia 'Cambrian explosion'
    python scripts/wiki_tools.py get_article_summary 'Cambrian explosion'
    python scripts/wiki_tools.py get_article_sections 'Cambrian explosion'
    python scripts/wiki_tools.py get_related_articles 'Cambrian explosion' 8

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

_WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
_WIKI_ACTION = "https://en.wikipedia.org/w/api.php"
_UA = {
    "User-Agent": "wiki-dive-skill/1.0 (https://skills.sh)",
    "Accept": "application/json",
}


def _http_get_json(url: str, params: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode(resp.headers.get_content_charset() or "utf-8"))


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _title_to_url(title: str) -> str:
    return f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def search_wikipedia(query: str, max_results: int = 6) -> dict:
    """Search Wikipedia for articles matching a keyword query."""
    try:
        data = _http_get_json(_WIKI_ACTION, {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": min(max_results, 20),
            "format": "json",
        })
    except Exception as e:
        return {"error": f"Wikipedia search failed: {type(e).__name__}: {e}"}
    hits = data.get("query", {}).get("search", []) or []
    results = [{
        "title": h.get("title"),
        "snippet": _strip_html(h.get("snippet", "")),
        "url": _title_to_url(h.get("title", "")),
    } for h in hits]
    return {"results": results}


def get_article_summary(title: str) -> dict:
    """Lead summary (REST endpoint) — a few paragraphs."""
    try:
        data = _http_get_json(
            f"{_WIKI_REST}/page/summary/{urllib.parse.quote(title.replace(' ', '_'))}"
        )
    except Exception as e:
        return {"error": f"Wikipedia summary failed: {type(e).__name__}: {e}"}
    return {
        "title": data.get("title"),
        "summary": data.get("extract"),
        "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")
               or _title_to_url(title),
        "thumbnail": (data.get("thumbnail") or {}).get("source"),
    }


def get_article_sections(title: str) -> dict:
    """Full plain-text article via the action API."""
    try:
        data = _http_get_json(_WIKI_ACTION, {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": title,
            "format": "json",
        })
    except Exception as e:
        return {"error": f"Wikipedia article fetch failed: {type(e).__name__}: {e}"}
    pages = data.get("query", {}).get("pages", {}) or {}
    page = next(iter(pages.values())) if pages else {}
    if "missing" in page:
        return {"error": f"No Wikipedia article titled {title!r}"}
    return {
        "title": page.get("title"),
        "extract": page.get("extract", ""),
        "url": _title_to_url(title),
    }


def get_related_articles(title: str, max_results: int = 8) -> dict:
    """Internal links from the article — used to discover related concepts."""
    try:
        data = _http_get_json(_WIKI_ACTION, {
            "action": "query",
            "titles": title,
            "prop": "links",
            "pllimit": min(max_results * 3, 30),
            "plnamespace": 0,
            "format": "json",
        })
    except Exception as e:
        return {"error": f"Wikipedia related-links failed: {type(e).__name__}: {e}"}
    pages = list((data.get("query", {}).get("pages") or {}).values())
    if not pages:
        return {"source": title, "related": []}
    related = [
        {"title": lnk.get("title", ""), "url": _title_to_url(lnk.get("title", ""))}
        for lnk in pages[0].get("links", [])[:max_results]
    ]
    return {"source": title, "related": related}


_USAGE = """\
usage:
  python scripts/wiki_tools.py search_wikipedia <query> [max_results=6]
  python scripts/wiki_tools.py get_article_summary <title>
  python scripts/wiki_tools.py get_article_sections <title>
  python scripts/wiki_tools.py get_related_articles <title> [max_results=8]
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "search_wikipedia":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result: object = search_wikipedia(argv[2], n)
        elif cmd == "get_article_summary":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_article_summary(argv[2])
        elif cmd == "get_article_sections":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_article_sections(argv[2])
        elif cmd == "get_related_articles":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 8
            result = get_related_articles(argv[2], n)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
