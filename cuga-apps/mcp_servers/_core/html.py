"""HTML text extraction used by mcp-web's fetch_webpage tool."""
from __future__ import annotations

from typing import List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_readable_text(html: str, max_chars: int = 10_000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n…[truncated]"
    return out


def extract_links(html: str, base_url: str, limit: int = 100) -> List[Tuple[str, str]]:
    """Return [(text, absolute_url), ...]."""
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip()
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        out.append((text[:200], absolute))
        if len(out) >= limit:
            break
    return out
