"""mcp-knowledge — Wikipedia, arXiv, Semantic Scholar.

Tools:
  - search_wikipedia(query, max_results)
  - get_wikipedia_article(title, full)
  - search_arxiv(query, max_results, category)
  - get_arxiv_paper(arxiv_id)
  - search_semantic_scholar(query, max_results)
  - get_paper_references(paper_id)

All APIs are free / public — no keys required.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result, get_json, get_xml
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_KNOWLEDGE_PORT  # noqa: E402

mcp = make_server("mcp-knowledge")

# ── Wikipedia ──────────────────────────────────────────────────────────
_WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
_WIKI_ACTION = "https://en.wikipedia.org/w/api.php"


@mcp.tool()
def search_wikipedia(query: str, max_results: int = 6) -> str:
    """Search Wikipedia for articles matching the query.

    Returns title, snippet, and a canonical article URL per match.

    Args:
        query: Search terms.
        max_results: Number of results (default 6, max 20).
    """
    try:
        data = get_json(_WIKI_ACTION, params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": min(max_results, 20),
            "format": "json",
        })
        hits = data.get("query", {}).get("search", [])
        results = [{
            "title":   h.get("title"),
            "snippet": _strip_html(h.get("snippet", "")),
            "url":     f"https://en.wikipedia.org/wiki/{h.get('title', '').replace(' ', '_')}",
        } for h in hits]
        return tool_result({"results": results})
    except Exception as exc:
        return tool_error(f"Wikipedia search failed: {exc}", code="upstream")


@mcp.tool()
def get_wikipedia_article(title: str, full: bool = False) -> str:
    """Fetch a Wikipedia article by exact title.

    If full=False (default), returns the REST lead summary (a few paragraphs).
    If full=True, returns the full plain-text extract via the action API.

    Args:
        title: Exact Wikipedia article title (case-sensitive, spaces allowed).
        full: Whether to return the full article (default False — summary only).
    """
    return _wiki_article(title, full=full)


def _wiki_article(title: str, full: bool) -> str:
    try:
        if not full:
            data = get_json(f"{_WIKI_REST}/page/summary/{title.replace(' ', '_')}")
            return tool_result({
                "title":   data.get("title"),
                "summary": data.get("extract"),
                "url":     (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
                "thumbnail": (data.get("thumbnail") or {}).get("source"),
            })
        data = get_json(_WIKI_ACTION, params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": title,
            "format": "json",
        })
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values())) if pages else {}
        return tool_result({
            "title":   page.get("title"),
            "extract": page.get("extract", ""),
            "url":     f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        })
    except Exception as exc:
        return tool_error(f"Wikipedia fetch failed: {exc}", code="upstream")


@mcp.tool()
def get_article_summary(title: str) -> str:
    """Fetch the lead summary of a Wikipedia article (a few paragraphs).

    Equivalent to get_wikipedia_article(title, full=False). Kept as a distinct
    tool because several apps semantically distinguish "summary" from "full
    sections" in their prompts.

    Args:
        title: Exact Wikipedia article title.
    """
    return _wiki_article(title, full=False)


@mcp.tool()
def get_article_sections(title: str) -> str:
    """Fetch the full plain-text content of a Wikipedia article, section by section.

    Equivalent to get_wikipedia_article(title, full=True). Use when the lead
    summary isn't detailed enough and the caller wants the whole article.

    Args:
        title: Exact Wikipedia article title.
    """
    return _wiki_article(title, full=True)


def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", s or "").strip()


@mcp.tool()
def get_related_articles(title: str, max_results: int = 8) -> str:
    """Fetch links to related articles from a Wikipedia page.

    Use this to discover closely related concepts and decide what to read next
    for broader context.

    Args:
        title: Exact Wikipedia article title.
        max_results: Maximum related titles to return (default 8).
    """
    try:
        data = get_json(_WIKI_ACTION, params={
            "action":    "query",
            "titles":    title,
            "prop":      "links",
            "pllimit":   min(max_results * 3, 30),
            "plnamespace": 0,
            "format":    "json",
        })
        pages = list((data.get("query", {}).get("pages") or {}).values())
        if not pages:
            return tool_result({"source": title, "related": []})
        from urllib.parse import quote
        related = [
            {
                "title": lnk.get("title", ""),
                "url":   f"https://en.wikipedia.org/wiki/{quote(lnk.get('title', '').replace(' ', '_'))}",
            }
            for lnk in pages[0].get("links", [])[:max_results]
        ]
        return tool_result({"source": title, "related": related})
    except Exception as exc:
        return tool_error(f"Wikipedia related-articles lookup failed: {exc}", code="upstream")


# ── arXiv ──────────────────────────────────────────────────────────────
_ATOM = "http://www.w3.org/2005/Atom"
_ARXIV_API = "https://export.arxiv.org/api/query"


@mcp.tool()
def search_arxiv(query: str, max_results: int = 6, category: str = "") -> str:
    """Search arXiv for recent papers matching a query.

    Returns title, authors, abstract excerpt, arXiv ID, and published date
    for each hit, sorted by most recent submission.

    Args:
        query: Search terms (e.g. "large language models reasoning").
        max_results: Number of papers to return (default 6, max 20).
        category: Optional arXiv category filter like "cs.AI", "cs.LG",
                  "stat.ML". Leave empty to search all.
    """
    search_q = f"all:{query}"
    if category:
        search_q = f"cat:{category} AND all:{query}"
    try:
        root = get_xml(_ARXIV_API, params={
            "search_query": search_q,
            "max_results": min(max_results, 20),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        entries = root.findall(f"{{{_ATOM}}}entry")
        if not entries:
            return tool_result({"results": [], "message": "No papers found."})
        results = []
        for e in entries:
            arxiv_id = (e.findtext(f"{{{_ATOM}}}id") or "").strip().split("/abs/")[-1]
            title   = (e.findtext(f"{{{_ATOM}}}title") or "").replace("\n", " ").strip()
            summary = (e.findtext(f"{{{_ATOM}}}summary") or "").replace("\n", " ").strip()
            results.append({
                "arxiv_id":  arxiv_id,
                "title":     title,
                "authors":   [a.findtext(f"{{{_ATOM}}}name") or "" for a in e.findall(f"{{{_ATOM}}}author")][:5],
                "abstract":  summary[:600] + ("…" if len(summary) > 600 else ""),
                "published": (e.findtext(f"{{{_ATOM}}}published") or "")[:10],
                "url":       f"https://arxiv.org/abs/{arxiv_id}",
                "pdf":       f"https://arxiv.org/pdf/{arxiv_id}",
            })
        return tool_result({"results": results})
    except Exception as exc:
        return tool_error(f"arXiv search failed: {exc}", code="upstream")


@mcp.tool()
def get_arxiv_paper(arxiv_id: str) -> str:
    """Fetch full metadata + abstract for a specific arXiv paper.

    arxiv_id looks like "2305.11206" or "2305.11206v2". Use this when the
    user pastes an arXiv URL or ID directly.

    Args:
        arxiv_id: The arXiv paper ID.
    """
    clean = arxiv_id.strip().split("/abs/")[-1].strip()
    try:
        root = get_xml(_ARXIV_API, params={"id_list": clean, "max_results": 1})
        entries = root.findall(f"{{{_ATOM}}}entry")
        if not entries:
            return tool_error(f"No paper found for ID: {arxiv_id}", code="not_found")
        e = entries[0]
        return tool_result({
            "arxiv_id":  clean,
            "title":     (e.findtext(f"{{{_ATOM}}}title") or "").replace("\n", " ").strip(),
            "authors":   [a.findtext(f"{{{_ATOM}}}name") or "" for a in e.findall(f"{{{_ATOM}}}author")],
            "abstract":  (e.findtext(f"{{{_ATOM}}}summary") or "").replace("\n", " ").strip(),
            "published": (e.findtext(f"{{{_ATOM}}}published") or "")[:10],
            "updated":   (e.findtext(f"{{{_ATOM}}}updated") or "")[:10],
            "categories":[c.get("term", "") for c in e.findall(f"{{{_ATOM}}}category")],
            "url":       f"https://arxiv.org/abs/{clean}",
            "pdf":       f"https://arxiv.org/pdf/{clean}",
        })
    except Exception as exc:
        return tool_error(f"arXiv fetch failed: {exc}", code="upstream")


# ── Semantic Scholar ───────────────────────────────────────────────────
_S2_API = "https://api.semanticscholar.org/graph/v1"
_S2_FIELDS = "title,authors,year,abstract,citationCount,url,externalIds,openAccessPdf"
_S2_REF_FIELDS = "title,authors,year,citationCount,url,externalIds"


@mcp.tool()
def search_semantic_scholar(query: str, max_results: int = 6) -> str:
    """Search Semantic Scholar for papers matching a query.

    Richer metadata than arXiv: citation counts, open-access links, and coverage
    beyond CS/ML (biology, medicine, social science). Use for highly-cited
    papers or when arXiv coverage is thin.

    Args:
        query: Search terms.
        max_results: Number of papers to return (default 6, max 20).
    """
    try:
        data = get_json(
            f"{_S2_API}/paper/search",
            params={"query": query, "limit": min(max_results, 20), "fields": _S2_FIELDS},
        )
        papers = data.get("data", [])
        if not papers:
            return tool_result({"results": [], "message": "No papers found."})
        results = []
        for p in papers:
            ext_ids = p.get("externalIds") or {}
            pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
            arxiv_id = ext_ids.get("ArXiv", "")
            abstract = p.get("abstract") or ""
            results.append({
                "paper_id":       p.get("paperId", ""),
                "title":          p.get("title", ""),
                "authors":        [a.get("name", "") for a in (p.get("authors") or [])[:5]],
                "year":           p.get("year"),
                "abstract":       abstract[:600] + ("…" if len(abstract) > 600 else ""),
                "citation_count": p.get("citationCount", 0),
                "url":            p.get("url", ""),
                "arxiv_id":       arxiv_id,
                "arxiv_url":      f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                "pdf_url":        pdf_url,
            })
        return tool_result({"results": results})
    except Exception as exc:
        return tool_error(f"Semantic Scholar search failed: {exc}", code="upstream")


@mcp.tool()
def get_paper_references(paper_id: str) -> str:
    """Fetch the reference list of a Semantic Scholar paper.

    paper_id is the Semantic Scholar paperId from search results, or an arXiv
    ID prefixed with "arXiv:" (e.g. "arXiv:2305.11206"). Returns up to 10
    cited papers with title, authors, year, and citation count.

    Args:
        paper_id: Semantic Scholar paperId or "arXiv:XXXX.XXXXX".
    """
    try:
        data = get_json(
            f"{_S2_API}/paper/{paper_id}/references",
            params={"fields": _S2_REF_FIELDS, "limit": 10},
        )
        refs = [item.get("citedPaper", {}) for item in (data.get("data") or [])]
        results = []
        for p in refs:
            if not p.get("title"):
                continue
            ext_ids = p.get("externalIds") or {}
            arxiv_id = ext_ids.get("ArXiv", "")
            results.append({
                "title":          p.get("title", ""),
                "authors":        [a.get("name", "") for a in (p.get("authors") or [])[:3]],
                "year":           p.get("year"),
                "citation_count": p.get("citationCount", 0),
                "url":            p.get("url", ""),
                "arxiv_url":      f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
            })
        return tool_result({"references": results})
    except Exception as exc:
        return tool_error(f"Semantic Scholar references failed: {exc}", code="upstream")


if __name__ == "__main__":
    run(mcp, MCP_KNOWLEDGE_PORT)
