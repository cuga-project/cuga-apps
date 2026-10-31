"""Thin httpx wrappers for MCP tools.

Every outbound call goes through here so timeouts, user-agent, caching, and
retry-on-429 behavior are consistent.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional
import xml.etree.ElementTree as ET

import httpx

log = logging.getLogger(__name__)

# A descriptive User-Agent is required by several public APIs (Wikipedia in
# particular returns 429s for generic/placeholder agents). Override with a real
# contact via MCP_USER_AGENT in production if you have one.
_UA = os.getenv(
    "MCP_USER_AGENT",
    "cuga-apps-mcp/0.1 (https://github.com/cuga-project/cuga-apps)",
)
_TIMEOUT = float(os.getenv("MCP_HTTP_TIMEOUT", "20"))

# Retry config for transient throttling/unavailability. Honors the server's
# Retry-After header when present, otherwise exponential backoff. Total added
# wait is bounded (cap per attempt) so a tool call can't hang indefinitely.
_RETRY_STATUS = {429, 503}
_MAX_RETRIES = int(os.getenv("MCP_HTTP_RETRIES", "3"))
_BACKOFF = float(os.getenv("MCP_HTTP_BACKOFF", "1.0"))
_MAX_BACKOFF = float(os.getenv("MCP_HTTP_MAX_BACKOFF", "8"))

# In-memory TTL cache for GET responses. The hosted MCP servers share one
# outbound IP, and without a cache every question re-fetches the same article
# or price until Wikipedia/CoinGecko answer 429 (#50). Entries are evicted LRU
# past _CACHE_MAX. Per-call cache_ttl overrides the default; cache_ttl=0 opts
# out entirely for anything that must be live.
_CACHE_TTL = float(os.getenv("MCP_HTTP_CACHE_TTL", "600"))
_CACHE_MAX = int(os.getenv("MCP_HTTP_CACHE_MAX", "1000"))
_cache: OrderedDict[tuple, tuple[float, httpx.Response]] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(url: str, params: Optional[dict], headers: Optional[dict]) -> tuple:
    return (
        url,
        tuple(sorted((str(k), str(v)) for k, v in (params or {}).items())),
        tuple(sorted((str(k), str(v)) for k, v in (headers or {}).items())),
    )


def _cache_get(key: tuple) -> Optional[httpx.Response]:
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        expires_at, resp = hit
        if time.monotonic() >= expires_at:
            del _cache[key]
            return None
        _cache.move_to_end(key)
        return resp


def _cache_put(key: tuple, resp: httpx.Response, ttl: float) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl, resp)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "*/*"},
        follow_redirects=True,
    )


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    """Seconds to wait before the next attempt — the server's Retry-After if it
    sent a sane numeric one, else exponential backoff. Capped at _MAX_BACKOFF."""
    ra = resp.headers.get("Retry-After", "").strip()
    if ra.isdigit():
        return min(float(ra), _MAX_BACKOFF)
    return min(_BACKOFF * (2 ** attempt), _MAX_BACKOFF)


def _get(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cache_ttl: Optional[float] = None,
) -> httpx.Response:
    """GET with a TTL cache and retry on 429/503. Raises on any other 4xx/5xx
    (and on the final 429/503 after retries are exhausted), exactly like
    raise_for_status. cache_ttl=None uses the default TTL; cache_ttl<=0 skips
    the cache."""
    ttl = _CACHE_TTL if cache_ttl is None else cache_ttl
    key = _cache_key(url, params, headers)
    if ttl > 0:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    with _client() as c:
        for attempt in range(_MAX_RETRIES + 1):
            r = c.get(url, params=params, headers=headers)
            if r.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                delay = _retry_after(r, attempt)
                log.warning(
                    "HTTP %s from %s — retry %d/%d in %.1fs",
                    r.status_code, url, attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            r.raise_for_status()
            if ttl > 0:
                _cache_put(key, r, ttl)
            return r
    # Unreachable (the loop either returns or raises), but keeps type-checkers happy.
    r.raise_for_status()
    return r


def get_json(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cache_ttl: Optional[float] = None,
) -> Any:
    return _get(url, params=params, headers=headers, cache_ttl=cache_ttl).json()


def get_text(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cache_ttl: Optional[float] = None,
) -> str:
    return _get(url, params=params, headers=headers, cache_ttl=cache_ttl).text


def get_xml(url: str, params: Optional[dict] = None, cache_ttl: Optional[float] = None) -> ET.Element:
    return ET.fromstring(get_text(url, params=params, cache_ttl=cache_ttl))
