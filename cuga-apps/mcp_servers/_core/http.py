"""Thin httpx wrappers for MCP tools.

Every outbound call goes through here so timeouts, user-agent, and
retry-on-429 behavior are consistent.
"""
from __future__ import annotations

import logging
import os
import time
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


def _get(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> httpx.Response:
    """GET with retry on 429/503. Raises on any other 4xx/5xx (and on the final
    429/503 after retries are exhausted), exactly like raise_for_status."""
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
            return r
    # Unreachable (the loop either returns or raises), but keeps type-checkers happy.
    r.raise_for_status()
    return r


def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
    return _get(url, params=params, headers=headers).json()


def get_text(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> str:
    return _get(url, params=params, headers=headers).text


def get_xml(url: str, params: Optional[dict] = None) -> ET.Element:
    return ET.fromstring(get_text(url, params=params))
