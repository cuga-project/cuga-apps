"""CLI helper for the webpage_summarizer skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/web_tools.py fetch_url 'https://example.com'
    python scripts/web_tools.py fetch_url 'https://example.com' 5000

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

_UA = {
    "User-Agent": "webpage-summarizer-skill/1.0 (https://skills.sh)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


class _ReadableExtractor(HTMLParser):
    """Strip scripts/styles/nav/header/footer/aside, keep visible text."""

    _DROP = {"script", "style", "noscript", "header", "footer", "nav", "aside",
             "form", "svg"}
    _BLOCK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "blockquote", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth_drop = 0
        self._in_title = False
        self.title: str = ""
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in self._DROP:
            self._depth_drop += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._BLOCK and self._depth_drop == 0:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str):
        if tag in self._DROP and self._depth_drop > 0:
            self._depth_drop -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self._BLOCK and self._depth_drop == 0:
            self._chunks.append("\n")

    def handle_data(self, data: str):
        if self._depth_drop > 0:
            return
        if self._in_title:
            self.title += data
        else:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        # Collapse runs of whitespace inside lines, then drop blank lines.
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln)


def fetch_url(url: str, max_chars: int = 10_000) -> dict:
    """Fetch a webpage → {url, title, text}. Returns {error: ...} on failure."""
    if not re.match(r"^https?://", url, flags=re.I):
        return {"error": f"URL must start with http:// or https://: {url!r}"}
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code} fetching {url}"}
    except urllib.error.URLError as e:
        return {"error": f"Network error fetching {url}: {e.reason}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    parser = _ReadableExtractor()
    try:
        parser.feed(html)
    except Exception as e:
        return {"error": f"HTML parse failed: {type(e).__name__}: {e}"}
    text = parser.text()
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
        truncated = True
    return {
        "url": url,
        "title": parser.title.strip(),
        "text": text,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_USAGE = """\
usage:
  python scripts/web_tools.py fetch_url <url> [max_chars=10000]
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd = argv[1]
    try:
        if cmd == "fetch_url":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr)
                return 2
            max_chars = int(argv[3]) if len(argv) > 3 else 10_000
            result: object = fetch_url(argv[2], max_chars)
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
