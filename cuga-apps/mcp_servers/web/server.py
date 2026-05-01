"""mcp-web — generic web I/O primitives.

Tools:
  - web_search(query, max_results)           Tavily
  - fetch_webpage(url, max_chars)            readable text extraction
  - fetch_webpage_links(url, limit)          enumerate outbound links
  - fetch_feed(url, max_items)               RSS/Atom via feedparser
  - search_feeds(feed_urls, keywords, ...)   keyword filter across feeds

Runs at streamable-http on MCP_WEB_PORT (default 29100).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result, get_json, get_text
from mcp_servers._core.html import extract_readable_text, extract_links
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_WEB_PORT  # noqa: E402

mcp = make_server("mcp-web")


@mcp.tool()
def web_search(query: str, max_results: int = 6) -> str:
    """Search the web via Tavily and return recent, relevant results.

    Use this when you need current facts, news, or information not in training data.
    Returns title, URL, snippet, and published date per result.

    Args:
        query: Natural-language search query.
        max_results: Number of results (default 6, max 20).

    Env:
        TAVILY_API_KEY must be set.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return tool_error("TAVILY_API_KEY not set on the MCP server.", code="missing_key")
    try:
        from tavily import TavilyClient
    except ImportError:
        return tool_error("tavily-python not installed on the MCP server.", code="missing_dep")
    try:
        client = TavilyClient(api_key=api_key)
        raw = client.search(query, max_results=min(max_results, 20))
        return tool_result(raw)
    except Exception as exc:
        return tool_error(f"Tavily search failed: {exc}", code="upstream")


@mcp.tool()
def fetch_webpage(url: str, max_chars: int = 10000) -> str:
    """Fetch a webpage and return its readable text content.

    Strips scripts, styles, navigation, headers, and footers. Truncates to
    max_chars to keep returns manageable.

    Args:
        url: Absolute URL to fetch (http:// or https://).
        max_chars: Truncation limit (default 10000).
    """
    try:
        html = get_text(url)
        return tool_result({"url": url, "text": extract_readable_text(html, max_chars)})
    except Exception as exc:
        return tool_error(f"Fetch failed: {exc}", code="upstream")


@mcp.tool()
def fetch_webpage_links(url: str, limit: int = 100) -> str:
    """Fetch a webpage and return its outbound hyperlinks as (text, absolute_url) pairs.

    Args:
        url: Absolute URL to fetch.
        limit: Maximum number of links to return (default 100).
    """
    try:
        html = get_text(url)
        links = extract_links(html, base_url=url, limit=limit)
        return tool_result({
            "url": url,
            "links": [{"text": t, "url": u} for t, u in links],
        })
    except Exception as exc:
        return tool_error(f"Fetch failed: {exc}", code="upstream")


@mcp.tool()
def fetch_feed(url: str, max_items: int = 20) -> str:
    """Fetch and parse an RSS or Atom feed.

    Returns the feed title plus a list of items (title, link, summary, published).

    Args:
        url: Absolute URL of the feed.
        max_items: Maximum items to return (default 20).
    """
    try:
        import feedparser
    except ImportError:
        return tool_error("feedparser not installed on the MCP server.", code="missing_dep")
    try:
        parsed = feedparser.parse(url)
        items = []
        for entry in parsed.entries[:max_items]:
            items.append({
                "title":     getattr(entry, "title", ""),
                "link":      getattr(entry, "link", ""),
                "summary":   getattr(entry, "summary", "")[:1000],
                "published": getattr(entry, "published", getattr(entry, "updated", "")),
            })
        return tool_result({
            "feed_title": parsed.feed.get("title", "") if hasattr(parsed, "feed") else "",
            "items": items,
        })
    except Exception as exc:
        return tool_error(f"Feed parse failed: {exc}", code="upstream")


