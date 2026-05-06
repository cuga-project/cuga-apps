"""Tools for the voice_of_customer skill.

The host supplies an MCP-loaded `web_search` tool at agent construction.
This skill's tools.py only adds a thin specialist wrapper that pre-shapes
the query and returns just the snippet trio (title/url/snippet).
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

# The host injects this at construction time. See specialists.py.
_WEB_SEARCH: Optional[Callable[..., Awaitable[Any]]] = None


def bind_web_search(fn: Callable[..., Awaitable[Any]]) -> None:
    """Called once by specialists.py during agent construction to wire in
    the MCP web_search coroutine. The skill cannot import MCP directly
    (the bridge is host-only)."""
    global _WEB_SEARCH
    _WEB_SEARCH = fn


def _envelope_ok(data) -> str:
    return json.dumps({"ok": True, "data": data})


def _envelope_err(msg: str, code: str = "upstream") -> str:
    return json.dumps({"ok": False, "error": msg, "code": code})


async def _search_reviews(business_name: str, city: str,
                          complaints_focus: bool = False) -> dict:
    if _WEB_SEARCH is None:
        raise RuntimeError(
            "web_search not bound — host must call bind_web_search() at startup"
        )
    if complaints_focus:
        query = f'"{business_name}" {city} reviews complaints problems'
    else:
        query = f'"{business_name}" {city} reviews'
    raw = await _WEB_SEARCH(query=query, max_results=5)
    # MCP web_search returns the unwrapped envelope's data — typically a list
    # of {title, url, snippet, ...} dicts, or a {results: [...]} dict.
    if isinstance(raw, dict) and "results" in raw:
        items = raw["results"]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        # If the bridge returned a JSON string envelope, parse it.
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "results" in parsed:
                items = parsed["results"]
            elif isinstance(parsed, list):
                items = parsed
            else:
                items = []
        except json.JSONDecodeError:
            items = []
    else:
        items = []
    hits = []
    for it in items[:5]:
        if not isinstance(it, dict):
            continue
        hits.append({
            "title":   (it.get("title") or "").strip()[:200],
            "url":     it.get("url") or "",
            "snippet": (it.get("content") or it.get("snippet") or "").strip()[:600],
        })
    return {"query": query, "hits": hits}


try:
    from langchain_core.tools import tool

    @tool
    async def search_reviews(business_name: str, city: str,
                              complaints_focus: bool = False) -> str:
        """Search for review-site snippets about a specific business.

        Args:
            business_name:    Exact business name (will be quoted in the query).
            city:             City / neighborhood to disambiguate (REQUIRED).
            complaints_focus: True to skew the query toward "complaints
                              problems" — use only on the second pass when
                              the first pass returned mostly positive hits.
        """
        try:
            return _envelope_ok(await _search_reviews(business_name, city, complaints_focus))
        except Exception as e:
            return _envelope_err(f"search_reviews failed: {e}")

    TOOLS = [search_reviews]
except ImportError:
    TOOLS = []
