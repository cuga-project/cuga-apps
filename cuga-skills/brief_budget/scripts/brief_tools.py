"""CLI helpers for the brief_budget skill — stdlib only.

Wraps arXiv, Semantic Scholar, Wikipedia, Tavily, and stdlib HTML reader so
the agent can compose a literature-style brief while tracking its own budget.

    python scripts/brief_tools.py search_arxiv 'mixture of experts' 5 cs.LG
    python scripts/brief_tools.py get_arxiv_paper 2305.11206
    python scripts/brief_tools.py search_semantic_scholar 'attention' 5
    python scripts/brief_tools.py get_paper_references arXiv:2305.11206
    python scripts/brief_tools.py search_wikipedia 'Quantum error correction'
    python scripts/brief_tools.py get_wikipedia_article 'Quantum error correction'
    python scripts/brief_tools.py web_search 'state of RAG' 5
    python scripts/brief_tools.py fetch_webpage 'https://example.com'

Env:
  TAVILY_API_KEY  — required for web_search

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

_UA = {"User-Agent": "brief-budget-skill/1.0 (https://skills.sh)"}

_ATOM = "http://www.w3.org/2005/Atom"
_ARXIV_API = "https://export.arxiv.org/api/query"
_S2_API = "https://api.semanticscholar.org/graph/v1"
_S2_FIELDS = "title,authors,year,abstract,citationCount,url,externalIds"
_S2_REF_FIELDS = "title,authors,year,citationCount,url,externalIds"
_WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
_WIKI_ACTION = "https://en.wikipedia.org/w/api.php"
_TAVILY = "https://api.tavily.com/search"


def _http_get(url: str, params: dict | None = None) -> str:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def _http_get_json(url: str, params: dict | None = None) -> dict | list:
    return json.loads(_http_get(url, params))


def _http_get_xml(url: str, params: dict | None = None) -> ET.Element:
    return ET.fromstring(_http_get(url, params))


def _http_post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={**_UA, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

def search_arxiv(query: str, max_results: int = 6, category: str | None = None) -> dict:
    search_q = f"all:{query}"
    if category:
        search_q = f"cat:{category} AND all:{query}"
    try:
        root = _http_get_xml(_ARXIV_API, {
            "search_query": search_q, "max_results": min(max_results, 20),
            "sortBy": "submittedDate", "sortOrder": "descending",
        })
    except Exception as e:
        return {"error": f"arXiv search failed: {type(e).__name__}: {e}"}
    entries = root.findall(f"{{{_ATOM}}}entry")
    results = []
    for e in entries:
        arxiv_id = (e.findtext(f"{{{_ATOM}}}id") or "").strip().split("/abs/")[-1]
        results.append({
            "arxiv_id": arxiv_id,
            "title": (e.findtext(f"{{{_ATOM}}}title") or "").replace("\n", " ").strip(),
            "authors": [a.findtext(f"{{{_ATOM}}}name") or ""
                        for a in e.findall(f"{{{_ATOM}}}author")][:5],
            "abstract": (e.findtext(f"{{{_ATOM}}}summary") or "")
                        .replace("\n", " ").strip()[:600],
            "published": (e.findtext(f"{{{_ATOM}}}published") or "")[:10],
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf": f"https://arxiv.org/pdf/{arxiv_id}",
        })
    return {"results": results}


def get_arxiv_paper(arxiv_id: str) -> dict:
    clean = arxiv_id.strip().split("/abs/")[-1]
    try:
        root = _http_get_xml(_ARXIV_API, {"id_list": clean, "max_results": 1})
    except Exception as e:
        return {"error": f"arXiv fetch failed: {type(e).__name__}: {e}"}
    entries = root.findall(f"{{{_ATOM}}}entry")
    if not entries:
        return {"error": f"No paper found for ID: {arxiv_id}"}
    e = entries[0]
    return {
        "arxiv_id": clean,
        "title": (e.findtext(f"{{{_ATOM}}}title") or "").replace("\n", " ").strip(),
        "authors": [a.findtext(f"{{{_ATOM}}}name") or ""
                    for a in e.findall(f"{{{_ATOM}}}author")],
        "abstract": (e.findtext(f"{{{_ATOM}}}summary") or "").replace("\n", " ").strip(),
        "published": (e.findtext(f"{{{_ATOM}}}published") or "")[:10],
        "url": f"https://arxiv.org/abs/{clean}",
    }


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(query: str, max_results: int = 6) -> dict:
    try:
        data = _http_get_json(f"{_S2_API}/paper/search", {
            "query": query, "limit": min(max_results, 20), "fields": _S2_FIELDS,
        })
    except Exception as e:
        return {"error": f"S2 search failed: {type(e).__name__}: {e}"}
    papers = data.get("data") or []
    results = []
    for p in papers:
        ext_ids = p.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        abstract = p.get("abstract") or ""
        results.append({
            "paper_id": p.get("paperId", ""),
            "title": p.get("title", ""),
            "authors": [a.get("name", "") for a in (p.get("authors") or [])[:5]],
            "year": p.get("year"),
            "abstract": abstract[:600],
            "citation_count": p.get("citationCount", 0),
            "url": p.get("url", ""),
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        })
    return {"results": results}


def get_paper_references(paper_id: str) -> dict:
    try:
        data = _http_get_json(
            f"{_S2_API}/paper/{urllib.parse.quote(paper_id, safe=':')}/references",
            {"fields": _S2_REF_FIELDS, "limit": 10},
        )
    except Exception as e:
        return {"error": f"S2 references failed: {type(e).__name__}: {e}"}
    refs = [item.get("citedPaper", {}) for item in (data.get("data") or [])]
    results = []
    for p in refs:
        if not p.get("title"):
            continue
        ext_ids = p.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        results.append({
            "title": p.get("title", ""),
            "authors": [a.get("name", "") for a in (p.get("authors") or [])[:3]],
            "year": p.get("year"),
            "citation_count": p.get("citationCount", 0),
            "url": p.get("url", ""),
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        })
    return {"references": results}


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

def search_wikipedia(query: str, max_results: int = 6) -> dict:
    try:
        data = _http_get_json(_WIKI_ACTION, {
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": min(max_results, 20), "format": "json",
        })
    except Exception as e:
        return {"error": f"Wikipedia search failed: {type(e).__name__}: {e}"}
    hits = data.get("query", {}).get("search", []) or []
    return {"results": [{
        "title": h.get("title"),
        "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", "") or "").strip(),
        "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote((h.get('title') or '').replace(' ', '_'))}",
    } for h in hits]}


def get_wikipedia_article(title: str) -> dict:
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
    }


# ---------------------------------------------------------------------------
# Web search + page fetch
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5) -> dict:
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
    return {"query": query, "results": [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "content": (r.get("content") or "")[:800]}
        for r in (data.get("results") or [])
    ]}


class _ReadableExtractor(HTMLParser):
    _DROP = {"script", "style", "noscript", "header", "footer", "nav",
             "aside", "form", "svg"}
    _BLOCK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "blockquote", "pre"}

    def __init__(self):
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
    return {"url": url, "title": parser.title.strip(),
            "text": text, "truncated": truncated}


_USAGE = """\
usage:
  python scripts/brief_tools.py search_arxiv <query> [max_results=6] [category=-]
  python scripts/brief_tools.py get_arxiv_paper <arxiv_id>
  python scripts/brief_tools.py search_semantic_scholar <query> [max_results=6]
  python scripts/brief_tools.py get_paper_references <paper_id>
  python scripts/brief_tools.py search_wikipedia <query> [max_results=6]
  python scripts/brief_tools.py get_wikipedia_article <title>
  python scripts/brief_tools.py web_search <query> [max_results=5]
  python scripts/brief_tools.py fetch_webpage <url> [max_chars=8000]
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "search_arxiv":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            cat = argv[4] if len(argv) > 4 and argv[4] != "-" else None
            result: object = search_arxiv(argv[2], n, cat)
        elif cmd == "get_arxiv_paper":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_arxiv_paper(argv[2])
        elif cmd == "search_semantic_scholar":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result = search_semantic_scholar(argv[2], n)
        elif cmd == "get_paper_references":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_paper_references(argv[2])
        elif cmd == "search_wikipedia":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result = search_wikipedia(argv[2], n)
        elif cmd == "get_wikipedia_article":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_wikipedia_article(argv[2])
        elif cmd == "web_search":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 5
            result = web_search(argv[2], n)
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