@mcp.tool()
def search_feeds(feed_urls: list[str], keywords: list[str], max_per_feed: int = 50) -> str:
    """Fetch multiple RSS/Atom feeds and return items whose title or summary
    matches any of the given keywords (case-insensitive).

    Args:
        feed_urls: Feed URLs to scan.
        keywords: Keywords to filter items by (any-match, case-insensitive).
        max_per_feed: Per-feed cap before filtering (default 50).
    """
    try:
        import feedparser
    except ImportError:
        return tool_error("feedparser not installed on the MCP server.", code="missing_dep")
    kws = [k.lower() for k in keywords if k]
    hits = []
    for url in feed_urls:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:max_per_feed]:
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                haystack = f"{title}\n{summary}".lower()
                if any(k in haystack for k in kws):
                    hits.append({
                        "feed":      parsed.feed.get("title", url),
                        "title":     title,
                        "link":      getattr(entry, "link", ""),
                        "summary":   summary[:500],
                        "published": getattr(entry, "published", ""),
                    })
        except Exception:
            continue
    return tool_result({"matches": hits, "count": len(hits)})


# ── YouTube ─────────────────────────────────────────────────────────────
import re

_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?.*?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)"
    r"([a-zA-Z0-9_-]{11})"
)


def _yt_video_id(url: str) -> str | None:
    m = _YOUTUBE_ID_RE.search(url)
    if m:
        return m.group(1)
    s = url.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", s):
        return s
    return None


def _yt_format_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


@mcp.tool()
def get_youtube_video_info(youtube_url: str) -> str:
    """Get metadata for a YouTube video: title, channel, canonical URL.

    Uses YouTube's oEmbed endpoint — no API key required. Call this before
    get_youtube_transcript to confirm the video is the right one.

    Args:
        youtube_url: Full YouTube URL or bare 11-char video ID.
    """
    vid = _yt_video_id(youtube_url)
    if not vid:
        return tool_error(f"Could not parse video ID from: {youtube_url}", code="bad_input")
    canonical = f"https://www.youtube.com/watch?v={vid}"
    try:
        data = get_json(
            "https://www.youtube.com/oembed",
            params={"url": canonical, "format": "json"},
        )
        return tool_result({
            "video_id":    vid,
            "title":       data.get("title", ""),
            "channel":     data.get("author_name", ""),
            "channel_url": data.get("author_url", ""),
            "url":         canonical,
        })
    except Exception as exc:
        return tool_error(f"oEmbed lookup failed: {exc}", code="upstream")


@mcp.tool()
def get_youtube_transcript(youtube_url: str, max_words: int = 5000) -> str:
    """Fetch the captions transcript of a YouTube video, with timestamps.

    Tries English first, falls back to any available language. Truncates at
    max_words to keep return size manageable. Will fail if the video has no
    captions/subtitles.

    Args:
        youtube_url: Full YouTube URL or bare 11-char video ID.
        max_words: Cap on returned word count (default 5000).
    """
    vid = _yt_video_id(youtube_url)
    if not vid:
        return tool_error(f"Could not parse video ID from: {youtube_url}", code="bad_input")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return tool_error(
            "youtube-transcript-api not installed on the MCP server.",
            code="missing_dep",
        )
    try:
        ytt = YouTubeTranscriptApi()
        try:
            fetched = ytt.fetch(vid, languages=["en", "en-US", "en-GB"])
        except Exception:
            fetched = ytt.fetch(vid)
        segments = [
            {"start": s.start, "text": s.text, "duration": s.duration}
            for s in fetched
        ]
    except Exception as exc:
        return tool_error(f"Transcript unavailable: {exc}", code="upstream")
    if not segments:
        return tool_error("No transcript segments found.", code="not_found")

    lines: list[str] = []
    word_count = 0
    truncated = False
    for seg in segments:
        text = (seg["text"] or "").strip()
        if not text:
            continue
        lines.append(f"[{_yt_format_ts(seg['start'])}] {text}")
        word_count += len(text.split())
        if word_count > max_words:
            truncated = True
            break

    last = segments[-1]
    total_duration = _yt_format_ts(last["start"] + last.get("duration", 0))
    transcript = "\n".join(lines)
    if truncated:
        cutoff = _yt_format_ts(segments[len(lines) - 1]["start"])
        transcript += f"\n\n[TRUNCATED at {cutoff} — full video is {total_duration}]"

    return tool_result({
        "video_id":          vid,
        "url":               f"https://www.youtube.com/watch?v={vid}",
        "segments_returned": len(lines),
        "total_segments":    len(segments),
        "total_duration":    total_duration,
        "truncated":         truncated,
        "transcript":        transcript,
    })


if __name__ == "__main__":
    run(mcp, MCP_WEB_PORT)
