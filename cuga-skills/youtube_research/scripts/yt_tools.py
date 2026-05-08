"""CLI helpers for the youtube_research skill.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/yt_tools.py web_search 'transformer site:youtube.com' 6
    python scripts/yt_tools.py get_youtube_video_info 'https://youtu.be/abc123'
    python scripts/yt_tools.py get_youtube_transcript 'abc123' 5000

Env:
  TAVILY_API_KEY                — required for web_search

Pip deps (declared in SKILL.md frontmatter):
  youtube-transcript-api>=0.6   — required for get_youtube_transcript

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request

_UA = {"User-Agent": "youtube-research-skill/1.0 (https://skills.sh)"}
_TAVILY = "https://api.tavily.com/search"
_OEMBED = "https://www.youtube.com/oembed"

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


def _http_post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={**_UA, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())


def _http_get_json(url: str, params: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def web_search(query: str, max_results: int = 6) -> dict:
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
    return {
        "query": query,
        "results": [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "content": (r.get("content") or "")[:800]}
            for r in (data.get("results") or [])
        ],
    }


def get_youtube_video_info(url_or_id: str) -> dict:
    vid = _yt_video_id(url_or_id)
    if not vid:
        return {"error": f"Could not parse video ID from: {url_or_id!r}"}
    canonical = f"https://www.youtube.com/watch?v={vid}"
    try:
        data = _http_get_json(_OEMBED, {"url": canonical, "format": "json"})
    except Exception as e:
        return {"error": f"oEmbed lookup failed: {type(e).__name__}: {e}"}
    return {
        "video_id": vid,
        "title": data.get("title", ""),
        "channel": data.get("author_name", ""),
        "channel_url": data.get("author_url", ""),
        "url": canonical,
    }


def get_youtube_transcript(url_or_id: str, max_words: int = 5000) -> dict:
    vid = _yt_video_id(url_or_id)
    if not vid:
        return {"error": f"Could not parse video ID from: {url_or_id!r}"}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"error": "youtube-transcript-api not installed (declared in SKILL.md requirements)"}
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
    except Exception as e:
        return {"error": f"Transcript unavailable: {type(e).__name__}: {e}"}
    if not segments:
        return {"error": "No transcript segments found."}
    lines, word_count, truncated = [], 0, False
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
    return {
        "video_id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "segments_returned": len(lines),
        "total_segments": len(segments),
        "total_duration": total_duration,
        "truncated": truncated,
        "transcript": transcript,
    }


_USAGE = """\
usage:
  python scripts/yt_tools.py web_search <query> [max_results=6]
  python scripts/yt_tools.py get_youtube_video_info <url_or_id>
  python scripts/yt_tools.py get_youtube_transcript <url_or_id> [max_words=5000]

Requires:
  TAVILY_API_KEY (web_search)
  youtube-transcript-api (get_youtube_transcript) — declared in SKILL.md
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "web_search":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            n = int(argv[3]) if len(argv) > 3 else 6
            result: object = web_search(argv[2], n)
        elif cmd == "get_youtube_video_info":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_youtube_video_info(argv[2])
        elif cmd == "get_youtube_transcript":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            mx = int(argv[3]) if len(argv) > 3 else 5000
            result = get_youtube_transcript(argv[2], mx)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
