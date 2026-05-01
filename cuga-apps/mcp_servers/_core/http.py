"""Thin httpx wrappers for MCP tools.

Every outbound call goes through here so timeouts, user-agent, and
retry-on-429 behavior are consistent.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional
import xml.etree.ElementTree as ET

import httpx

log = logging.getLogger(__name__)

_UA = os.getenv("MCP_USER_AGENT", "cuga-apps-mcp/0.1 (+https://github.com/)")
_TIMEOUT = float(os.getenv("MCP_HTTP_TIMEOUT", "20"))


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "*/*"},
        follow_redirects=True,
    )


def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
    with _client() as c:
        r = c.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()


def get_text(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> str:
    with _client() as c:
        r = c.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.text


def get_xml(url: str, params: Optional[dict] = None) -> ET.Element:
    return ET.fromstring(get_text(url, params=params))
