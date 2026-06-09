"""CLI helpers for the paper_scout skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/paper_tools.py search_arxiv 'mixture of experts' 5 cs.LG
    python scripts/paper_tools.py get_arxiv_paper 2305.11206
    python scripts/paper_tools.py search_semantic_scholar 'BERT' 5
    python scripts/paper_tools.py get_paper_references arXiv:2305.11206

Pass `-` for category in search_arxiv to skip the filter.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

_UA = {"User-Agent": "paper-scout-skill/1.0 (https://skills.sh)"}
_ATOM = "http://www.w3.org/2005/Atom"
_ARXIV_API = "https://export.arxiv.org/api/query"
_S2_API = "https://api.semanticscholar.org/graph/v1"
_S2_FIELDS = "title,authors,year,abstract,citationCount,url,externalIds,openAccessPdf"
_S2_REF_FIELDS = "title,authors,year,citationCount,url,externalIds"


def _http_get(url: str, params: Optional[dict] = None, timeout: float = 25.0) -> str:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _http_get_json(url: str, params: Optional[dict] = None) -> dict:
    return json.loads(_http_get(url, params))


def _http_get_xml(url: str, params: Optional[dict] = None) -> ET.Element:
    return ET.fromstring(_http_get(url, params))


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

def search_arxiv(query: str, max_results: int = 6, category: Optional[str] = None) -> dict:
    """Search arXiv → list of paper dicts (most recent first)."""
    search_q = f"all:{query}"
    if category:
        search_q = f"cat:{category} AND all:{query}"
    try:
        root = _http_get_xml(_ARXIV_API, {
            "search_query": search_q,
            "max_results": min(max_results, 20),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
    except Exception as e:
        return {"error": f"arXiv search failed: {type(e).__name__}: {e}"}
    entries = root.findall(f"{{{_ATOM}}}entry")
    if not entries:
        return {"results": [], "message": "No papers found."}
    results = []
    for e in entries:
        arxiv_id = (e.findtext(f"{{{_ATOM}}}id") or "").strip().split("/abs/")[-1]
        title = (e.findtext(f"{{{_ATOM}}}title") or "").replace("\n", " ").strip()
        summary = (e.findtext(f"{{{_ATOM}}}summary") or "").replace("\n", " ").strip()
        results.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": [a.findtext(f"{{{_ATOM}}}name") or ""
                        for a in e.findall(f"{{{_ATOM}}}author")][:5],
            "abstract": summary[:600] + ("…" if len(summary) > 600 else ""),
            "published": (e.findtext(f"{{{_ATOM}}}published") or "")[:10],
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf": f"https://arxiv.org/pdf/{arxiv_id}",
        })
    return {"results": results}


def get_arxiv_paper(arxiv_id: str) -> dict:
    """Fetch full metadata + abstract for one arXiv paper."""
    clean = arxiv_id.strip().split("/abs/")[-1].strip()
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
        "updated": (e.findtext(f"{{{_ATOM}}}updated") or "")[:10],
        "categories": [c.get("term", "") for c in e.findall(f"{{{_ATOM}}}category")],
        "url": f"https://arxiv.org/abs/{clean}",
        "pdf": f"https://arxiv.org/pdf/{clean}",
    }


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(query: str, max_results: int = 6) -> dict:
    """Search Semantic Scholar → list of paper dicts with citation counts."""
    try:
        data = _http_get_json(f"{_S2_API}/paper/search", {
            "query": query,
            "limit": min(max_results, 20),
            "fields": _S2_FIELDS,
        })
    except Exception as e:
        return {"error": f"Semantic Scholar search failed: {type(e).__name__}: {e}"}
    papers = data.get("data") or []
    if not papers:
        return {"results": [], "message": "No papers found."}
    results = []
    for p in papers:
        ext_ids = p.get("externalIds") or {}
        pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
        arxiv_id = ext_ids.get("ArXiv", "")
        abstract = p.get("abstract") or ""
        results.append({
            "paper_id": p.get("paperId", ""),
            "title": p.get("title", ""),
            "authors": [a.get("name", "") for a in (p.get("authors") or [])[:5]],
            "year": p.get("year"),
            "abstract": abstract[:600] + ("…" if len(abstract) > 600 else ""),
            "citation_count": p.get("citationCount", 0),
            "url": p.get("url", ""),
            "arxiv_id": arxiv_id,
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
            "pdf_url": pdf_url,
        })
    return {"results": results}


def get_paper_references(paper_id: str) -> dict:
    """Fetch the reference list of a paper."""
    try:
        data = _http_get_json(
            f"{_S2_API}/paper/{urllib.parse.quote(paper_id, safe=':')}/references",
            {"fields": _S2_REF_FIELDS, "limit": 10},
        )
    except Exception as e:
        return {"error": f"Semantic Scholar references failed: {type(e).__name__}: {e}"}
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
# CLI
# ---------------------------------------------------------------------------

_USAGE = """\
usage:
  python scripts/paper_tools.py search_arxiv <query> [max_results=6] [category=-]
  python scripts/paper_tools.py get_arxiv_paper <arxiv_id>
  python scripts/paper_tools.py search_semantic_scholar <query> [max_results=6]
  python scripts/paper_tools.py get_paper_references <paper_id>

Pass `-` for category to skip the filter.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "search_arxiv":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            max_results = int(argv[3]) if len(argv) > 3 else 6
            category = argv[4] if len(argv) > 4 and argv[4] != "-" else None
            result: object = search_arxiv(argv[2], max_results, category)
        elif cmd == "get_arxiv_paper":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            result = get_arxiv_paper(argv[2])
        elif cmd == "search_semantic_scholar":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            max_results = int(argv[3]) if len(argv) > 3 else 6
            result = search_semantic_scholar(argv[2], max_results)
        elif cmd == "get_paper_references":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            result = get_paper_references(argv[2])
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
