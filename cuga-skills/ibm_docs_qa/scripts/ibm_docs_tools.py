"""CLI helpers for the ibm_docs_qa skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/ibm_docs_tools.py web_search 'site:cloud.ibm.com kubernetes' 6
    python scripts/ibm_docs_tools.py fetch_webpage 'https://cloud.ibm.com/docs/...'

`web_search` requires TAVILY_API_KEY in the environment.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

_UA = {
    "User-Agent": "ibm-docs-qa-skill/1.0 (https://skills.sh)",
    "Accept": "text/html,application/json,*/*;q=0.8",
}
_TAVILY = "https://api.tavily.com/search"


def _http_post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={**_UA, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())


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
             "content": (r.get("content") or "")[:1000]}
            for r in (data.get("results") or [])
        ],
    }


class _ReadableExtractor(HTMLParser):
    _DROP = {"script", "style", "noscript", "header", "footer", "nav",
             "aside", "form", "svg"}
    _BLOCK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "blockquote", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth_drop = 0
        self._in_title = False
        self.title = ""
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._DROP: self._depth_drop += 1
        elif tag == "title": self._in_title = True
        elif tag in self._BLOCK and self._depth_drop == 0:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._DROP and self._depth_drop > 0: self._depth_drop -= 1
        elif tag == "title": self._in_title = False
        elif tag in self._BLOCK and self._depth_drop == 0:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._depth_drop > 0: return
        if self._in_title: self.title += data
        else: self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln)


def fetch_webpage(url: str, max_chars: int = 8000) -> dict:
    if not re.match(r"^https?://", url, flags=re.I):
        return {"error": f"URL must start with http/https: {url!r}"}
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read().decode(charset, errors="replace")
    except Exception as e:
        return {"error": f"Fetch failed: {type(e).__name__}: {e}"}
    parser = _ReadableExtractor()
    try:
        parser.feed(html)
    except Exception as e:
        return {"error": f"Parse failed: {type(e).__name__}: {e}"}
    text = parser.text()
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
        truncated = True
    return {"url": url, "title": parser.title.strip(), "text": text,
            "truncated": truncated}


_USAGE = """\
usage:
  python scripts/ibm_docs_tools.py web_search <query> [max_results=6]
  python scripts/ibm_docs_tools.py fetch_webpage <url> [max_chars=8000]

web_search requires TAVILY_API_KEY in environment.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "web_search":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result: object = web_search(argv[2], n)
        elif cmd == "fetch_webpage":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            mx = int(argv[3]) if len(argv) > 3 else 8000
            result = fetch_webpage(argv[2], mx)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
