"""CLI helpers for the newsletter skill.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/feed_tools.py fetch_feed 'https://hnrss.org/frontpage' 15
    python scripts/feed_tools.py search_feeds \\
        'https://blog.langchain.dev/rss/,https://anthropic.com/news/rss' \\
        'agents,rag,reasoning' 50

Pip deps (declared in SKILL.md frontmatter):
  feedparser>=6.0   — handles RSS, Atom, and the messy world of real feeds

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import sys


def _load_feedparser():
    try:
        import feedparser  # type: ignore
    except ImportError:
        return None
    return feedparser


def fetch_feed(url: str, max_items: int = 20) -> dict:
    fp = _load_feedparser()
    if fp is None:
        return {"error": "feedparser not installed (declared in SKILL.md requirements as feedparser>=6.0)"}
    try:
        parsed = fp.parse(url)
    except Exception as e:
        return {"error": f"Feed parse failed: {type(e).__name__}: {e}"}
    if getattr(parsed, "bozo", 0) and not getattr(parsed, "entries", []):
        exc = parsed.get("bozo_exception")
        return {"error": f"Feed parse failed: {exc!r}"}
    feed_title = ""
    if hasattr(parsed, "feed"):
        feed_title = parsed.feed.get("title", "") or ""
    items = []
    for entry in (parsed.entries or [])[:max_items]:
        items.append({
            "title": getattr(entry, "title", "") or "",
            "link": getattr(entry, "link", "") or "",
            "summary": (getattr(entry, "summary", "") or "")[:1000],
            "published": getattr(entry, "published",
                                 getattr(entry, "updated", "")) or "",
            "author": getattr(entry, "author", "") or "",
        })
    return {"feed_url": url, "feed_title": feed_title, "items": items}


def search_feeds(feed_urls: list[str], keywords: list[str], max_per_feed: int = 50) -> dict:
    fp = _load_feedparser()
    if fp is None:
        return {"error": "feedparser not installed (declared in SKILL.md requirements as feedparser>=6.0)"}
    kws = [k.lower() for k in keywords if k]
    if not kws:
        return {"error": "no keywords given"}
    matches: list[dict] = []
    feed_errors: list[dict] = []
    for url in feed_urls:
        if not url:
            continue
        try:
            parsed = fp.parse(url)
        except Exception as e:
            feed_errors.append({"feed_url": url, "error": f"{type(e).__name__}: {e}"})
            continue
        if getattr(parsed, "bozo", 0) and not getattr(parsed, "entries", []):
            feed_errors.append({"feed_url": url, "error": str(parsed.get("bozo_exception"))})
            continue
        feed_title = parsed.feed.get("title", url) if hasattr(parsed, "feed") else url
        for entry in (parsed.entries or [])[:max_per_feed]:
            title = getattr(entry, "title", "") or ""
            summary = getattr(entry, "summary", "") or ""
            haystack = f"{title}\n{summary}".lower()
            if any(k in haystack for k in kws):
                matches.append({
                    "feed": feed_title,
                    "feed_url": url,
                    "title": title,
                    "link": getattr(entry, "link", "") or "",
                    "summary": summary[:600],
                    "published": getattr(entry, "published",
                                         getattr(entry, "updated", "")) or "",
                })
    return {
        "matches": matches,
        "count": len(matches),
        "feed_count": len(feed_urls),
        "feed_errors": feed_errors,
    }


_USAGE = """\
usage:
  python scripts/feed_tools.py fetch_feed <url> [max_items=20]
  python scripts/feed_tools.py search_feeds <feed_urls_csv> <keywords_csv> [max_per_feed=50]

feed_urls_csv: comma-separated list of feed URLs
keywords_csv:  comma-separated list of keywords

Requires: feedparser>=6.0 (declared in SKILL.md)
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "fetch_feed":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 20
            result: object = fetch_feed(argv[2], n)
        elif cmd == "search_feeds":
            if len(argv) < 4: print(_USAGE, file=sys.stderr); return 2
            feeds = [u.strip() for u in argv[2].split(",") if u.strip()]
            kws = [k.strip() for k in argv[3].split(",") if k.strip()]
            mx = int(argv[4]) if len(argv) > 4 else 50
            result = search_feeds(feeds, kws, mx)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
