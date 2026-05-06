"""Tools for the person_finder skill.

`search_owner` wraps the host-injected MCP web_search.
`guess_email_from_name` generates common cold-email patterns from a name.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

_WEB_SEARCH: Optional[Callable[..., Awaitable[Any]]] = None


def bind_web_search(fn: Callable[..., Awaitable[Any]]) -> None:
    global _WEB_SEARCH
    _WEB_SEARCH = fn


def _envelope_ok(data) -> str:
    return json.dumps({"ok": True, "data": data})


def _envelope_err(msg: str, code: str = "upstream") -> str:
    return json.dumps({"ok": False, "error": msg, "code": code})


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = urlparse(url).hostname or ""
    # strip leading www.
    return host[4:] if host.lower().startswith("www.") else host


def _patterns_for(first: str, last: str, domain: str) -> list[str]:
    f = re.sub(r"[^a-z]", "", first.lower())
    l = re.sub(r"[^a-z]", "", last.lower())
    if not f or not l or not domain:
        return []
    # Ordered by hit-rate in published cold-email pattern surveys: first.last
    # is the modal pattern at small businesses, then flast / first, then
    # last.first as a tail.
    return [
        f"{f}.{l}@{domain}",
        f"{f[0]}{l}@{domain}",
        f"{f}@{domain}",
        f"{f}{l}@{domain}",
        f"{f}_{l}@{domain}",
        f"{l}.{f}@{domain}",
    ]


async def _search_owner(business_name: str, city: str) -> dict:
    if _WEB_SEARCH is None:
        raise RuntimeError("web_search not bound")
    query = f'"{business_name}" {city} (owner OR founder OR GM OR manager)'
    raw = await _WEB_SEARCH(query=query, max_results=5)
    if isinstance(raw, dict) and "results" in raw:
        items = raw["results"]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            items = parsed.get("results", []) if isinstance(parsed, dict) else (
                parsed if isinstance(parsed, list) else []
            )
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


def _guess_email(first_name: str, last_name: str, domain: str) -> dict:
    domain = _domain_from_url(domain) or domain
    candidates = _patterns_for(first_name or "", last_name or "", domain)
    if not candidates:
        return {"best_guess": None, "candidates": [], "domain": domain}
    return {"best_guess": candidates[0], "candidates": candidates, "domain": domain}


try:
    from langchain_core.tools import tool

    @tool
    async def search_owner(business_name: str, city: str) -> str:
        """Search for the owner / founder / GM of a specific business.

        Args:
            business_name: Exact business name.
            city:          City / area to disambiguate.
        """
        try:
            return _envelope_ok(await _search_owner(business_name, city))
        except Exception as e:
            return _envelope_err(f"search_owner failed: {e}")

    @tool
    def guess_email_from_name(first_name: str, last_name: str, domain: str) -> str:
        """Generate ordered cold-email pattern guesses for a person at a domain.

        Args:
            first_name: First name (case-insensitive, non-letters stripped).
            last_name:  Last name.
            domain:     Domain or full URL — the registrable host is extracted.
        """
        return _envelope_ok(_guess_email(first_name, last_name, domain))

    TOOLS = [search_owner, guess_email_from_name]
except ImportError:
    TOOLS = []
